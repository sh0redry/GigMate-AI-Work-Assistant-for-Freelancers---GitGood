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
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const originalFetch = globalThis.fetch;
const directory = await mkdtemp(join(tmpdir(), "gigmate-app-dom-"));
const require = createRequire(import.meta.url);
const components = [
  "App",
  "BusinessLoopWorkspace",
  "BusinessLoopReview",
  "LoopCommand",
  "OrderLifecycle",
  "InspectOrderAttempt",
  "OrderCreation",
  "CalendarWorkspace",
  "ReviewWorkspace",
  "DeliveryGuide",
  "ApprovalsWorkspace",
  "WorkOrderWorkspace",
  "ConnectionWorkspace",
  "ChatChoices",
  "WahaMessages",
  "WahaMedia",
  "WahaSend",
];
for (const name of [
  ...components,
  "features",
  "business-loop-api",
  "useWorkspaceData",
  "order-command-api",
  "calendar-view",
  "calendar-api",
  "approvals-api",
  "approval-view",
  "business-store",
  "environment",
  "read-cache",
  "useStableState",
  "workspace-api",
  "work-order-view",
  "connection-api",
  "waha-live-api",
  "waha-sync-api",
  "waha-media-api",
  "waha-send-api",
  "connection-state",
  "chat-choices",
]) {
  const extension = components.includes(name) ? "tsx" : "ts";
  const source = await readFile(
    new URL(`./src/${name}.${extension}`, import.meta.url),
    "utf8",
  );
  const code = ts
    .transpileModule(source, {
      fileName: `${name}.${extension}`,
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
        jsx: ts.JsxEmit.ReactJSX,
      },
    })
    .outputText.replace(/import "\.\/connection\.css";\s*/g, "")
    .replace(/"\.\/([\w-]+)(?:\.ts)?"/g, '"./$1.mjs"')
    .replace(/"(react(?:\/jsx-runtime)?)"/g, (_, specifier) =>
      JSON.stringify(pathToFileURL(require.resolve(specifier)).href),
    );
  await writeFile(join(directory, name + ".mjs"), code);
}
const { App } = await import(pathToFileURL(join(directory, "App.mjs")));
let root;
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  document.getElementById("root").replaceChildren();
  sessionStorage.clear();
  globalThis.fetch = originalFetch;
  delete globalThis.__GIGMATE_ENVIRONMENTS__;
  dom.reconfigure({ url: "http://localhost/" });
});
after(async () => {
  dom.window.close();
  for (const name of [
    "window",
    "document",
    "sessionStorage",
    "IS_REACT_ACT_ENVIRONMENT",
  ])
    delete globalThis[name];
  await rm(directory, { recursive: true });
});
function fixture({ denied = false } = {}) {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/auth/login"))
      return denied
        ? Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 })
        : Response.json({
            data: {
              username: "learner",
              csrf_token: "synthetic-csrf",
              account_id: "synthetic-account",
            },
          });
    if (url.endsWith("/workspace-capabilities"))
      return Response.json({
        data: {
          calendar_export: true,
          create_order: false,
          order_status: false,
          address_confirmation: false,
          manual_assignment: false,
          business_sending: false,
          automatic_understanding: false,
        },
      });
    if (url.endsWith("/auth/logout"))
      return Response.json({ data: { ok: true } });
    if (
      options.method === "GET" &&
      [
        "/work-orders?",
        "/tasks?",
        "/calendar-events?",
        "/connectors?",
        "/review-items?",
        "/conversations?",
      ].some((path) => url.includes(path))
    )
      return Response.json({ items: [], next_cursor: null });
    throw new Error(`Unexpected request ${options.method} ${url}`);
  };
  return calls;
}
async function mount() {
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(App)));
}
async function fill(input, value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    ).set.call(input, value);
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}
async function login() {
  await fill(
    document.querySelector('input[autocomplete="username"]'),
    "learner",
  );
  await fill(
    document.querySelector('input[type="password"]'),
    "synthetic-password",
  );
  await act(async () =>
    document
      .querySelector("form")
      .dispatchEvent(
        new window.Event("submit", { bubbles: true, cancelable: true }),
      ),
  );
}
const button = (text) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent === text);
function noDemo() {
  assert.equal(
    /D-01 演示|模拟扫码|工单回放|虚构回放输入|demo-only-change-me/.test(
      document.body.textContent,
    ),
    false,
  );
}
test("signed-out product has blank credentials, no business reads or demo bypass, and rejected login stays signed out", async () => {
  const calls = fixture({ denied: true });
  await mount();
  assert.equal(calls.length, 0);
  assert.equal(
    document.querySelector('input[autocomplete="username"]').value,
    "",
  );
  assert.equal(document.querySelector('input[type="password"]').value, "");
  assert.equal(document.querySelector("nav"), null);
  noDemo();
  await login();
  assert.match(document.body.textContent, /账号或密码不正确/);
  assert.equal(document.querySelector("nav"), null);
  assert.deepEqual(
    calls.map((c) => c.url),
    ["/api/v1/auth/login"],
  );
});
test("authenticated product lands in honest empty business workspace, connects through owned API, and logout clears the screen and password", async () => {
  const calls = fixture();
  await mount();
  await login();
  assert.equal(button("业务工作台").getAttribute("aria-pressed"), "true");
  assert.match(document.body.textContent, /当前还没有工单/);
  assert.match(document.body.textContent, /自动建单尚未开放/);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    username: "learner",
    password: "synthetic-password",
  });
  assert.equal(
    calls.some((c) => c.url.includes("/replay")),
    false,
  );
  noDemo();
  await act(async () => button("WhatsApp 连接").click());
  assert.match(document.body.textContent, /还没有本机连接/);
  assert.match(document.body.textContent, /请联系接入负责人检查当前账号/);
  assert.equal(
    calls.some((c) => c.url.includes("/connectors?")),
    true,
  );
  noDemo();
  await act(async () => button("退出").click());
  assert.equal(document.querySelector("nav"), null);
  assert.equal(document.querySelector('input[type="password"]').value, "");
  assert.equal(document.body.textContent.includes("当前账号：learner"), false);
  const logout = calls.find((c) => c.url.endsWith("/auth/logout"));
  assert.equal(logout.options.headers["X-CSRF-Token"], "synthetic-csrf");
});

