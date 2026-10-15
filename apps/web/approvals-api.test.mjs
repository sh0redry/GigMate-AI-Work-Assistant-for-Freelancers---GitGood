import assert from "node:assert/strict";
import { test } from "node:test";
import { approvalsApi } from "./src/approvals-api.ts";
import { approveProblem, reissueProblem } from "./src/approval-view.ts";
import {
  accountId,
  action,
  fixture,
  memoryStorage,
} from "./approval-fixtures.mjs";
const signal = () => new AbortController().signal;
test("approval reads every action/message page, uses canonical source conversation and freezes exact snapshot command", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  const api = approvalsApi(
    "csrf",
    accountId,
    async (url, options) => {
      if (url.includes("/messages?"))
        return Response.json(
          url.includes("cursor=later")
            ? { items: data.messages, next_cursor: null }
            : { items: [], next_cursor: "later" },
        );
      return fetcher(url, options);
    },
    storage,
  );
  const snapshot = await api.load("a1", signal());
  assert.equal(snapshot.messages.length, 1);
  assert.equal(approveProblem(snapshot, Date.now()), "");
  await api.submit(
    snapshot.action,
    "approve",
    snapshot.conversation.context_version,
  );
  assert.equal(data.writes.length, 1);
  assert.deepEqual(data.writes[0].body, {
    expected_version: 3,
    expected_context_version: 4,
    expected_action_revision: 1,
    snapshot_hash: snapshot.action.snapshot_hash,
  });
  assert.equal(data.writes[0].options.headers["X-CSRF-Token"], "csrf");
  assert.equal(data.actions[0].delivery_status, "not_submitted");
  assert.equal(api.attempt(), null);
});
test("unknown approval survives adapter recreation; refresh never resends and explicit original retry preserves key/body", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  let api = approvalsApi("old-csrf", accountId, fetcher, storage);
  data.drop = true;
  await assert.rejects(api.submit(data.actions[0], "approve", 4), {
    code: "RESULT_UNKNOWN",
  });
  const original = structuredClone(data.writes[0]);
  api = approvalsApi("new-csrf", accountId, fetcher, storage);
  assert.equal(api.attempt().actionId, "a1");
  await api.load("", signal());
  await api.load("a1", signal());
  assert.equal(data.writes.length, 1);
  await assert.rejects(api.submit(data.actions[0], "cancel", 4, "cancel"), {
    code: "UNRESOLVED_ATTEMPT",
  });
  const result = await api.retryOriginal();
  assert.equal(result.state, "approved");
  assert.equal(
    data.writes[1].options.headers["Idempotency-Key"],
    original.options.headers["Idempotency-Key"],
  );
  assert.deepEqual(data.writes[1].body, original.body);
  assert.equal(data.writes[1].options.headers["X-CSRF-Token"], "new-csrf");
  assert.equal(storage.values.size, 0);
});
test("private context denial permits local rejection, while revoked/missing sources and stale versions block approval", async () => {
  const { data, fetcher } = fixture();
  const api = approvalsApi("csrf", accountId, fetcher, memoryStorage());
  data.messages[0].revoked = true;
  assert.match(
    approveProblem(await api.load("a1", signal()), Date.now()),
    /原文/,
  );
  data.messages[0].revoked = false;
  data.order.version = 4;
  assert.match(
    approveProblem(await api.load("a1", signal()), Date.now()),
    /变化/,
  );
  data.denied = true;
  const denied = await api.load("a1", signal());
  assert.match(denied.contextError, /不能批准/);
  const result = await api.submit(denied.action, "reject", 4, "先确认时间");
  assert.equal(result.closed_note, "先确认时间");
});
test("cross-account actions and cyclic pagination fail closed; corrupt/unavailable journal cannot dispatch", async () => {
  const { data, fetcher } = fixture();
  data.actions[0].account_id = "other";
  await assert.rejects(
    approvalsApi("csrf", accountId, fetcher, memoryStorage()).load(
      "a1",
      signal(),
    ),
    { code: "INVALID_RESPONSE" },
  );
  data.actions[0].account_id = accountId;
  const looping = async (url, opts) =>
    url.includes("/actions?")
      ? Response.json({ items: [], next_cursor: "loop" })
      : fetcher(url, opts);
  await assert.rejects(
    approvalsApi("csrf", accountId, looping, memoryStorage()).load(
      "a1",
      signal(),
    ),
    { code: "INVALID_RESPONSE" },
  );
  const storage = memoryStorage();
  storage.setItem(`gigmate-approval-attempt:/api/v1:${accountId}`, "{bad");
  const bad = approvalsApi("csrf", accountId, fetcher, storage);
  assert.ok(bad.storageError());
  await assert.rejects(bad.submit(data.actions[0], "approve", 4), {
    code: "UNRESOLVED_ATTEMPT",
  });
  await assert.rejects(
    approvalsApi("csrf", accountId, fetcher, null).submit(
      data.actions[0],
      "approve",
      4,
    ),
    { code: "ATTEMPT_STORAGE_UNAVAILABLE" },
  );
  assert.equal(data.writes.length, 0);
});
test("uncertain reissue is replayed once with its original key, never as a fresh generated question", async () => {
  const { data, fetcher } = fixture();
  const api = approvalsApi("csrf", accountId, fetcher, memoryStorage());
  data.actions[0] = action({
    state: "cancelled",
    closed_reason: "superseded",
    reissuable: true,
  });
  data.conversation.context_version = 5;
  data.drop = true;
  await assert.rejects(api.submit(data.actions[0], "reissue", 5), {
    code: "RESULT_UNKNOWN",
  });
  const again = await api.retryOriginal();
  assert.equal(again.id, "new-action");
  assert.equal(data.actions.length, 2);
  assert.equal(
    data.writes[0].options.headers["Idempotency-Key"],
    data.writes[1].options.headers["Idempotency-Key"],
  );
});
test("same-context repeated reissue is blocked in UI while the C uniqueness defect remains; new context can be reviewed", async () => {
  const { data, fetcher } = fixture();
  data.actions = [
    action({ id: "old", state: "expired" }),
    action({ id: "a1", state: "expired", reissuable: true }),
  ];
  const api = approvalsApi("csrf", accountId, fetcher, memoryStorage());
  assert.match(reissueProblem(await api.load("a1", signal())), /已经重新提问/);
  data.conversation.context_version = 5;
  assert.equal(reissueProblem(await api.load("a1", signal())), "");
});
test("attempts are isolated by account/environment and transport destination is bound at construction", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  globalThis.__GIGMATE_ENVIRONMENTS__ = {
    defaultEnvironment: "isolated",
    targets: {
      real: "http://127.0.0.1:18702",
      isolated: "http://127.0.0.1:18000",
    },
    publicTestAccount: {
      username: "merchant",
      password: "demo-only-change-me",
    },
  };
  try {
    const isolated = approvalsApi("csrf", accountId, fetcher, storage);
    data.drop = true;
    await assert.rejects(isolated.submit(data.actions[0], "approve", 4), {
      code: "RESULT_UNKNOWN",
    });
    globalThis.__GIGMATE_ENVIRONMENTS__.defaultEnvironment = "real";
    assert.equal(
      approvalsApi("csrf", accountId, fetcher, storage).attempt(),
      null,
    );
    assert.equal(
      approvalsApi("csrf", "another-account", fetcher, storage).attempt(),
      null,
    );
    await isolated.retryOriginal();
    assert.ok(
      data.writes.every((w) => w.url.startsWith("/environments/isolated/api/")),
    );
  } finally {
    delete globalThis.__GIGMATE_ENVIRONMENTS__;
  }
});
test("expired login during original-request retry preserves earlier uncertainty until authenticated same-key lookup", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  let denied = false;
  const transport = (url, opts) =>
    denied && opts.method === "POST"
      ? Promise.resolve(
          Response.json(
            { error: { code: "UNAUTHENTICATED" } },
            { status: 401 },
          ),
        )
      : fetcher(url, opts);
  const api = approvalsApi("csrf", accountId, transport, storage);
  data.drop = true;
  await assert.rejects(api.submit(data.actions[0], "approve", 4), {
    code: "RESULT_UNKNOWN",
  });
  denied = true;
  await assert.rejects(api.retryOriginal(), { code: "UNAUTHENTICATED" });
  assert.ok(approvalsApi("csrf", accountId, transport, storage).attempt());
  denied = false;
  await api.retryOriginal();
  assert.equal(storage.values.size, 0);
});
test("a previously constructed adapter cannot overwrite another mount's unknown intent", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  const first = approvalsApi("csrf", accountId, fetcher, storage);
  const stale = approvalsApi("csrf", accountId, fetcher, storage);
  data.drop = true;
  await assert.rejects(first.submit(data.actions[0], "approve", 4), {
    code: "RESULT_UNKNOWN",
  });
  const record = [...storage.values.values()][0];
  await assert.rejects(stale.submit(data.actions[0], "cancel", 4, "stop"), {
    code: "UNRESOLVED_ATTEMPT",
  });
  assert.equal([...storage.values.values()][0], record);
  assert.equal(data.writes.length, 1);
});
test("expiry and recipient mismatch block approval even when versions and text remain unchanged", async () => {
  const { data, fetcher } = fixture();
  const api = approvalsApi("csrf", accountId, fetcher, memoryStorage());
  data.actions[0].expires_at = "2000-01-01T00:00:00Z";
  assert.match(
    approveProblem(await api.load("a1", signal()), Date.now()),
    /过期/,
  );
  data.actions[0].expires_at = "2099-01-01T00:00:00Z";
  data.messages.push({ ...data.messages[0], revision: 2 });
  assert.match(
    approveProblem(await api.load("a1", signal()), Date.now()),
    /原文/,
  );
  data.messages.pop();
  data.messages[0].text = null;
  assert.match(
    approveProblem(await api.load("a1", signal()), Date.now()),
    /原文/,
  );
  data.actions[0].recipient = "unrelated-conversation";
  assert.match(
    approveProblem(await api.load("a1", signal()), Date.now()),
    /收件会话/,
  );
});
test("a successful HTTP response with the wrong operation state remains uncertain rather than clearing the original intent", async () => {
  const storage = memoryStorage();
  const api = approvalsApi(
    "csrf",
    accountId,
    async () => Response.json({ data: action() }),
    storage,
  );
  await assert.rejects(api.submit(action(), "approve", 4), {
    code: "RESULT_UNKNOWN",
  });
  assert.ok(api.attempt());
  assert.equal(storage.values.size, 1);
});

