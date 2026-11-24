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

// Bounded AI assistant panel (ADR 0011, batch 4). Synthetic data only; the
// fake fetch answers like the backend, nothing reaches a model or WhatsApp.
const require = createRequire(import.meta.url);
const directory = await mkdtemp(join(tmpdir(), "gigmate-assistant-"));
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
const { AssistantPanel } = await load("AssistantPanel");
const { setLocale } = await load("i18n");
const dom = new JSDOM('<div id="root"></div>', {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.localStorage = dom.window.localStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const originalFetch = globalThis.fetch;
let root;

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = undefined;
  document.getElementById("root").replaceChildren();
  globalThis.fetch = originalFetch;
  setLocale("zh");
});
after(async () => rm(directory, { recursive: true, force: true }));

const uid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const CHAT = uid(2),
  ORDER = uid(3),
  MESSAGE = uid(5);

function turnView(id, overrides = {}) {
  return {
    id,
    thread_id: uid(70),
    status: "completed",
    question: "下周有空吗",
    intent: "availability",
    context: {
      conversation_id: null,
      expected_context_version: null,
      work_order_id: null,
      expected_work_order_version: null,
      selected_sources: [],
    },
    answer: {
      kind: "slots",
      text: "可安排的时段：\n- 12/01（周二）13:30–19:00",
      slots: [],
      work_order_ids: [],
      draft_id: null,
      unverified_claims: [],
      citations: [
        {
          kind: "free_slots",
          message: null,
          work_order_id: null,
          work_order_version: null,
        },
      ],
      execution_authority: false,
    },
    error_code: null,
    engine: "rules",
    created_at: "2026-11-25T02:00:00Z",
    completed_at: "2026-11-25T02:00:01Z",
    scrubbed_at: null,
    ...overrides,
  };
}

function draftView(overrides = {}) {
  return {
    id: uid(80),
    turn_id: uid(60),
    conversation_id: CHAT,
    work_order_id: null,
    base_work_order_version: null,
    context_version: 7,
    kind: "reply_draft",
    text: "您好，周二下午可以。谢谢！",
    sources: [{ message_id: MESSAGE, message_revision: 1 }],
    unverified_claims: [],
    status: "proposed",
    revoke_reason: null,
    expires_at: "2026-11-26T02:00:00Z",
    created_at: "2026-11-25T02:00:00Z",
    consumed_at: null,
    revoked_at: null,
    scrubbed_at: null,
    execution_authority: false,
    ...overrides,
  };
}

/** A fake backend. `turns` maps id -> list of views returned on successive reads. */
function backend({
  caps = {
    enabled: true,
    engine: "rules",
    vendor: null,
    sends_customer_text: false,
    daily_turns: 200,
  },
  submitted = (n) => turnView(uid(60 + n), { status: "queued", answer: null }),
  reads = {},
  draft = draftView(),
  consume,
  failPostOnce = false,
  status,
} = {}) {
  const calls = [];
  let posts = 0;
  let postFailed = false;
  const read = {};
  globalThis.fetch = async (url, options = {}) => {
    url = String(url);
    calls.push({ url, options });
    if (status) return Response.json({ error: { code: "X" } }, { status });
    if (url.endsWith("/assistant/capabilities"))
      return Response.json({ data: caps });
    if (url.includes("/conversations/"))
      return Response.json({ data: { id: CHAT, context_version: 7 } });
    if (url.endsWith("/assistant/turns") && options.method === "POST") {
      if (failPostOnce && !postFailed) {
        postFailed = true;
        throw new TypeError("network down");
      }
      return Response.json({ data: submitted(posts++) }, { status: 202 });
    }
    const turn = url.match(/\/assistant\/turns\/([\w-]+)$/);
    if (turn) {
      const list = reads[turn[1]] ?? [
        turnView(turn[1], { thread_id: uid(70) }),
      ];
      const index = Math.min(read[turn[1]] ?? 0, list.length - 1);
      read[turn[1]] = index + 1;
      return Response.json({ data: list[index] });
    }
    if (url.endsWith("/consume")) return consume(url, calls);
    if (url.includes("/assistant/drafts/"))
      return Response.json({ data: draft });
    return Response.json(
      { error: { code: "UNEXPECTED_TEST_ROUTE" } },
      { status: 404 },
    );
  };
  return calls;
}

