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
  "NavIcon",
  "BusinessLoopWorkspace",
  "ProductTools",
  "BusinessLoopReview",
  "LoopCommand",
  "OrderLifecycle",
  "InspectOrderAttempt",
  "ReplyPanel",
  "ManualFieldEditor",
  "LoopCommand",
  "OrderCreation",
  "CalendarWorkspace",
  "ReviewWorkspace",
  "DeliveryGuide",
  "ApprovalsWorkspace",
  "WorkOrderWorkspace",
  "ManualFieldEditor",
  "LoopCommand",
  "ConnectionWorkspace",
  "ChatChoices",
  "WahaMessages",
  "WahaMedia",
  "WahaSend",
  "GuidedTour",
  "new-request-banner",
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
  "i18n",
  "locales",
  "work-order-view",
  "contact-label",
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
const { setLocale } = await import(pathToFileURL(join(directory, "i18n.mjs")));
let root;
afterEach(async () => {
  await act(async () => setLocale("zh"));
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
  assert.match(document.body.textContent, /还没有工单/);
  assert.match(document.body.textContent, /再点「新建工单」/);
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
  assert.match(document.body.textContent, /当前服务未启用/);
  assert.equal(button("业务管理"), undefined);
  assert.equal(button("新建工单"), undefined);
  assert.ok(
    calls.every(
      (c) => !c.url.includes("/daily-summary") && !c.url.includes("/settings/"),
    ),
  );
  assert.match(document.body.textContent, /未知结果先核查/);
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
  assert.match(document.body.textContent, /状态未核实/);
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
  await act(async () => button("新建工单").click());
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
  assert.equal(button("取消工单"), undefined);
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

test("language switching keeps login input, authenticated page and raw customer content", async () => {
  const data = deliveryFixture();
  data.order.summary = "已确认"; // Intentionally equals a translated UI label.
  data.messages[0].text = "业务工作台";
  await mount();
  await fill(
    document.querySelector('input[autocomplete="username"]'),
    "learner",
  );
  await fill(
    document.querySelector('input[type="password"]'),
    "synthetic-password",
  );
  const user = document.querySelector('input[autocomplete="username"]');
  await act(async () => button("English").click());
  assert.equal(document.documentElement.lang, "en-HK");
  assert.equal(document.querySelector('input[autocomplete="username"]'), user);
  assert.equal(user.value, "learner");
  assert.equal(
    document.querySelector('input[type="password"]').value,
    "synthetic-password",
  );
  assert.ok(button("Open workspace"));
  await act(async () =>
    document
      .querySelector("form")
      .dispatchEvent(
        new window.Event("submit", { bubbles: true, cancelable: true }),
      ),
  );
  assert.ok(button("Workspace"));
  assert.ok(document.body.textContent.includes("已确认"));
  assert.ok(document.body.textContent.includes("业务工作台"));
  const logins = data.calls.filter((c) => c.url.endsWith("/auth/login")).length;
  await act(async () => button("粵語").click());
  assert.equal(document.documentElement.lang, "yue-Hant-HK");
  assert.ok(button("工作台"));
  assert.ok(document.body.textContent.includes("已确认"));
  assert.ok(document.body.textContent.includes("业务工作台"));
  assert.equal(
    data.calls.filter((c) => c.url.endsWith("/auth/login")).length,
    logins,
  );
});

test("business sending resolves a different chat UUID from the owned conversation and verifies the linked receipt", async () => {
  const { BusinessLoopReview } = await import(
    pathToFileURL(join(directory, "BusinessLoopReview.mjs"))
  );
  const account = "00000000-0000-4000-8000-000000000001",
    conversation = "00000000-0000-4000-8000-000000000002",
    chat = "00000000-0000-4000-8000-000000000003",
    connection = "00000000-0000-4000-8000-000000000004",
    order = "00000000-0000-4000-8000-000000000005",
    actionId = "00000000-0000-4000-8000-000000000006",
    sendId = "00000000-0000-4000-8000-000000000007";
  const action = {
    id: actionId,
    account_id: account,
    conversation_id: conversation,
    work_order_id: order,
    body: "已确认",
    state: "approved",
    revision: 2,
    snapshot_hash: "sha256:synthetic",
    expires_at: new Date(Date.now() + 60000).toISOString(),
  };
  globalThis.fetch = async (url) => {
    if (url.includes("/actions?"))
      return Response.json({ items: [action], next_cursor: null });
    if (url.includes("/connectors?"))
      return Response.json({ items: [{ id: connection }], next_cursor: null });
    if (url.endsWith("/setup"))
      return Response.json({
        data: {
          connection_id: connection,
          control_version: 4,
          enabled: true,
          available: true,
          provider_sample_stale: false,
        },
      });
    if (url.endsWith("/sending/permission"))
      return Response.json({
        data: { version: 5, enabled: true, chat_ids: [chat], expires_at: null },
      });
    if (url.endsWith("/chats"))
      return Response.json({
        data: [{ id: chat, selected: true, conversation_id: conversation }],
      });
    if (url.endsWith("/sending/actions/" + sendId))
      return Response.json({
        data: {
          id: sendId,
          chat_id: chat,
          work_order_id: order,
          payload: { kind: "text", text: "已确认" },
          state: "accepted",
          delivery_status: "sent",
        },
      });
    throw Error("Unexpected read " + url);
  };
  const errors = [],
    submitted = [];
  const api = {
    pending: null,
    error: "",
    read: async () => ({ ...action }),
    submit: async (value) => {
      submitted.push(value);
      return { ...action };
    },
  };
  const props = {
    api,
    csrf: "csrf",
    accountId: account,
    features: {
      business_loop_reviewed: true,
      business_sending: true,
      manual_assignment: false,
    },
    orders: [{ id: order, summary: "Synthetic order" }],
    onDone: () => {},
    onError: (e) => errors.push(e),
    onBusy: () => {},
  };
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(BusinessLoopReview, props)));
  await select("业务草稿", actionId);
  await select("发送连接", connection);
  assert.ok(button("发送给客人"));
  await act(async () => button("发送给客人").click());
  await tick("我已核对内容、来源及当前版本");
  await act(async () => button("确认发送").click());
  assert.equal(submitted.length, 1);
  assert.equal(submitted[0].body.connection_id, connection);
  assert.equal(submitted[0].body.expected_permission_version, 5);
  assert.ok(submitted[0].review.includes("已确认")); // Exact body is preserved.
  action.state = "executing";
  action.send_action_id = sendId;
  await act(async () =>
    root.render(
      createElement(BusinessLoopReview, { ...props, api: { ...api } }),
    ),
  );
  assert.match(document.body.textContent, /关联回执/);
  assert.deepEqual(errors, []);
});

