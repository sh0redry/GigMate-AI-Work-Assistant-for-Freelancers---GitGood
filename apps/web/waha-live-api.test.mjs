import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const directory = await mkdtemp(join(tmpdir(), "gigmate-http-api-"));
for (const name of [
  "connection-api",
  "waha-live-api",
  "waha-sync-api",
  "waha-media-api",
]) {
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
const { liveConnectionApi, ConnectionError, clearConnectionAttempts } =
  await import(pathToFileURL(join(directory, "connection-api.mjs")));
const original = globalThis.fetch;
const { synchronizationApi } = await import(
  pathToFileURL(join(directory, "waha-sync-api.mjs"))
);
const { mediaApi } = await import(
  pathToFileURL(join(directory, "waha-media-api.mjs"))
);
afterEach(() => {
  globalThis.fetch = original;
  delete globalThis.sessionStorage;
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

test("media lost response retains exact source, consent, version and key", async () => {
  const posts = [];
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(setup({ control_version: posts.length ? 99 : 7 }));
    assert.equal(url, base + "/media/jobs");
    assert.equal(init.headers["X-CSRF-Token"], "synthetic-csrf");
    posts.push([JSON.parse(init.body), init.headers["Idempotency-Key"]]);
    if (posts.length === 1)
      throw new TypeError("Synthetic lost media response");
    return json({ id: opid, attachment_id: choice, state: "pending" });
  };
  const api = mediaApi(id, "synthetic-csrf");
  const input = {
    snapshot_id: choice,
    consent_download: true,
    process: true,
    consent_model: true,
  };
  await assert.rejects(
    api.start(input, "original"),
    (e) => e.code === "MEDIA_REQUEST_UNKNOWN",
  );
  assert.equal((await api.start(input, "original")).id, opid);
  assert.deepEqual(posts[0], posts[1]);
  assert.equal(posts[1][0].expected_version, 7);
  await assert.rejects(
    api.start({ ...input, consent_model: false }, "original"),
    (e) => e.code === "IDEMPOTENCY_CONFLICT",
  );
  assert.equal(posts.length, 2);
});

test("media preview, review and read-only result lookup use owned backend without provider URLs", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    assert.ok(url.startsWith(base));
    assert.equal(init.credentials, "same-origin");
    assert.equal(init.cache, "no-store");
    calls.push([url, init.body ? JSON.parse(init.body) : null]);
    if (url.endsWith("/setup")) return json(setup());
    if (url.endsWith("/content"))
      return new Response("Synthetic text", {
        headers: { "Content-Type": "text/plain" },
      });
    return json({ id: choice });
  };
  const api = mediaApi(id, "synthetic-csrf");
  assert.equal(await (await api.preview(choice)).text(), "Synthetic text");
  await api.reconcile(opid);
  await api.review(
    { id: choice, version: 2, context_version: 8, result_job_id: opid },
    "Synthetic checked source",
  );
  assert.deepEqual(calls.at(-1)[1], {
    expected_attachment_version: 2,
    expected_context_version: 8,
    expected_result_job_id: opid,
    reviewed: true,
    note: "Synthetic checked source",
  });
  assert.ok(calls.some(([url]) => url.endsWith("/reconcile")));
  assert.ok(!JSON.stringify(calls).includes("api/files"));
});

test("old media backend and revoked source fail clearly without automatic retry", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return error("NOT_FOUND", 404);
  };
  const api = mediaApi(id, "synthetic-csrf");
  await assert.rejects(
    api.capabilities(),
    (e) => e.code === "MEDIA_API_NOT_INSTALLED",
  );
  assert.equal(calls, 1);
  globalThis.fetch = async () => error("SOURCE_REVOKED", 409);
  await assert.rejects(api.preview(choice), (e) => e.code === "SOURCE_REVOKED");
});

