import assert from "node:assert/strict";
import { createServer, request } from "node:http";
import { test } from "node:test";
import { localPairingMiddleware } from "./local-pairing.mjs";

const id = "00000000-0000-4000-8000-000000000099";
const other = "00000000-0000-4000-8000-000000000098";
// Synthetic 1px PNG, never an account QR.
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);
const status = Buffer.from(
  JSON.stringify({
    state: "SCAN_QR_CODE",
    connected: false,
    qr_available: true,
    api_key: "synthetic-secret-must-not-leak",
  }),
);

async function fixture(t, options = {}) {
  let calls = 0;
  const middleware = localPairingMiddleware({
    target: "http://127.0.0.1:18702",
    root: "/synthetic-workspace",
    provider: options.useRealProvider
      ? undefined
      : async (_root, selected, kind) => {
          calls++;
          assert.equal(selected, id);
          return options.provider
            ? options.provider(kind)
            : kind === "qr"
              ? png
              : status;
        },
    backendFetch:
      options.backendFetch ??
      (async (url, config) => {
        assert.match(
          url,
          /^http:\/\/127\.0\.0\.1:18702\/api\/v1\/connectors\?/,
        );
        if (config.headers.Cookie !== "gigmate_session=synthetic-test")
          return Response.json({}, { status: 401 });
        return Response.json({
          items: [{ id, enabled: true }],
          next_cursor: null,
        });
      }),
  });
  const server = createServer(
    (req, res) =>
      void middleware(req, res, () => {
        res.statusCode = 404;
        res.end();
      }),
  );
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  return {
    calls: () => calls,
    request: (kind = "qr", headers = {}, selected = id, method = "GET") =>
      new Promise((resolve, reject) => {
        const req = request(
          `${origin}/__gigmate_local_pairing/${selected}/${kind}`,
          {
            method,
            headers: {
              "X-GigMate-Local-Pairing": "1",
              Cookie: "gigmate_session=synthetic-test",
              ...headers,
            },
          },
          (res) => {
            const chunks = [];
            res.on("data", (chunk) => chunks.push(chunk));
            res.on("end", () =>
              resolve(
                new Response(Buffer.concat(chunks), {
                  status: res.statusCode,
                  headers: res.headers,
                }),
              ),
            );
            res.on("error", reject);
          },
        );
        req.on("error", reject);
        req.end();
      }),
  };
}

test("owned authenticated reads return a private PNG and safe status only", async (t) => {
  const f = await fixture(t);
  const qr = await f.request();
  assert.equal(qr.status, 200);
  assert.equal(qr.headers.get("content-type"), "image/png");
  assert.match(qr.headers.get("cache-control"), /no-store/);
  assert.equal(qr.headers.get("cross-origin-resource-policy"), "same-origin");
  assert.deepEqual(Buffer.from(await qr.arrayBuffer()), png);
  assert.deepEqual(await (await f.request("status")).json(), {
    state: "SCAN_QR_CODE",
    connected: false,
    qr_available: true,
  });
});

test("unauthenticated, foreign origins, rebinding hosts and other connections never reach provider", async (t) => {
  const f = await fixture(t);
  for (const [headers, selected, code] of [
    [{ Cookie: "" }, id, 401],
    [{ Cookie: "gigmate_session=wrong-account" }, id, 401],
    [{ Origin: "https://foreign.invalid" }, id, 403],
    [{ Host: "foreign.invalid:5173" }, id, 403],
    [{ "Sec-Fetch-Site": "cross-site" }, id, 403],
    [{ "X-GigMate-Local-Pairing": "" }, id, 403],
    [{}, other, 404],
  ])
    assert.equal((await f.request("qr", headers, selected)).status, code);
  assert.equal((await f.request("qr", {}, id, "POST")).status, 405);
  assert.equal((await f.request("../../private-config")).status, 404);
  assert.equal(f.calls(), 0);
});

test("paused receiving permission denies the QR", async (t) => {
  const f = await fixture(t, {
    backendFetch: async () =>
      Response.json({ items: [{ id, enabled: false }] }),
  });
  assert.equal((await f.request()).status, 403);
  assert.equal(f.calls(), 0);
});

test("login is revalidated after QR retrieval", async (t) => {
  let reads = 0;
  const f = await fixture(t, {
    backendFetch: async () =>
      ++reads === 1
        ? Response.json({ items: [{ id, enabled: true }] })
        : Response.json({}, { status: 401 }),
  });
  const result = await f.request();
  assert.equal(result.status, 401);
  assert.equal(result.headers.get("content-type"), "application/json");
  assert.equal(f.calls(), 1);
});

test("pagination resolves ownership, provider failures are redacted, invalid PNGs rejected", async (t) => {
  const f = await fixture(t, {
    backendFetch: async (url) =>
      Response.json(
        url.includes("cursor=")
          ? { items: [{ id, enabled: true }], next_cursor: null }
          : { items: [], next_cursor: "synthetic-cursor" },
      ),
    provider: () => {
      throw new Error("private raw response with synthetic-secret");
    },
  });
  const failure = await f.request();
  assert.equal(failure.status, 503);
  assert.equal((await failure.json()).error.code, "LOCAL_PAIRING_UNAVAILABLE");
  const invalid = await fixture(t, {
    provider: () => Buffer.from("not-a-png"),
  });
  assert.equal((await invalid.request()).status, 502);
});

test("connected sessions have no QR; provider state conflicts remain explicit", async (t) => {
  const f = await fixture(t, {
    provider: (kind) => {
      if (kind === "qr") throw new Error("WAHA_NOT_WAITING_FOR_QR");
      return Buffer.from(
        JSON.stringify({
          state: "WORKING",
          connected: true,
          qr_available: false,
        }),
      );
    },
  });
  assert.equal((await f.request()).status, 409);
  assert.deepEqual(await (await f.request("status")).json(), {
    state: "WORKING",
    connected: true,
    qr_available: false,
  });
});

test("backend unavailability fails closed without invoking the provider", async (t) => {
  const f = await fixture(t, {
    backendFetch: async () => {
      throw new Error("backend unavailable");
    },
  });
  assert.equal((await f.request()).status, 503);
  assert.equal(f.calls(), 0);
  assert.throws(
    () => localPairingMiddleware({ target: "http://127.0.0.1:18000" }),
    /requires/,
  );
});

test("a missing project Python environment returns an actionable error", async (t) => {
  const f = await fixture(t, { useRealProvider: true });
  const result = await f.request();
  assert.equal(result.status, 503);
  assert.equal((await result.json()).error.code, "LOCAL_PYTHON_UNAVAILABLE");
});