async function loopFixture({ field = "quantity", invalid = "" } = {}) {
  const data = deliveryFixture();
  const fallback = globalThis.fetch;
  const primary = data.order.conversation_ids[0];
  const second = "00000000-0000-4000-8000-000000000009";
  const sourceId = "00000000-0000-4000-8000-000000000010";
  data.order.conversation_ids.push(second);
  const change = {
    id: "00000000-0000-4000-8000-000000000011",
    work_order_id: data.order.id,
    field,
    new_value:
      field === "quantity"
        ? "12"
        : { kind: "date_only", date: "2026-12-01", timezone: "Asia/Hong_Kong" },
    status: "proposed",
    customer_confirmation: "ambiguous",
    base_work_order_version: 3,
    context_version: invalid === "stale" ? 8 : 9,
    conflict_ids: [],
    sources: [{ message_id: sourceId, message_revision: 1 }],
  };
  if (invalid === "mixed")
    change.sources.push({
      message_id: data.messages[0].id,
      message_revision: 1,
    });
  const secondMessages = [
    {
      ...data.messages[0],
      id: sourceId,
      conversation_id: second,
      revoked: invalid === "revoked",
    },
  ];
  if (invalid === "revision")
    secondMessages.push({ ...secondMessages[0], revision: 2 });
  const calls = [],
    writes = [];
  let unavailable = false;
  globalThis.fetch = async (url, options) => {
    calls.push(url);
    if (options.method === "POST") {
      writes.push(JSON.parse(options.body));
      data.order.version++;
      return Response.json({ data: data.order });
    }
    if (unavailable && url.endsWith("/daily-summary"))
      return Response.json({ error: { code: "UNAVAILABLE" } }, { status: 503 });
    if (url.endsWith("/daily-summary"))
      return Response.json({
        data: {
          date: "2026-11-01",
          timezone: "Asia/Hong_Kong",
          today: [],
          waiting_for_customer: [],
          due_soon: [],
          needs_decision: [],
          suggestions: [],
        },
      });
    if (url.endsWith("/settings/schedule"))
      return Response.json({ data: null });
    if (url.endsWith("/work-orders/" + data.order.id))
      return Response.json({ data: data.order });
    if (url.endsWith("/checklist"))
      return Response.json({
        data: { work_order_id: data.order.id, items: [], ready: true },
      });
    if (url.endsWith("/schedule-check"))
      return Response.json({
        data: { work_order_id: data.order.id, risks: [], suggestions: [] },
      });
    if (url.includes("/changes?"))
      return Response.json({ items: [change], next_cursor: null });
    if (url.includes(`/conversations/${second}/messages?`))
      return Response.json({ items: secondMessages, next_cursor: null });
    if (url.endsWith(`/conversations/${second}`))
      return invalid === "paused"
        ? Response.json({ error: { code: "NOT_FOUND" } }, { status: 404 })
        : Response.json({
            data: {
              id: second,
              account_id: "synthetic-account",
              context_version: 9,
            },
          });
    if (url.includes("/actions?"))
      return Response.json({ items: [], next_cursor: null });
    return fallback(url, options);
  };
  const { BusinessLoopWorkspace } = await import(
    pathToFileURL(join(directory, "BusinessLoopWorkspace.mjs"))
  );
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(BusinessLoopWorkspace, {
        csrf: "csrf",
        accountId: "synthetic-account",
        features: {
          business_loop_reviewed: true,
          business_sending: false,
          manual_assignment: false,
        },
        onSessionExpired: () => {},
        onBusyChange: () => {},
        onOpenOrder: () => {},
      }),
    ),
  );
  return {
    ...data,
    calls,
    writes,
    primary,
    second,
    offline: () => {
      unavailable = true;
    },
  };
}

