import { accessSync, constants, statSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function testPython({
  repositoryRoot = fileURLToPath(new URL("../../", import.meta.url)),
  env = process.env,
  platform = process.platform,
} = {}) {
  const override = env.GIGMATE_TEST_PYTHON;
  const executable = override
    ? resolve(override)
    : resolve(
        repositoryRoot,
        ".venv",
        platform === "win32" ? "Scripts/python.exe" : "bin/python",
      );
  try {
    if (!statSync(executable).isFile()) throw new Error("Not a file");
    accessSync(executable, constants.X_OK);
  } catch {
    const setup =
      platform === "win32"
        ? "py -3.12 -m venv .venv"
        : "python3.12 -m venv .venv";
    throw new Error(
      `Frontend tests require an executable Python: ${executable}. ` +
        (override
          ? "Fix GIGMATE_TEST_PYTHON; the configured path is not usable."
          : `Create the project virtual environment from the repository root (${setup}), or set GIGMATE_TEST_PYTHON to an existing Python executable.`),
    );
  }
  return executable;
}
