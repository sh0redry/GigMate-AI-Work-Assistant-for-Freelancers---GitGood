import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { testPython } from "./test-python.mjs";

test("the actual environment suite passes without a Python PATH command or override", async () => {
  const directory = await mkdtemp(join(tmpdir(), "gigmate-no-python-path-"));
  try {
    const env = Object.fromEntries(
      Object.entries(process.env).filter(
        ([name]) =>
          !["path", "gigmate_test_python", "node_test_context"].includes(
            name.toLowerCase(),
          ),
      ),
    );
    env.PATH = directory;
    const result = execFileSync(
      process.execPath,
      ["--test", "environment.test.mjs"],
      {
        cwd: fileURLToPath(new URL("./", import.meta.url)),
        env,
        encoding: "utf8",
        timeout: 30000,
      },
    );
    assert.match(result, /(?:#|ℹ) pass 7/);
    assert.match(result, /(?:#|ℹ) fail 0/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("explicit Python override executes even when the checkout has no virtual environment", async () => {
  const directory = await mkdtemp(join(tmpdir(), "gigmate-python-override-"));
  try {
    const selected = testPython({
      repositoryRoot: directory,
      env: { GIGMATE_TEST_PYTHON: testPython() },
    });
    const result = execFileSync(selected, ["-c", "print('override works')"], {
      env: { ...process.env, PATH: directory },
      encoding: "utf8",
    });
    assert.equal(result.trim(), "override works");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("missing project Python gives platform-specific setup guidance instead of skipping", async () => {
  const directory = await mkdtemp(join(tmpdir(), "gigmate-missing-python-"));
  try {
    for (const platform of ["darwin", "linux", "win32"]) {
      assert.throws(
        () => testPython({ repositoryRoot: directory, env: {}, platform }),
        (error) => {
          assert.match(
            error.message,
            /Frontend tests require an executable Python/,
          );
          assert.match(error.message, /GIGMATE_TEST_PYTHON/);
          assert.ok(
            error.message.includes(
              platform === "win32"
                ? "py -3.12 -m venv .venv"
                : "python3.12 -m venv .venv",
            ),
          );
          return true;
        },
      );
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("an invalid explicit override never falls back to a different interpreter", () => {
  assert.throws(
    () =>
      testPython({
        env: { GIGMATE_TEST_PYTHON: "not-an-installed-gigmate-python" },
      }),
    /Fix GIGMATE_TEST_PYTHON/,
  );
});