for (const field of ["quantity", "deadline"])
  test(`business management confirms ${field} from the second linked conversation with its own version`, async () => {
    const data = await loopFixture({ field });
    assert.ok(
      data.calls.some((url) => url.endsWith(`/conversations/${data.second}`)),
    );
    assert.ok(button("接受此提议"));
    await act(async () => button("接受此提议").click());
    assert.match(
      document.querySelector('[aria-label="操作复核"]').textContent,
      /会话 v9/,
    );
    await tick("我已核对内容、来源及当前版本");
    await act(async () => button("确认保存").click());
    assert.equal(data.writes.length, 1);
    assert.equal(data.writes[0].expected_context_version, 9);
    assert.equal(data.writes[0].expected_version, 3);
    assert.match(document.body.textContent, /保存结果已确认/);
    data.offline();
    await act(async () => button("刷新业务管理").click());
    assert.ok(document.querySelector('[role="alert"]'));
    assert.doesNotMatch(document.body.textContent, /保存结果已确认/);
  });

for (const invalid of ["mixed", "revoked", "revision", "stale", "paused"])
  test(`business management refuses ${invalid} second-conversation evidence`, async () => {
    const data = await loopFixture({ invalid });
    assert.equal(button("接受此提议"), undefined);
    assert.deepEqual(data.writes, []);
  });

