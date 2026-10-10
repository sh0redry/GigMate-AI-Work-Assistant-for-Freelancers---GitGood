import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import ts from "typescript";
import { JSDOM } from "jsdom";
import { act, createElement } from "react";

// A local DOM, real workspace/component/hooks and real HTTP adapter; no browser,
// provider, credentials or real contacts. API state survives workspace remounts.
const dom = new JSDOM("<main id='root'></main>", { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const originalFetch = globalThis.fetch;
const directory = await mkdtemp(join(tmpdir(), "gigmate-workspace-dom-"));
const require = createRequire(import.meta.url);
const modules = [
  "ConnectionWorkspace",
  "ChatChoices",
  "WahaMessages",
  "WahaMedia",
  "connection-api",
  "waha-live-api",
  "waha-sync-api",
  "waha-media-api",
  "connection-state",
  "chat-choices",
];
for (const name of modules) {
  const extension = [
    "ConnectionWorkspace",
    "ChatChoices",
    "WahaMessages",
    "WahaMedia",
  ].includes(name)
    ? "tsx"
    : "ts";
  const source = await readFile(
    new URL(`./src/${name}.${extension}`, import.meta.url),
    "utf8",
  );
  const code = ts
    .transpileModule(source, {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
        jsx: ts.JsxEmit.ReactJSX,
      },
    })
    .outputText.replace(/import "\.\/connection\.css";\s*/g, "")
    .replace(/"\.\/([\w-]+)"/g, '"./$1.mjs"')
    .replace(/"(react(?:\/jsx-runtime)?)"/g, (_, specifier) =>
      JSON.stringify(pathToFileURL(require.resolve(specifier)).href),
    );
  await writeFile(join(directory, name + ".mjs"), code);
}
const { ConnectionWorkspace } = await import(
  pathToFileURL(join(directory, "ConnectionWorkspace.mjs"))
);
let root;
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  document.getElementById("root").replaceChildren();
  sessionStorage.clear();
  globalThis.fetch = originalFetch;
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
  if (
    !resolve(directory).startsWith(resolve(tmpdir()) + sep) ||
    !basename(directory).startsWith("gigmate-workspace-dom-")
  )
    throw new Error("Invalid cleanup target");
  await rm(directory, { recursive: true });
});
const id = "00000000-0000-4000-8000-000000000070";
const base = `/api/v1/connectors/${id}`;
const rows = Array.from({ length: 107 }, (_, i) => ({
  id: `00000000-0000-4000-8000-${String(i + 1000).padStart(12, "0")}`,
  label: `Synthetic ${i + 1}`,
  selected: false,
  expires_at: new Date(Date.now() + 600000).toISOString(),
  kind: i % 3 === 2 ? "group" : "direct",
}));
function server({ initial = [], overrides = {} } = {}) {
  let version = 7,
    loaded = initial.length ? 100 : 0;
  const selected = new Set(initial.map((i) => rows[i].id));
  const catalogRows = rows.map((row, i) => ({ ...row, ...overrides[i] }));
  const discoveries = [],
    writes = [],
    requests = [];
  const setup = () => ({
    connection_id: id,
    control_version: version,
    enabled: true,
    available: true,
    provider_state: "WORKING",
    provider_observed_at: new Date().toISOString(),
    provider_sample_stale: false,
    active_operation_id: null,
    last_operation_id: null,
  });
  const catalog = () =>
    catalogRows.slice(0, loaded).map((c) => ({
      ...c,
      selected: selected.has(c.id),
      expires_at: selected.has(c.id) ? null : c.expires_at,
    }));
  const json = (data) =>
    new Response(JSON.stringify({ data }), {
      headers: { "Content-Type": "application/json" },
    });
  const page = (items) =>
    new Response(JSON.stringify({ items, next_cursor: null }), {
      headers: { "Content-Type": "application/json" },
    });
  globalThis.fetch = async (url, init = {}) => {
    requests.push([url, init.method ?? "GET"]);
    if (url === "/api/v1/connectors?limit=100")
      return page([
        {
          id,
          enabled: true,
          state: "WORKING",
          stale: false,
          live_connected: true,
          pipeline_ready: true,
          review_required: false,
          unresolved_issues: 0,
          observed_at: new Date().toISOString(),
        },
      ]);
    if (url === base + "/setup") return json(setup());
    if (
      url.endsWith("/recovery-issues?limit=100") ||
      url.endsWith("/sync-jobs?limit=100") ||
      url.endsWith("/source-gaps?limit=100")
    )
      return page([]);
    if (url === base + "/operations") {
      const command = JSON.parse(init.body);
      assert.equal(init.headers["X-CSRF-Token"], "synthetic-csrf");
      assert.equal(command.action, "discover");
      assert.equal(command.expected_version, version);
      discoveries.push(command);
      loaded = command.offset ? rows.length : 100;
      return json({
        id: "00000000-0000-4000-8000-000000000071",
        connection_id: id,
        action: "discover",
        state: "succeeded",
        control_version: version,
        error_code: null,
        next_offset: loaded === 100 ? 100 : null,
      });
    }
    if (url === base + "/chats" && init.method === "PUT") {
      const command = JSON.parse(init.body);
      assert.equal(init.headers["X-CSRF-Token"], "synthetic-csrf");
      assert.equal(command.expected_version, version);
      assert.equal(command.consent, true);
      assert.ok(
        command.selected_ids.every((value) => rows.some((c) => c.id === value)),
      );
      writes.push(command);
      selected.clear();
      command.selected_ids.forEach((value) => selected.add(value));
      version++;
      return json(setup());
    }
    if (url === base + "/chats") return json(catalog());
    throw new Error(`Unexpected synthetic request: ${init.method} ${url}`);
  };
  return { discoveries, writes, requests, selected };
}
async function mount() {
  root = createRoot(document.getElementById("root"));
  await act(async () =>
    root.render(createElement(ConnectionWorkspace, { csrf: "synthetic-csrf" })),
  );
}
function button(text) {
  const node = [...document.querySelectorAll("button")].find(
    (x) => x.textContent.trim() === text,
  );
  assert.ok(node, `Missing button ${text}`);
  return node;
}
async function click(text) {
  const node = button(text);
  assert.equal(node.disabled, false, `${text} must be enabled`);
  await act(async () => node.click());
}
async function choose(label, value) {
  const node = [...document.querySelectorAll(".chat-choices label")]
    .find((x) => x.textContent.trim().startsWith(label))
    ?.querySelector("select");
  assert.ok(node, `Missing select ${label}`);
  await act(async () => {
    node.value = value;
    node.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  });
}
function checkbox(i) {
  return document.querySelector(
    `input[aria-label="Synthetic ${i + 1} · ${rows[i].kind === "group" ? "群聊" : "个人聊天"} · 会话 ${i + 1}"]`,
  );
}
async function tick(i) {
  const node = checkbox(i);
  assert.ok(node, `Choice ${i + 1} must be on this page`);
  assert.equal(node.disabled, false);
  await act(async () => node.click());
}
const summary = () => document.querySelector(".chat-page-summary").textContent;

