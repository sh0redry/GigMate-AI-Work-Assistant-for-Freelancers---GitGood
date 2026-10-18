import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { mkdtemp, readFile, readdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import ts from "typescript";
import { JSDOM } from "jsdom";
import { act, createElement } from "react";

const require = createRequire(import.meta.url);
const directory = await mkdtemp(join(tmpdir(), "gigmate-conversations-"));
for (const filename of (
  await readdir(new URL("./src", import.meta.url))
).filter((name) => /\.(tsx|ts)$/.test(name) && name !== "main.tsx")) {
  const source = await readFile(
    new URL(`./src/${filename}`, import.meta.url),
    "utf8",
  );
  const code = ts
    .transpileModule(source, {
      fileName: filename,
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
        jsx: ts.JsxEmit.ReactJSX,
      },
    })
    .outputText.replace(/import "\.\/[^"\n]+\.css";\s*/g, "")
    .replace(/"\.\/([\w-]+)(?:\.ts)?"/g, '"./$1.mjs"')
    .replace(/"(react(?:\/jsx-runtime)?)"/g, (_, specifier) =>
      JSON.stringify(pathToFileURL(require.resolve(specifier)).href),
    );
  await writeFile(
    join(directory, filename.replace(/\.(tsx|ts)$/, ".mjs")),
    code,
  );
}
const load = (name) => import(pathToFileURL(join(directory, `${name}.mjs`)));
const { CustomerConversations } = await load("CustomerConversations");
const { ConversationBusiness } = await load("ConversationBusiness");
const { conversationApi } = await load("conversation-api");
const { orderedMessages, sourceMatch, nearConversationBottom } =
  await load("conversation-view");