test("seconds in follow-up input do not crash the business page and invalid dates cannot dispatch", async () => {
  const data = await loopFixture();
  const selectSource = document.querySelector('[aria-label="业务操作原文"]');
  await act(async () => {
    selectSource.value = data.messages[0].id + ":1";
    selectSource.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
  const input = document.querySelector('input[type="datetime-local"]');
  await fill(input, "2026-11-01T08:30:15.123");
  assert.ok(button("核对延期跟进"));
  await act(async () => button("核对延期跟进").click());
  await tick("我已核对内容、来源及当前版本");
  await act(async () => button("确认保存").click());
  assert.equal(data.writes[0].until, "2026-11-01T00:30:15.123Z");
  // Browsers normally sanitize invalid dates; exercise the handler's failure
  // branch too rather than relying on a specific browser's input behavior.
  await act(async () => {
    Object.defineProperty(input, "value", {
      configurable: true,
      get: () => "2026-02-31T08:30",
    });
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  assert.ok(document.querySelector('[aria-label="业务管理"]'));
  assert.match(document.body.textContent, /跟进时间无效/);
  assert.equal(button("核对延期跟进"), undefined);
  assert.equal(data.writes.length, 1);
});

test("review and recovery render the exact formatted snapshot without translating customer-like UI templates", async () => {
  const { LoopCommand, LoopRecovery } = await import(
    pathToFileURL(join(directory, "LoopCommand.mjs"))
  );
  const review = "Content updated: 已确认 <img onerror=synthetic> {0}";
  const intent = {
    path: "/work-orders/00000000-0000-4000-8000-000000000003/defer",
    body: {},
    review,
  };
  const api = { pending: null, error: "" };
  const props = {
    api,
    intent,
    label: "review",
    onDone: () => {},
    onError: () => {},
    onBusy: () => {},
  };
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(LoopCommand, props)));
  await act(async () => button("review").click());
  assert.equal(document.querySelector('[role="region"] p').textContent, review);
  for (const locale of ["en", "yue", "zh"]) {
    await act(async () => {
      setLocale(locale);
      root.render(createElement(LoopCommand, props));
    });
    assert.equal(
      document.querySelector('[role="region"] p').textContent,
      review,
    );
  }
  await act(async () =>
    root.render(
      createElement(LoopRecovery, {
        ...props,
        api: { pending: { intent, key: "synthetic" } },
      }),
    ),
  );
  assert.equal(document.querySelector('[role="region"] p').textContent, review);
  assert.equal(document.querySelector("img"), null);
});

test("business replies load paginated connections and prepare exact authorised sending without writing", async () => {
  const { BusinessLoopReview } = await import(
    pathToFileURL(join(directory, "BusinessLoopReview.mjs"))
  );
  const accountId = "00000000-0000-4000-8000-000000000001";
  const actionId = "00000000-0000-4000-8000-000000000006";
  const conversationId = "00000000-0000-4000-8000-000000000002";
  const connectionId = "00000000-0000-4000-8000-000000000009";
  const chatId = "00000000-0000-4000-8000-000000000010";
  const draft = {
    id: actionId,
    account_id: accountId,
    work_order_id: "00000000-0000-4000-8000-000000000003",
    conversation_id: conversationId,
    revision: 1,
    state: "approved",
    body: "Synthetic approved reply",
    expires_at: "2099-10-17T00:00:00Z",
    snapshot_hash: "synthetic-snapshot",
    send_action_id: null,
  };
  const reads = [],
    errors = [],
    writes = [];
  globalThis.fetch = async (url, options) => {
    assert.equal(options.method, "GET");
    const parsed = new URL(url, "http://localhost");
    const path = parsed.pathname.replace(/^.*\/api\/v1/, "");
    reads.push(path + parsed.search);
    if (path === "/actions")
      return Response.json({ items: [draft], next_cursor: null });
    if (path === "/connectors")
      return Response.json(
        parsed.searchParams.has("cursor")
          ? { items: [{ id: connectionId }], next_cursor: null }
          : {
              items: [{ id: "00000000-0000-4000-8000-000000000008" }],
              next_cursor: "synthetic-next",
            },
      );
    if (path.endsWith("/setup"))
      return Response.json({
        data: {
          connection_id: connectionId,
          enabled: true,
          available: true,
          provider_sample_stale: false,
          control_version: 3,
        },
      });
    if (path.endsWith("/sending/permission"))
      return Response.json({
        data: {
          version: 2,
          enabled: true,
          chat_ids: [chatId],
          expires_at: "2099-10-17T00:00:00Z",
        },
      });
    if (path.endsWith("/chats"))
      return Response.json({
        data: [{ id: chatId, conversation_id: conversationId, selected: true }],
      });
    throw Error("Unexpected synthetic read: " + path);
  };
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(BusinessLoopReview, {
        api: {
          read: async () => draft,
          pending: null,
          error: "",
          submit: (...args) => writes.push(args),
        },
        csrf: "synthetic-reply-csrf",
        accountId,
        features: { business_sending: true, manual_assignment: false },
        orders: [],
        onDone() {},
        onBusy() {},
        onError: (e) => errors.push(e),
      }),
    ),
  );
  const select = (label) =>
    [...document.querySelectorAll("label")]
      .find((node) => node.textContent.includes(label))
      .querySelector("select");
  await act(async () => {
    select("业务草稿").value = actionId;
    select("业务草稿").dispatchEvent(
      new window.Event("change", { bubbles: true }),
    );
  });
  assert.equal(select("发送连接").options.length, 3);
  await act(async () => {
    select("发送连接").value = connectionId;
    select("发送连接").dispatchEvent(
      new window.Event("change", { bubbles: true }),
    );
  });
  assert.ok(reads.some((path) => path.includes("cursor=synthetic-next")));
  assert.equal(button("发送给客人").disabled, false);
  assert.deepEqual(errors, []);
  assert.deepEqual(writes, []);
});