test("workspace saves hidden selections across pages and filters, then reloads and remounts both", async () => {
  const api = server();
  await mount();
  await click("发现最近会话");
  assert.equal(document.querySelectorAll(".chat-choice").length, 8);
  await tick(0);
  await click("下一页");
  assert.equal(checkbox(0), null);
  await tick(8);
  await choose("会话类型", "group");
  assert.equal(checkbox(0), null);
  assert.equal(checkbox(8).checked, true);
  await choose("每页", "16");
  assert.equal(
    api.discoveries.length,
    1,
    "paging/filtering must not discover on the server",
  );
  assert.match(summary(), /已勾选 2 个/);
  await click("保存会话授权");
  assert.deepEqual(api.writes[0].selected_ids, [rows[0].id, rows[8].id]);
  await click("重新载入会话");
  await choose("会话类型", "all");
  assert.equal(checkbox(0).checked, true);
  assert.equal(checkbox(8).checked, true);
  assert.equal(
    button("保存会话授权").disabled,
    true,
    "successful reread must clear dirty state",
  );
  await act(async () => root.unmount());
  root = null;
  await mount();
  await click("载入会话与授权");
  assert.equal(checkbox(0).checked, true);
  await click("下一页");
  assert.equal(checkbox(8).checked, true);
  await click("撤销全部授权");
  assert.deepEqual(
    api.writes[1].selected_ids,
    [],
    "global withdrawal includes hidden first-page authorization",
  );
  assert.equal(api.selected.size, 0);
  assert.equal(api.discoveries.length, 1);
});

test("display paging never discovers automatically; explicit load-more retains selection and cursor", async () => {
  const api = server();
  await mount();
  await click("发现最近会话");
  const requestsBeforeBrowsing = api.requests.length;
  await tick(0);
  await click("下一页");
  await choose("会话类型", "group");
  await choose("每页", "24");
  assert.equal(api.discoveries.length, 1);
  assert.equal(button("载入更多会话（每批最多 100 个）").disabled, false);
  assert.equal(
    api.requests.length,
    requestsBeforeBrowsing,
    "display changes must not make any extra API call",
  );
  await click("载入更多会话（每批最多 100 个）");
  assert.deepEqual(
    api.discoveries.map((x) => x.offset ?? 0),
    [0, 100],
  );
  await choose("会话类型", "all");
  assert.match(summary(), /已载入 107 个会话/);
  assert.match(summary(), /已勾选 1 个/);
  assert.equal(checkbox(0).checked, true);
  assert.equal(document.querySelectorAll(".chat-choice").length, 24);
  assert.equal(
    [...document.querySelectorAll("button")].some((x) =>
      x.textContent.includes("载入更多会话"),
    ),
    false,
  );
  await click("下一页");
  assert.equal(api.discoveries.length, 2);
});

test("missing names keep real choice IDs; authorized fallbacks remain withdrawable and phone labels explicit", async () => {
  const api = server({
    initial: [0],
    overrides: {
      0: { label: "Authorized conversation" },
      1: { label: "" },
      2: { label: "+1 202 555 0101", kind: "direct" },
    },
  });
  await mount();
  await click("载入会话与授权");
  const authorized = document.querySelector(
    'input[aria-label="已授权个人聊天 · 个人聊天 · 会话 1"]',
  );
  const unnamed = () =>
    document.querySelector(
      'input[aria-label="未命名个人聊天 · 个人聊天 · 会话 2"]',
    );
  assert.equal(authorized.checked, true);
  assert.equal(
    authorized.disabled,
    false,
    "missing nickname must not prevent withdrawal",
  );
  assert.ok(unnamed());
  const phone = document.querySelector(
    'input[aria-label="+1 202 555 0101 · 个人聊天 · 会话 3"]',
  );
  assert.match(phone.closest("label").textContent, /未提供昵称/);
  await act(async () => authorized.click());
  await click("保存会话授权");
  assert.deepEqual(api.writes[0].selected_ids, []);
  await act(async () => unnamed().click());
  await click("保存会话授权");
  assert.deepEqual(
    api.writes[1].selected_ids,
    [rows[1].id],
    "name fallback must retain the real nonempty canonical ID",
  );
  assert.equal(button("保存会话授权").disabled, true);
});