test("sync lost response replays exact consent range and authority rather than creating another intent", async () => {
  const writes = [];
  let version = 7;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(setup({ control_version: version }));
    assert.equal(url, base + "/sync-jobs");
    assert.equal(init.headers["X-CSRF-Token"], "synthetic-csrf");
    writes.push({ body: init.body, key: init.headers["Idempotency-Key"] });
    if (writes.length === 1) throw new TypeError("Synthetic lost response");
    return json({ id: opid, state: "pending" });
  };
  const api = synchronizationApi(id, "synthetic-csrf");
  const command = {
    chat_ids: [choice],
    since: "2026-10-08T00:00:00Z",
    until: "2026-10-09T00:00:00Z",
    max_records: 100,
    consent: true,
    issue_id: null,
    source_gap_id: null,
  };
  await assert.rejects(
    api.start(command, "stable-sync"),
    (e) => e.code === "SYNC_RESULT_UNCERTAIN",
  );
  version = 9;
  await api.start(command, "stable-sync");
  assert.deepEqual(writes[0], writes[1]);
  assert.equal(JSON.parse(writes[1].body).expected_version, 7);
  await assert.rejects(
    api.start({ ...command, max_records: 500 }, "stable-sync"),
    (e) => e.code === "IDEMPOTENCY_CONFLICT",
  );
});

test("sync timeline/cancel use owner backend without media URLs or provider administration", async () => {
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push([url, init]);
    if (url.endsWith("/setup")) return json(setup());
    if (url.includes("/timeline"))
      return new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
      });
    if (url.endsWith("/cancel")) return json({ id: opid, state: "cancelled" });
    if (url.endsWith("/chats"))
      return json([
        { id: choice, selected: true, kind: "group" },
        { id: "other", selected: false },
      ]);
    throw new Error("Unexpected route");
  };
  const api = synchronizationApi(id, "synthetic-csrf");
  assert.equal((await api.chats()).length, 1);
  await api.timeline(choice, "cursor one");
  await api.cancel(opid);
  assert(seen.every(([u, i]) => u.startsWith(base) && i.cache === "no-store"));
  const cancelled = seen.find(([u]) => u.endsWith("/cancel"));
  assert.equal(JSON.parse(cancelled[1].body).expected_version, 7);
  assert(seen.some(([u]) => u.includes("cursor=cursor%20one")));
});

test("discovery forwards pagination and exposes next offset without losing prior authority", async () => {
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup")) return json(setup());
    if (url.endsWith("/operations")) {
      assert.equal(JSON.parse(init.body).offset, 100);
      return json(op({ action: "discover", next_offset: 200 }));
    }
    if (url.endsWith("/chats"))
      return json([
        {
          id: choice,
          label: "Synthetic",
          selected: false,
          kind: "group",
          expires_at: null,
        },
      ]);
    throw new Error("Unexpected route");
  };
  assert.equal(
    (await liveConnectionApi("csrf").chats(id, 100)).next_offset,
    200,
  );
});

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

test("paused or unavailable setup reads authorization without queuing provider inspection", async () => {
  for (const extra of [
    { enabled: false, provider_sample_stale: true },
    { available: false },
  ]) {
    const routes = [];
    globalThis.fetch = async (url, init) => {
      routes.push([url, init.method]);
      if (url.endsWith("/setup")) return json(setup(extra));
      if (url.endsWith("/chats"))
        return json([
          { id: choice, label: "已授权会话", selected: true, expires_at: null },
        ]);
      throw new Error("unexpected mutation");
    };
    const api = liveConnectionApi("synthetic-csrf");
    const p = await api.pairing(id, true);
    if (extra.enabled === false) assert.equal(p.qr_available, false);
    assert.equal((await api.selection(id)).selected.length, 1);
    assert.ok(routes.every(([, method]) => method === "GET"));
  }
});

