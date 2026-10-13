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
import { developmentEnvironments } from "./vite.config.ts";
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
  "ApprovalsWorkspace",
  "WorkOrderWorkspace",
  "ConnectionWorkspace",
  "ChatChoices",
  "WahaMessages",
  "WahaMedia",
];
for (const name of [
  ...components,
  "approvals-api",
  "approval-view",
  "replay-store",
  "environment",
  "workspace-api",
  "work-order-view",
  "connection-api",
  "waha-live-api",
  "waha-sync-api",
  "waha-media-api",
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
    if (url.endsWith("/auth/logout"))
      return Response.json({ data: { ok: true } });
    if (
      options.method === "GET" &&
      ["/work-orders?", "/tasks?", "/calendar-events?", "/connectors?"].some(
        (path) => url.includes(path),
      )
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
  assert.match(document.body.textContent, /自动建单和手动新建功能尚未开放/);
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

function developmentConfig() {
  globalThis.__GIGMATE_ENVIRONMENTS__ = {
    defaultEnvironment: "isolated",
    publicTestAccount: {
      username: "merchant",
      password: "demo-only-change-me",
    },
    targets: {
      real: "http://127.0.0.1:18702",
      isolated: "http://127.0.0.1:18012",
    },
  };
}
test("current live startup configuration shows real labels, connector navigation and bound requests", async () => {
  globalThis.__GIGMATE_ENVIRONMENTS__ = developmentEnvironments({
    GIGMATE_REAL_API_URL: "http://127.0.0.1:18712",
    GIGMATE_DEFAULT_ENV: "real",
  });
  const calls = fixture();
  await mount();
  assert.match(document.body.textContent, /真实连接（本机开发）/);
  assert.match(document.body.textContent, /127.0.0.1:18712/);
  await login();
  await act(async () => button("WhatsApp 连接").click());
  assert.ok(calls.some((call) => call.url.includes("/connectors")));
  assert.ok(
    calls.every((call) => call.url.startsWith("/environments/real/api/v1/")),
  );
});
test("synthetic connector self-check keeps connector navigation but labels fictional data and offers no real-backend switch", async () => {
  globalThis.__GIGMATE_ENVIRONMENTS__ = developmentEnvironments({
    GIGMATE_REAL_API_URL: "http://127.0.0.1:18802",
    GIGMATE_ISOLATED_API_URL: "http://127.0.0.1:18804",
    GIGMATE_DEFAULT_ENV: "real",
    GIGMATE_SYNTHETIC_PROVIDER: "1",
  });
  // Even a manually entered isolated URL cannot select a maintainer backend.
  dom.reconfigure({ url: "http://localhost/environments/isolated/" });
  const calls = fixture();
  await mount();
  assert.match(document.body.textContent, /合成连接自检（虚构数据）/);
  assert.match(document.body.textContent, /不可扫码/);
  assert.match(document.body.textContent, /127.0.0.1:18802/);
  assert.doesNotMatch(document.body.textContent, /真实连接（本机开发）/);
  assert.equal(document.querySelector(".environment-switch"), null);
  await login();
  await act(async () => button("WhatsApp 连接").click());
  assert.ok(calls.some((call) => call.url.includes("/connectors")));
  assert.ok(
    calls.every((call) => call.url.startsWith("/environments/real/api/v1/")),
  );
});
test("development login names the isolated environment, shows public test credentials and routes all business reads there", async () => {
  developmentConfig();
  const calls = fixture();
  await mount();
  assert.match(document.body.textContent, /隔离测试（虚构数据）/);
  assert.match(document.body.textContent, /merchant/);
  assert.match(document.body.textContent, /demo-only-change-me/);
  assert.equal(
    document.querySelector(".environment-switch").getAttribute("href"),
    "/environments/real/",
  );
  await login();
  assert.ok(
    calls.every((c) => c.url.startsWith("/environments/isolated/api/v1/")),
  );
  assert.match(document.body.textContent, /隔离测试（虚构数据）/);
  assert.equal(button("WhatsApp 连接"), undefined);
  assert.deepEqual(
    [...document.querySelector("nav").querySelectorAll("button")].map(
      (b) => b.textContent,
    ),
    ["业务工作台", "回复审批"],
  );
  assert.equal(
    calls.some((c) => c.url.includes("/connectors")),
    false,
  );
});
test("opening the other environment starts signed out with empty inputs and keeps request metadata separate", async () => {
  developmentConfig();
  const calls = fixture();
  await mount();
  await login();
  sessionStorage.setItem(
    "gigmate-control-attempt:isolated:pending",
    "synthetic-uncertain",
  );
  await act(async () => root.unmount());
  dom.reconfigure({ url: "http://localhost/environments/real/" });
  await mount();
  assert.equal(document.querySelector("nav"), null);
  assert.equal(document.querySelector('input[type="password"]').value, "");
  assert.equal(
    document.querySelector('input[autocomplete="username"]').value,
    "",
  );
  assert.match(document.body.textContent, /真实连接（本机开发）/);
  assert.match(document.body.textContent, /尚未正式上线/);
  assert.equal(
    document.querySelector(".environment-switch").getAttribute("href"),
    "/environments/isolated/",
  );
  const before = calls.length;
  await login();
  assert.ok(
    calls
      .slice(before)
      .every((c) => c.url.startsWith("/environments/real/api/v1/")),
  );
  await act(async () => button("WhatsApp 连接").click());
  assert.ok(calls.at(-1).url.startsWith("/environments/real/api/v1/"));
  await act(async () => button("退出").click());
  assert.equal(
    sessionStorage.getItem("gigmate-control-attempt:isolated:pending"),
    "synthetic-uncertain",
  );
});
test("environment navigation is blocked during an unresolved login", async () => {
  developmentConfig();
  let finish;
  globalThis.fetch = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  await mount();
  await login();
  const link = document.querySelector(".environment-switch");
  assert.equal(link.getAttribute("aria-disabled"), "true");
  const click = new window.MouseEvent("click", {
    bubbles: true,
    cancelable: true,
  });
  await act(async () => link.dispatchEvent(click));
  assert.equal(click.defaultPrevented, true);
  await act(async () =>
    finish(
      Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
    ),
  );
  assert.equal(link.getAttribute("aria-disabled"), "false");
});