test("a denied global sessionStorage getter returns a protected read-only adapter with zero POSTs", async () => {
  const { data, fetcher } = fixture();
  const previous = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    get() {
      throw new DOMException("Synthetic getter refused", "SecurityError");
    },
  });
  try {
    const api = approvalsApi("csrf", accountId, fetcher);
    assert.match(api.storageError(), /不能提交/);
    assert.equal((await api.load("a1", signal())).action.id, "a1");
    await assert.rejects(api.submit(data.actions[0], "approve", 4), {
      code: "ATTEMPT_STORAGE_UNAVAILABLE",
    });
    assert.equal(data.writes.length, 0);
  } finally {
    if (previous) Object.defineProperty(globalThis, "sessionStorage", previous);
    else delete globalThis.sessionStorage;
  }
});

for (const method of ["getItem", "setItem"]) {
  test(`journal ${method} rejection leaves reads usable and blocks dispatch rather than using memory-only state`, async () => {
    const { data, fetcher } = fixture();
    const storage = memoryStorage();
    storage[method] = () => {
      throw new DOMException("Synthetic storage policy", "SecurityError");
    };
    const api = approvalsApi("csrf", accountId, fetcher, storage);
    assert.equal((await api.load("a1", signal())).action.id, "a1");
    await assert.rejects(api.submit(data.actions[0], "approve", 4), {
      code: "ATTEMPT_STORAGE_UNAVAILABLE",
    });
    assert.ok(api.storageError());
    await assert.rejects(api.submit(data.actions[0], "approve", 4), {
      code: "ATTEMPT_STORAGE_UNAVAILABLE",
    });
    assert.equal(data.writes.length, 0);
  });
}