async function mount(props = {}) {
  const events = { adopted: [], opened: [], expired: 0 };
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(AssistantPanel, {
        csrf: "synthetic-csrf",
        pollMs: 1,
        onSessionExpired: () => events.expired++,
        onOpenOrder: (id) => events.opened.push(id),
        ...props,
      }),
    ),
  );
  await settle();
  return events;
}

async function settle(rounds = 8) {
  for (let i = 0; i < rounds; i++)
    await act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
}

const button = (text) =>
  [...document.querySelectorAll("button")].find(
    (element) => element.textContent.trim() === text,
  );
const panelText = () => document.querySelector(".assistant-panel").textContent;

async function type(text) {
  const area = document.querySelector(".assistant-panel textarea");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(area, text);
    area.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}

async function click(element) {
  assert.ok(element, "control exists");
  await act(async () => element.click());
  await settle();
}

const posts = (calls) =>
  calls.filter(
    (c) => c.url.endsWith("/assistant/turns") && c.options.method === "POST",
  );

test("discloses the offline engine and a model vendor before anything is asked", async () => {
  backend();
  await mount();
  assert.match(panelText(), /只用本地规则回答，不会把聊天内容发给模型供应商/);
  await act(async () => root.unmount());
  backend({
    caps: {
      enabled: true,
      engine: "model",
      vendor: "SyntheticVendor",
      sends_customer_text: true,
      daily_turns: 200,
    },
  });
  await mount();
  assert.match(panelText(), /发送给 SyntheticVendor 处理/);
  await act(async () => root.unmount());
  backend({
    caps: {
      enabled: false,
      engine: "rules",
      vendor: null,
      sends_customer_text: false,
      daily_turns: 200,
    },
  });
  await mount();
  assert.match(panelText(), /助手已关闭/);
  assert.equal(
    document.querySelector(".assistant-panel textarea").disabled,
    true,
  );
});

test("a Today-page question is posted once with a key, polled to completion and threaded", async () => {
  const calls = backend({
    reads: {
      [uid(60)]: [
        turnView(uid(60), { status: "running", answer: null }),
        turnView(uid(60)),
      ],
    },
  });
  await mount();
  await type("下周有空吗");
  await click(button("提问"));
  const [first] = posts(calls);
  assert.ok(first.options.headers["Idempotency-Key"]);
  assert.equal(first.options.headers["X-CSRF-Token"], "synthetic-csrf");
  assert.deepEqual(JSON.parse(first.options.body), {
    question: "下周有空吗",
    thread_id: null,
  });
  assert.match(panelText(), /12\/01（周二）13:30–19:00/);
  assert.match(panelText(), /依据：你的工作时间和已确认预约/);
  await type("我有哪些订单");
  await click(button("提问"));
  assert.equal(JSON.parse(posts(calls)[1].options.body).thread_id, uid(70));
  assert.equal(document.querySelectorAll(".assistant-turn").length, 2);
});

test("a chat question carries the fresh context version, selected order and sources", async () => {
  const calls = backend();
  await mount({
    conversation: CHAT,
    order: { id: ORDER, version: 3 },
    sources: [{ message_id: MESSAGE, message_revision: 1 }],
  });
  assert.match(panelText(), /将基于当前聊天和所选工单回答/);
  assert.match(panelText(), /已选 1 条客户消息作为回复依据/);
  await type("帮我回一下，说可以");
  await click(button("提问"));
  assert.deepEqual(JSON.parse(posts(calls)[0].options.body).context, {
    conversation_id: CHAT,
    expected_context_version: 7,
    work_order_id: ORDER,
    expected_work_order_version: 3,
    selected_sources: [{ message_id: MESSAGE, message_revision: 1 }],
  });
});

