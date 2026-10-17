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
import { accountId, fixture } from "./approval-fixtures.mjs";
const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const directory = await mkdtemp(join(tmpdir(), "gigmate-d03-dom-"));
const require = createRequire(import.meta.url);
for (const name of [
  "ApprovalsWorkspace",
  "approvals-api",
  "approval-view",
  "environment",
  "read-cache",
  "useStableState",
  "workspace-api",
  "i18n",
  "locales",
  "work-order-view",
]) {
  const ext = name === "ApprovalsWorkspace" ? "tsx" : "ts";
  const source = await readFile(
    new URL(`./src/${name}.${ext}`, import.meta.url),
    "utf8",
  );
  const code = ts
    .transpileModule(source, {
      fileName: `${name}.${ext}`,
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
        jsx: ts.JsxEmit.ReactJSX,
      },
    })
    .outputText.replace(/"\.\/([\w-]+)(?:\.ts)?"/g, '"./$1.mjs"')
    .replace(/"(react(?:\/jsx-runtime)?)"/g, (_, name) =>
      JSON.stringify(pathToFileURL(require.resolve(name)).href),
    );
  await writeFile(join(directory, name + ".mjs"), code);
}
const { ApprovalsWorkspace } = await import(
  pathToFileURL(join(directory, "ApprovalsWorkspace.mjs"))
);
const { approvalsApi } = await import(
  pathToFileURL(join(directory, "approvals-api.mjs"))
);
let root;
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  document.getElementById("root").replaceChildren();
  sessionStorage.clear();
});
after(async () => {
  dom.window.close();
  for (const key of [
    "window",
    "document",
    "sessionStorage",
    "IS_REACT_ACT_ENVIRONMENT",
  ])
    delete globalThis[key];
  await rm(directory, { recursive: true });
});
function button(label) {
  const result = [...document.querySelectorAll("button")].find(
    (b) => b.textContent === label,
  );
  assert.ok(result, label);
  return result;
}
async function click(label) {
  await act(async () => button(label).click());
}
async function mount(f, extra = {}) {
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(ApprovalsWorkspace, {
        csrf: "csrf",
        accountId,
        onSessionExpired() {},
        onBusyChange() {},
        api: approvalsApi("csrf", accountId, f.fetcher, sessionStorage),
        ...extra,
      }),
    ),
  );
}
async function review() {
  await click("核对这份草稿");
  await act(async () =>
    document.querySelector('input[type="checkbox"]').click(),
  );
}
test("exact review and checkbox gate approval; approval stays unsent and filtering keeps selected history", async () => {
  const f = fixture();
  await mount(f);
  assert.ok(document.body.textContent.includes(f.data.actions[0].body));
  assert.equal(f.data.writes.length, 0);
  await click("核对这份草稿");
  assert.equal(button("批准这份草稿").disabled, true);
  await act(async () =>
    document.querySelector('input[type="checkbox"]').click(),
  );
  await click("批准这份草稿");
  assert.equal(f.data.writes.length, 1);
  assert.match(document.body.textContent, /已批准，尚未发送/);
  assert.match(document.body.textContent, /尚未提交发送/);
  assert.match(document.body.textContent, /不在筛选结果/);
});
test("refresh invalidates reviewed content; stale reads block every write and private context still permits local rejection", async () => {
  const f = fixture();
  await mount(f);
  await review();
  f.data.actions[0] = {
    ...f.data.actions[0],
    body: "新的完整正文",
    revision: 2,
    snapshot_hash: "sha256:" + "b".repeat(64),
  };
  await click("刷新审批");
  assert.equal(document.querySelector('input[type="checkbox"]'), null);
  assert.match(document.body.textContent, /重新核对/);
  f.data.offline = true;
  await click("刷新审批");
  assert.equal(button("核对这份草稿").disabled, true);
  assert.equal(f.data.writes.length, 0);
  f.data.offline = false;
  f.data.denied = true;
  await click("刷新审批");
  await review();
  assert.equal(button("批准这份草稿").disabled, true);
  const input = document.querySelector("textarea");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(input, "需要另行确认");
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    input.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  });
  assert.equal(button("拒绝草稿").disabled, false);
  await click("拒绝草稿");
  assert.equal(f.data.writes[0].operation, "reject");
  assert.equal(f.data.actions[0].closed_reason, "rejected");
});
test("lost response survives remount, never auto-retries, then explicitly uses the original intent", async () => {
  const f = fixture();
  await mount(f);
  await review();
  f.data.drop = true;
  await click("批准这份草稿");
  assert.match(document.body.textContent, /原请求等待核对/);
  assert.equal(f.data.writes.length, 1);
  await act(async () => root.unmount());
  root = null;
  await mount(f);
  await click("刷新审批");
  assert.equal(f.data.writes.length, 1);
  await review();
  await click("核对后重试原请求");
  assert.equal(f.data.writes.length, 2);
  assert.equal(
    f.data.writes[0].options.headers["Idempotency-Key"],
    f.data.writes[1].options.headers["Idempotency-Key"],
  );
  assert.doesNotMatch(document.body.textContent, /原请求等待核对/);
});
test("double approval and navigation are blocked while a write is in flight", async () => {
  const f = fixture();
  const busy = [];
  await mount(f, { onBusyChange: (b) => busy.push(b) });
  await review();
  let resolve;
  f.data.delayed = new Promise((r) => (resolve = r));
  await act(async () => {
    button("批准这份草稿").click();
    button("批准这份草稿").click();
  });
  assert.equal(f.data.writes.length, 1);
  assert.equal(button("刷新审批").disabled, true);
  assert.equal(busy.at(-1), true);
  await act(async () => resolve());
  assert.equal(busy.at(-1), false);
});
test("an unauthorized read arriving after unmount cannot expire a newer login", async () => {
  const f = fixture();
  let reject;
  let expired = 0;
  const blocked = new Promise((_, no) => (reject = no));
  const api = approvalsApi("csrf", accountId, f.fetcher, sessionStorage);
  api.load = () => blocked;
  await mount(f, { api, onSessionExpired: () => expired++ });
  await act(async () => root.unmount());
  root = null;
  await act(async () =>
    reject(Object.assign(new Error("old login"), { code: "UNAUTHENTICATED" })),
  );
  assert.equal(expired, 0);
});