test("delivery login and navigation contain no test environment or public credentials", async () => {
  const calls = fixture();
  globalThis.__GIGMATE_ENVIRONMENTS__ = {
    defaultEnvironment: "isolated",
    publicTestAccount: {
      username: "merchant",
      password: "demo-only-change-me",
    },
  };
  await mount();
  assert.doesNotMatch(
    document.body.textContent,
    /隔离测试|公开开发测试账号|demo-only-change-me|切换到/,
  );
  await login();
  for (const page of ["日历与待办", "人工复核", "功能与使用说明"]) {
    await act(async () => button(page).click());
    assert.ok(document.querySelector('[aria-current="page"]'));
  }
  assert.match(document.body.textContent, /暂不可用/);
  assert.equal(button("业务管理"), undefined);
  assert.equal(button("新建工单"), undefined);
  assert.ok(
    calls.every(
      (c) => !c.url.includes("/daily-summary") && !c.url.includes("/settings/"),
    ),
  );
  assert.match(document.body.textContent, /C 业务审批与 A/);
  assert.ok(calls.every((c) => c.url.startsWith("/api/v1/")));
  assert.equal(calls.filter((c) => c.options.method === "POST").length, 1);
});
test("old environment URLs fail closed without login or backend reads", async () => {
  const calls = fixture();
  dom.reconfigure({ url: "http://localhost/environments/isolated/" });
  await mount();
  assert.match(document.body.textContent, /旧入口已停用/);
  assert.equal(calls.length, 0);
  assert.equal(document.querySelector("form"), null);
  assert.equal(
    document.querySelector('a[href="/"]').textContent,
    "打开当前工作台",
  );
});
test("a rejected capability read leaves missing functions unavailable", async () => {
  fixture();
  const original = globalThis.fetch;
  globalThis.fetch = (url, opts) =>
    url.endsWith("/workspace-capabilities")
      ? Promise.resolve(
          Response.json({ error: { code: "UNAVAILABLE" } }, { status: 503 }),
        )
      : original(url, opts);
  await mount();
  await login();
  await act(async () => button("功能与使用说明").click());
  assert.match(document.body.textContent, /能力状态无法核对/);
  assert.match(document.body.textContent, /暂不可用/);
});

