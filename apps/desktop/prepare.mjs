import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
const here = path.dirname(fileURLToPath(import.meta.url)),
  root = path.resolve(here, "../..");
const out = path.join(here, "build");
await fs.rm(out, { recursive: true, force: true });
await fs.mkdir(path.join(out, "runtime"), { recursive: true });
// Explicit source allowlist: never copy local-data, .env, credentials, screenshots,
// Python/Node environments, working database files or developer sessions.
const sources = [
  "apps/backend/src",
  "apps/backend/migrations",
  "apps/backend/alembic.ini",
  "apps/backend/requirements.lock",
  "contracts",
  "scripts/desktop_init.py",
  "scripts/waha_ingress.py",
  "scripts/waha_local.py",
  "scripts/waha_container_config.py",
];
for (const relative of sources) {
  await fs.mkdir(path.dirname(path.join(out, "runtime", relative)), {
    recursive: true,
  });
  await fs.cp(path.join(root, relative), path.join(out, "runtime", relative), {
    recursive: true,
    filter: (source) =>
      !["__pycache__", ".pytest_cache", ".DS_Store"].includes(
        path.basename(source),
      ),
  });
}
await fs.copyFile(
  path.join(here, "runtime.Dockerfile"),
  path.join(out, "runtime", "Dockerfile"),
);
await fs.cp(path.join(root, "apps/web/dist"), path.join(out, "web"), {
  recursive: true,
});
const source = execFileSync("git", ["rev-parse", "HEAD"], {
  cwd: root,
  encoding: "utf8",
}).trim();
const version = JSON.parse(
  await fs.readFile(path.join(here, "package.json"), "utf8"),
).version;
await fs.writeFile(
  path.join(out, "install.json"),
  JSON.stringify({ version, source, buildId: `${version}:${source}` }),
);
console.log(
  "Prepared allowlisted runtime and compiled web assets; no developer data copied.",
);
