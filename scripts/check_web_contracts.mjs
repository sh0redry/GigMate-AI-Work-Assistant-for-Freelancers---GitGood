// Detect generated frontend type drift without rewriting the checked-in file.
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "apps/web");
const directory = mkdtempSync(join(web, ".contract-check-"));
if (!directory.startsWith(web + "/") && !directory.startsWith(web + "\\")) throw new Error("Invalid temp path");
try {
  const output = join(directory, "api.d.ts");
  const commands = [
    [join(web, "node_modules/openapi-typescript/bin/cli.js"), join(root, "contracts/openapi.json"), "-o", output],
    [join(web, "node_modules/prettier/bin/prettier.cjs"), "--write", output],
  ];
  for (const args of commands) {
    const result = spawnSync(process.execPath, args, { cwd: web, stdio: "inherit" });
    if (result.status !== 0) process.exitCode = 1;
    if (result.status !== 0) throw new Error("Frontend contract generation failed");
  }
  if (readFileSync(output, "utf8") !== readFileSync(join(web, "src/generated/api.d.ts"), "utf8")) {
    throw new Error("Frontend contract drift: run npm run generate:api in apps/web");
  }
  console.log("Frontend generated types match implemented OpenAPI.");
} finally {
  rmSync(directory, { recursive: true });
}