function deliveryFixture() {
  const calls = fixture(),
    fallback = globalThis.fetch;
  const orderId = "00000000-0000-4000-8000-000000000003",
    conversationId = "00000000-0000-4000-8000-000000000002",
    messageId = "00000000-0000-4000-8000-000000000005";
  const source = { message_id: messageId, message_revision: 1 };
  const schedule = {
    kind: "timed",
    start_at: "2026-11-01T02:00:00Z",
    end_at: "2026-11-01T03:00:00Z",
    timezone: "Asia/Hong_Kong",
  };
  const order = {
    id: orderId,
    account_id: "synthetic-account",
    version: 3,
    summary: "Synthetic delivery order",
    status: "confirmed",
    conversation_ids: [conversationId],
    updated_at: "2026-10-14T00:00:00Z",
    pending_change_ids: [],
    fields: {
      schedule: { status: "confirmed", value: schedule, sources: [source] },
      address: { status: "missing", value: null, sources: [] },
    },
  };
  const messages = [
    {
      id: messageId,
      conversation_id: conversationId,
      revision: 1,
      occurred_at: "2026-10-14T00:00:00Z",
      direction: "incoming",
      source: "live",
      text: "Synthetic customer source",
      revoked: false,
    },
    {
      id: "00000000-0000-4000-8000-000000000006",
      conversation_id: conversationId,
      revision: 1,
      occurred_at: "2026-10-14T00:00:00Z",
      direction: "outgoing",
      source: "api",
      text: "Synthetic merchant echo",
      revoked: false,
    },
  ];
  globalThis.fetch = async (url, options) => {
    const page = (items) => Response.json({ items, next_cursor: null });
    if (options.method === "GET") {
      if (url.includes("/work-orders?")) return page([order]);
      if (url.includes("/calendar-events?"))
        return page([
          {
            id: "formal",
            work_order_id: orderId,
            work_order_version: 3,
            tentative: false,
            schedule,
            sources: [source],
            buffer_minutes: 0,
          },
          {
            id: "tentative",
            work_order_id: orderId,
            work_order_version: 3,
            tentative: true,
            schedule,
            sources: [source],
            buffer_minutes: 0,
          },
        ]);
      if (url.includes("/conversations?"))
        return page([
          {
            id: conversationId,
            account_id: "synthetic-account",
            context_version: 4,
            work_order_ids: [orderId],
          },
        ]);
      if (url.includes("/messages?")) return page(messages);
      if (url.endsWith("/conversations/" + conversationId))
        return Response.json({
          data: {
            id: conversationId,
            account_id: "synthetic-account",
            context_version: 4,
            work_order_ids: [orderId],
          },
        });
      if (url.includes("/changes?")) return page([]);
      if (url.includes("/review-items?"))
        return page([
          {
            id: "job",
            conversation_id: conversationId,
            message_id: messageId,
            context_version: 3,
            current_context_version: 4,
            reason: "ASSIGNMENT_NEEDS_REVIEW",
            state: "completed",
            observed_at: "2026-10-14T00:00:00Z",
          },
        ]);
    }
    return fallback(url, options);
  };
  return { calls, order, messages };
}
async function select(label, value) {
  const input = [...document.querySelectorAll("label")]
    .find((l) => l.textContent.startsWith(label))
    ?.querySelector("select");
  assert.ok(input);
  await act(async () => {
    input.value = value;
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
}
async function tick(text) {
  const input = [...document.querySelectorAll("label")]
    .find((l) => l.textContent.includes(text))
    ?.querySelector("input[type=checkbox]");
  assert.ok(input);
  await act(async () => input.click());
}

test("new-order flow selects only customer sources, binds review and stays gated after consent", async () => {
  const data = deliveryFixture();
  const fallback = globalThis.fetch;
  globalThis.fetch = async (url, options) =>
    url.endsWith("/workspace-capabilities")
      ? Response.json({
          data: {
            calendar_export: true,
            create_order: true,
            order_status: true,
            address_confirmation: true,
            manual_assignment: false,
            business_sending: false,
            automatic_understanding: false,
          },
        })
      : fallback(url, options);
  await mount();
  await login();
  await act(async () =>
    document.querySelector("nav").querySelectorAll("button")[1].click(),
  );
  await select("已授权会话", data.order.conversation_ids[0]);
  await tick("这是另一项业务");
  const summary = [...document.querySelectorAll("label")]
    .find((l) => l.textContent === "业务摘要")
    .querySelector("input");
  await fill(summary, "Synthetic second order");
  const address = [...document.querySelectorAll("label")]
    .find((l) => l.textContent.startsWith("客户提供的地址"))
    .querySelector("input");
  await fill(address, "Synthetic customer address");
  assert.equal(button("核对新工单").disabled, true);
  assert.match(document.body.textContent, /必须选择客户说明地址的原文/);
  assert.doesNotMatch(
    document.querySelector("aside").textContent,
    /Synthetic merchant echo/,
  );
  await tick("作为地址依据");
  await act(async () => button("核对新工单").click());
  await tick("我已核对摘要");
  assert.equal(button("保存新工单").disabled, false);
  await fill(summary, "Changed after review");
  assert.match(document.body.textContent, /内容或来源已变化/);
  assert.equal(data.calls.filter((c) => c.options.method === "POST").length, 1);
});
test("calendar renders formal/tentative appointments, gates export and opens the exact order", async () => {
  deliveryFixture();
  await mount();
  await login();
  await act(async () => button("日历与待办").click());
  await act(async () => button("全部安排").click());
  const downloads = [...document.querySelectorAll("button")].filter(
    (b) => b.textContent === "加入我的日历 (.ics)",
  );
  assert.equal(downloads.length, 2);
  assert.equal(downloads[0].disabled, false);
  assert.equal(downloads[1].disabled, true);
  assert.match(document.body.textContent, /暂定或未确认预约不能导出/);
  await act(async () =>
    [...document.querySelectorAll("button")]
      .find((b) => b.textContent === "查看工单")
      .click(),
  );
  assert.match(document.body.textContent, /Synthetic delivery order/);
  assert.equal(document.querySelectorAll("main").length, 1);
  assert.equal(button("已取消"), undefined);
});
test("review inbox distinguishes old rounds, shows source and leaves unavailable assignment disabled", async () => {
  deliveryFixture();
  await mount();
  await login();
  await act(async () => button("人工复核").click());
  assert.match(document.body.textContent, /历史轮次/);
  assert.match(document.body.textContent, /无法确定属于哪张工单/);
  await act(async () => button("查看这条会话原文").click());
  assert.match(document.body.textContent, /Synthetic customer source/);
  assert.equal(button("保存人工归单／延期跟进"), undefined);
});

test("leaving the calendar aborts a late private download before creating a saved file", async () => {
  deliveryFixture();
  const fallback = globalThis.fetch;
  let finish,
    signal,
    saved = 0;
  const original = URL.createObjectURL;
  URL.createObjectURL = () => {
    saved++;
    return "blob:synthetic";
  };
  globalThis.fetch = (url, options) =>
    url.endsWith("/formal.ics")
      ? new Promise((resolve) => {
          finish = resolve;
          signal = options.signal;
        })
      : fallback(url, options);
  try {
    await mount();
    await login();
    await act(async () => button("日历与待办").click());
    await act(async () => button("全部安排").click());
    await act(async () =>
      [...document.querySelectorAll("button")]
        .find((b) => b.textContent === "加入我的日历 (.ics)")
        .click(),
    );
    assert.ok(signal);
    await act(async () => button("功能与使用说明").click());
    assert.equal(signal.aborted, true);
    await act(async () =>
      finish(
        new Response("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", {
          headers: { "content-type": "text/calendar" },
        }),
      ),
    );
    assert.equal(saved, 0);
  } finally {
    URL.createObjectURL = original;
  }
});