const { clearReadCache, setReadScope } = await load("read-cache");
const { unavailableFeatures } = await load("features");
const { setLocale } = await load("i18n");
const dom = new JSDOM('<div id="root"></div>', {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.localStorage = dom.window.localStorage;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const original = {
  fetch: globalThis.fetch,
  setInterval: globalThis.setInterval,
  clearInterval: globalThis.clearInterval,
  dateNow: Date.now,
};
let root,
  timers = new Map(),
  nextTimer = 1;
globalThis.setInterval = (fn, delay) => {
  const id = nextTimer++;
  timers.set(id, { fn, delay });
  return id;
};
globalThis.clearInterval = (id) => timers.delete(id);
dom.window.HTMLElement.prototype.scrollIntoView = function () {
  this.dataset.scrolled = "true";
};
dom.window.confirm = () => true;
const uid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const connection = uid(1),
  chatA = uid(2),
  chatB = uid(3),
  conversationA = uid(4),
  conversationB = uid(5),
  orderId = uid(6);
const choice = (id = chatA, conversation = conversationA) => ({
  id,
  conversation_id: conversation,
  label: id === chatA ? "Synthetic Alpha" : "Synthetic Beta",
  selected: true,
  expires_at: null,
  kind: "direct",
});
const message = (id = uid(10), chat = chatA, conversation = conversationA) => ({
  id,
  chat_id: chat,
  conversation_id: conversation,
  source_message_id: uid(110),
  occurred_at: "2026-10-18T02:00:00Z",
  observed_at: "2026-10-18T02:00:01Z",
  origin: "live",
  evidence: "revision",
  revision: 1,
  direction: "incoming",
  text: "Synthetic source <img src=x>",
  revoked: false,
  kind: "text",
  mimetype: null,
  filename: null,
  sender_id: null,
  reply_to_id: null,
  attachment_reading: "not_applicable",
  processing_state: "completed",
  delivery_status: null,
});
const order = {
  id: orderId,
  account_id: uid(100),
  version: 1,
  summary: "Synthetic job",
  status: "confirmed",
  conversation_ids: [conversationA],
  updated_at: "2026-10-18T02:00:00Z",
  pending_change_ids: [],
  fields: {
    address: {
      status: "missing",
      value: null,
      sources: [{ message_id: uid(110), message_revision: 1 }],
    },
  },
};
const draft = {
  id: uid(20),
  work_order_id: orderId,
  conversation_id: conversationA,
  kind: "follow_up",
  text: "Synthetic proposed reply",
  context_version: 1,
  base_work_order_version: 1,
  proposal_id: uid(21),
  status: "proposed",
  expires_at: "2099-10-18T02:00:00Z",
  revoked_at: null,
  consumed_at: null,
  note: null,
  created_at: "2026-10-18T02:00:00Z",
  execution_authority: false,
};

function fixture({ draftsAvailable = false, override } = {}) {
  const calls = [],
    data = {
      a: [message()],
      b: [
        {
          ...message(uid(11), chatB, conversationB),
          text: "Synthetic Beta content",
        },
      ],
      denied: false,
    };
  globalThis.fetch = async (url, options = {}) => {
    url = String(url);
    calls.push({ url, options });
    const custom = await override?.(url, options, data);
    if (custom) return custom;
    if (url.endsWith("/connectors?limit=50"))
      return Response.json({
        items: [
          {
            id: connection,
            connector: "waha",
            enabled: true,
            live_connected: true,
            stale: false,
            state: "connected",
            pipeline_ready: true,
          },
        ],
        next_cursor: null,
      });
    if (url.endsWith("/chats"))
      return Response.json({
        data: [
          choice(),
          choice(chatB, conversationB),
          { ...choice(uid(99)), label: "Not allowed", selected: false },
        ],
      });
    if (url.includes("/timeline?"))
      return data.denied
        ? Response.json(
            { error: { code: "CONVERSATION_NOT_ALLOWED" } },
            { status: 403 },
          )
        : Response.json({
            items: url.includes(chatA) ? data.a : data.b,
            next_cursor: null,
          });
    if (url.includes("/work-orders?"))
      return Response.json({ items: [order], next_cursor: null });
    if (url.includes(`/work-orders/${orderId}/drafts`))
      return draftsAvailable
        ? Response.json({ items: [draft], next_cursor: null })
        : Response.json({ detail: "Not found" }, { status: 404 });
    if (url.includes(`/drafts/${draft.id}/consume`))
      return Response.json({
        data: {
          ...draft,
          status: "consumed",
          consumed_at: "2026-10-18T03:00:00Z",
        },
      });
    if (url.endsWith("/sending/capabilities"))
      return Response.json({ data: { enabled: true } });
    if (url.endsWith("/sending/permission"))
      return Response.json({
        data: {
          version: 1,
          enabled: true,
          chat_ids: [chatA, chatB],
          expires_at: "2099-10-18T02:00:00Z",
        },
      });
    if (url.includes("/sending/actions?") || url.includes("/sending/policies?"))
      return Response.json({ items: [], next_cursor: null });
    return Response.json(
      { error: { code: "UNEXPECTED_TEST_ROUTE" } },
      { status: 404 },
    );
  };
  return { calls, data };
}
const button = (text) =>
  [...document.querySelectorAll("button")].find(
    (element) => element.textContent.trim() === text,
  );
async function click(element) {
  assert.ok(element, "control exists");
  await act(async () => {
    element.click();
  });
}
async function change(element, value) {
  assert.ok(element);
  await act(async () => {
    if (element.tagName === "SELECT") {
      element.value = value;
      element.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    } else {
      Object.getOwnPropertyDescriptor(
        dom.window[
          element.tagName === "TEXTAREA"
            ? "HTMLTextAreaElement"
            : "HTMLInputElement"
        ].prototype,
        "value",
      ).set.call(element, value);
      element.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    }
  });
}
function labelled(text) {
  const label = [...document.querySelectorAll("label")].find(
    (element) => element.firstChild?.textContent === text,
  );
  return label?.querySelector("input, select, textarea");
}
async function mount(extra = {}) {
  setReadScope("synthetic-account:synthetic-session");
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(CustomerConversations, {
        csrf: "synthetic-csrf",
        active: true,
        features: { ...unavailableFeatures, create_order: true },
        onSessionExpired() {},
        onBusyChange() {},
        onOpenOrder() {},
        onCreate() {},
        onConnect() {},
        ...extra,
      }),
    ),
  );
}
async function poll(delay) {
  await act(async () => {
    for (const { fn, delay: value } of [...timers.values()])
      if (value === delay) await fn();
  });
}
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  document.getElementById("root").replaceChildren();
  assert.equal(timers.size, 0, "unmount must remove every poll timer");
  timers.clear();
  Date.now = original.dateNow;
  delete document.hidden;
  sessionStorage.clear();
  localStorage.clear();
  clearReadCache();
  setReadScope("");
  setLocale("zh");
  globalThis.fetch = original.fetch;
});
after(async () => {
  Object.assign(globalThis, original);
  dom.window.close();
  for (const name of [
    "window",
    "document",
    "localStorage",
    "sessionStorage",
    "IS_REACT_ACT_ENVIRONMENT",
  ])
    delete globalThis[name];
  await rm(directory, { recursive: true });
});