test("rendering with a denied storage getter shows readable guidance, still loads drafts and sends no mutations", async () => {
  const f = fixture();
  const previous = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );
  const oldFetch = globalThis.fetch;
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    get() {
      throw new DOMException("Synthetic denied storage", "SecurityError");
    },
  });
  globalThis.fetch = f.fetcher;
  try {
    root = createRoot(document.getElementById("root"));
    await act(async () =>
      root.render(
        createElement(ApprovalsWorkspace, {
          csrf: "csrf",
          accountId,
          onSessionExpired() {},
          onBusyChange() {},
        }),
      ),
    );
    assert.match(document.body.textContent, /浏览器不允许保存原请求/);
    assert.ok(document.body.textContent.includes(f.data.actions[0].body));
    await review();
    assert.equal(button("批准这份草稿").disabled, true);
    await click("刷新审批");
    assert.equal(f.data.writes.length, 0);
  } finally {
    Object.defineProperty(globalThis, "sessionStorage", previous);
    globalThis.fetch = oldFetch;
  }
});

test("unchanged refresh preserves reviewed consent, focused checkbox and enabled action without a loading flash", async () => {
  const f = fixture();
  await mount(f);
  await review();
  const checkbox = document.querySelector('input[type="checkbox"]');
  checkbox.focus();
  await click("刷新审批");
  assert.equal(document.querySelector('input[type="checkbox"]'), checkbox);
  assert.equal(checkbox.checked, true);
  assert.equal(document.activeElement, checkbox);
  assert.equal(button("批准这份草稿").disabled, false);
  assert.doesNotMatch(document.body.textContent, /正在读取审批数据/);
  assert.equal(f.data.writes.length, 0);
});
