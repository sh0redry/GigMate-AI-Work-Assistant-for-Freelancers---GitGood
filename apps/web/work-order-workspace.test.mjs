import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import ts from "typescript";
import { JSDOM } from "jsdom";
import { act, createElement } from "react";
const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const directory = await mkdtemp(join(tmpdir(), "gigmate-d02-dom-"));
const require = createRequire(import.meta.url);
for (const name of [
  "WorkOrderWorkspace",
  "OrderLifecycle",
  "InspectOrderAttempt",
  "ReplyPanel",
  "approvals-api",
  "approval-view",
  "order-command-api",
  "features",
  "business-store",
  "environment",
  "read-cache",
  "useStableState",
  "workspace-api",
  "i18n",
  "locales",
  "work-order-view",
]) {
  const source = await readFile(
    new URL(
      `./src/${name}.${["WorkOrderWorkspace", "OrderLifecycle", "InspectOrderAttempt", "ReplyPanel"].includes(name) ? "tsx" : "ts"}`,
      import.meta.url,
    ),
    "utf8",
  );
  const code = ts
    .transpileModule(source, {
      fileName:
        name +
        ([
          "WorkOrderWorkspace",
          "OrderLifecycle",
          "InspectOrderAttempt",
          "ReplyPanel",
        ].includes(name)
          ? ".tsx"
          : ".ts"),
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
        jsx: ts.JsxEmit.ReactJSX,
      },
    })
    .outputText.replace(/"\.\/([\w-]+)(?:\.ts)?"/g, '"./$1.mjs"')
    .replace(/"(react(?:\/jsx-runtime)?)"/g, (_, specifier) =>
      JSON.stringify(pathToFileURL(require.resolve(specifier)).href),
    );
  await writeFile(join(directory, name + ".mjs"), code);
}
const { WorkOrderWorkspace } = await import(
  pathToFileURL(join(directory, "WorkOrderWorkspace.mjs"))
);
let root;
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  document.getElementById("root").replaceChildren();
});
after(async () => {
  dom.window.close();
  delete globalThis.window;
  delete globalThis.document;
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  await rm(directory, { recursive: true });
});
const messages = [
  {
    id: "m1",
    revision: 1,
    conversation_id: "c1",
    direction: "incoming",
    source: "replay",
    occurred_at: "2026-10-12T00:00:00Z",
    text: "Synthetic first",
    revoked: false,
  },
  {
    id: "m2",
    revision: 1,
    conversation_id: "c2",
    direction: "incoming",
    source: "replay",
    occurred_at: "2026-10-12T00:01:00Z",
    text: "Synthetic second",
    revoked: false,
  },
];
const schedule = {
  kind: "timed",
  start_at: "2026-10-12T08:30:00Z",
  end_at: "2026-10-12T09:30:00Z",
  timezone: "Asia/Hong_Kong",
};
const source = { message_id: "m2", message_revision: 1 };
function fixture() {
  const orders = [
    {
      id: "order",
      version: 3,
      summary: "Synthetic booking",
      status: "confirmed",
      conversation_ids: ["c1", "c2"],
      updated_at: "2026-10-12T00:00:00Z",
      fields: {
        schedule: { value: schedule, status: "confirmed", sources: [source] },
        address: { value: null, status: "missing", sources: [] },
      },
    },
  ];
  let change = {
    id: "change",
    work_order_id: "order",
    field: "schedule",
    status: "proposed",
    old_value: schedule,
    new_value: {
      ...schedule,
      start_at: "2026-10-12T10:00:00Z",
      end_at: "2026-10-12T11:00:00Z",
    },
    base_work_order_version: 3,
    context_version: 9,
    customer_confirmation: "ambiguous",
    proposer: "customer",
    conflict_ids: [],
    sources: [source],
  };
  const writes = [];
  let unavailable = false;
  const request = async (path, body) => {
    if (unavailable) throw new Error("Synthetic outage");
    if (body) {
      writes.push({ path, body });
      orders[0] = { ...orders[0], version: 4 };
      change = { ...change, status: "confirmed" };
      return { data: orders[0] };
    }
    if (path === "/conversations/c1")
      return { data: { id: "c1", context_version: 4 } };
    if (path === "/conversations/c2")
      return { data: { id: "c2", context_version: 9 } };
    let items = [];
    if (path.startsWith("/work-orders?")) items = orders;
    if (path.startsWith("/work-orders/order/changes")) items = [change];
    if (path.startsWith("/conversations/c1/messages")) items = [messages[0]];
    if (path.startsWith("/conversations/c2/messages")) items = [messages[1]];
    if (path.startsWith("/tasks?"))
      items = [
        {
          id: "task",
          title: "Synthetic prepare",
          state: "pending",
          work_order_id: "order",
          work_order_version: 3,
          due: {
            kind: "date_only",
            date: "2026-10-12",
            timezone: "Asia/Hong_Kong",
          },
          depends_on: [],
          sources: [source],
        },
        {
          id: "old",
          title: "Synthetic cancelled",
          state: "cancelled",
          work_order_id: "order",
          work_order_version: 2,
          due: null,
          depends_on: [],
          sources: [source],
        },
      ];
    if (path.startsWith("/calendar-events?"))
      items = [
        {
          id: "event",
          work_order_id: "order",
          work_order_version: 3,
          schedule,
          tentative: false,
          buffer_minutes: 0,
          sources: [source],
        },
      ];
    return { items, next_cursor: null };
  };
  return {
    request,
    writes,
    change: () => change,
    update: (value) => {
      change = { ...change, ...value };
    },
    offline: () => {
      unavailable = true;
    },
    online: () => {
      unavailable = false;
    },
  };
}
const buttons = () => [...document.querySelectorAll("button")];
const button = (text) => buttons().find((b) => b.textContent === text);
async function click(text) {
  const b = button(text);
  assert.ok(b, text);
  assert.equal(b.disabled, false, text);
  await act(async () => b.click());
}
async function mount(f, props = {}) {
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(WorkOrderWorkspace, {
        csrf: "synthetic",
        onSessionExpired: () => {},
        onBusyChange: () => {},
        request: f.request,
        ...props,
      }),
    ),
  );
}
test("business workspace renders both conversations, missing fields and the next step without replay controls; confirmation states its effect before saving", async () => {
  const f = fixture();
  await mount(f);
  assert.match(document.body.textContent, /Synthetic first/);
  assert.match(document.body.textContent, /Synthetic second/);
  assert.match(document.body.textContent, /回复含糊/);
  assert.match(document.body.textContent, /还没有地址/);
  assert.equal(button("回放：15:00 冲突改期"), undefined);
  assert.equal(
    document.body.textContent.includes("Synthetic cancelled"),
    false,
  );
  await click("确认新时间");
  assert.match(document.body.textContent, /日历和准备待办会一起更新/);
  await click("确认");
  assert.equal(f.writes.length, 1);
  assert.deepEqual(f.writes[0].body, {
    expected_version: 3,
    expected_context_version: 9,
    apply_calendar_update: true,
  });
  assert.match(document.body.textContent, /已保存本次提议/);
});
test("a refreshed changed proposal invalidates an open review and never silently submits new content", async () => {
  const f = fixture();
  await mount(f);
  await click("确认新时间");
  f.update({
    new_value: {
      ...schedule,
      start_at: "2026-10-12T12:00:00Z",
      end_at: "2026-10-12T13:00:00Z",
    },
  });
  await click("刷新");
  assert.match(document.body.textContent, /内容刚更新了/);
  assert.equal(button("确认").disabled, true);
  assert.equal(f.writes.length, 0);
});
test("outage marks retained data stale, disables confirmation and recovers with a read", async () => {
  const f = fixture();
  await mount(f);
  f.offline();
  await click("刷新");
  assert.match(document.body.textContent, /上次读到的内容/);
  assert.equal(button("确认新时间").disabled, true);
  f.online();
  await click("刷新");
  assert.equal(button("确认新时间").disabled, false);
  assert.equal(f.writes.length, 0);
});
test("conflicts and missing source revisions stay blocked without replay controls", async () => {
  const f = fixture();
  f.update({ conflict_ids: ["busy"] });
  await mount(f);
  assert.match(document.body.textContent, /撞了/);
  assert.equal(button("确认新时间"), undefined);
  assert.equal(button("回放：15:00 冲突改期"), undefined);
  f.update({
    conflict_ids: [],
    sources: [{ message_id: "m2", message_revision: 2 }],
  });
  await click("刷新");
  assert.match(document.body.textContent, /依据的消息暂时读不到/);
  assert.equal(button("确认新时间").disabled, true);
  assert.equal(f.writes.length, 0);
});

