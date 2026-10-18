const test = require("node:test"),
  assert = require("node:assert/strict");
const http = require("node:http");
const {
  needsSetup,
  validateProfile,
  updateAI,
  aiReady,
} = require("./settings.cjs");
const {
  newProfile,
  composeDocument,
  planCleanup,
  executeCleanup,
  OWNER,
} = require("./runtime.cjs");
const { listenLoopback, CSP } = require("./web-security.cjs");

test("existing profiles survive every installer fingerprint; invalid profiles refuse recovery", () => {
  for (const fingerprint of [
    undefined,
    "old-version",
    "copied-executable",
    "restored-backup",
  ])
    assert.equal(needsSetup({ fingerprint, secret: "encrypted" }), false);
  assert.equal(needsSetup(null), true);
  const profile = newProfile({
    username: "synthetic",
    password: "synthetic-password",
  });
  assert.equal(validateProfile(profile), profile);
  assert.throws(
    () => validateProfile({ ...profile, dbPassword: undefined }),
    /PRIVATE_PROFILE_UNREADABLE/,
  );
});

test("AI activation binds consent, valid pricing and explicit key removal", () => {
  const profile = newProfile({
    username: "synthetic",
    password: "synthetic-password",
    modelKey: "synthetic-key",
  });
  assert.equal(aiReady(profile), false);
  assert.throws(
    () => updateAI(profile, { aiEnabled: true }),
    /INVALID_SETTINGS/,
  );
  updateAI(profile, {
    aiEnabled: true,
    aiConsent: true,
    inputPrice: "0.001",
    outputPrice: "0.002",
  });
  assert.equal(aiReady(profile), true);
  const credentials = [profile.id, profile.connectionId, profile.dbPassword];
  updateAI(profile, { aiEnabled: false, modelKey: "" });
  assert.equal(aiReady(profile), false);
  assert.equal(profile.modelKey, "synthetic-key");
  updateAI(profile, { clearKey: true, aiEnabled: false });
  assert.equal(profile.modelKey, "");
  assert.deepEqual(
    [profile.id, profile.connectionId, profile.dbPassword],
    credentials,
  );
});

test("monitor cannot access model secrets and incomplete prices keep the worker offline", () => {
  const profile = newProfile({
    username: "synthetic",
    password: "synthetic-password",
    modelKey: "synthetic",
    aiEnabled: true,
    aiConsent: true,
    inputPrice: "0.001",
    outputPrice: "0.002",
  });
  const build = (p) =>
    composeDocument(p, "/synthetic", "http://127.0.0.1:27880");
  const doc = build(profile);
  assert.equal(doc.services.worker.environment.GIGMATE_LLM_LIVE, "1");
  assert.equal(
    doc.services.worker.environment.GIGMATE_LLM_COST_INPUT_USD_PER_1K,
    "0.001",
  );
  assert.deepEqual(doc.services.monitor.volumes, [
    "private-config:/workspace/local-data/waha-a02:ro",
  ]);
  assert.equal(
    doc.services.monitor.environment.GIGMATE_LLM_API_KEY_FILE,
    undefined,
  );
  assert.ok(
    doc.services.worker.volumes.includes("model-secrets:/run/desktop-model:ro"),
  );
  for (const inputPrice of ["", "NaN", "Infinity", "-1", "0.1usd"]) {
    assert.equal(
      build({ ...profile, inputPrice }).services.worker.environment
        .GIGMATE_LLM_LIVE,
      "0",
    );
  }
  assert.equal(
    build({ ...profile, aiEnabled: false }).services.worker.environment
      .GIGMATE_LLM_LIVE,
    "0",
  );
});

test("occupied persisted loopback port falls back without taking the other service", async () => {
  const occupied = http.createServer((_, res) => res.end("unrelated"));
  const own = http.createServer((_, res) => res.end("ours"));
  try {
    const used = await listenLoopback(occupied);
    const selected = await listenLoopback(own, used);
    assert.notEqual(selected, used);
    assert.equal(own.address().address, "127.0.0.1");
    const response = await fetch(`http://127.0.0.1:${used}`);
    assert.equal(await response.text(), "unrelated");
    assert.match(CSP, /media-src 'self' blob:/);
    assert.match(CSP, /frame-src 'self' blob:/);
    assert.match(CSP, /object-src 'none'/);
  } finally {
    occupied.closeAllConnections();
    own.closeAllConnections();
    await Promise.all([
      new Promise((r) => occupied.close(r)),
      new Promise((r) => own.close(r)),
    ]);
  }
});

test("explicit cleanup excludes current/legacy/unrelated resources; stale and forged selections refuse deletion", async () => {
  const removed = [];
  let changed = false;
  const execute = async (_, args) => {
    if (args[0] === "ps")
      return ["ours", "current", "legacy", "unrelated"].join("\n");
    if (args[0] === "volume" && args[1] === "ls") return "ours-data";
    if (args[0] === "inspect" || args[1] === "inspect") {
      const id = args[0] === "inspect" ? args[1] : args[2];
      const project =
        id === "legacy"
          ? "gigmate-waha-recovery"
          : id === "unrelated"
            ? "customer-database"
            : id === "current"
              ? "gigmate-desktop-abcdefab"
              : "gigmate-desktop-12345678";
      const labels = {
        "com.docker.compose.project": project,
        ...(id === "ours" || id === "current" || id === "ours-data"
          ? { [OWNER]: "true" }
          : {}),
      };
      return JSON.stringify([
        {
          Id: id,
          Name: id,
          Created: changed ? "changed" : "original",
          CreatedAt: changed ? "changed" : "original",
          Labels: labels,
          Config: { Labels: labels },
        },
      ]);
    }
    removed.push(args);
    return "";
  };
  const plan = await planCleanup("fake-docker", "gigmate-desktop-abcdefab", {
    execute,
  });
  assert.deepEqual(
    plan.map((p) => p.id),
    ["ours", "ours-data"],
  );
  assert.deepEqual(removed, []);
  const withLegacy = await planCleanup(
    "fake-docker",
    "gigmate-desktop-abcdefab",
    { execute, includeLegacy: true },
  );
  assert.ok(withLegacy.find((p) => p.id === "legacy" && p.legacy));
  await assert.rejects(
    executeCleanup("fake-docker", plan, ["container:unrelated"], { execute }),
    /CLEANUP_SELECTION_INVALID/,
  );
  await assert.rejects(
    executeCleanup("fake-docker", plan, ["container:ours", "container:ours"], {
      execute,
    }),
    /CLEANUP_SELECTION_INVALID/,
  );
  changed = true;
  await assert.rejects(
    executeCleanup("fake-docker", plan, ["container:ours"], { execute }),
    /CLEANUP_PLAN_CHANGED/,
  );
  assert.deepEqual(removed, []);
  changed = false;
  await executeCleanup("fake-docker", plan, ["container:ours"], { execute });
  assert.deepEqual(removed, [["rm", "-f", "ours"]]);
});