test("malformed connector list reports an error without crashing the business reply page", async () => {
  const { BusinessLoopReview } = await import(
    pathToFileURL(join(directory, "BusinessLoopReview.mjs"))
  );
  const errors = [];
  globalThis.fetch = async (url) =>
    Response.json(
      url.includes("/connectors")
        ? { data: [] }
        : { items: [], next_cursor: null },
    );
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(BusinessLoopReview, {
        api: { pending: null, error: "" },
        csrf: "synthetic-invalid-csrf",
        accountId: "synthetic-account",
        features: { business_sending: true, manual_assignment: false },
        orders: [],
        onDone() {},
        onBusy() {},
        onError: (e) => errors.push(e),
      }),
    ),
  );
  assert.match(document.body.textContent, /归单与业务回复/);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].code, "INVALID_RESPONSE");
  assert.equal(button("核对并提交业务发送"), undefined);
});

function reviewDecisionFixture({
  reason = "EXTRACTION_NEEDS_REVIEW",
  stale = false,
} = {}) {
  const data = deliveryFixture(),
    fallback = globalThis.fetch;
  const writes = [];
  let resolved = false;
  const job = "00000000-0000-4000-8000-000000000099";
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/workspace-capabilities"))
      return Response.json({
        data: {
          calendar_export: true,
          create_order: true,
          order_status: true,
          address_confirmation: true,
          manual_assignment: true,
          business_sending: false,
          automatic_understanding: true,
          business_loop_reviewed: true,
        },
      });
    if (url.includes("/new-order-suggestions?"))
      return Response.json({ items: [], next_cursor: null });
    if (url.includes("/review-items?"))
      return Response.json({
        items: resolved
          ? []
          : [
              {
                id: job,
                conversation_id: data.order.conversation_ids[0],
                message_id: data.messages[0].id,
                context_version: stale ? 3 : 4,
                current_context_version: 4,
                reason,
                state: "completed",
                observed_at: "2026-10-14T00:00:00Z",
              },
            ],
        next_cursor: null,
      });
    if (url.endsWith(`/review-items/${job}/assign`)) {
      const body = JSON.parse(options.body);
      writes.push({ body, options });
      resolved = true;
      return Response.json({
        data: {
          job_id: job,
          conversation_id: data.order.conversation_ids[0],
          action: body.action,
          work_order_id: body.work_order_id,
          state: "completed",
        },
      });
    }
    return fallback(url, options);
  };
  return { ...data, writes };
}
test("feature guide describes live availability and opens calendar directly", async () => {
  fixture();
  await mount();
  await login();
  await act(async () => button("功能与使用说明").click());
  assert.doesNotMatch(document.body.textContent, /仍在等待接通/);
  const card = [...document.querySelectorAll("article")].find((a) =>
    a.textContent.includes("导出手机日历"),
  );
  assert.match(card.textContent, /现在可以使用/);
  await act(async () => card.querySelector("button").click());
  assert.ok(document.querySelector('[aria-label="日历与待办"]'));
});
test("manual review dismisses the exact current message only after explicit review", async () => {
  const data = reviewDecisionFixture();
  await mount();
  await login();
  await act(async () => button("人工复核").click());
  await act(async () => button("查看这条会话原文").click());
  await act(async () => button("标记无需归单").click());
  assert.equal(data.writes.length, 0);
  assert.equal(button("确认保存").disabled, true);
  await tick("我已核对内容、来源及当前版本");
  await act(async () => button("确认保存").click());
  assert.equal(data.writes.length, 1);
  assert.deepEqual(data.writes[0].body, {
    action: "dismiss",
    expected_context_version: 4,
    work_order_id: null,
  });
  assert.ok(data.writes[0].options.headers["Idempotency-Key"]);
  assert.equal(button("查看这条会话原文"), undefined);
});
test("manual review assigns a same-conversation open order and carries current context", async () => {
  const data = reviewDecisionFixture();
  await mount();
  await login();
  await act(async () => button("人工复核").click());
  await act(async () => button("查看这条会话原文").click());
  await select("归入工单", data.order.id);
  await act(async () => button("核对归单").click());
  await tick("我已核对内容、来源及当前版本");
  await act(async () => button("确认保存").click());
  assert.deepEqual(data.writes[0].body, {
    action: "assign",
    expected_context_version: 4,
    work_order_id: data.order.id,
  });
});
test("stale review records cannot be dismissed and unknown model outcomes cannot be reassigned", async () => {
  const data = reviewDecisionFixture({ stale: true });
  await mount();
  await login();
  await act(async () => button("人工复核").click());
  await act(async () => button("查看这条会话原文").click());
  assert.equal(button("标记无需归单").disabled, true);
  assert.equal(data.writes.length, 0);
});
test("unknown model outcome keeps manual creation available but blocks reassignment", async () => {
  const data = reviewDecisionFixture({ reason: "MODEL_OUTCOME_UNKNOWN" });
  await mount();
  await login();
  await act(async () => button("人工复核").click());
  await act(async () => button("查看这条会话原文").click());
  await select("归入工单", data.order.id);
  assert.equal(button("核对归单"), undefined);
  assert.equal(data.writes.length, 0);
  await act(async () => button("为这条会话新建工单").click());
  const label = [...document.querySelectorAll("label")].find((l) =>
    l.textContent.startsWith("已授权会话"),
  );
  assert.equal(
    label.querySelector("select").value,
    data.order.conversation_ids[0],
  );
  assert.equal(data.writes.length, 0);
});
test("first sign-in starts an interactive walkthrough that waits for the user's own clicks", async () => {
  fixture();
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  // jsdom lays nothing out; give elements a visible box so targets count as shown.
  const measure = window.HTMLElement.prototype.getBoundingClientRect;
  window.HTMLElement.prototype.getBoundingClientRect = () => ({
    top: 10,
    left: 10,
    width: 120,
    height: 32,
    right: 130,
    bottom: 42,
  });
  try {
    await mount();
    await login();
    const dialog = () => document.querySelector('.tour [role="dialog"]');
    assert.ok(dialog(), "tour opens on first sign-in");
    assert.match(dialog().textContent, /欢迎使用 GigMate/);
    await act(async () => button("下一步").click());
    assert.match(dialog().textContent, /第 1 步：连接 WhatsApp/);
    // A waiting step has no "next": only the real highlighted button moves on.
    assert.equal(button("下一步"), undefined);
    assert.match(dialog().textContent, /等你点亮起来的按钮/);
    const nav = document.querySelector('[data-tour="nav-connect"]');
    assert.ok(nav, "the real navigation button is the tour target");
    await act(async () => nav.click());
    assert.match(dialog().textContent, /扫码，然后勾选业务聊天/);
    await act(async () => button("跳过引导").click());
    assert.equal(dialog(), null);
    assert.ok([...store.values()].includes("done"));
    // Seen once on this account: signing in again does not start it again.
    await act(async () => root.unmount());
    document.getElementById("root").replaceChildren();
    await mount();
    await login();
    assert.equal(dialog(), null);
    // It can always be replayed from the help page.
    await act(async () => button("功能与使用说明").click());
    await act(async () => button("重新查看新手引导").click());
    assert.match(dialog().textContent, /欢迎使用 GigMate/);
  } finally {
    window.HTMLElement.prototype.getBoundingClientRect = measure;
    delete globalThis.localStorage;
  }
});