test("configuration-free withdrawal rereads persistent selection and keeps paused reception", async () => {
  let selected = true,
    version = 7;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(
        setup({ available: false, enabled: false, control_version: version }),
      );
    if (init.method === "PUT") {
      assert.deepEqual(JSON.parse(init.body), {
        expected_version: 7,
        selected_ids: [],
        consent: true,
      });
      selected = false;
      version++;
      return json(
        setup({ available: false, enabled: false, control_version: version }),
      );
    }
    if (url.endsWith("/chats"))
      return json(
        selected
          ? [
              {
                id: choice,
                label: "已授权会话",
                selected: true,
                expires_at: null,
              },
            ]
          : [],
      );
    throw new Error("unexpected route");
  };
  const api = liveConnectionApi("synthetic-csrf");
  const saved = await api.save(id, await api.selection(id), [], "unused");
  assert.equal(saved.selected.length, 0);
  assert.equal(saved.control_version, 8);
  assert.equal((await api.pairing(id)).enabled, false);
});

test("last terminal failure remains visible without blocking new user intention", async () => {
  globalThis.fetch = async (url) =>
    url.endsWith("/setup")
      ? json(setup({ last_operation_id: opid }))
      : json(
          op({
            state: "failed",
            action: "recover",
            error_code: "WAHA_UNAVAILABLE",
          }),
        );
  const value = await liveConnectionApi("synthetic-csrf").pairing(id);
  assert.equal(value.operation_id, null);
  assert.equal(value.operation_state, "failed");
  assert.equal(value.operation_action, "recover");
  assert.equal(value.operation_error, "WAHA_UNAVAILABLE");
});

function memoryStorage() {
  const rows = new Map();
  return {
    get length() {
      return rows.size;
    },
    key: (i) => [...rows.keys()][i] ?? null,
    getItem: (key) => rows.get(key) ?? null,
    setItem: (key, value) => rows.set(key, value),
    removeItem: (key) => rows.delete(key),
  };
}

test("lost discovery page survives reload and restores the exact offset, limit, version, key and next cursor", async () => {
  globalThis.sessionStorage = memoryStorage();
  const posts = [];
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(setup({ control_version: posts.length ? 99 : 7 }));
    if (url.endsWith("/chats"))
      return json([
        {
          id: choice,
          label: "Synthetic later page",
          selected: false,
          expires_at: null,
        },
      ]);
    assert.equal(url, base + "/operations");
    posts.push({
      body: JSON.parse(init.body),
      key: init.headers["Idempotency-Key"],
    });
    if (posts.length === 1) throw new TypeError("Synthetic lost page response");
    return json(
      op({
        action: "discover",
        control_version: posts.at(-1).body.expected_version,
        next_offset: posts.at(-1).body.offset + 100,
      }),
      202,
    );
  };
  await assert.rejects(
    liveConnectionApi("synthetic-csrf").chats(id, 200),
    (e) => e.code === "OPERATION_RESULT_UNKNOWN",
  );
  const reloaded = liveConnectionApi("synthetic-csrf");
  assert.equal((await reloaded.pairing(id, true)).retry_available, true);
  await assert.rejects(
    reloaded.chats(id, 0),
    (e) => e.code === "OPERATION_RESULT_UNKNOWN",
  );
  assert.equal(posts.length, 1);
  const restored = await reloaded.retry(id);
  assert.deepEqual(posts[0], posts[1]);
  assert.deepEqual(posts[1].body, {
    action: "discover",
    expected_version: 7,
    offset: 200,
    limit: 100,
  });
  assert.equal(restored.next_offset, 300);
  assert.equal(restored.items[0].id, choice);
  assert.equal(sessionStorage.length, 0);
  assert.equal(
    (await reloaded.chats(id, restored.next_offset)).next_offset,
    400,
  );
  assert.equal(posts[2].body.expected_version, 99);
  assert.notEqual(posts[2].key, posts[1].key);
});

