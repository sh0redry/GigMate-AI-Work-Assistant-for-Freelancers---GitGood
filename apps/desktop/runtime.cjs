const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawn } = require("node:child_process");
const LEGACY_PROJECTS = new Set([
  "gigmate-waha-a02",
  "gigmate-waha-team",
  "gigmate-waha-recovery",
]);
const OWNER = "org.gitgood.gigmate.desktop";
function localDockerHost(host) {
  return (
    !host || host.startsWith("unix:///") || host.startsWith("npipe:////./pipe/")
  );
}
function run(binary, args, { input, timeout = 1800000 } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, {
      shell: false,
      windowsHide: true,
      env: {
        ...process.env,
        PATH:
          (path.isAbsolute(binary)
            ? path.dirname(binary) + path.delimiter
            : "") + (process.env.PATH || ""),
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "",
      size = 0,
      finished = false;
    const fail = () => {
      if (!finished) {
        finished = true;
        reject(new Error("LOCAL_SERVICE_COMMAND_FAILED"));
      }
    };
    const timer = setTimeout(() => {
      child.kill();
      fail();
    }, timeout);
    child.on("error", () => {
      clearTimeout(timer);
      fail();
    });
    child.stdout.on("data", (chunk) => {
      size += chunk.length;
      if (size <= 4 * 1024 * 1024) stdout += chunk.toString();
    });
    // Never return Docker/pip stderr: it can include private configuration.
    child.stderr.resume();
    child.on("close", (code) => {
      clearTimeout(timer);
      if (finished) return;
      finished = true;
      code === 0
        ? resolve(stdout)
        : reject(new Error("LOCAL_SERVICE_COMMAND_FAILED"));
    });
    child.stdin.on("error", () => {});
    child.stdin.end(input);
  });
}
async function findDocker(
  platform = process.platform,
  home = require("node:os").homedir(),
) {
  const candidates =
    platform === "darwin"
      ? [
          "/Applications/Docker.app/Contents/Resources/bin/docker",
          path.join(
            home,
            "Applications/Docker.app/Contents/Resources/bin/docker",
          ),
          "/usr/local/bin/docker",
          "docker",
        ]
      : platform === "win32"
        ? [
            path.join(
              process.env.ProgramFiles || "C:\\Program Files",
              "Docker/Docker/resources/bin/docker.exe",
            ),
            path.join(
              process.env.LOCALAPPDATA || home,
              "Programs/DockerDesktop/resources/bin/docker.exe",
            ),
            "docker.exe",
          ]
        : ["docker"];
  for (const bin of candidates) {
    try {
      await run(bin, ["--version"], { timeout: 10000 });
      return bin;
    } catch {}
  }
  throw new Error("DOCKER_INSTALL_REQUIRED");
}
async function verifyLocalDocker(docker) {
  if (!localDockerHost(process.env.DOCKER_HOST))
    throw new Error("REMOTE_DOCKER_NOT_ALLOWED");
  const host = (
    await run(
      docker,
      ["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
      { timeout: 15000 },
    )
  ).trim();
  if (!localDockerHost(host)) throw new Error("REMOTE_DOCKER_NOT_ALLOWED");
  await run(docker, ["info", "--format", "{{.OSType}}"], {
    timeout: 15000,
  }).then((value) => {
    if (value.trim() !== "linux")
      throw new Error("DOCKER_LINUX_CONTAINERS_REQUIRED");
  });
  await run(docker, ["compose", "version"], { timeout: 15000 });
}
async function writePrivate(file, content) {
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  await fs.writeFile(file, content, { mode: 0o600 });
}
function newProfile(options) {
  return {
    schema: 1,
    id: crypto.randomUUID(),
    username: options.username,
    password: options.password,
    modelKey: options.modelKey || "",
    model: "deepseek-chat",
    dbPassword: crypto.randomBytes(24).toString("hex"),
    wahaKey: crypto.randomBytes(32).toString("hex"),
    webhookSecret: crypto.randomBytes(32).toString("hex"),
    connectionId: crypto.randomUUID(),
  };
}
function projectFor(profile) {
  if (!/^[a-f0-9-]{36}$/.test(profile.id))
    throw new Error("INVALID_LOCAL_PROFILE");
  return "gigmate-desktop-" + profile.id.slice(0, 8);
}
function composeDocument(profile, resources, origin, arch = process.arch) {
  const owner = { [OWNER]: "true" },
    image = "gigmate-local-backend:0.3.0";
  const environment = {
    DATABASE_URL: `postgresql+psycopg://gigmate:${profile.dbPassword}@db:5432/gigmate`,
    APP_MODE: "product",
    COOKIE_SECURE: "false",
    TRUSTED_ORIGINS: origin,
    WAHA_CONNECTOR_CONFIG: "/run/desktop-config/ingress.json",
    WAHA_CONTROL_CONFIG: "/run/desktop-config/config.json",
    WAHA_CONTROL_INTERNAL: "true",
    WAHA_SEND_ENABLED: "true",
    WAHA_MEDIA_ENABLED: "true",
    WAHA_MEDIA_ROOT: "/run/waha-media",
    GIGMATE_WORKSPACE_TIMEZONE: "Asia/Hong_Kong",
    GIGMATE_EXTRACTION_PROVIDER: profile.modelKey ? "reviewed_llm" : "disabled",
    GIGMATE_LLM_PROVIDER: "deepseek",
    GIGMATE_LLM_MODEL: "deepseek-chat",
    GIGMATE_LLM_ENDPOINT: "https://api.deepseek.com",
    GIGMATE_LLM_ALLOW_LIVE_ORIGIN: "1",
    GIGMATE_LLM_LIVE: "1",
    GIGMATE_LLM_API_KEY_FILE: "/run/desktop-config/model.key",
    GIGMATE_LLM_COST_BUDGET_USD: "0.10",
  };
  const backend = {
    image,
    build: { context: path.join(resources, "runtime") },
    environment,
    labels: owner,
    volumes: ["private-config:/run/desktop-config:ro", "media:/run/waha-media"],
    restart: "no",
  };
  return {
    name: projectFor(profile),
    services: {
      db: {
        image: "postgres:17.9",
        environment: {
          POSTGRES_USER: "gigmate",
          POSTGRES_PASSWORD: profile.dbPassword,
          POSTGRES_DB: "gigmate",
        },
        volumes: ["database:/var/lib/postgresql/data"],
        labels: owner,
        restart: "no",
        healthcheck: {
          test: ["CMD-SHELL", "pg_isready -U gigmate -d gigmate"],
          interval: "2s",
          timeout: "3s",
          retries: 45,
        },
      },
      init: {
        ...backend,
        user: "0:0",
        volumes: [
          "private-config:/run/desktop-config",
          "media:/run/waha-media",
        ],
        command: ["python", "scripts/desktop_init.py"],
        profiles: ["setup"],
      },
      waha: {
        image:
          arch === "arm64"
            ? "devlikeapro/waha:arm-2026.9.1@sha256:b4216daddb7d5c1eb3ab99e608b76a005ec7523e766f923939d229718df4aafb"
            : "devlikeapro/waha:latest-2026.9.1@sha256:41283bd89922ec3f722e5a772b844c451634d4aa72e9c34043c3480184f970fe",
        environment: {
          WHATSAPP_DEFAULT_ENGINE: "WEBJS",
          WAHA_API_KEY:
            "sha512:" +
            crypto.createHash("sha512").update(profile.wahaKey).digest("hex"),
          WAHA_DASHBOARD_ENABLED: "false",
          WHATSAPP_SWAGGER_ENABLED: "false",
          WAHA_PRINT_QR: "false",
          WAHA_LOG_LEVEL: "error",
          WAHA_HTTP_LOG_LEVEL: "error",
          WAHA_EVENTS_DOWNLOAD_MEDIA: "false",
          WAHA_API_DOWNLOAD_MEDIA: "false",
          WAHA_APPS_ENABLED: "false",
        },
        volumes: ["whatsapp:/app/.sessions"],
        shm_size: "512m",
        labels: owner,
        restart: "no",
      },
      ingress: {
        ...backend,
        ports: ["127.0.0.1::8000"],
        healthcheck: {
          test: [
            "CMD",
            "python",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')",
          ],
          interval: "3s",
          timeout: "3s",
          retries: 40,
        },
      },
      worker: { ...backend, command: ["python", "-m", "gigmate.worker"] },
      monitor: {
        ...backend,
        volumes: [
          ...backend.volumes,
          "private-config:/workspace/local-data/waha-a02:ro",
        ],
        command: ["python", "scripts/waha_ingress.py", "watch", "--container"],
      },
    },
    volumes: Object.fromEntries(
      ["database", "private-config", "whatsapp", "media"].map((name) => [
        name,
        { labels: owner },
      ]),
    ),
  };
}
function isOwnedResource(labels = {}) {
  return (
    labels[OWNER] === "true" ||
    LEGACY_PROJECTS.has(labels["com.docker.compose.project"])
  );
}
async function cleanOwnedDocker(docker, { execute = run } = {}) {
  // No prune, no wildcard volume names, no remote engines. Every destructive
  // target is inspected again and must have a known GigMate ownership label.
  const containerIds = (await execute(docker, ["ps", "-aq"]))
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  for (const id of containerIds) {
    const [item] = JSON.parse(await execute(docker, ["inspect", id]));
    if (isOwnedResource(item.Config?.Labels))
      await execute(docker, ["rm", "-f", id]);
  }
  const names = (await execute(docker, ["volume", "ls", "-q"]))
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  for (const name of names) {
    const [item] = JSON.parse(
      await execute(docker, ["volume", "inspect", name]),
    );
    if (
      isOwnedResource(item.Labels) ||
      name === "gigmate-waha-a02_model-secret"
    )
      await execute(docker, ["volume", "rm", name]);
  }
}
async function startRuntime({
  docker,
  profile,
  resources,
  privateDir,
  origin,
  progress = () => {},
}) {
  await verifyLocalDocker(docker);
  const compose = path.join(privateDir, "compose.json");
  await writePrivate(
    compose,
    JSON.stringify(composeDocument(profile, resources, origin)),
  );
  const base = [
    "compose",
    "--project-name",
    projectFor(profile),
    "-f",
    compose,
  ];
  progress("正在准备 Python 后端环境；首次需要联网下载依赖…");
  await run(docker, [...base, "build", "ingress"]);
  progress("正在启动全新数据库…");
  await run(docker, [...base, "up", "-d", "--wait", "db"]);
  progress("正在创建本地账号和私密配置…");
  await run(docker, [...base, "run", "--rm", "-T", "init"], {
    input: JSON.stringify(profile),
  });
  // The initializer runs as root only to fix named-volume ownership; all
  // long-running processes use the unprivileged appuser.
  await run(docker, [
    ...base,
    "run",
    "--rm",
    "-T",
    "--entrypoint",
    "python",
    "init",
    "-c",
    "import os,pathlib; roots=[pathlib.Path('/run/desktop-config'),pathlib.Path('/run/waha-media')]; [(os.chown(p,1000,1000),os.chmod(p,0o700 if p.is_dir() else 0o600)) for r in roots for p in [r,*r.rglob('*')]]",
  ]);
  progress("正在启动 WhatsApp 连接、业务服务和消息处理…");
  const startServices = () =>
    run(docker, [
      ...base,
      "up",
      "-d",
      "--wait",
      "waha",
      "ingress",
      "worker",
      "monitor",
    ]);
  try {
    await startServices();
  } catch {
    progress("部分本地服务尚未就绪，正在重试启动；不会重复提交业务操作…");
    await startServices();
  }
  const port = (await run(docker, [...base, "port", "ingress", "8000"])).trim();
  if (!/^127\.0\.0\.1:\d+$/.test(port))
    throw new Error("INVALID_LOCAL_BACKEND_PORT");
  return {
    backend: "http://" + port,
    stop: () =>
      run(docker, [
        ...base,
        "stop",
        "worker",
        "monitor",
        "ingress",
        "waha",
        "db",
      ]),
  };
}
module.exports = {
  OWNER,
  LEGACY_PROJECTS,
  localDockerHost,
  run,
  findDocker,
  verifyLocalDocker,
  writePrivate,
  newProfile,
  projectFor,
  composeDocument,
  isOwnedResource,
  cleanOwnedDocker,
  startRuntime,
};
