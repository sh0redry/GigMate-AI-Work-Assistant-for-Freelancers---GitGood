import assert from "node:assert/strict";
import { test, after, afterEach } from "node:test";
import { readFile, writeFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import ts from "typescript";
import { JSDOM } from "jsdom";
import { act, createElement } from "react";
const require = createRequire(import.meta.url),
  dir = await mkdtemp(join(tmpdir(), "gm-manual-field-"));
const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
for (const name of [
  "ManualFieldEditor",
  "LoopCommand",
  "business-loop-api",
  "features",
  "workspace-api",
  "work-order-view",
  "useStableState",
  "i18n",
  "locales",
  "environment",
  "read-cache",
]) {
  const extension = ["ManualFieldEditor", "LoopCommand"].includes(name)
    ? "tsx"
    : "ts";
  const input = await readFile(
    new URL(`./src/${name}.${extension}`, import.meta.url),
    "utf8",
  );
  const output = ts
    .transpileModule(input, {
      fileName: `${name}.${extension}`,
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
  await writeFile(join(dir, `${name}.mjs`), output);
}
const { ManualFieldEditor } = await import(
  pathToFileURL(join(dir, "ManualFieldEditor.mjs"))
);
const account = "00000000-0000-4000-8000-000000000001",
  orderId = "00000000-0000-4000-8000-000000000003",
  chat = "00000000-0000-4000-8000-000000000002",
  messageId = "00000000-0000-4000-8000-000000000005";
const order = {
  id: orderId,
  account_id: account,
  summary: "合成毕业照",
  version: 1,
  status: "pending_confirmation",
  conversation_ids: [chat],
  fields: { address: { value: null, status: "missing", sources: [] } },
};
const data = {
  orders: [order],
  messages: [
    {
      id: messageId,
      conversation_id: chat,
      revision: 1,
      direction: "incoming",
      text: "地址是香港大学地铁站 A 出口",
      occurred_at: "2030-10-20T00:00:00Z",
      revoked: false,
    },
  ],
  contexts: { [chat]: 2 },
  contextVersion: 2,
  changes: [],
  tasks: [],
  calendar: [],
  selected: orderId,
};
let root,
  writes = [],
  done = 0;
const oldFetch = globalThis.fetch;
async function mount(snapshot = data) {
  root ??= createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(
      createElement(ManualFieldEditor, {
        csrf: "synthetic",
        accountId: account,
        features: { business_loop_reviewed: true, manual_field_editing: true },
        order,
        data: snapshot,
        disabled: false,
        onDone: () => {
          done++;
        },
        onBusy: () => {},
      }),
    ),
  );
}
function button(text) {
  return [...document.querySelectorAll("button")].find(
    (button) => button.textContent === text,
  );
}
async function click(text) {
  await act(async () => button(text).click());
}
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  writes = [];
  done = 0;
  sessionStorage.clear();
  document.getElementById("root").replaceChildren();
  globalThis.fetch = oldFetch;
});
after(async () => {
  dom.window.close();
  await rm(dir, { recursive: true });
  delete globalThis.window;
  delete globalThis.document;
  delete globalThis.sessionStorage;
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
});
async function fill() {
  await click("手动补充／修改字段");
  const textarea = document.querySelector("textarea");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(textarea, "香港大学地铁站 A 出口");
    textarea.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
  const source = document.querySelectorAll("select")[1];
  await act(async () => {
    source.value = `${messageId}:1`;
    source.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  });
}
test("a missed address can be saved after explicit source review without sending or claiming customer confirmation", async () => {
  globalThis.fetch = async (url, options) => {
    writes.push({ url, body: JSON.parse(options.body) });
    return new Response(JSON.stringify({ data: { ...order, version: 2 } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  await mount();
  await fill();
  assert.equal(writes.length, 0);
  assert.equal(button("核对修改").disabled, false);
  await click("核对修改");
  assert.equal(button("确认保存").disabled, true);
  const consent = [...document.querySelectorAll('input[type="checkbox"]')].at(
    -1,
  );
  await act(async () => consent.click());
  await click("确认保存");
  assert.equal(writes.length, 1);
  assert.match(writes[0].url, /\/manual-field$/);
  assert.equal(writes[0].body.value, "香港大学地铁站 A 出口");
  assert.equal(writes[0].body.customer_confirmed, false);
  assert.deepEqual(writes[0].body.sources, [
    { message_id: messageId, message_revision: 1 },
  ]);
  assert.equal(done, 1);
});
test("missing/revoked sources cannot be selected; new context invalidates an open review", async () => {
  globalThis.fetch = async () => {
    throw Error("must not submit");
  };
  await mount({ ...data, messages: [{ ...data.messages[0], revoked: true }] });
  await click("手动补充／修改字段");
  assert.equal(document.querySelectorAll("select")[1].options.length, 1);
  assert.equal(button("核对修改").disabled, true);
  await mount();
  await click("手动补充／修改字段");
  await fill();
  await click("核对修改");
  assert.ok(button("确认保存"));
  await mount({ ...data, contexts: { [chat]: 3 }, contextVersion: 3 });
  assert.equal(button("确认保存"), undefined);
  assert.equal(writes.length, 0);
});

test("changing a reviewed field value clears customer-confirmation attribution", async () => {
  await mount();
  await fill();
  const confirmed = document.querySelector('input[type="checkbox"]');
  await act(async () => confirmed.click());
  assert.equal(confirmed.checked, true);
  const textarea = document.querySelector("textarea");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(textarea, "另一项待核对的合成地址");
    textarea.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
  assert.equal(confirmed.checked, false);
  assert.equal(writes.length, 0);
});