test("restored discovery retains an explicitly stored page size and rejects malformed pagination metadata", async () => {
  globalThis.sessionStorage = memoryStorage();
  const stored = {
    key: "synthetic-page-key",
    body: { action: "discover", expected_version: 4, offset: 80, limit: 40 },
  };
  sessionStorage.setItem(
    "gigmate-control-attempt:" + id,
    JSON.stringify(stored),
  );
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/operations")) {
      assert.deepEqual(JSON.parse(init.body), stored.body);
      assert.equal(init.headers["Idempotency-Key"], stored.key);
      return json(op({ action: "discover", next_offset: 120 }));
    }
    if (url.endsWith("/chats")) return json([]);
    return json(setup());
  };
  assert.equal(
    (await liveConnectionApi("synthetic-csrf").retry(id)).next_offset,
    120,
  );
  for (const body of [
    { ...stored.body, offset: -1 },
    { ...stored.body, offset: 10001 },
    { ...stored.body, limit: 101 },
    { ...stored.body, offset: "80" },
    { ...stored.body, action: "connect" },
  ]) {
    sessionStorage.setItem(
      "gigmate-control-attempt:" + id,
      JSON.stringify({ ...stored, body }),
    );
    assert.equal(
      (await liveConnectionApi("synthetic-csrf").pairing(id)).retry_available,
      false,
    );
  }
});
test("lost response survives adapter recreation and only explicit original-key retry submits", async () => {
  globalThis.sessionStorage = memoryStorage();
  const posts = [];
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(
        setup({
          provider_sample_stale: true,
          control_version: posts.length ? 99 : 0,
        }),
      );
    assert.equal(init.method, "POST");
    posts.push([JSON.parse(init.body), init.headers["Idempotency-Key"]]);
    if (posts.length === 1) throw new TypeError("lost");
    return json(op());
  };
  const before = liveConnectionApi("synthetic-csrf");
  await assert.rejects(
    before.start(id, "original-key"),
    (e) => e.code === "OPERATION_RESULT_UNKNOWN",
  );
  const after = liveConnectionApi("synthetic-csrf");
  assert.equal((await after.pairing(id, true)).retry_available, true);
  await assert.rejects(
    after.restart(id, "new-key"),
    (e) => e.code === "OPERATION_RESULT_UNKNOWN",
  );
  assert.equal(posts.length, 1);
  await after.retry(id);
  assert.deepEqual(posts[0], posts[1]);
  assert.equal(posts[1][0].expected_version, 0);
  assert.equal(globalThis.sessionStorage.length, 0);
});

test("logout removes only request-attempt metadata", () => {
  globalThis.sessionStorage = memoryStorage();
  sessionStorage.setItem("gigmate-control-attempt:" + id, "synthetic");
  sessionStorage.setItem("unrelated-setting", "keep");
  clearConnectionAttempts();
  assert.equal(sessionStorage.length, 1);
  assert.equal(sessionStorage.getItem("unrelated-setting"), "keep");
});

test("partial JSON or gateway failure after submission remains unknown without another write", async () => {
  for (const reply of [
    () => new Response("{"),
    () => json(null),
    () => new Response("gateway", { status: 502 }),
  ]) {
    let writes = 0;
    globalThis.fetch = async (url, init) => {
      if (url.endsWith("/setup")) return json(setup());
      writes++;
      return reply();
    };
    const api = liveConnectionApi("synthetic-csrf");
    await assert.rejects(
      api.start(id, "original"),
      (e) => e.code === "OPERATION_RESULT_UNKNOWN",
    );
    assert.equal((await api.pairing(id, true)).retry_available, true);
    assert.equal(writes, 1);
  }
});

