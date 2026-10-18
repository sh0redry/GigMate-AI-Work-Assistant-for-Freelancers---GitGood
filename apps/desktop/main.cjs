const {
  app,
  BrowserWindow,
  ipcMain,
  safeStorage,
  shell,
  Menu,
  dialog,
} = require("electron");
const fs = require("node:fs/promises"),
  path = require("node:path"),
  http = require("node:http"),
  crypto = require("node:crypto");
const { pathToFileURL } = require("node:url");
const runtime = require("./runtime.cjs");
const {
  needsSetup,
  validateProfile,
  aiReady,
  updateAI,
} = require("./settings.cjs");
const { CSP, listenLoopback } = require("./web-security.cjs");
app.setName("GigMate");
app.enableSandbox();
let setupWindow,
  businessWindow,
  services,
  managedDocker,
  server,
  origin,
  backend,
  profile,
  record,
  cleanupReview,
  maintenanceBusy = false,
  starting = false,
  quitting = false,
  needsReset = true;
const resources = app.isPackaged
  ? process.resourcesPath
  : path.join(__dirname, "build");
const dataRoot = () => app.getPath("userData"),
  recordPath = () => path.join(dataRoot(), "profile.json");
const localSetup = pathToFileURL(path.join(__dirname, "setup.html")).href;
const errors = {
  DOCKER_INSTALL_REQUIRED:
    "需要先安装 Docker Desktop。点“安装 Docker”，完成系统安装后再点启动。",
  REMOTE_DOCKER_NOT_ALLOWED:
    "请将 Docker 切换为本机 Docker Desktop，不能清理或连接远程 Docker。",
  DOCKER_LINUX_CONTAINERS_REQUIRED:
    "请把 Docker Desktop 切换到 Linux containers。",
  LOCAL_SERVICE_COMMAND_FAILED:
    "本地服务未能启动。请确认 Docker 正在运行、磁盘空间充足并且网络可下载镜像，然后重试。",
  SECRET_STORE_UNAVAILABLE: "系统钥匙串暂不可用，请解锁系统登录钥匙串后重试。",
  INVALID_SETTINGS:
    "请设置账号和至少 12 位密码；填写 API Key 后还需明确同意启用 AI。",
  CLEANUP_PLAN_CHANGED: "资源已变化或清单已过期，请重新查看清理清单。",
  CLEANUP_SELECTION_INVALID: "请重新选择清单内的资源并输入删除确认文字。",
};
function progress(message) {
  if (setupWindow && !setupWindow.isDestroyed())
    setupWindow.webContents.send("gigmate:progress", message);
}
async function fingerprint() {
  const install = JSON.parse(
    await fs.readFile(path.join(resources, "install.json"), "utf8"),
  );
  return install.buildId; // Provenance only; never a reset/deletion trigger.
}
async function readRecord() {
  try {
    return JSON.parse(await fs.readFile(recordPath(), "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw new Error("PRIVATE_PROFILE_UNREADABLE");
  }
}
function secretStore() {
  if (!safeStorage.isEncryptionAvailable())
    throw new Error("SECRET_STORE_UNAVAILABLE");
}
function decode(record) {
  secretStore();
  return validateProfile(
    JSON.parse(safeStorage.decryptString(Buffer.from(record.secret, "base64"))),
  );
}
async function saveProfile() {
  secretStore();
  await runtime.writePrivate(
    recordPath(),
    JSON.stringify({
      fingerprint: await fingerprint(),
      secret: safeStorage
        .encryptString(JSON.stringify(profile))
        .toString("base64"),
    }),
  );
}
function trustedSetup(event) {
  if (
    !setupWindow ||
    event.sender !== setupWindow.webContents ||
    event.senderFrame?.url !== localSetup
  )
    throw new Error("UNTRUSTED_SETUP_REQUEST");
}
async function showSetup() {
  if (setupWindow && !setupWindow.isDestroyed()) {
    setupWindow.show();
    return;
  }
  setupWindow = new BrowserWindow({
    width: 760,
    height: 790,
    minWidth: 560,
    minHeight: 600,
    title: "GigMate · 一键启动",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  setupWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  setupWindow.webContents.on("will-navigate", (event, url) => {
    if (url !== localSetup) event.preventDefault();
  });
  await setupWindow.loadFile(path.join(__dirname, "setup.html"));
}
async function startDocker() {
  if (process.platform === "darwin") {
    for (const application of [
      "/Applications/Docker.app",
      path.join(app.getPath("home"), "Applications/Docker.app"),
    ]) {
      try {
        await fs.access(application);
        await runtime.run("/usr/bin/open", ["-a", application], {
          timeout: 10000,
        });
        return;
      } catch {}
    }
  } else if (process.platform === "win32") {
    for (const file of [
      path.join(
        process.env.ProgramFiles || "C:\\Program Files",
        "Docker/Docker/Docker Desktop.exe",
      ),
      path.join(
        process.env.LOCALAPPDATA || app.getPath("home"),
        "Programs/DockerDesktop/Docker Desktop.exe",
      ),
    ]) {
      try {
        await fs.access(file);
        await shell.openPath(file);
        return;
      } catch {}
    }
  }
}
async function readyDocker() {
  let docker;
  try {
    docker = await runtime.findDocker();
  } catch {
    throw new Error("DOCKER_INSTALL_REQUIRED");
  }
  try {
    await runtime.verifyLocalDocker(docker);
    return docker;
  } catch (error) {
    if (
      error.message.startsWith("REMOTE_") ||
      error.message === "DOCKER_LINUX_CONTAINERS_REQUIRED"
    )
      throw error;
    progress("正在打开 Docker Desktop；首次请完成系统权限和许可确认…");
    await startDocker();
  }
  const until = Date.now() + 180000;
  while (Date.now() < until) {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    try {
      await runtime.verifyLocalDocker(docker);
      return docker;
    } catch {}
  }
  throw new Error("LOCAL_SERVICE_COMMAND_FAILED");
}
function contentType(file) {
  return (
    {
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".css": "text/css; charset=utf-8",
      ".svg": "image/svg+xml",
      ".png": "image/png",
      ".webmanifest": "application/manifest+json",
      ".json": "application/json",
    }[path.extname(file)] || "application/octet-stream"
  );
}
async function serveWeb() {
  if (server) return;
  server = http.createServer(async (req, res) => {
    try {
      if (
        !req.url.startsWith("/") ||
        req.url.startsWith("//") ||
        req.headers.host !== new URL(origin).host
      ) {
        res.writeHead(403).end();
        return;
      }
      const pathname = new URL(req.url, origin).pathname;
      if (pathname.startsWith("/api/") || pathname === "/health") {
        if (!backend) {
          res.writeHead(503).end();
          return;
        }
        const target = new URL(req.url, backend);
        const proxy = http.request(
          target,
          {
            method: req.method,
            headers: { ...req.headers, host: req.headers.host },
          },
          (response) => {
            res.writeHead(response.statusCode, response.headers);
            response.pipe(res);
          },
        );
        proxy.on("error", () => {
          if (!res.headersSent) res.writeHead(502);
          res.end();
        });
        req.pipe(proxy);
        return;
      }
      const web = path.join(resources, "web"),
        relative = decodeURIComponent(pathname).replace(/^\/+/, ""),
        requested = path.resolve(web, relative || "index.html");
      if (!requested.startsWith(web + path.sep)) {
        res.writeHead(403).end();
        return;
      }
      let file = requested;
      try {
        if (!(await fs.stat(file)).isFile())
          file = path.join(web, "index.html");
      } catch {
        file = path.join(web, "index.html");
      }
      const bytes = await fs.readFile(file);
      res.writeHead(200, {
        "Content-Type": contentType(file),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Content-Security-Policy": CSP,
      });
      res.end(bytes);
    } catch {
      res.writeHead(500).end();
    }
  });
  try {
    profile.webPort = await listenLoopback(server, profile.webPort || 0);
  } catch (error) {
    server.close();
    server = undefined;
    throw error;
  }
  origin = `http://127.0.0.1:${profile.webPort}`;
  await saveProfile();
}
async function openBusiness() {
  if (businessWindow && !businessWindow.isDestroyed()) {
    businessWindow.show();
    businessWindow.focus();
    await businessWindow.loadURL(origin);
    return;
  }
  businessWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 760,
    minHeight: 600,
    title: "GigMate",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: "persist:gigmate-" + profile.id,
    },
  });
  businessWindow.on("closed", () => {
    businessWindow = null;
    if (!quitting) app.quit();
  });
  businessWindow.webContents.on("will-navigate", (event, url) => {
    if (new URL(url).origin !== origin) event.preventDefault();
  });
  businessWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  await businessWindow.loadURL(origin);
  setupWindow?.hide();
}
async function start(options = {}) {
  if (maintenanceBusy) throw new Error("MAINTENANCE_BUSY");
  if (starting) return;
  starting = true;
  try {
    progress("正在检查 Docker 和本机环境…");
    const docker = await readyDocker();
    managedDocker = docker;
    if (needsReset) {
      if (
        typeof options.username !== "string" ||
        !options.username.trim() ||
        options.username.length > 64 ||
        typeof options.password !== "string" ||
        options.password.length < 12 ||
        options.password.length > 128 ||
        typeof options.modelKey !== "string" ||
        options.modelKey.length > 512 ||
        /[\r\n\0]/.test(options.modelKey)
      )
        throw new Error("INVALID_SETTINGS");
      profile = runtime.newProfile({
        ...options,
        username: options.username.trim(),
      });
      await saveProfile();
      needsReset = false;
    } else {
      if (!profile) profile = decode(record);
      profile = updateAI({ ...profile }, options);
      await saveProfile();
    }
    backend = undefined; // Old services must not be routed during reconfiguration.
    if (profile.aiEnabled && !aiReady(profile))
      progress("AI 配置不完整或价格无效，本次关闭 AI，继续启动手动工作台。");
    await serveWeb();
    services = await runtime.startRuntime({
      docker,
      profile,
      resources,
      privateDir: path.join(dataRoot(), "runtime"),
      origin,
      progress,
    });
    backend = services.backend;
    delete profile.password;
    await saveProfile();
    progress(
      aiReady(profile)
        ? "启动完成。AI 已配置；请登录并授权聊天。"
        : "启动完成。AI 未启用（需 Key、明确授权及有效美元价格），可手动处理业务。",
    );
    await openBusiness();
  } catch (error) {
    progress(
      errors[error.message] ||
        "启动未完成，请检查 Docker、网络或系统钥匙串后重试。",
    );
    throw new Error(errors[error.message] || "STARTUP_FAILED");
  } finally {
    starting = false;
  }
}
async function maintenance(operation) {
  if (starting || maintenanceBusy) throw new Error("MAINTENANCE_BUSY");
  maintenanceBusy = true;
  try {
    return await operation();
  } finally {
    maintenanceBusy = false;
  }
}
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const win =
      businessWindow && !businessWindow.isDestroyed()
        ? businessWindow
        : setupWindow;
    win?.show();
    win?.focus();
  });
  app
    .whenReady()
    .then(async () => {
      record = await readRecord();
      needsReset = needsSetup(record);
      if (!needsReset) profile = decode(record);
      ipcMain.handle("gigmate:status", (event) => {
        trustedSetup(event);
        return {
          needsReset,
          username: profile?.username || "merchant",
          keyConfigured: !!profile?.modelKey,
          aiEnabled: aiReady(profile || {}),
          inputPrice: profile?.inputPrice || "",
          outputPrice: profile?.outputPrice || "",
          budget: profile?.budget || "0.10",
        };
      });
      ipcMain.handle("gigmate:start", (event, options) => {
        trustedSetup(event);
        return start(options);
      });
      ipcMain.handle("gigmate:cleanup-plan", async (event, includeLegacy) => {
        trustedSetup(event);
        return maintenance(async () => {
          const docker = await readyDocker();
          const entries = await runtime.planCleanup(
            docker,
            profile ? runtime.projectFor(profile) : "",
            { includeLegacy: includeLegacy === true },
          );
          cleanupReview = {
            token: crypto.randomUUID(),
            expires: Date.now() + 120000,
            entries,
          };
          return cleanupReview;
        });
      });
      ipcMain.handle("gigmate:cleanup", async (event, options) => {
        trustedSetup(event);
        return maintenance(async () => {
          const review = cleanupReview;
          cleanupReview = undefined; // Single-use, including uncertain failures.
          if (
            starting ||
            !review ||
            review.expires < Date.now() ||
            options?.token !== review.token ||
            options.confirmation !== "删除所选数据"
          )
            throw new Error("CLEANUP_PLAN_CHANGED");
          const docker = await readyDocker();
          await runtime.executeCleanup(
            docker,
            review.entries,
            options.selected,
            { expiresAt: review.expires },
          );
          return true;
        });
      });
      ipcMain.handle("gigmate:install-docker", async (event) => {
        trustedSetup(event);
        const url =
          process.platform === "darwin"
            ? `https://desktop.docker.com/mac/main/${process.arch === "arm64" ? "arm64" : "amd64"}/Docker.dmg`
            : "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe";
        await shell.openExternal(url);
        return true;
      });
      Menu.setApplicationMenu(
        Menu.buildFromTemplate([
          {
            label: "GigMate",
            submenu: [
              { label: "启动／连接设置", click: () => void showSetup() },
              {
                label: "在浏览器打开",
                click: () => origin && void shell.openExternal(origin),
              },
              { type: "separator" },
              { role: "quit" },
            ],
          },
          { role: "editMenu" },
          { role: "viewMenu" },
        ]),
      );
      await showSetup();
      if (!needsReset) void start().catch(() => {});
    })
    .catch(() => {
      dialog.showErrorBox(
        "GigMate",
        "本地配置无法读取或解密。数据未被删除。请保留配置与 Docker 卷，恢复原系统钥匙串或联系维护者；不要清空或重建。",
      );
      app.quit();
    });
  app.on("activate", () => {
    if (businessWindow && !businessWindow.isDestroyed()) businessWindow.show();
    else void showSetup();
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    void runtime
      .cancelActiveCommands()
      .then(() =>
        services
          ? services.stop()
          : managedDocker && profile
            ? runtime.stopRuntime(
                managedDocker,
                profile,
                path.join(dataRoot(), "runtime"),
              )
            : undefined,
      )
      .catch(() => {})
      .finally(() => {
        server?.close();
        app.exit();
      });
  });
}
