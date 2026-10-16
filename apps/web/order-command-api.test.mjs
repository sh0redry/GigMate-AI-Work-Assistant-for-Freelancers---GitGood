import assert from "node:assert/strict";
import { test } from "node:test";
import { orderCommands } from "./src/order-command-api.ts";
const account = "00000000-0000-4000-8000-000000000001",
  id = "00000000-0000-4000-8000-000000000003",
  change = "00000000-0000-4000-8000-000000000006";
const intent = {
  kind: "confirm",
  orderId: id,
  changeId: change,
  review: {
    summary: "Synthetic order",
    oldValue: null,
    newValue: "Synthetic revised time",
    sources: [],
  },
  body: {
    expected_version: 3,
    expected_context_version: 4,
    apply_calendar_update: true,
  },
};
function memory() {
  const map = new Map();
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => map.set(k, v),
    removeItem: (k) => map.delete(k),
  };
}
const result = () =>
  Response.json({
    data: {
      id,
      account_id: account,
      version: 4,
      conversation_ids: ["c"],
      fields: {
        schedule: { value: "Synthetic revised time", status: "confirmed" },
        address: { value: null, status: "missing" },
      },
      status: "confirmed",
    },
  });
test("lost confirm survives reopening and uses exact original key and command only after explicit retry", async () => {
  const storage = memory(),
    calls = [];
  const fetcher = async (url, opts) => {
    calls.push({ url, opts });
    if (calls.length === 1) throw new Error("synthetic lost response");
    return result();
  };
  const first = orderCommands("csrf", account, fetcher, storage);
  await assert.rejects(first.submit(intent), { code: "RESULT_UNKNOWN" });
  const key = first.attempt.key;
  const next = orderCommands("new-csrf", account, fetcher, storage);
  assert.equal(calls.length, 1);
  assert.equal(next.attempt.key, key);
  await assert.rejects(next.submit(intent), { code: "UNRESOLVED_ATTEMPT" });
  await next.retry();
  assert.equal(calls.length, 2);
  assert.equal(
    calls[0].opts.headers["Idempotency-Key"],
    calls[1].opts.headers["Idempotency-Key"],
  );
  assert.equal(calls[0].opts.body, calls[1].opts.body);
  assert.equal(calls[1].opts.headers["X-CSRF-Token"], "new-csrf");
  assert.equal(next.attempt, null);
});
test("denied global storage getter is read-safe and blocks all POSTs", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    get() {
      throw new Error("denied");
    },
  });
  try {
    let calls = 0;
    const api = orderCommands("csrf", account, async () => {
      calls++;
      return result();
    });
    assert.ok(api.error);
    await assert.rejects(api.submit(intent));
    assert.equal(calls, 0);
  } finally {
    if (descriptor)
      Object.defineProperty(globalThis, "sessionStorage", descriptor);
    else delete globalThis.sessionStorage;
  }
});
test("write denial and journal corruption never dispatch or clear the saved record", async () => {
  for (const storage of [
    {
      getItem: () => null,
      setItem() {
        throw new Error();
      },
    },
    {
      getItem: () => "{broken",
      removeItem() {
        throw new Error("must not delete");
      },
    },
  ]) {
    let calls = 0;
    const api = orderCommands(
      "csrf",
      account,
      async () => {
        calls++;
        return result();
      },
      storage,
    );
    await assert.rejects(api.submit(intent));
    assert.equal(calls, 0);
  }
});
test("partial/foreign/5xx responses and auth refusal of original retry preserve uncertainty", async () => {
  for (const response of [
    Response.json({ data: {} }),
    Response.json({
      data: {
        id,
        account_id: "another-account",
        version: 4,
        conversation_ids: [],
        fields: {},
      },
    }),
    Response.json({ error: { code: "UNAVAILABLE" } }, { status: 503 }),
  ]) {
    const storage = memory();
    const api = orderCommands("csrf", account, async () => response, storage);
    await assert.rejects(api.submit(intent));
    const saved = api.attempt;
    const restored = orderCommands(
      "csrf",
      account,
      async () =>
        Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
      storage,
    );
    await assert.rejects(restored.retry(), { code: "UNAUTHENTICATED" });
    assert.deepEqual(restored.attempt, saved);
  }
});
test("initial version conflict clears a known rejected intent for renewed review", async () => {
  const api = orderCommands(
    "csrf",
    account,
    async () =>
      Response.json({ error: { code: "VERSION_CONFLICT" } }, { status: 409 }),
    memory(),
  );
  await assert.rejects(api.submit(intent), { code: "VERSION_CONFLICT" });
  assert.equal(api.attempt, null);
});
test("verified response with failed cleanup blocks fresh operations and retains the original key", async () => {
  const storage = memory();
  storage.removeItem = () => {
    throw new Error();
  };
  const api = orderCommands("csrf", account, async () => result(), storage);
  await assert.rejects(api.submit(intent), {
    code: "ATTEMPT_STORAGE_UNAVAILABLE",
  });
  assert.ok(api.attempt);
  assert.ok(api.error);
  await assert.rejects(api.submit(intent), { code: "UNRESOLVED_ATTEMPT" });
});
test("an older mount never overwrites a different saved intent", async () => {
  const storage = memory();
  const older = orderCommands("csrf", account, async () => result(), storage),
    newer = orderCommands(
      "csrf",
      account,
      async () => {
        throw new Error();
      },
      storage,
    );
  await assert.rejects(newer.submit(intent));
  await assert.rejects(older.submit(intent), {
    code: "ATTEMPT_STORAGE_UNAVAILABLE",
  });
  assert.ok(newer.attempt);
  assert.equal(
    orderCommands("csrf", "another-account", async () => result(), storage)
      .attempt,
    null,
  );
});
test("creation and lifecycle target payloads retain original values on lost responses", async () => {
  for (const value of [
    {
      kind: "create",
      body: {
        conversation_id: change,
        summary: "Synthetic job",
        schedule: null,
        schedule_sources: [],
        address: null,
        address_sources: [],
        confirm_additional_order: false,
      },
    },
    {
      kind: "status",
      orderId: id,
      body: { expected_version: 3, status: "cancelled" },
    },
  ]) {
    const storage = memory();
    const api = orderCommands(
      "csrf",
      account,
      async () => {
        throw new Error();
      },
      storage,
    );
    await assert.rejects(api.submit(value), { code: "RESULT_UNKNOWN" });
    assert.deepEqual(
      orderCommands("csrf", account, fetch, storage).attempt.intent,
      value,
    );
  }
});

