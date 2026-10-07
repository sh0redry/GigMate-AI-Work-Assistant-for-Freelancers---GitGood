import { execFile } from "node:child_process";
import { resolve } from "node:path";
import { promisify } from "node:util";

const execute = promisify(execFile);
const prefix = "/__gigmate_local_pairing/";
const loopback = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);
const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

// Run Andy's existing read-only adapter in a separate server process. Only safe
// status fields or PNG bytes leave Python; no config, keys or QR files are served.
const providerProgram = `
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "apps/backend/src"))
sys.path.insert(0, str(Path.cwd()))
try:
    from scripts.waha_local import load_config
    from scripts.waha_ingress import local_binding
    from scripts.waha_team import PROFILE, environment
    from gigmate.waha_client import LocalWahaClient
    from gigmate.waha_adapter import AdapterError
    if not PROFILE.exists():
        raise AdapterError("LOCAL_CONFIG_INVALID_OR_MISSING")
    environment()  # Validate the existing developer-owned workspace profile.
    config = load_config()
    binding = local_binding(config)
    if binding.connection_id != sys.argv[1]:
        raise AdapterError("LOCAL_BINDING_MISMATCH")
    client = LocalWahaClient(config)
    try:
        if sys.argv[2] == "qr":
            sys.stdout.buffer.write(client.qr())
        else:
            value = client.status()
            print(json.dumps({"state": value["state"], "connected": value["connected"], "qr_available": value["state"] == "SCAN_QR_CODE"}))
    finally:
        client.close()
except ImportError:
    print(json.dumps({"error": {"code": "LOCAL_PAIRING_DEPENDENCIES_MISSING"}}))
    sys.exit(1)
except Exception as error:
    code = getattr(error, "code", "LOCAL_PAIRING_UNAVAILABLE")
    print(json.dumps({"error": {"code": code}}))
    sys.exit(1)
`;

async function readProvider(root, id, kind) {
  try {
    const result = await execute(
      resolve(
        root,
        ".venv",
        process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
      ),
      ["-c", providerProgram, id, kind],
      {
        cwd: root,
        encoding: "buffer",
        timeout: 25000,
        maxBuffer: 2 * 1024 * 1024,
        windowsHide: true,
      },
    );
    return result.stdout;
  } catch (error) {
    let code =
      error.code === "ENOENT"
        ? "LOCAL_PYTHON_UNAVAILABLE"
        : "LOCAL_PAIRING_UNAVAILABLE";
    try {
      const candidate = JSON.parse(error.stdout?.toString()).error?.code;
      if (/^[A-Z_]{1,80}$/.test(candidate)) code = candidate;
    } catch {
      // Never expose process stderr or raw provider responses.
    }
    throw new Error(code);
  }
}

export function localPairingMiddleware({
  target,
  root,
  provider = readProvider,
  backendFetch = fetch,
}) {
  // This bridge is deliberately restricted to Andy's existing local ingress.
  if (target !== "http://127.0.0.1:18702") {
    throw new Error(
      "Local pairing requires GIGMATE_API_URL=http://127.0.0.1:18702",
    );
  }
  let active = 0;
  return async (req, res, next) => {
    if (!req.url?.startsWith(prefix)) return next();
    res.setHeader("Cache-Control", "private, no-store, max-age=0");
    res.setHeader("Pragma", "no-cache");
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("Vary", "Cookie");
    const fail = (status, code) => {
      res.statusCode = status;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ error: { code, message: code } }));
    };
    const host = req.headers.host;
    if (
      !loopback.has(req.socket.remoteAddress) ||
      !/^(127\.0\.0\.1|localhost):\d+$/.test(host ?? "") ||
      (req.headers.origin && req.headers.origin !== `http://${host}`) ||
      ["cross-site", "same-site"].includes(req.headers["sec-fetch-site"]) ||
      req.headers["x-gigmate-local-pairing"] !== "1"
    )
      return fail(403, "LOCAL_PAIRING_FORBIDDEN");
    if (req.method !== "GET") return fail(405, "METHOD_NOT_ALLOWED");
    const match = req.url.match(
      /^\/__gigmate_local_pairing\/([a-f0-9-]{36})\/(status|qr)$/,
    );
    if (!match) return fail(404, "LOCAL_PAIRING_NOT_FOUND");
    const token = req.headers.cookie?.match(
      /(?:^|;\s*)gigmate_session=([A-Za-z0-9_-]+)(?:;|$)/,
    )?.[1];
    if (!token) return fail(401, "UNAUTHENTICATED");
    const owned = async () => {
      let cursor = "";
      for (let page = 0; page < 10; page++) {
        const response = await backendFetch(
          `${target}/api/v1/connectors?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
          {
            headers: { Cookie: `gigmate_session=${token}` },
            redirect: "error",
            signal: AbortSignal.timeout(5000),
          },
        );
        if (response.status === 401) return [401, "UNAUTHENTICATED"];
        if (response.status === 403) return [403, "CONSENT_REVOKED"];
        if (!response.ok) return [503, "LOCAL_PAIRING_UNAVAILABLE"];
        const data = await response.json();
        if (!Array.isArray(data.items))
          return [503, "LOCAL_PAIRING_UNAVAILABLE"];
        const connector = data.items.find((item) => item.id === match[1]);
        if (connector)
          return connector.enabled ? null : [403, "CONSENT_REVOKED"];
        if (!data.next_cursor) break;
        cursor = data.next_cursor;
      }
      return [404, "LOCAL_BINDING_MISMATCH"];
    };
    try {
      const denied = await owned();
      if (denied) return fail(...denied);
      if (active >= 2) return fail(429, "LOCAL_PAIRING_BUSY");
      active++;
      let data;
      try {
        data = await provider(root, match[1], match[2]);
      } finally {
        active--;
      }
      // Do not return a QR if the app login/consent expired during retrieval.
      const expired = await owned();
      if (expired) return fail(...expired);
      if (match[2] === "qr") {
        if (
          !Buffer.isBuffer(data) ||
          data.length > 2 * 1024 * 1024 ||
          !data.subarray(0, 8).equals(pngSignature)
        )
          return fail(502, "WAHA_INVALID_QR");
        res.setHeader("Content-Type", "image/png");
        res.end(data);
      } else {
        const value = JSON.parse(data.toString());
        if (
          typeof value.state !== "string" ||
          typeof value.connected !== "boolean" ||
          typeof value.qr_available !== "boolean"
        )
          return fail(502, "LOCAL_PAIRING_UNAVAILABLE");
        res.setHeader("Content-Type", "application/json");
        res.end(
          JSON.stringify({
            state: value.state,
            connected: value.connected,
            qr_available: value.qr_available,
          }),
        );
      }
    } catch (error) {
      const code = /^[A-Z_]{1,80}$/.test(error.message)
        ? error.message
        : "LOCAL_PAIRING_UNAVAILABLE";
      fail(code === "WAHA_NOT_WAITING_FOR_QR" ? 409 : 503, code);
    }
  };
}
