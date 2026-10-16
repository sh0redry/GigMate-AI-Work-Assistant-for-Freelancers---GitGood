import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { createServer as viteServer } from "vite";
import { execFileSync } from "node:child_process";
import { developmentTarget, applicationProxy } from "./vite.config.ts";
import { apiBase } from "./src/environment.ts";
import { testPython } from "./test-python.mjs";
test("development has exactly one explicit local business target", () => {
  assert.equal(developmentTarget({}), "http://127.0.0.1:18702");
  assert.equal(
    developmentTarget({ GIGMATE_REAL_API_URL: "http://localhost:18802" }),
    "http://localhost:18802",
  );
});
test("unsafe destinations and ports fail clearly", () => {
  for (const url of [
    "https://example.com",
    "http://127.0.0.1:0",
    "http://127.0.0.1:65536",
    "http://user:password@localhost:8000",
    "http://localhost:8000/path",
  ])
    assert.throws(() => developmentTarget({ GIGMATE_REAL_API_URL: url }));
});
test("old isolated settings cannot select the delivery backend", () => {
  assert.equal(
    developmentTarget({
      GIGMATE_API_URL: "http://localhost:18000",
      GIGMATE_ISOLATED_API_URL: "http://localhost:18001",
      GIGMATE_DEFAULT_ENV: "isolated",
    }),
    "http://127.0.0.1:18702",
  );
});
test("browser path and injected legacy settings cannot redirect API requests", () => {
  globalThis.window = { location: { pathname: "/environments/isolated/" } };
  globalThis.__GIGMATE_ENVIRONMENTS__ = { defaultEnvironment: "isolated" };
  assert.equal(apiBase(), "/api/v1");
  delete globalThis.window;
  delete globalThis.__GIGMATE_ENVIRONMENTS__;
});
test("synthetic tooling filters private configuration and passes only one loopback target", () => {
  const value = execFileSync(
    testPython(),
    [
      "-c",
      'from scripts.check_waha_setup import synthetic_frontend_environment; import json; print(json.dumps(synthetic_frontend_environment({"DATABASE_URL":"secret","WAHA_CONTROL_CONFIG":"secret","OPENAI_API_KEY":"secret","GIGMATE_REAL_API_URL":"http://localhost:18702"})))',
    ],
    { cwd: new URL("../../", import.meta.url), encoding: "utf8" },
  );
  assert.deepEqual(JSON.parse(value), {
    GIGMATE_REAL_API_URL: "http://127.0.0.1:18802",
    CI: "1",
  });
});
async function withProxy(run) {
  let backend, vite;
  const received = [];
  try {
    backend = createServer((req, res) => {
      received.push(req.url);
      if (req.url.endsWith("login"))
        res.setHeader("set-cookie", [
          "gigmate_session=synthetic; Path=/; HttpOnly; SameSite=Strict",
          "unrelated=secret",
        ]);
      res.setHeader("content-type", "application/json");
      res.end(
        JSON.stringify({ path: req.url, cookie: req.headers.cookie ?? null }),
      );
    });
    await new Promise((r) => backend.listen(0, "127.0.0.1", r));
    vite = await viteServer({
      configFile: false,
      logLevel: "silent",
      server: {
        host: "127.0.0.1",
        port: 0,
        proxy: {
          "/api": applicationProxy(
            "http://127.0.0.1:" + backend.address().port,
          ),
        },
      },
    });
    await vite.listen();
    await run("http://127.0.0.1:" + vite.httpServer.address().port, received);
  } finally {
    await vite?.close();
    if (backend) await new Promise((r) => backend.close(r));
  }
}
test("single proxy preserves session attributes and forwards only the app session", async () =>
  withProxy(async (origin) => {
    const login = await fetch(origin + "/api/v1/auth/login");
    assert.match(
      login.headers.get("set-cookie"),
      /gigmate_session=synthetic; Path=\/; HttpOnly; SameSite=Strict/,
    );
    assert.doesNotMatch(login.headers.get("set-cookie"), /unrelated/);
    const response = await fetch(origin + "/api/v1/work-orders", {
      headers: {
        cookie:
          "other=secret; gigmate_session=synthetic; gigmate_session_real=old",
      },
    });
    assert.deepEqual(await response.json(), {
      path: "/api/v1/work-orders",
      cookie: "gigmate_session=synthetic",
    });
  }));
test("legacy environment URLs never reach a second backend", async () =>
  withProxy(async (origin, received) => {
    await fetch(origin + "/environments/isolated/api/v1/work-orders");
    assert.equal(received.length, 0);
    await fetch(origin + "/api/v1/work-orders");
    assert.deepEqual(received, ["/api/v1/work-orders"]);
  }));
