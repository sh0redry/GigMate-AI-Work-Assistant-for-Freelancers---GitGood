import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  sessionFetch,
  setReadScope,
  clearReadCache,
  stableShare,
  privateReadPath,
} from "./src/read-cache.ts";
afterEach(() => setReadScope(""));
test("conditional reads always contact server; matching authenticated 304 reuses body", async () => {
  setReadScope("synthetic-account:session-1");
  let calls = 0;
  const fetcher = async (_u, options) => {
    calls++;
    if (calls === 1)
      return Response.json(
        { data: { version: 1 } },
        { headers: { ETag: 'W/"one"' } },
      );
    assert.equal(new Headers(options.headers).get("If-None-Match"), 'W/"one"');
    return new Response(null, { status: 304, headers: { ETag: 'W/"one"' } });
  };
  const one = await sessionFetch("/api/v1/work-orders", {}, fetcher),
    two = await sessionFetch("/api/v1/work-orders", {}, fetcher);
  assert.deepEqual(await one.json(), await two.json());
  assert.equal(calls, 2);
});
test("failed revalidation never returns stale success; authorization errors erase cache", async () => {
  setReadScope("one");
  let mode = "ok";
  const fetcher = async (_u, o) => {
    if (mode === "ok")
      return Response.json({ data: 1 }, { headers: { ETag: 'W/"a"' } });
    if (mode === "network") throw Error("offline");
    if (mode === "denied") return new Response(null, { status: 403 });
    assert.equal(new Headers(o.headers).get("if-none-match"), null);
    return Response.json({ data: 2 });
  };
  await sessionFetch("/api/v1/tasks", {}, fetcher);
  mode = "network";
  await assert.rejects(sessionFetch("/api/v1/tasks", {}, fetcher), /offline/);
  mode = "denied";
  assert.equal((await sessionFetch("/api/v1/tasks", {}, fetcher)).status, 403);
  mode = "after";
  await sessionFetch("/api/v1/tasks", {}, fetcher);
});
test("scope changes discard old cache and ignore late former-session reads", async () => {
  setReadScope("account-A:session");
  let complete;
  const pending = sessionFetch(
    "/api/v1/tasks",
    {},
    () => new Promise((r) => (complete = r)),
  );
  setReadScope("account-B:session");
  complete(Response.json({ data: "A" }, { headers: { ETag: 'W/"a"' } }));
  await assert.rejects(pending, (e) => e.name === "AbortError");
});
test("mutations invalidate even when network result is unknown; no repeat dispatch", async () => {
  setReadScope("A");
  let reads = 0,
    writes = 0;
  const fetcher = async (_u, o) => {
    if (o.method === "POST") {
      writes++;
      throw Error("lost");
    }
    reads++;
    if (reads === 2)
      assert.equal(new Headers(o.headers).get("if-none-match"), null);
    return Response.json({ data: 1 }, { headers: { ETag: 'W/"a"' } });
  };
  await sessionFetch("/api/v1/tasks", {}, fetcher);
  await assert.rejects(
    sessionFetch("/api/v1/work-orders", { method: "POST" }, fetcher),
  );
  await sessionFetch("/api/v1/tasks", {}, fetcher);
  assert.equal(writes, 1);
});
test("mismatched 304 fails clearly and private files/QR/replay bypass snapshots", async () => {
  setReadScope("A");
  await assert.rejects(
    sessionFetch(
      "/api/v1/tasks",
      {},
      async () =>
        new Response(null, { status: 304, headers: { ETag: 'W/"unknown"' } }),
    ),
    /Unmatched/,
  );
  for (const p of [
    "/api/v1/auth/login",
    "/api/v1/connectors/x/qr",
    "/api/v1/connectors/x/media/attachments/id/content?download=true",
    "/api/v1/calendar-events/id.ics",
    "/api/v1/replay",
  ])
    assert.equal(privateReadPath(p), false, p);
  clearReadCache();
});
test("equal snapshots share references; a changed leaf replaces only its branch and opaque blobs stay opaque", () => {
  const first = {
    orders: [
      { id: "a", version: 1 },
      { id: "b", version: 1 },
    ],
    tasks: [],
  };
  assert.equal(stableShare(first, structuredClone(first)), first);
  const next = stableShare(first, {
    orders: [
      { id: "a", version: 2 },
      { id: "b", version: 1 },
    ],
    tasks: [],
  });
  assert.notEqual(next, first);
  assert.equal(next.orders[1], first.orders[1]);
  assert.equal(next.tasks, first.tasks);
  assert.notEqual(next.orders[0], first.orders[0]);
  const a = new Blob(["a"]),
    b = new Blob(["a"]);
  assert.equal(stableShare(a, b), b);
  assert.deepEqual(stableShare({ a: 1 }, { b: 1 }), { b: 1 });
});