test("a newly authorized conversation at version zero can open manual creation", async () => {
  const data = deliveryFixture(),
    fallback = globalThis.fetch,
    chat = data.order.conversation_ids[0];
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/workspace-capabilities"))
      return Response.json({
        data: {
          calendar_export: true,
          create_order: true,
          order_status: true,
          address_confirmation: true,
          manual_assignment: false,
          business_sending: false,
          automatic_understanding: false,
          business_loop_reviewed: false,
          manual_field_editing: false,
        },
      });
    if (url.endsWith("/conversations/" + chat))
      return Response.json({
        data: {
          id: chat,
          account_id: "synthetic-account",
          context_version: 0,
          work_order_ids: [data.order.id],
        },
      });
    if (url.includes("/messages?"))
      return Response.json({ items: [], next_cursor: null });
    return fallback(url, options);
  };
  await mount();
  await login();
  await act(async () => button("新建工单").click());
  await select("已授权会话", chat);
  await tick("这是另一项业务");
  const input = [...document.querySelectorAll("label")]
    .find((label) => label.textContent === "业务摘要")
    .querySelector("input");
  await fill(input, "Synthetic first contact without message history");
  assert.equal(button("核对新工单").disabled, false);
});
test("a new job the customer mentioned opens creation with address and time prefilled", async () => {
  const data = deliveryFixture();
  const conversation = data.order.conversation_ids[0],
    messageId = data.messages[0].id;
  const fallback = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/workspace-capabilities"))
      return Response.json({
        data: {
          calendar_export: true,
          create_order: true,
          order_status: true,
          address_confirmation: true,
          manual_assignment: false,
          business_sending: false,
          automatic_understanding: false,
          business_loop_reviewed: true,
          manual_field_editing: false,
        },
      });
    if (url.includes("/new-order-suggestions?"))
      return Response.json({
        items: [
          {
            id: "00000000-0000-4000-8000-0000000000c1",
            conversation_id: conversation,
            context_version: 4,
            created_at: "2026-10-18T00:00:00Z",
            sources: [{ message_id: messageId, message_revision: 1 }],
            suggestion: {
              summary: "陈小姐另约全家福",
              fields: [
                {
                  field: "address",
                  value: "旺角弥敦道 1 号",
                  sources: [{ message_id: messageId, message_revision: 1 }],
                  reason: "客人给了地址。",
                },
                {
                  field: "schedule",
                  value: {
                    kind: "timed",
                    start_at: "2026-10-20T07:00:00Z",
                    end_at: "2026-10-20T08:00:00Z",
                    timezone: "Asia/Hong_Kong",
                  },
                  sources: [{ message_id: messageId, message_revision: 1 }],
                  reason: "客人给了时间。",
                },
              ],
              missing_fields: [],
              unresolved_questions: [],
              confidence: 0.8,
            },
          },
        ],
        next_cursor: null,
      });
    return fallback(url, options);
  };
  await mount();
  await login();
  assert.match(
    document.body.textContent,
    /客人提到一件新事：「陈小姐另约全家福」/,
  );
  await act(async () => button("另开一单（已预填）").click());
  const input = (prefix) =>
    [...document.querySelectorAll("label")]
      .find((l) => l.textContent.startsWith(prefix))
      .querySelector("input, select");
  assert.equal(input("业务摘要").value, "陈小姐另约全家福");
  assert.equal(input("客户提供的地址").value, "旺角弥敦道 1 号");
  assert.equal(input("时间信息").value, "timed");
  assert.equal(input("开始（香港时间）").value, "2026-10-20T15:00");
  assert.equal(input("结束（香港时间）").value, "2026-10-20T16:00");
  // Nothing is written until the merchant reviews and confirms.
  assert.equal(data.calls.filter((c) => c.options.method === "POST").length, 1);
});