test("timeline validates ownership, replaces edited/revoked content and refuses looping cursors", async () => {
  const api = conversationApi("synthetic", async () =>
    Response.json({
      items: [{ ...message(), chat_id: chatB }],
      next_cursor: null,
    }),
  );
  await assert.rejects(
    api.timeline(connection, choice(), 1),
    (error) => error.code === "INVALID_RESPONSE",
  );
  const loop = conversationApi("synthetic", async () =>
    Response.json({ items: [message()], next_cursor: "same" }),
  );
  await assert.rejects(
    loop.timeline(connection, choice(), 3),
    (error) => error.code === "INVALID_RESPONSE",
  );
  const changed = { ...message(), revision: 2, revoked: true, text: null };
  assert.deepEqual(orderedMessages([message(), changed]), [changed]);
  assert.equal(sourceMatch(changed, uid(110), 1), false);
  assert.equal(sourceMatch(message(), uid(110), 1), true);
});

test("timeline refresh reaches an earlier anchor across page shifts and caps a missing anchor", async () => {
  let calls = 0;
  const api = conversationApi("synthetic", async (url) => {
    calls++;
    const index = Number(
      new URL(url, "http://localhost").searchParams.get("cursor") ?? 0,
    );
    return Response.json({
      items: [
        {
          ...message(uid(1000 + index)),
          occurred_at: `2026-10-18T01:${String(59 - index).padStart(2, "0")}:00Z`,
        },
      ],
      next_cursor: String(index + 1),
    });
  });
  const found = await api.timeline(connection, choice(), 1, uid(1002));
  assert.equal(found.pages, 3);
  assert.equal(found.truncated, false);
  assert.equal(calls, 3);
  calls = 0;
  const capped = await api.timeline(connection, choice(), 1, "missing");
  assert.equal(capped.pages, 10);
  assert.equal(capped.truncated, true);
  assert.equal(calls, 10);
});

