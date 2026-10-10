import assert from "node:assert/strict";
import { test } from "node:test";
import { workspaceApi, allPages, replayApi } from "./src/workspace-api.ts";

test("HTML proxy failures become a readable error without exposing HTML or parser details", async () => {
  const request = workspaceApi(
    "",
    async () => new Response("<html>502</html>", { status: 502 }),
  );
  await assert.rejects(
    request("/work-orders"),
    (error) =>
      error.code === "UNAVAILABLE" &&
      /读取数据/.test(error.message) &&
      !/SyntaxError|html/.test(error.message),
  );
  await assert.rejects(
    request("/replay", { scenario: "available" }),
    /结果暂无法确认/,
  );
});
test("invalid login and expired sessions have different user messages", async () => {
  const request = workspaceApi("", async () =>
    Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
  );
  await assert.rejects(request("/auth/login", {}), /账号或密码/);
  await assert.rejects(request("/work-orders"), /登录已过期/);
});
test("failed mutations preserve CSRF and single-dispatch semantics with unknown outcomes", async () => {
  let calls = 0;
  const request = workspaceApi("synthetic-csrf", async (_url, options) => {
    calls++;
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.headers["X-CSRF-Token"], "synthetic-csrf");
    assert.ok(options.headers["Idempotency-Key"]);
    throw new TypeError("synthetic network error");
  });
  await assert.rejects(request("/replay", {}), /避免反复提交/);
  assert.equal(calls, 1);
});
test("cancelled reads retain cancellation rather than producing an offline warning", async () => {
  const controller = new AbortController();
  controller.abort();
  const request = workspaceApi("", async () => {
    throw new Error("cancelled");
  });
  await assert.rejects(
    request("/work-orders", undefined, controller.signal),
    (error) => error.name === "AbortError",
  );
});
test("all list pages are read and cyclic or malformed pagination fails clearly", async () => {
  const paths = [];
  const values = await allPages(async (path) => {
    paths.push(path);
    return path.includes("cursor=")
      ? { items: [2], next_cursor: null }
      : { items: [1], next_cursor: "opaque /?" };
  }, "/tasks");
  assert.deepEqual(values, [1, 2]);
  assert.match(paths[1], /cursor=opaque%20%2F%3F/);
  await assert.rejects(
    allPages(async () => ({ items: [], next_cursor: "same" }), "/tasks"),
    /完整读取/,
  );
  await assert.rejects(
    allPages(async () => ({ items: null, next_cursor: null }), "/tasks"),
    /列表数据无效/,
  );
});
test("an unseeded environment never requests a conversation named undefined", async () => {
  const paths = [];
  const api = replayApi(async (path) => {
    paths.push(path);
    return { items: [], next_cursor: null };
  });
  assert.equal((await api.load("", new AbortController().signal)).selected, "");
  assert.equal(paths.length, 3);
  assert.ok(paths.every((path) => !path.includes("conversations")));
});
test("confirmation binds the loaded order and context versions without altering its payload", async () => {
  let sent;
  const api = replayApi(async (path, body) => {
    sent = { path, body };
    return { data: {} };
  });
  await api.confirm(
    {
      selected: "order",
      orders: [{ id: "order", version: 7 }],
      contextVersion: 9,
    },
    { id: "change", work_order_id: "order" },
  );
  assert.equal(sent.path, "/work-orders/order/changes/change/confirm");
  assert.deepEqual(sent.body, {
    expected_version: 7,
    expected_context_version: 9,
    apply_calendar_update: true,
  });
  await assert.rejects(
    api.confirm(
      { selected: "order", orders: [{ id: "order", version: 7 }] },
      { id: "change", work_order_id: "different" },
    ),
    /业务已切换/,
  );
});