test("an address proposal states its effect and uses the canonical non-calendar confirmation", async () => {
  const f = fixture();
  f.update({
    field: "address",
    new_value: "Synthetic new venue",
    customer_confirmation: "pending",
  });
  await mount(f, { features: { address_confirmation: true } });
  await click("确认新地址");
  await click("确认");
  assert.equal(f.writes.length, 1);
  assert.equal(f.writes[0].body.apply_calendar_update, false);
  assert.match(document.body.textContent, /仍需客户核实/);
});

test("receipt recovery requires a readonly result and separate consent before retiring the local journal", async () => {
  const { InspectOrderAttempt } = await import(
    pathToFileURL(join(directory, "InspectOrderAttempt.mjs"))
  );
  let inspected = 0,
    retired = 0,
    done = 0;
  const commands = {
    attempt: { key: "synthetic-key" },
    error: "",
    inspect: async () => {
      inspected++;
      return {
        summary: "Synthetic saved order",
        version: 4,
        status: "pending_confirmation",
      };
    },
    retireInspected: () => retired++,
  };
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(InspectOrderAttempt, {
        commands,
        ready: true,
        busy: false,
        onBusy: () => {},
        onError: (e) => {
          throw e;
        },
        onDone: () => done++,
      }),
    ),
  );
  assert.equal(button("结束已核对的原记录"), undefined);
  await click("只读核对已保存结果");
  assert.equal(inspected, 1);
  assert.equal(button("结束已核对的原记录").disabled, true);
  await act(async () =>
    document.querySelector('input[type="checkbox"]').click(),
  );
  await click("结束已核对的原记录");
  assert.equal(retired, 1);
  assert.equal(done, 1);
});

test("an incomplete start-time proposal is a next step to ask the client, never confirmable", async () => {
  const f = fixture();
  f.update({ status: "needs_review", new_value: "2026-10-12T08:30:00Z" });
  await mount(f);
  assert.match(document.body.textContent, /客人说了时间，但还不完整/);
  assert.match(document.body.textContent, /先问客人/);
  assert.equal(button("确认新时间"), undefined);
  assert.equal(f.writes.length, 0);
});