for (const method of ["getItem", "removeItem"]) {
  test(`cleanup ${method} rejection retains a verified original intent, blocks fresh writes, and recovers only with its original key`, async () => {
    const { data, fetcher } = fixture();
    const storage = memoryStorage();
    const originalMethod = storage[method];
    let refused = false;
    storage[method] = (...args) => {
      if (refused)
        throw new DOMException("Synthetic cleanup refusal", "SecurityError");
      return originalMethod(...args);
    };
    const transport = async (url, options) => {
      const response = await fetcher(url, options);
      if (options.method === "POST") refused = true;
      return response;
    };
    const api = approvalsApi("csrf", accountId, transport, storage);
    const result = await api.submit(data.actions[0], "approve", 4);
    assert.equal(result.state, "approved");
    assert.match(api.storageError(), /无法清理/);
    assert.ok(api.attempt());
    const record = [...storage.values.values()][0];
    assert.equal((await api.load("a1", signal())).action.state, "approved");
    await assert.rejects(api.submit(result, "cancel", 4, "cancel"), {
      code: "UNRESOLVED_ATTEMPT",
    });
    assert.equal([...storage.values.values()][0], record);
    assert.equal(data.writes.length, 1);
    refused = false;
    const restored = approvalsApi("new-csrf", accountId, fetcher, storage);
    await restored.retryOriginal();
    assert.equal(
      data.writes[1].options.headers["Idempotency-Key"],
      data.writes[0].options.headers["Idempotency-Key"],
    );
    assert.equal(data.writes[1].options.body, data.writes[0].options.body);
    assert.equal(storage.values.size, 0);
  });
}

