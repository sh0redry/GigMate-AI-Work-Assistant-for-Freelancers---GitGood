import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createServer as httpServer } from "node:http";
import { createServer as viteServer } from "vite";
import {
  developmentEnvironments,
  developmentProxies,
  environmentProxy,
} from "./vite.config.ts";
import { currentEnvironment, apiBase } from "./src/environment.ts";

test("current A acceptance shell commands select their real ingress, including custom ports", async () => {
  for (const language of ["en", "zh"]) {
    for (const name of ["integration", "message-sync"]) {
      const guide = await readFile(
        new URL(
          `../../docs/${language}/role-a-${name}-acceptance.md`,
          import.meta.url,
        ),
        "utf8",
      );
      assert.doesNotMatch(guide, /GIGMATE_API_URL/);
      assert.match(guide, /GIGMATE_DEFAULT_ENV[= ]/);
      const commands = [
        ...guide.matchAll(
          /GIGMATE_REAL_API_URL\s*=\s*['"]?(http:\/\/127\.0\.0\.1:\d+)/g,
        ),
      ];
      assert.ok(
        commands.length > 0,
        `${language}/${name} needs a copyable command`,
      );
      for (const command of commands) {
        const ingress = command[1];
        const startup = guide.slice(command.index).split("npm run dev")[0];
        const selected = startup.match(
          /GIGMATE_DEFAULT_ENV\s*=\s*['"]?(real|isolated)/,
        );
        assert.ok(
          selected,
          `${language}/${name} must select a startup environment`,
        );
        assert.equal(selected[1], "real");
        const config = developmentEnvironments({
          GIGMATE_REAL_API_URL: ingress,
          GIGMATE_DEFAULT_ENV: selected[1],
        });
        assert.equal(config.targets[config.defaultEnvironment], ingress);
        assert.notEqual(config.targets.real, config.targets.isolated);
      }
    }
  }
  const custom = developmentEnvironments({
    GIGMATE_REAL_API_URL: "http://127.0.0.1:18712",
    GIGMATE_DEFAULT_ENV: "real",
  });
  assert.equal(
    custom.targets[custom.defaultEnvironment],
    "http://127.0.0.1:18712",
  );
});

test("setup runner's actual frontend configuration pins its synthetic ingress and ignores inherited destinations", () => {
  const script = fileURLToPath(
    new URL("../../scripts/check_waha_setup.py", import.meta.url),
  );
  const env = JSON.parse(
    execFileSync(
      process.env.GIGMATE_TEST_PYTHON ?? "python",
      [
        "-c",
        "import json, runpy, sys; module = runpy.run_path(sys.argv[1]); print(json.dumps(module['synthetic_frontend_environment'](json.loads(sys.argv[2]))))",
        script,
        JSON.stringify({
          PATH: process.env.PATH,
          GIGMATE_REAL_API_URL: "http://127.0.0.1:18702",
          GIGMATE_ISOLATED_API_URL: "http://127.0.0.1:18000",
          GIGMATE_API_URL: "http://127.0.0.1:18712",
          GIGMATE_DEFAULT_ENV: "isolated",
          WAHA_CONTROL_CONFIG: "synthetic-private-config",
        }),
      ],
      { encoding: "utf8" },
    ),
  );
  const config = developmentEnvironments(env);
  assert.equal(config.syntheticProvider, true);
  assert.equal(config.defaultEnvironment, "real");
  assert.equal(config.targets.real, "http://127.0.0.1:18802");
  const proxies = developmentProxies(config);
  assert.deepEqual(Object.keys(proxies), ["/environments/real/api"]);
  assert.equal(
    proxies["/environments/real/api"].target,
    "http://127.0.0.1:18802",
  );
  assert.equal(env.GIGMATE_API_URL, undefined);
  assert.equal(env.WAHA_CONTROL_CONFIG, undefined);
});

test("synthetic provider mode fails without its explicit backend and real route selection", () => {
  assert.throws(
    () =>
      developmentEnvironments({
        GIGMATE_SYNTHETIC_PROVIDER: "1",
        GIGMATE_DEFAULT_ENV: "real",
      }),
    /explicit local API/,
  );
  assert.throws(
    () =>
      developmentEnvironments({
        GIGMATE_SYNTHETIC_PROVIDER: "1",
        GIGMATE_REAL_API_URL: "http://127.0.0.1:18802",
      }),
    /DEFAULT_ENV=real/,
  );
  assert.throws(
    () => developmentEnvironments({ GIGMATE_SYNTHETIC_PROVIDER: "true" }),
    /must be 0 or 1/,
  );
});

test("development destinations reject remote, same-port and invalid default configuration", () => {
  assert.equal(developmentEnvironments({}).defaultEnvironment, "isolated");
  assert.throws(
    () =>
      developmentEnvironments({ GIGMATE_REAL_API_URL: "https://example.com" }),
    /local HTTP/,
  );
  assert.throws(
    () =>
      developmentEnvironments({
        GIGMATE_REAL_API_URL: "http://localhost:18000",
      }),
    /separate backend/,
  );
  assert.throws(
    () => developmentEnvironments({ GIGMATE_DEFAULT_ENV: "production" }),
    /real or isolated/,
  );
  assert.throws(
    () =>
      developmentEnvironments({ GIGMATE_REAL_API_URL: "http://127.0.0.1:0" }),
    /port/,
  );
  assert.equal(
    developmentEnvironments({ GIGMATE_API_URL: "http://127.0.0.1:18012" })
      .targets.isolated,
    "http://127.0.0.1:18012",
  );
});
test("published deployment uses its own API without a development environment", () => {
  assert.equal(currentEnvironment(), null);
  assert.equal(apiBase(), "/api/v1");
});
test("real HTTP proxies isolate same-named sessions, preserve CSRF/origin and rewrite logout cookies", async () => {
  const servers = [];
  let vite;
  try {
    const targets = {};
    for (const environment of ["real", "isolated"]) {
      const server = httpServer((request, response) => {
        response.setHeader("content-type", "application/json");
        if (request.url.endsWith("/login"))
          response.setHeader(
            "set-cookie",
            "gigmate_session=synthetic-" +
              environment +
              "; Path=/; HttpOnly; SameSite=Strict",
          );
        if (request.url.endsWith("/logout"))
          response.setHeader(
            "set-cookie",
            "gigmate_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict",
          );
        response.end(
          JSON.stringify({
            environment,
            path: request.url,
            cookie: request.headers.cookie ?? null,
            csrf: request.headers["x-csrf-token"],
            origin: request.headers.origin,
          }),
        );
      });
      servers.push(server);
      await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
      targets[environment] = "http://127.0.0.1:" + server.address().port;
    }
    vite = await viteServer({
      configFile: false,
      logLevel: "silent",
      server: {
        host: "127.0.0.1",
        port: 0,
        proxy: {
          "/environments/real/api": environmentProxy("real", targets.real),
          "/environments/isolated/api": environmentProxy(
            "isolated",
            targets.isolated,
          ),
        },
      },
    });
    await vite.listen();
    const origin = "http://127.0.0.1:" + vite.httpServer.address().port;
    for (const environment of ["real", "isolated"]) {
      const base = origin + `/environments/${environment}/api/v1`;
      const login = await fetch(base + "/auth/login", { method: "POST" });
      const cookie = login.headers.get("set-cookie");
      assert.match(
        cookie,
        new RegExp(`^gigmate_session_${environment}=synthetic-${environment};`),
      );
      assert.match(cookie, new RegExp(`Path=/environments/${environment}/`));
      assert.match(cookie, /HttpOnly/);
      assert.match(cookie, /SameSite=Strict/);
      const result = await fetch(base + "/work-orders", {
        headers: {
          cookie:
            "gigmate_session=legacy; gigmate_session_real=synthetic-real; gigmate_session_isolated=synthetic-isolated; provider-secret=do-not-forward",
          "x-csrf-token": "synthetic-csrf",
          origin,
        },
      });
      assert.deepEqual(await result.json(), {
        environment,
        path: "/api/v1/work-orders",
        cookie: "gigmate_session=synthetic-" + environment,
        csrf: "synthetic-csrf",
        origin,
      });
      const legacy = await fetch(base + "/work-orders", {
        headers: { cookie: "gigmate_session=legacy" },
      });
      assert.equal((await legacy.json()).cookie, null);
      const logout = await fetch(base + "/auth/logout", { method: "POST" });
      assert.match(
        logout.headers.get("set-cookie"),
        new RegExp(
          `^gigmate_session_${environment}=; Path=/environments/${environment}/; Max-Age=0`,
        ),
      );
    }
  } finally {
    if (vite) await vite.close();
    await Promise.all(
      servers.map((server) => new Promise((resolve) => server.close(resolve))),
    );
  }
});
