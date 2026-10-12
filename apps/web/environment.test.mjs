import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer as httpServer } from "node:http";
import { createServer as viteServer } from "vite";
import { developmentEnvironments, environmentProxy } from "./vite.config.ts";
import { currentEnvironment, apiBase } from "./src/environment.ts";

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