test("an unknown submission is checked with the same key and body, never asked twice", async () => {
  const calls = backend({ failPostOnce: true });
  await mount({ conversation: CHAT });
  await type("下周有空吗");
  await click(button("提问"));
  assert.match(panelText(), /不会重复提问/);
  assert.equal(
    document.querySelector(".assistant-panel textarea").disabled,
    true,
  );
  assert.equal(button("提问").disabled, true);
  await click(button("核对上次提问"));
  const [lost, checked] = posts(calls);
  assert.equal(
    lost.options.headers["Idempotency-Key"],
    checked.options.headers["Idempotency-Key"],
  );
  assert.equal(lost.options.body, checked.options.body);
  assert.equal(button("核对上次提问"), undefined);
  assert.equal(document.querySelectorAll(".assistant-turn").length, 1);
});

test("a draft is put in the composer once and never consumed twice", async () => {
  let consumes = 0;
  const calls = backend({
    reads: {
      [uid(60)]: [
        turnView(uid(60), {
          intent: "reply_draft",
          answer: {
            ...turnView(uid(60)).answer,
            kind: "draft",
            text: "已准备好草稿：\n您好，周二下午可以。谢谢！",
            draft_id: uid(80),
            citations: [
              {
                kind: "message",
                message: { message_id: MESSAGE, message_revision: 1 },
                work_order_id: null,
                work_order_version: null,
              },
            ],
          },
        }),
      ],
    },
    consume: () => {
      consumes++;
      return Response.json({
        data: draftView({
          status: "consumed",
          consumed_at: "2026-11-25T02:01:00Z",
        }),
      });
    },
  });
  const events = await mount({
    conversation: CHAT,
    adoptEnabled: true,
    onAdopt: (text) => events.adopted.push(text),
  });
  await type("帮我回一下，说周二下午可以");
  await click(button("提问"));
  assert.match(panelText(), /依据：1 条客户消息/);
  await click(button("放入输入框（不发送）"));
  assert.deepEqual(events.adopted, ["您好，周二下午可以。谢谢！"]);
  assert.equal(consumes, 1);
  assert.equal(button("放入输入框（不发送）"), undefined);
  assert.match(panelText(), /已放入输入框，请核对后再发送/);
  assert.ok(!calls.some((c) => /send|approve|actions/.test(c.url)));
});

test("a draft already used elsewhere offers no adopt button", async () => {
  let consumes = 0;
  backend({
    reads: {
      [uid(60)]: [
        turnView(uid(60), {
          intent: "reply_draft",
          answer: {
            ...turnView(uid(60)).answer,
            kind: "draft",
            text: "草稿",
            draft_id: uid(80),
            citations: [],
          },
        }),
      ],
    },
    draft: draftView({ status: "consumed" }),
    consume: () => {
      consumes++;
      throw new TypeError("network down");
    },
  });
  const events = await mount({
    conversation: CHAT,
    adoptEnabled: true,
    onAdopt: (text) => events.adopted.push(text),
  });
  await type("帮我回一下，说可以");
  await click(button("提问"));
  // The draft read after completion reports it was consumed elsewhere.
  assert.equal(button("放入输入框（不发送）"), undefined);
});

test("revoked and expired drafts explain why and cannot be adopted", async () => {
  for (const [draft, text] of [
    [
      draftView({ status: "revoked", revoke_reason: "context_changed" }),
      /聊天有新消息，草稿已失效/,
    ],
    [draftView({ status: "expired" }), /草稿已过期/],
  ]) {
    backend({
      draft,
      reads: {
        [uid(60)]: [
          turnView(uid(60), {
            answer: {
              ...turnView(uid(60)).answer,
              kind: "draft",
              text: "草稿",
              draft_id: uid(80),
            },
          }),
        ],
      },
    });
    await mount({ conversation: CHAT, adoptEnabled: true, onAdopt: () => {} });
    await type("帮我回一下，说可以");
    await click(button("提问"));
    assert.match(panelText(), text);
    assert.equal(button("放入输入框（不发送）"), undefined);
    await act(async () => root.unmount());
    root = undefined;
    document.getElementById("root").replaceChildren();
  }
});

