import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const directory = await mkdtemp(join(tmpdir(), "gigmate-http-api-"));
for (const name of ["connection-api", "waha-live-api"]) {
  const source = await readFile(
    new URL(`./src/${name}.ts`, import.meta.url),
    "utf8",
  );
  let code = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
  }).outputText;
  code = code
    .replaceAll('"./connection-api"', '"./connection-api.mjs"')
    .replaceAll('"./waha-live-api"', '"./waha-live-api.mjs"');
  await writeFile(join(directory, name + ".mjs"), code);
}
const { liveConnectionApi, ConnectionError } = await import(
  pathToFileURL(join(directory, "connection-api.mjs"))
);
const original = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = original;
});
after(async () => {
  if (
    !resolve(directory).startsWith(resolve(tmpdir()) + sep) ||
    !basename(directory).startsWith("gigmate-http-api-")
  )
    throw new Error("Invalid cleanup target");
  await rm(directory, { recursive: true });
});
const id = "00000000-0000-4000-8000-000000000070";
const opid = "00000000-0000-4000-8000-000000000071";
const choice = "00000000-0000-4000-8000-000000000072";
const base = `/api/v1/connectors/${id}`;
const setup = (extra = {}) => ({
  connection_id: id,
  control_version: 7,
  enabled: true,
  available: true,
  provider_state: "WORKING",
  provider_observed_at: "2026-10-08T00:00:00Z",
  provider_sample_stale: false,
  active_operation_id: null,
  last_operation_id: null,
  ...extra,
});
const op = (extra = {}) => ({
  id: opid,
  connection_id: id,
  action: "connect",
  state: "succeeded",
  control_version: 8,
  error_code: null,
  provider_state: "WORKING",
  provider_observed_at: "2026-10-08T00:00:00Z",
  ...extra,
});
const json = (data, status = 200) =>
  new Response(JSON.stringify({ data }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const error = (code, status) =>
  new Response(JSON.stringify({ error: { code, message: code } }), { status });

test("lost operation response preserves exact version/body/key and never uses local bridge", async () => {
  let version = 7;
  const posts = [];
  globalThis.fetch = async (url, init) => {
    assert.equal(init.credentials, "same-origin");
    assert.equal(init.cache, "no-store");
    assert.ok(!url.includes("__gigmate"));
    if (url.endsWith("/setup"))
      return json(setup({ control_version: version }));
    if (url.endsWith("/operations")) {
      posts.push({ body: JSON.parse(init.body), headers: init.headers });
      if (posts.length === 1) {
        version = 8;
        throw new TypeError("lost response");
      }
      return json(op(), 202);
    }
    throw new Error("unexpected route");
  };
  const api = liveConnectionApi("synthetic-csrf");
  await assert.rejects(
    api.start(id, "same-key"),
    (e) => e.code === "OPERATION_RESULT_UNKNOWN",
  );
  assert.equal((await api.start(id, "same-key")).connected, true);
  assert.deepEqual(posts[0], posts[1]);
  assert.equal(posts[0].headers["X-CSRF-Token"], "synthetic-csrf");
  assert.equal(posts[0].body.expected_version, 7);
});

test("unknown intent is shown as uncertain and reconciled only by explicit request", async () => {
  const mutations = [];
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(setup({ active_operation_id: opid }));
    if (url.endsWith("/reconcile")) {
      mutations.push(url);
      return json(op());
    }
    if (url.endsWith(`/operations/${opid}`))
      return json(op({ state: "result_unknown" }));
    throw new Error("unexpected route");
  };
  const api = liveConnectionApi("synthetic-csrf");
  const value = await api.pairing(id);
  assert.equal(value.state, "RESULT_UNKNOWN");
  assert.equal(value.connected, false);
  assert.equal(mutations.length, 0);
  await api.reconcile(id);
  assert.deepEqual(mutations, [base + `/operations/${opid}/reconcile`]);
});

test("discovery then save uses canonical opaque IDs and latest authority", async () => {
  let selected = false,
    version = 7;
  const rows = () => [
    { id: choice, label: "Synthetic participant", selected, expires_at: null },
  ];
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(setup({ control_version: version }));
    if (url.endsWith("/operations")) {
      assert.equal(JSON.parse(init.body).action, "discover");
      return json(op({ action: "discover", control_version: version }));
    }
    if (url.endsWith("/chats") && init.method === "PUT") {
      assert.deepEqual(JSON.parse(init.body), {
        expected_version: 7,
        selected_ids: [choice],
        consent: true,
      });
      selected = true;
      version++;
      return json(setup({ control_version: version }));
    }
    if (url.endsWith("/chats")) return json(rows());
    throw new Error("unexpected route");
  };
  const api = liveConnectionApi("synthetic-csrf");
  const before = await api.selection(id);
  const discovered = await api.chats(id, 0);
  const result = await api.save(id, before, discovered.items, "save-key");
  assert.equal(result.control_version, 8);
  assert.equal(result.selected[0].id, choice);
});

test("authority conflicts and expired choices are not retried silently", async () => {
  for (const code of [
    "WAHA_SETUP_VERSION_CONFLICT",
    "CHAT_CHOICE_EXPIRED_OR_UNAVAILABLE",
  ]) {
    let writes = 0;
    globalThis.fetch = async () => {
      writes++;
      return error(code, 409);
    };
    await assert.rejects(
      liveConnectionApi("synthetic-csrf").save(
        id,
        { control_version: 7, selected: [], choices: [] },
        [],
        "key",
      ),
      (e) => e instanceof ConnectionError && e.code === code,
    );
    assert.equal(writes, 1);
  }
});

test("review keeps explicit no-import confirmation and QR uses private backend", async () => {
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/review")) {
      assert.deepEqual(JSON.parse(init.body), {
        issue_ids: [choice],
        confirmed_no_import: true,
      });
      return json({ reviewed: 1 });
    }
    if (url.endsWith("/qr"))
      return new Response("synthetic-bytes", {
        headers: { "Content-Type": "image/png" },
      });
    throw new Error("unexpected route");
  };
  const api = liveConnectionApi("synthetic-csrf");
  assert.equal(await api.reviewIssues(id, [choice]), 1);
  assert.equal((await api.qr(id)).type, "image/png");
});

test("readiness refresh and pause/resume use session/CSRF without profile files", async () => {
  const actions = [];
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup")) return json(setup());
    actions.push({
      url,
      body: JSON.parse(init.body),
      csrf: init.headers["X-CSRF-Token"],
    });
    return json(setup());
  };
  const api = liveConnectionApi("synthetic-csrf");
  await api.pause(id);
  await api.resume(id);
  assert.deepEqual(
    actions.map((x) => x.url),
    [base + "/pause", base + "/resume"],
  );
  assert.ok(
    actions.every(
      (x) => x.body.expected_version === 7 && x.csrf === "synthetic-csrf",
    ),
  );
});
