import { test } from "node:test";
import assert from "node:assert/strict";
import { businessLoopApi } from "./src/business-loop-api.ts";
import { unavailableFeatures } from "./src/features.ts";
const account = "00000000-0000-4000-8000-000000000001",
  order = "00000000-0000-4000-8000-000000000002";
const features = { ...unavailableFeatures, business_loop_reviewed: true };
function storage() {
  const m = new Map();
  return {
    getItem: (k) => m.get(k) ?? null,
    setItem: (k, v) => m.set(k, v),
    removeItem: (k) => m.delete(k),
  };
}
const intent = {
  path: `/work-orders/${order}/archive`,
  body: { expected_version: 3 },
  review: "归档已完成工单 v3",
};
test("pending routes require reviewed release and separate assignment/sending flags", async () => {
  let n = 0;
  const fetcher = async () => {
    n++;
    return Response.json({ data: {} });
  };
  const off = businessLoopApi(
    "csrf",
    account,
    unavailableFeatures,
    fetcher,
    storage(),
  );
  await assert.rejects(
    off.read("/daily-summary"),
    (e) => e.code === "FEATURE_UNAVAILABLE",
  );
  await assert.rejects(off.submit(intent), /安全验收/);
  const on = businessLoopApi("csrf", account, features, fetcher, storage());
  await assert.rejects(
    on.submit({ ...intent, path: `/actions/${order}/send` }),
    /安全验收/,
  );
  await assert.rejects(
    on.submit({ ...intent, path: `/review-items/${order}/assign` }),
    /安全验收/,
  );
  assert.equal(n, 0);
});
test("unknown writes survive reload and use original frozen body and idempotency key only on explicit retry", async () => {
  const disk = storage(),
    calls = [];
  let failure = true;
  const fetcher = async (url, options) => {
    calls.push({ url, ...options });
    if (failure) throw Error("lost");
    return Response.json({
      data: { account_id: account, id: order, version: 4 },
    });
  };
  const api = businessLoopApi("csrf", account, features, fetcher, disk);
  await assert.rejects(api.submit(intent), (e) => e.code === "RESULT_UNKNOWN");
  const original = api.pending;
  intent.body.expected_version = 99;
  assert.equal(calls.length, 1);
  assert.equal(original.intent.body.expected_version, 3);
  failure = false;
  const reloaded = businessLoopApi("csrf", account, features, fetcher, disk);
  await reloaded.retry();
  assert.equal(
    calls[1].headers["Idempotency-Key"],
    calls[0].headers["Idempotency-Key"],
  );
  assert.equal(calls[1].body, calls[0].body);
  assert.equal(reloaded.pending, null);
  intent.body.expected_version = 3;
});
test("cross account or malformed results retain original journal", async () => {
  for (const data of [
    [],
    { account_id: "other", id: order, version: 4 },
    { account_id: account, id: "other", version: 4 },
  ]) {
    const api = businessLoopApi(
      "csrf",
      account,
      features,
      async () => Response.json({ data }),
      storage(),
    );
    await assert.rejects(
      api.submit(intent),
      (e) => e.code === "RESULT_UNKNOWN",
    );
    assert.ok(api.pending);
  }
});
test("initial definite version rejection releases attempt, ambiguous retry rejection preserves it", async () => {
  let fail = false;
  const fetcher = async () => {
    if (fail) throw Error("lost");
    return Response.json(
      { error: { code: "VERSION_CONFLICT" } },
      { status: 409 },
    );
  };
  const api = businessLoopApi("csrf", account, features, fetcher, storage());
  await assert.rejects(api.submit(intent));
  assert.equal(api.pending, null);
  fail = true;
  await assert.rejects(api.submit(intent));
  fail = false;
  await assert.rejects(api.retry());
  assert.ok(api.pending);
});
test("PUT recovery is read-only and accepts only exact next-version matching settings", async () => {
  const disk = storage();
  let calls = 0;
  const settings = {
    version: 0,
    timezone: "Asia/Hong_Kong",
    work_days: [1, 2],
    work_hours: { start: "09:00", end: "18:00" },
    breaks: [],
    buffer_minutes: 30,
    preparation_minutes: 60,
    default_duration_minutes: 60,
  };
  const api = businessLoopApi(
    "csrf",
    account,
    features,
    async (_url, options) => {
      calls++;
      if (options.method === "PUT") throw Error("lost");
      assert.equal(options.method, "GET");
      return Response.json({ data: { ...settings, version: 1 } });
    },
    disk,
  );
  await assert.rejects(
    api.submit({
      path: "/settings/schedule",
      method: "PUT",
      body: { expected_version: 0, settings },
      review: "排期设置",
    }),
  );
  await api.retry();
  assert.equal(calls, 2);
  assert.equal(api.pending, null);
});
test("storage unavailable blocks writes before dispatch", async () => {
  let calls = 0;
  const api = businessLoopApi(
    "csrf",
    account,
    features,
    async () => {
      calls++;
    },
    {
      getItem() {
        throw Error("blocked");
      },
    },
  );
  await assert.rejects(api.submit(intent));
  assert.equal(calls, 0);
});