test("unknown consume outcome offers a read-only check instead of a retry", async () => {
  let consumes = 0;
  let draftReads = 0;
  backend({
    reads: {
      [uid(60)]: [
        turnView(uid(60), {
          answer: {
            ...turnView(uid(60)).answer,
            kind: "draft",
            text: "草稿",
            draft_id: uid(80),
          },
        }),
      ],
    },
    consume: () => {
      consumes++;
      throw new TypeError("network down");
    },
  });
  const plain = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (String(url).endsWith(`/assistant/drafts/${uid(80)}`)) {
      draftReads++;
      return Response.json({
        data: draftView(draftReads > 1 ? { status: "consumed" } : {}),
      });
    }
    return plain(url, options);
  };
  const events = await mount({
    conversation: CHAT,
    adoptEnabled: true,
    onAdopt: (text) => events.adopted.push(text),
  });
  await type("帮我回一下，说可以");
  await click(button("提问"));
  await click(button("放入输入框（不发送）"));
  assert.equal(consumes, 1);
  assert.deepEqual(events.adopted, []);
  assert.equal(button("放入输入框（不发送）"), undefined);
  await click(button("核对草稿状态"));
  assert.equal(consumes, 1);
  assert.deepEqual(events.adopted, ["您好，周二下午可以。谢谢！"]);
});

test("superseded, unknown and failed turns say so without a draft", async () => {
  backend({
    submitted: (n) =>
      [
        turnView(uid(61), {
          status: "superseded",
          answer: null,
          error_code: "ASSISTANT_CONTEXT_STALE",
        }),
        turnView(uid(62), {
          status: "unknown",
          answer: null,
          error_code: "ASSISTANT_RESULT_UNKNOWN",
        }),
        turnView(uid(63), {
          status: "failed",
          answer: null,
          error_code: "ASSISTANT_PLAN_INVALID",
        }),
      ][n],
  });
  await mount();
  for (const q of ["一", "二", "三"]) {
    await type(q);
    await click(button("提问"));
  }
  const text = panelText();
  assert.match(text, /这次回答已作废/);
  assert.match(text, /不会自动重试/);
  assert.match(text, /这次没能回答（ASSISTANT_PLAN_INVALID）/);
});

test("order links open the order; answers are shown as text, not translated", async () => {
  backend({
    reads: {
      [uid(60)]: [
        turnView(uid(60), {
          intent: "order_status",
          answer: {
            ...turnView(uid(60)).answer,
            kind: "orders",
            text: "<b>合成工单</b>",
            work_order_ids: [ORDER],
            citations: [],
          },
        }),
      ],
    },
  });
  const events = await mount();
  setLocale("en");
  await settle();
  await type("my orders");
  await click(button("Ask"));
  assert.ok(
    document
      .querySelector(".assistant-answer")
      .textContent.includes("<b>合成工单</b>"),
  );
  assert.equal(document.querySelector(".assistant-answer b"), null);
  await click(button("Open related order 1"));
  assert.deepEqual(events.opened, [ORDER]);
});

test("an expired session reports once and asks nothing", async () => {
  const calls = backend({ status: 401 });
  const events = await mount();
  assert.equal(events.expired, 1);
  assert.equal(posts(calls).length, 0);
});

test("unmounting stops polling", async () => {
  const calls = backend({
    reads: {
      [uid(60)]: [turnView(uid(60), { status: "running", answer: null })],
    },
  });
  await mount();
  await type("下周有空吗");
  await act(async () => button("提问").click());
  await settle(2);
  await act(async () => root.unmount());
  root = undefined;
  const before = calls.length;
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.equal(calls.length, before);
});