test("only authorised chats are shown; raw HTML remains text and no read receipt or media download is issued", async () => {
  const { calls } = fixture();
  await mount();
  assert.ok(!document.body.textContent.includes("Not allowed"));
  await click(document.querySelector(".conversation-choice"));
  assert.match(
    document.querySelector(".conversation-scroll").textContent,
    /Synthetic source <img src=x>/,
  );
  assert.equal(document.querySelectorAll(".conversation-scroll img").length, 0);
  assert.equal(
    calls.filter((call) => call.options.method === "POST").length,
    0,
  );
  assert.ok(
    !calls.some((call) => /download|read-receipt|media\//.test(call.url)),
  );
});

test("switching chats isolates messages and keeps unsent text only in session memory", async () => {
  fixture();
  await mount();
  await click(document.querySelectorAll(".conversation-choice")[0]);
  await change(
    document.querySelector(".conversation-composer textarea"),
    "Synthetic unsent Alpha",
  );
  await click(document.querySelectorAll(".conversation-choice")[1]);
  assert.equal(
    document.querySelector(".conversation-composer textarea").value,
    "",
  );
  assert.ok(
    !document
      .querySelector(".conversation-scroll")
      .textContent.includes("Synthetic source"),
  );
  await change(
    document.querySelector(".conversation-composer textarea"),
    "Synthetic unsent Beta",
  );
  await click(document.querySelectorAll(".conversation-choice")[0]);
  assert.equal(
    document.querySelector(".conversation-composer textarea").value,
    "Synthetic unsent Alpha",
  );
  assert.equal(localStorage.length, 0);
  assert.equal(sessionStorage.length, 0);
});

test("a late response from the previous chat cannot enter the current conversation", async () => {
  let release,
    held = false;
  fixture({
    override: (url) => {
      if (held && url.includes(chatA) && url.includes("timeline"))
        return new Promise((resolve) => {
          release = resolve;
        });
    },
  });
  await mount();
  held = true;
  await click(document.querySelectorAll(".conversation-choice")[0]);
  await click(document.querySelectorAll(".conversation-choice")[1]);
  await act(async () =>
    release(Response.json({ items: [message()], next_cursor: null })),
  );
  assert.match(
    document.querySelector(".conversation-scroll").textContent,
    /Synthetic Beta content/,
  );
  assert.ok(
    !document
      .querySelector(".conversation-scroll")
      .textContent.includes("Synthetic source"),
  );
});

test("polling applies revocation to the same bubble and does not restore original text", async () => {
  const { data } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  data.a = [{ ...message(), revision: 2, revoked: true, text: null }];
  await poll(3000);
  assert.equal(document.querySelectorAll(".conversation-message").length, 1);
  assert.match(
    document.querySelector(".conversation-scroll").textContent,
    /此消息已撤回/,
  );
  assert.ok(
    !document
      .querySelector(".conversation-scroll")
      .textContent.includes("Synthetic source"),
  );
  assert.equal(
    document.querySelectorAll(".conversation-message input[type=checkbox]")
      .length,
    0,
  );
});

test("new messages do not pull a reader from earlier history and expose a jump control", async () => {
  const { data } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  const scroller = document.querySelector(".conversation-scroll");
  Object.defineProperty(scroller, "scrollHeight", {
    configurable: true,
    value: 1000,
  });
  Object.defineProperty(scroller, "clientHeight", {
    configurable: true,
    value: 200,
  });
  scroller.scrollTop = 40;
  await act(async () =>
    scroller.dispatchEvent(new dom.window.Event("scroll", { bubbles: true })),
  );
  data.a = [
    {
      ...message(uid(12)),
      occurred_at: "2026-10-18T03:00:00Z",
      text: "Synthetic new reply",
    },
    message(),
  ];
  await poll(3000);
  assert.equal(scroller.scrollTop, 40);
  await click(button("查看 1 条新消息"));
  assert.equal(scroller.scrollTop, 1000);
  assert.equal(
    nearConversationBottom({
      scrollTop: 40,
      clientHeight: 200,
      scrollHeight: 1000,
    }),
    false,
  );
});

test("only current incoming revisions can be carried into manual order review", async () => {
  let created;
  const { data } = fixture();
  data.a.push({
    ...message(uid(13)),
    origin: "history",
    evidence: "snapshot",
    source_message_id: null,
    revision: null,
  });
  await mount({
    onCreate: (conversation, sources) => {
      created = { conversation, sources };
    },
  });
  await click(document.querySelector(".conversation-choice"));
  assert.equal(
    document.querySelectorAll(".conversation-message input[type=checkbox]")
      .length,
    1,
  );
  await click(
    document.querySelector(".conversation-message input[type=checkbox]"),
  );
  await click(button("从所选消息核对新建工单"));
  assert.deepEqual(created, {
    conversation: conversationA,
    sources: [{ message_id: uid(110), message_revision: 1 }],
  });
});

test("a permission rejection clears visible content and disables sending", async () => {
  const { data } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(
    document.querySelector(".conversation-composer textarea"),
    "Synthetic unsent private text",
  );
  data.denied = true;
  await poll(3000);
  assert.equal(document.querySelectorAll(".conversation-message").length, 0);
  assert.match(document.body.textContent, /会话请求未完成/);
  assert.equal(document.querySelector(".conversation-composer"), null);
});

test("old draft API remains honestly unavailable without removing linked order details or manual replies", async () => {
  fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(labelled("选择关联工单"), orderId);
  assert.ok(button("打开工单处理"));
  assert.match(
    document.querySelector(".conversation-business").textContent,
    /当前后端尚未提供此会话功能/,
  );
  assert.ok(document.querySelector(".conversation-composer textarea"));
});

test("adopting a valid existing model suggestion consumes once but never submits a send", async () => {
  const { calls } = fixture({ draftsAvailable: true });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(labelled("选择关联工单"), orderId);
  const review = [...document.querySelectorAll("button")].find((element) =>
    element.textContent.startsWith("核对建议回复"),
  );
  await click(review);
  await click(button("采用到输入框（不发送）"));
  assert.equal(
    document.querySelector(".conversation-composer textarea").value,
    draft.text,
  );
  const posts = calls.filter((call) => call.options.method === "POST");
  assert.equal(posts.length, 1);
  assert.match(posts[0].url, /\/consume$/);
  assert.equal(posts[0].options.headers["X-CSRF-Token"], "synthetic-csrf");
});

test("a stopped workspace makes no background message requests", async () => {
  const { calls } = fixture();
  await mount({ active: false });
  await poll(3000);
  await poll(15000);
  assert.equal(calls.length, 0);
});

test("editing a selected source requires a fresh selection rather than silently upgrading the revision", async () => {
  const { data } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await click(
    document.querySelector(".conversation-message input[type=checkbox]"),
  );
  assert.equal(button("从所选消息核对新建工单").disabled, false);
  data.a = [{ ...message(), revision: 2, text: "Synthetic corrected source" }];
  await poll(3000);
  assert.equal(
    document.querySelector(".conversation-message input[type=checkbox]")
      .checked,
    false,
  );
  assert.equal(button("从所选消息核对新建工单").disabled, true);
});

test("source navigation highlights once, does not steal focus on polls and warns when that revision changes", async () => {
  const { data } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(labelled("选择关联工单"), orderId);
  await click(button("定位客户原话"));
  const bubble = document.querySelector(".conversation-message");
  assert.equal(bubble.dataset.highlight, "true");
  assert.equal(bubble.dataset.scrolled, "true");
  delete bubble.dataset.scrolled;
  await poll(3000);
  assert.equal(bubble.dataset.scrolled, undefined);
  data.a = [{ ...message(), revision: 2, text: "Synthetic changed source" }];
  await poll(3000);
  assert.match(document.body.textContent, /原依据已修改或撤回/);
});

test("loading an earlier page preserves the visible reading position", async () => {
  fixture({
    override: (url) => {
      if (url.includes(chatA) && url.includes("timeline?"))
        return url.includes("cursor=older")
          ? Response.json({
              items: [
                {
                  ...message(uid(9)),
                  occurred_at: "2026-10-18T01:00:00Z",
                  text: "Synthetic earlier message",
                },
              ],
              next_cursor: null,
            })
          : Response.json({ items: [message()], next_cursor: "older" });
    },
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  const scroller = document.querySelector(".conversation-scroll");
  Object.defineProperty(scroller, "scrollHeight", {
    configurable: true,
    get: () => document.querySelectorAll(".conversation-message").length * 1000,
  });
  Object.defineProperty(scroller, "clientHeight", {
    configurable: true,
    value: 200,
  });
  scroller.scrollTop = 40;
  await act(async () =>
    scroller.dispatchEvent(new dom.window.Event("scroll", { bubbles: true })),
  );
  await click(button("加载更早消息"));
  assert.equal(document.querySelectorAll(".conversation-message").length, 2);
  assert.equal(scroller.scrollTop, 1040);
});

test("a transient status failure retains unsent text but prevents sending until status is checked", async () => {
  let unavailable = false;
  fixture({
    override: (url) =>
      unavailable && url.includes("/connectors?limit=50")
        ? Response.json({ detail: "Service unavailable" }, { status: 503 })
        : null,
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(
    document.querySelector(".conversation-composer textarea"),
    "Synthetic pending text",
  );
  unavailable = true;
  await poll(15000);
  await poll(3000);
  assert.equal(
    document.querySelector(".conversation-composer textarea").value,
    "Synthetic pending text",
  );
  assert.equal(
    document.querySelector(".conversation-composer fieldset").disabled,
    true,
  );
});

test("a mismatched AI consume response is uncertain and cannot replace the manual composer or repeat automatically", async () => {
  const { calls } = fixture({
    draftsAvailable: true,
    override: (url) =>
      url.includes("/consume")
        ? Response.json({
            data: {
              ...draft,
              conversation_id: conversationB,
              status: "consumed",
            },
          })
        : null,
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(
    document.querySelector(".conversation-composer textarea"),
    "Synthetic merchant text",
  );
  await change(labelled("选择关联工单"), orderId);
  await click(
    [...document.querySelectorAll("button")].find((element) =>
      element.textContent.startsWith("核对建议回复"),
    ),
  );
  await click(button("采用到输入框（不发送）"));
  assert.equal(
    document.querySelector(".conversation-composer textarea").value,
    "Synthetic merchant text",
  );
  assert.equal(button("采用到输入框（不发送）").disabled, true);
  await poll(3000);
  assert.equal(
    calls.filter((call) => call.options.method === "POST").length,
    1,
  );
});

test("an unresolved gateway request blocks consuming another AI suggestion without hiding the original recovery path", async () => {
  const { calls } = fixture({ draftsAvailable: true });
  localStorage.setItem(
    `gigmate-send-intent:${connection}:${chatA}:${uid(50)}`,
    "pending",
  );
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(labelled("选择关联工单"), orderId);
  const review = [...document.querySelectorAll("button")].find((element) =>
    element.textContent.startsWith("核对建议回复"),
  );
  assert.equal(review.disabled, true);
  assert.ok(document.querySelector(".conversation-composer"));
  assert.equal(
    calls.filter((call) => call.options.method === "POST").length,
    0,
  );
});

test("quoted replies stay scoped to the selected chat and do not dispatch any send", async () => {
  const { calls } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await click(button("引用回复"));
  const quote = labelled("引用回复（可选，先载入时间线）");
  assert.equal(quote.value, uid(10));
  await click(document.querySelectorAll(".conversation-choice")[1]);
  assert.equal(labelled("引用回复（可选，先载入时间线）").value, "");
  assert.equal(
    calls.filter((call) => call.options.method === "POST").length,
    0,
  );
});

test("401 ends all polling even when the host does not unmount the workspace", async () => {
  let denied = false,
    expired = 0;
  const { calls } = fixture({
    override: (url) =>
      denied && url.includes("timeline?")
        ? Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 })
        : null,
  });
  await mount({ onSessionExpired: () => expired++ });
  await click(document.querySelector(".conversation-choice"));
  denied = true;
  await poll(3000);
  assert.equal(expired, 1);
  assert.equal(timers.size, 0);
  const count = calls.length;
  await poll(3000);
  await poll(15000);
  assert.equal(calls.length, count);
  assert.equal(document.querySelectorAll(".conversation-message").length, 0);
  assert.ok(button("刷新会话"));
});

test("preview denial pauses every loop and explicit refresh can recover without a stuck running flag", async () => {
  let denied = false;
  const { calls, data } = fixture({
    override: (url) =>
      denied && url.includes(chatB) && url.includes("timeline?")
        ? Response.json(
            { error: { code: "CONVERSATION_NOT_ALLOWED" } },
            { status: 403 },
          )
        : null,
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  denied = true;
  await poll(15000);
  assert.equal(timers.size, 0);
  const count = calls.length;
  await poll(15000);
  assert.equal(calls.length, count);
  denied = false;
  await click(button("刷新会话"));
  assert.equal(document.querySelectorAll(".conversation-choice").length, 2);
  assert.ok(timers.size > 0);
  data.b = [
    {
      ...message(uid(11), chatB, conversationB),
      text: "Synthetic recovered preview",
    },
  ];
  await poll(15000);
  assert.match(
    document.querySelectorAll(".conversation-choice")[1].textContent,
    /Synthetic recovered preview/,
  );
});

test("hidden documents make no poll requests and resume only when visible", async () => {
  const { calls } = fixture();
  await mount();
  await click(document.querySelector(".conversation-choice"));
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: true,
  });
  const count = calls.length;
  await poll(3000);
  await poll(15000);
  assert.equal(calls.length, count);
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
  await poll(3000);
  assert.equal(calls.length, count + 1);
});

test("temporary connector failures back off exponentially up to sixty seconds without erasing unsent text", async () => {
  let now = original.dateNow(),
    failing = false,
    requests = 0;
  Date.now = () => now;
  fixture({
    override: (url) => {
      if (!url.includes("/connectors?")) return null;
      requests++;
      return failing ? Response.json({}, { status: 503 }) : null;
    },
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(
    document.querySelector(".conversation-composer textarea"),
    "Synthetic retained during backoff",
  );
  failing = true;
  await poll(15000);
  const failed = requests;
  now += 15000;
  await poll(15000);
  assert.equal(requests, failed);
  now += 15000;
  await poll(15000);
  assert.equal(requests, failed + 1);
  now += 59000;
  await poll(15000);
  assert.equal(requests, failed + 1);
  failing = false;
  now += 1000;
  await poll(15000);
  assert.equal(requests, failed + 2);
  assert.equal(
    document.querySelector(".conversation-composer textarea").value,
    "Synthetic retained during backoff",
  );
});

test("a ten-page source lookup is one-shot; fast polls read one page and periodic history checks apply old revocations", async () => {
  let now = original.dateNow(),
    revoked = false,
    requests = 0;
  Date.now = () => now;
  fixture({
    override: (url) => {
      if (!url.includes(chatA) || !url.includes("timeline?")) return null;
      requests++;
      const page = Number(
        new URL(url, "http://localhost").searchParams.get("cursor") ?? 0,
      );
      return Response.json({
        items: [
          {
            ...message(uid(200 + page)),
            source_message_id: page === 9 ? uid(110) : uid(1000 + page),
            occurred_at: `2026-10-18T02:${String(59 - page).padStart(2, "0")}:00Z`,
            revoked: page === 9 && revoked,
            text: page === 9 && revoked ? null : `Synthetic history ${page}`,
          },
        ],
        next_cursor: page < 9 ? String(page + 1) : null,
      });
    },
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  await change(
    document.querySelector(".conversation-business select"),
    orderId,
  );
  const before = requests;
  await click(button("查找原文并核对版本"));
  assert.equal(requests - before, 10);
  assert.equal(document.querySelectorAll(".conversation-message").length, 10);
  let last = requests;
  await poll(3000);
  assert.equal(requests - last, 1);
  last = requests;
  await poll(3000);
  assert.equal(requests - last, 1);
  assert.equal(document.querySelectorAll(".conversation-message").length, 10);
  revoked = true;
  now += 30000;
  last = requests;
  await poll(3000);
  assert.equal(requests - last, 10);
  assert.doesNotMatch(
    document.querySelector(".conversation-scroll").textContent,
    /Synthetic history 9/,
  );
  last = requests;
  await poll(3000);
  assert.equal(requests - last, 1);
});

for (const reject of [false, true])
  test(`unmount aborts adoption and ignores a late ${reject ? "failure" : "success"}`, async () => {
    let settle, signal;
    const busy = [],
      adopted = [];
    fixture({
      draftsAvailable: true,
      override: (url, options) => {
        if (!url.includes("/consume")) return null;
        signal = options.signal;
        return new Promise((resolve, fail) => {
          settle = reject ? fail : resolve;
        });
      },
    });
    root = createRoot(document.getElementById("root"));
    await act(async () =>
      root.render(
        createElement(ConversationBusiness, {
          csrf: "synthetic",
          conversation: conversationA,
          messages: [message()],
          enabled: true,
          busy: false,
          onBusyChange: (value) => busy.push(value),
          onAdopt: (text) => adopted.push(text),
          onLocate() {},
          onOpenOrder() {},
          onSessionExpired() {},
        }),
      ),
    );
    await change(
      document.querySelector(".conversation-business select"),
      orderId,
    );
    await click(button("刷新工单与建议"));
    await click(
      [...document.querySelectorAll("button")].find((node) =>
        node.textContent.startsWith("核对建议回复"),
      ),
    );
    await click(button("采用到输入框（不发送）"));
    assert.ok(signal && !signal.aborted);
    await act(async () => root.unmount());
    root = null;
    assert.equal(signal.aborted, true);
    assert.equal(timers.size, 0);
    const count = busy.length;
    await act(async () =>
      settle(
        reject
          ? new Error("Synthetic delayed failure")
          : Response.json({
              data: {
                ...draft,
                status: "consumed",
                consumed_at: "2026-10-18T03:00:00Z",
              },
            }),
      ),
    );
    assert.equal(
      busy.length,
      count,
      "late completion must not unlock a different page",
    );
    assert.deepEqual(
      adopted,
      [],
      "late text must not enter another conversation",
    );
    assert.equal(document.querySelector(".conversation-composer"), null);
  });

test("preview batches request at most the eight visible chats", async () => {
  const choices = Array.from({ length: 12 }, (_, i) => ({
    ...choice(uid(300 + i), uid(400 + i)),
    label: `Synthetic contact ${i}`,
  }));
  let previews = 0;
  fixture({
    override: (url) => {
      if (url.endsWith("/chats")) return Response.json({ data: choices });
      if (!url.includes("/timeline?")) return null;
      previews++;
      const selected = choices.find((item) => url.includes(item.id));
      return Response.json({
        items: [message(uid(500), selected.id, selected.conversation_id)],
        next_cursor: null,
      });
    },
  });
  await mount();
  assert.equal(previews, 8);
  assert.equal(document.querySelectorAll(".conversation-choice").length, 8);
  await poll(15000);
  assert.equal(previews, 16);
  await click(button("下一页"));
  assert.equal(previews, 20);
  assert.equal(document.querySelectorAll(".conversation-choice").length, 4);
});

test("a fast preview denial stops and clears immediately while another preview is still pending", async () => {
  let denying = false,
    settle;
  fixture({
    override: (url) => {
      if (!denying || !url.includes("/timeline?")) return null;
      if (url.includes(chatA)) return Response.json({}, { status: 401 });
      return new Promise((resolve) => {
        settle = resolve;
      });
    },
  });
  await mount();
  await click(document.querySelector(".conversation-choice"));
  denying = true;
  // Do not wait for the slow sibling; privacy must be cleared before it answers.
  await act(async () => {
    for (const { fn, delay } of [...timers.values()])
      if (delay === 15000) void fn();
  });
  assert.equal(timers.size, 0);
  assert.equal(document.querySelectorAll(".conversation-message").length, 0);
  await act(async () =>
    settle(
      Response.json({
        items: [message(uid(11), chatB, conversationB)],
        next_cursor: null,
      }),
    ),
  );
  assert.equal(document.querySelectorAll(".conversation-choice").length, 0);
  assert.equal(document.querySelectorAll(".conversation-message").length, 0);
});

for (const status of [408, 429])
  test(`HTTP ${status} is a transient read failure, not a privacy denial`, async () => {
    const api = conversationApi("synthetic", async () =>
      Response.json({}, { status }),
    );
    await assert.rejects(
      api.connectors(),
      (error) => error.code === "UNAVAILABLE",
    );
  });
