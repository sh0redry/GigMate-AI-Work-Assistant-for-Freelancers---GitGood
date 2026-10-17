import assert from "node:assert/strict";
import { test } from "node:test";
import { businessApi, changeContext } from "./src/workspace-api.ts";
import { canConfirm } from "./src/business-store.ts";
import {
  conflictLabel,
  filterOrders,
  onDay,
  fieldValue,
  orderActionLabels,
  orderStates,
  reviewBinding,
  hongKongDateTime,
} from "./src/work-order-view.ts";
test("follow-up datetime accepts seconds and milliseconds, rejects impossible dates without throwing", () => {
  assert.equal(
    hongKongDateTime("2026-11-01T08:30"),
    "2026-11-01T00:30:00.000Z",
  );
  assert.equal(
    hongKongDateTime("2026-11-01T08:30:15"),
    "2026-11-01T00:30:15.000Z",
  );
  assert.equal(
    hongKongDateTime("2026-11-01T08:30:15.123"),
    "2026-11-01T00:30:15.123Z",
  );
  assert.equal(
    hongKongDateTime("2028-02-29T00:00"),
    "2028-02-28T16:00:00.000Z",
  );
  for (const raw of [
    "",
    "bad",
    "2026-02-29T10:00",
    "2026-02-31T10:00",
    "2026-11-01T24:30",
    "2026-11-01T08:60",
    "2026-11-01T08:30:61",
    "2026-11-01T08:30Z",
  ])
    assert.equal(hongKongDateTime(raw), null, raw);
});
const change = {
  id: "change",
  field: "schedule",
  work_order_id: "order",
  sources: [{ message_id: "m2", message_revision: 1 }],
  context_version: 9,
  base_work_order_version: 7,
  status: "proposed",
  conflict_ids: [],
};
const snapshot = () => ({
  selected: "order",
  orders: [{ id: "order", version: 7 }],
  contexts: { c1: 4, c2: 9 },
  contextVersion: 4,
  messages: [{ id: "m2", revision: 1, conversation_id: "c2", revoked: false }],
});
test("every linked conversation/page is loaded and confirmation uses the source conversation, not the first", async () => {
  const sent = [];
  const api = businessApi(async (path, body) => {
    sent.push({ path, body });
    if (body) return { data: {} };
    if (path.startsWith("/work-orders/order/changes"))
      return { items: [change], next_cursor: null };
    if (path.startsWith("/work-orders?"))
      return {
        items: [{ id: "order", version: 7, conversation_ids: ["c1", "c2"] }],
        next_cursor: null,
      };
    if (path === "/conversations/c1")
      return { data: { id: "c1", context_version: 4 } };
    if (path === "/conversations/c2")
      return { data: { id: "c2", context_version: 9 } };
    if (path.startsWith("/conversations/c1/messages"))
      return { items: [], next_cursor: null };
    if (path.startsWith("/conversations/c2/messages"))
      return path.includes("cursor=")
        ? {
            items: [
              {
                id: "m2",
                revision: 1,
                conversation_id: "c2",
                revoked: false,
                occurred_at: "2026-10-12T00:00:00Z",
              },
            ],
            next_cursor: null,
          }
        : { items: [], next_cursor: "next" };
    return { items: [], next_cursor: null };
  });
  const data = await api.load("order", new AbortController().signal);
  assert.equal(data.messages.length, 1);
  assert.deepEqual(data.contexts, { c1: 4, c2: 9 });
  await api.confirm(data, change);
  assert.equal(sent.at(-1).body.expected_context_version, 9);
  assert.ok(
    sent.some((v) => v.path.includes("c2/messages?limit=100&cursor=next")),
  );
});
test("missing, revoked or mixed-conversation sources fail closed before confirmation POST", async () => {
  let writes = 0;
  const api = businessApi(async () => {
    writes++;
    return { data: {} };
  });
  for (const modify of [
    (d) => (d.messages = []),
    (d) => (d.messages[0].revoked = true),
    (d) => (d.messages[0].revision = 2),
    (d) => {
      d.messages.push({
        id: "m1",
        revision: 1,
        conversation_id: "c1",
        revoked: false,
      });
    },
  ]) {
    const d = snapshot();
    modify(d);
    const c =
      d.messages.length === 2
        ? {
            ...change,
            sources: [
              ...change.sources,
              { message_id: "m1", message_revision: 1 },
            ],
          }
        : change;
    assert.equal(changeContext(d, c), null);
    await assert.rejects(api.confirm(d, c), /无法核对/);
  }
  assert.equal(writes, 0);
});
test("a denied later conversation never returns a partially writable snapshot", async () => {
  const api = businessApi(async (path) => {
    if (path.startsWith("/work-orders?"))
      return {
        items: [{ id: "order", conversation_ids: ["c1", "c2"] }],
        next_cursor: null,
      };
    if (path === "/conversations/c1")
      return { data: { id: "c1", context_version: 4 } };
    if (path === "/conversations/c2") throw new Error("consent revoked");
    return { items: [], next_cursor: null };
  });
  await assert.rejects(
    api.load("order", new AbortController().signal),
    /consent revoked/,
  );
});
test("review binding changes for content, source, order or context changes", () => {
  const d = snapshot();
  const binding = reviewBinding(d, change);
  assert.notEqual(
    reviewBinding(d, { ...change, new_value: "changed" }),
    binding,
  );
  assert.notEqual(reviewBinding(d, { ...change, sources: [] }), binding);
  d.orders[0].version++;
  assert.notEqual(reviewBinding(d, change), binding);
  d.orders[0].version--;
  d.contexts.c2++;
  assert.notEqual(reviewBinding(d, change), binding);
});
test("unsupported field confirmation is disabled even when versions match", () => {
  assert.equal(canConfirm({ ...change, field: "quantity" }, 7, 9), false);
  assert.equal(canConfirm({ ...change, field: "address" }, 7, 9), true);
  assert.equal(canConfirm(change, 7, 9), true);
});
test("search and status use canonical data and keep the original selection catalog intact", () => {
  const orders = [
    { summary: "陈小姐 证件照", status: "confirmed" },
    { summary: "ABC 设计", status: "waiting_customer" },
  ];
  assert.equal(filterOrders(orders, " abc ", "all").length, 1);
  assert.equal(filterOrders(orders, "", "waiting_customer").length, 1);
  assert.equal(filterOrders(orders, "陈小姐", "cancelled").length, 0);
  assert.equal(orders.length, 2);
});
test("Hong Kong daily calendar includes overnight spans but excludes events ending at midnight", () => {
  const event = (schedule) => ({ schedule });
  assert.equal(
    onDay(
      event({
        kind: "timed",
        start_at: "2026-10-11T15:30:00Z",
        end_at: "2026-10-11T16:30:00Z",
      }),
      "2026-10-12",
    ),
    true,
  );
  assert.equal(
    onDay(
      event({
        kind: "timed",
        start_at: "2026-10-11T15:00:00Z",
        end_at: "2026-10-11T16:00:00Z",
      }),
      "2026-10-12",
    ),
    false,
  );
  assert.equal(
    onDay(
      event({
        kind: "date_only",
        date: "2026-10-12",
        timezone: "America/New_York",
      }),
      "2026-10-12",
    ),
    true,
  );
  assert.match(
    fieldValue({
      kind: "date_only",
      date: "2026-10-12",
      timezone: "America/New_York",
    }),
    /2026-10-12 全天（America\/New_York）/,
  );
  assert.equal(fieldValue(null), "未提供");
  assert.equal(fieldValue(0), "0");
});

test("conflict identifiers resolve calendar entries before their work orders", () => {
  const data = {
    calendar: [{ id: "calendar-1", work_order_id: "order-2" }],
    orders: [{ id: "order-2", summary: "Synthetic other booking" }],
  };
  assert.equal(conflictLabel(data, "calendar-1"), "Synthetic other booking");
  assert.match(conflictLabel(data, "unavailable"), /日历/);
});

test("status buttons name the action, not the state they produce", () => {
  const states = new Set(Object.values(orderStates));
  for (const label of Object.values(orderActionLabels)) {
    assert.equal(
      states.has(label),
      false,
      `action label "${label}" repeats a state name`,
    );
  }
  assert.equal(orderActionLabels.cancelled, "取消工单");
  assert.equal(orderActionLabels.completed, "完成工单");
});