test("storage revocation after initialization blocks submission before dispatch and remains visibly blocked", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  const api = approvalsApi("csrf", accountId, fetcher, storage);
  storage.getItem = () => {
    throw new DOMException("Synthetic late policy", "SecurityError");
  };
  await assert.rejects(api.submit(data.actions[0], "approve", 4), {
    code: "ATTEMPT_STORAGE_UNAVAILABLE",
  });
  assert.ok(api.storageError());
  assert.equal(data.writes.length, 0);
});

test("completion from an old adapter never removes or overwrites a different saved intent", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  const api = approvalsApi(
    "csrf",
    accountId,
    async (url, options) => {
      const response = await fetcher(url, options);
      if (options.method === "POST") {
        const key = [...storage.values.keys()][0];
        const newer = {
          ...JSON.parse(storage.getItem(key)),
          key: crypto.randomUUID(),
          actionId: "newer-owned-action",
        };
        storage.setItem(key, JSON.stringify(newer));
      }
      return response;
    },
    storage,
  );
  assert.equal(
    (await api.submit(data.actions[0], "approve", 4)).state,
    "approved",
  );
  assert.equal(
    JSON.parse([...storage.values.values()][0]).actionId,
    "newer-owned-action",
  );
  assert.match(api.storageError(), /另一页面/);
});

test("a journal read refusal cannot erase an existing unknown request; restoring access recovers its exact key", async () => {
  const { data, fetcher } = fixture();
  const storage = memoryStorage();
  const original = approvalsApi("csrf", accountId, fetcher, storage);
  data.drop = true;
  await assert.rejects(original.submit(data.actions[0], "approve", 4), {
    code: "RESULT_UNKNOWN",
  });
  const record = [...storage.values.values()][0];
  const read = storage.getItem;
  storage.getItem = () => {
    throw new DOMException("Synthetic read denial", "SecurityError");
  };
  const denied = approvalsApi("csrf", accountId, fetcher, storage);
  assert.ok(denied.storageError());
  await denied.load("a1", signal());
  await assert.rejects(denied.submit(data.actions[0], "approve", 4), {
    code: "ATTEMPT_STORAGE_UNAVAILABLE",
  });
  assert.equal([...storage.values.values()][0], record);
  assert.equal(data.writes.length, 1);
  storage.getItem = read;
  const restored = approvalsApi("csrf", accountId, fetcher, storage);
  await restored.retryOriginal();
  assert.equal(
    data.writes[0].options.headers["Idempotency-Key"],
    data.writes[1].options.headers["Idempotency-Key"],
  );
  assert.equal(storage.values.size, 0);
});