test("definite rejected operation permits a fresh intention but never retries automatically", async () => {
  let writes = 0;
  globalThis.fetch = async (url) => {
    if (url.endsWith("/setup")) return json(setup());
    writes++;
    return error("WAHA_SETUP_VERSION_CONFLICT", 409);
  };
  const api = liveConnectionApi("synthetic-csrf");
  await assert.rejects(
    api.start(id, "first"),
    (e) => e.code === "WAHA_SETUP_VERSION_CONFLICT",
  );
  assert.equal((await api.pairing(id)).retry_available, false);
  assert.equal(writes, 1);
  await assert.rejects(
    api.start(id, "second"),
    (e) => e.code === "WAHA_SETUP_VERSION_CONFLICT",
  );
  assert.equal(writes, 2);
});

test("selection save adopts server persistent IDs rather than expired discovery IDs", async () => {
  let saved = false;
  const persistent = "00000000-0000-4000-8000-000000000073";
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(setup({ control_version: saved ? 8 : 7 }));
    if (init.method === "PUT") {
      assert.deepEqual(JSON.parse(init.body).selected_ids, [choice]);
      saved = true;
      return json(setup());
    }
    return json([
      {
        id: saved ? persistent : choice,
        label: "Synthetic participant",
        selected: saved,
        expires_at: saved ? null : "2026-10-09T00:00:00Z",
      },
    ]);
  };
  const api = liveConnectionApi("synthetic-csrf");
  const before = await api.selection(id);
  const result = await api.save(id, before, before.choices, "unused");
  assert.equal(result.selected[0].id, persistent);
  assert.equal(result.selected[0].expires_at, null);
  assert.equal(result.control_version, 8);
});

test("connector and issue pagination encodes cursors and denies stale login", async () => {
  const paths = [];
  globalThis.fetch = async (url) => {
    paths.push(url);
    return new Response(
      JSON.stringify({
        items: [{ id: paths.length }],
        next_cursor: paths.length % 2 ? "next/+=" : null,
      }),
    );
  };
  const api = liveConnectionApi("synthetic-csrf");
  assert.equal((await api.connectors()).length, 2);
  assert.equal((await api.issues(id)).length, 2);
  assert.ok(paths[1].endsWith("cursor=next%2F%2B%3D"));
  globalThis.fetch = async () => error("UNAUTHENTICATED", 401);
  await assert.rejects(api.connectors(), (e) => e.code === "UNAUTHENTICATED");
});

test("malformed or cyclic pages and non-PNG QR fail clearly", async () => {
  const api = liveConnectionApi("synthetic-csrf");
  for (const page of [{ items: [], next_cursor: "same" }, { data: [] }]) {
    globalThis.fetch = async () => new Response(JSON.stringify(page));
    await assert.rejects(
      api.connectors(),
      (e) => e.code === "INVALID_RESPONSE",
    );
  }
  globalThis.fetch = async () =>
    new Response("html", { headers: { "Content-Type": "text/html" } });
  await assert.rejects(api.qr(id), (e) => e.code === "WAHA_INVALID_QR");
});

test("a cancelled accepted operation remains definite, with no original request to retry", async () => {
  globalThis.fetch = async (url) =>
    url.endsWith("/setup") ? json(setup()) : json(op({ state: "cancelled" }));
  const api = liveConnectionApi("synthetic-csrf");
  await assert.rejects(
    api.start(id, "cancelled"),
    (e) => e.code === "WAHA_OPERATION_CANCELLED",
  );
  assert.equal((await api.pairing(id)).retry_available, false);
});

test("initial version-zero setup retains connect entry without a failed automatic inspection", async () => {
  let writes = 0;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/setup"))
      return json(
        setup({
          control_version: 0,
          provider_state: null,
          provider_sample_stale: true,
        }),
      );
    writes++;
    return error("WAHA_RESOURCE_NOT_FOUND", 404);
  };
  const api = liveConnectionApi("synthetic-csrf");
  assert.equal((await api.pairing(id)).available, true);
  assert.equal(writes, 0);
  assert.equal((await api.pairing(id, true)).available, true);
  assert.equal(writes, 1);
});
