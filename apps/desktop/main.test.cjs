// Run the actual main process against in-memory Electron/filesystem/Docker seams.
const test = require("node:test"),
  assert = require("node:assert/strict");
const fs = require("node:fs"),
  vm = require("node:vm"),
  path = require("node:path");
const { EventEmitter } = require("node:events");
const runtime = require("./runtime.cjs");
async function boot({ corrupt = false, missing = false, cleanupEntries } = {}) {
  const calls = [],
    handlers = new Map(),
    events = new Map();
  const windows = [];
  let clock = Date.now();
  const original = runtime.newProfile({
    username: "synthetic",
    password: "synthetic-password",
  });
  delete original.password;
  let record = {
    fingerprint: "old-build-and-executable-birthtime",
    secret: Buffer.from(JSON.stringify(original)).toString("base64"),
  };
  const fakeFS = {
    readFile: async (file) => {
      if (file.endsWith("profile.json")) {
        if (missing)
          throw Object.assign(new Error("missing"), { code: "ENOENT" });
        return JSON.stringify(record);
      }
      if (file.endsWith("install.json"))
        return JSON.stringify({ buildId: "new-build" });
      throw new Error("Unexpected read");
    },
    // A legacy reinstall marker must no longer cause filesystem access/reset.
    access: async () => {
      throw new Error("Unexpected access/reset");
    },
    rm: async () => {
      throw new Error("Unexpected filesystem deletion");
    },
  };
  class Window extends EventEmitter {
    constructor() {
      super();
      windows.push(this);
      this.webContents = { send() {}, on() {}, setWindowOpenHandler() {} };
    }
    async loadFile() {}
    async loadURL() {
      calls.push("open-business");
    }
    isDestroyed() {
      return false;
    }
    show() {}
    hide() {}
    focus() {}
  }
  const app = {
    isPackaged: false,
    setName() {},
    enableSandbox() {},
    requestSingleInstanceLock: () => true,
    getPath: (name) => "/synthetic/" + name,
    whenReady: () => Promise.resolve(),
    on: (name, callback) => events.set(name, callback),
    quit: () => calls.push("quit"),
    exit() {},
  };
  const electron = {
    app,
    BrowserWindow: Window,
    ipcMain: { handle: (name, callback) => handlers.set(name, callback) },
    safeStorage: {
      isEncryptionAvailable: () => true,
      encryptString: (text) => Buffer.from(text),
      decryptString: (buffer) => {
        if (corrupt) throw new Error("locked keychain");
        return buffer.toString();
      },
    },
    Menu: { setApplicationMenu() {}, buildFromTemplate: () => [] },
    shell: {},
    dialog: { showErrorBox: () => calls.push("recovery-error") },
  };
  const fakeRuntime = {
    ...runtime,
    findDocker: async () => "fake-docker",
    verifyLocalDocker: async () => {},
    writePrivate: async (file, content) => {
      if (file.endsWith("profile.json")) record = JSON.parse(content);
    },
    startRuntime: async ({ profile }) => {
      calls.push({
        kind: "start",
        id: profile.id,
        dbPassword: profile.dbPassword,
      });
      return { backend: "http://127.0.0.1:27881", stop: async () => {} };
    },
    planCleanup: async () => {
      if (cleanupEntries) return cleanupEntries;
      throw new Error("Unexpected automatic cleanup");
    },
    executeCleanup: async () => {
      if (cleanupEntries) {
        calls.push("explicit-cleanup");
        return;
      }
      throw new Error("Unexpected automatic deletion");
    },
  };
  const fakeHttp = {
    createServer: () => {
      const server = new EventEmitter();
      server.listen = () => queueMicrotask(() => server.emit("listening"));
      server.address = () => ({ port: 27880 });
      server.close = () => {};
      return server;
    },
  };
  const sandbox = {
    Buffer,
    URL,
    process,
    Date: { now: () => clock },
    console,
    setTimeout,
    clearTimeout,
    __dirname,
    require: (name) =>
      name === "electron"
        ? electron
        : name === "node:fs/promises"
          ? fakeFS
          : name === "node:http"
            ? fakeHttp
            : name === "./runtime.cjs"
              ? fakeRuntime
              : require(name),
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "main.cjs"), "utf8"),
    sandbox,
  );
  for (let i = 0; i < 20; i++)
    await new Promise((resolve) => setImmediate(resolve));
  return {
    calls,
    record,
    original,
    handlers,
    advance: (ms) => {
      clock += ms;
    },
    event: {
      sender: windows[0]?.webContents,
      senderFrame: {
        url: require("node:url").pathToFileURL(
          path.join(__dirname, "setup.html"),
        ).href,
      },
    },
  };
}

test("actual main reuses credentials on a changed build without reset or legacy deletion", async () => {
  const { calls, record, original } = await boot();
  assert.ok(calls.includes("open-business"));
  const started = calls.find((call) => call.kind === "start");
  assert.equal(started.id, original.id);
  assert.equal(started.dbPassword, original.dbPassword);
  assert.equal(record.fingerprint, "new-build");
  const saved = JSON.parse(Buffer.from(record.secret, "base64").toString());
  assert.equal(saved.connectionId, original.connectionId);
  assert.equal(saved.password, undefined);
});
test("unreadable OS-protected profile fails closed without provisioning or deletion", async () => {
  const { calls } = await boot({ corrupt: true });
  assert.deepEqual(calls, ["recovery-error", "quit"]);
});
test("first install waits for account setup and never starts cleanup", async () => {
  const { calls, handlers } = await boot({ missing: true });
  assert.deepEqual(calls, []);
  assert.ok(handlers.has("gigmate:start"));
  assert.ok(handlers.has("gigmate:cleanup-plan"));
});

test("actual cleanup IPC requires trusted setup, exact confirmation, unexpired single-use review", async () => {
  const { handlers, event, calls, advance } = await boot({
    cleanupEntries: [{ kind: "volume", id: "synthetic-old-volume" }],
  });
  const plan = handlers.get("gigmate:cleanup-plan"),
    remove = handlers.get("gigmate:cleanup");
  await assert.rejects(
    plan(
      { sender: {}, senderFrame: { url: "https://untrusted.invalid" } },
      true,
    ),
    /UNTRUSTED_SETUP_REQUEST/,
  );
  const first = await plan(event, false);
  advance(120001);
  await assert.rejects(
    remove(event, {
      token: first.token,
      selected: ["volume:synthetic-old-volume"],
      confirmation: "删除所选数据",
    }),
    /CLEANUP_PLAN_CHANGED/,
  );
  const second = await plan(event, false);
  await assert.rejects(
    remove(event, { token: second.token, confirmation: "wrong" }),
    /CLEANUP_PLAN_CHANGED/,
  );
  assert.ok(!calls.includes("explicit-cleanup"));
  const third = await plan(event, false);
  const options = {
    token: third.token,
    selected: ["volume:synthetic-old-volume"],
    confirmation: "删除所选数据",
  };
  assert.equal(await remove(event, options), true);
  await assert.rejects(remove(event, options), /CLEANUP_PLAN_CHANGED/);
  assert.equal(calls.filter((call) => call === "explicit-cleanup").length, 1);
});