test("successful proposed timed/date-only confirmations clear the journal and allow the next operation", async () => {
  for (const value of [
    {
      kind: "timed",
      start_at: "2026-12-01T07:00:00Z",
      end_at: "2026-12-01T08:00:00Z",
      timezone: "Asia/Hong_Kong",
    },
    { kind: "date_only", date: "2026-12-01", timezone: "Asia/Hong_Kong" },
  ]) {
    let count = 0;
    const api = orderCommands(
      "csrf",
      account,
      async () => {
        const body = (await result().json()).data;
        count++;
        if (count === 1) {
          body.status = "pending_confirmation";
          body.fields.schedule = { value, status: "proposed" };
        } else {
          body.version = 5;
          body.status = "cancelled";
        }
        return Response.json({ data: body });
      },
      memory(),
    );
    const saved = await api.submit({
      ...intent,
      review: { ...intent.review, field: "schedule", newValue: value },
    });
    assert.equal(saved.fields.schedule.status, "proposed");
    assert.equal(api.attempt, null);
    await api.submit({
      kind: "status",
      orderId: id,
      body: { expected_version: 4, status: "cancelled" },
    });
    assert.equal(count, 2);
  }
});
test("address confirmation binds address value and does not request calendar synchronization", async () => {
  for (const status of ["proposed", "confirmed"]) {
    const api = orderCommands(
      "csrf",
      account,
      async (_url, opts) => {
        assert.equal(JSON.parse(opts.body).apply_calendar_update, false);
        const body = (await result().json()).data;
        body.fields.address = { value: "Synthetic venue", status };
        return Response.json({ data: body });
      },
      memory(),
    );
    await api.submit({
      ...intent,
      review: {
        ...intent.review,
        field: "address",
        newValue: " \u0085Synthetic venue\u3000 ",
      },
      body: { ...intent.body, apply_calendar_update: false },
    });
    assert.equal(api.attempt, null);
  }
});
test("read-only receipt inspection can retire a completed original after explicit review without replaying it", async () => {
  const calls = [],
    storage = memory();
  const api = orderCommands(
    "csrf",
    account,
    async (url, opts) => {
      calls.push({ url, opts });
      if (calls.length === 1) throw new Error("synthetic lost response");
      assert.match(url, /\/work-order-command-results\/.+\/inspect$/);
      assert.equal(opts.headers["Idempotency-Key"], undefined);
      assert.deepEqual(JSON.parse(opts.body), {
        kind: "confirm",
        order_id: id,
        change_id: change,
        command: intent.body,
      });
      return result();
    },
    storage,
  );
  await assert.rejects(api.submit(intent), { code: "RESULT_UNKNOWN" });
  assert.throws(() => api.retireInspected(), { code: "UNRESOLVED_ATTEMPT" });
  const key = api.attempt.key;
  const saved = await api.inspect();
  assert.equal(saved.id, id);
  assert.equal(api.attempt.key, key);
  const reopened = orderCommands(
    "csrf",
    account,
    async () => result(),
    storage,
  );
  assert.throws(() => reopened.retireInspected(), {
    code: "UNRESOLVED_ATTEMPT",
  });
  api.retireInspected();
  assert.equal(api.attempt, null);
  assert.equal(calls.length, 2);
});
test("missing, foreign and unavailable receipts never permit dropping an uncertain command", async () => {
  for (const response of [
    () =>
      Response.json(
        { error: { code: "COMMAND_RESULT_PENDING" } },
        { status: 409 },
      ),
    async () => {
      const body = await result().json();
      body.data.account_id = "foreign";
      return Response.json(body);
    },
    () => {
      throw new Error("offline");
    },
  ]) {
    let calls = 0;
    const api = orderCommands(
      "csrf",
      account,
      (...args) => {
        if (++calls === 1) throw new Error("lost original");
        return response(...args);
      },
      memory(),
    );
    await assert.rejects(api.submit(intent));
    const key = api.attempt.key;
    await assert.rejects(api.inspect());
    assert.throws(() => api.retireInspected(), { code: "UNRESOLVED_ATTEMPT" });
    assert.equal(api.attempt.key, key);
    assert.equal(calls, 2);
  }
});
