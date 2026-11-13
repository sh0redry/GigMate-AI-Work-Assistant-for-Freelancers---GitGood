const test = require("node:test"),
  assert = require("node:assert/strict");
const {
  localDockerHost,
  newProfile,
  composeDocument,
  projectFor,
} = require("./runtime.cjs");
test("only local Unix sockets and local Windows named pipes may be managed", () => {
  for (const host of [
    undefined,
    "unix:///var/run/docker.sock",
    "npipe:////./pipe/docker_engine",
  ])
    assert.equal(localDockerHost(host), true);
  for (const host of [
    "ssh://team.example",
    "tcp://localhost:2375",
    "npipe:////server/pipe/docker_engine",
  ])
    assert.equal(localDockerHost(host), false);
});
test("fresh profiles have independent credentials and empty isolated volumes", () => {
  const a = newProfile({
      username: "merchant",
      password: "synthetic-password",
      modelKey: "sk-synthetic-do-not-use",
    }),
    b = newProfile({ username: "merchant", password: "synthetic-password" });
  assert.notEqual(a.dbPassword, b.dbPassword);
  assert.notEqual(a.connectionId, b.connectionId);
  assert.notEqual(projectFor(a), projectFor(b));
  const doc = composeDocument(
      a,
      "/synthetic-runtime",
      "http://127.0.0.1:27880",
      "arm64",
    ),
    text = JSON.stringify(doc);
  assert.equal(text.includes(a.modelKey), false);
  assert.equal(text.includes(a.password), false);
  assert.deepEqual(doc.services.ingress.ports, ["127.0.0.1::8000"]);
  assert.equal(doc.services.db.ports, undefined);
  assert.equal(doc.services.waha.ports, undefined);
  assert.equal(doc.services.ingress.environment.APP_MODE, "product");
  assert.equal(
    doc.services.ingress.environment.TRUSTED_ORIGINS,
    "http://127.0.0.1:27880",
  );
  assert.match(doc.services.waha.image, /@sha256:/);
  assert.match(doc.services.waha.image, /:arm-/);
  assert.equal(
    doc.services.ingress.volumes.includes(
      "private-config:/run/desktop-config:ro",
    ),
    true,
  );
  assert.equal(doc.services.worker.command.at(-1), "gigmate.worker");
});
test("closing during startup cancels only owned command trees and still permits cleanup", async () => {
  const runtime = require("./runtime.cjs");
  const operation = runtime.run(process.execPath, [
    "-e",
    "setInterval(()=>{},1000)",
  ]);
  const rejected = assert.rejects(
    operation,
    /LOCAL_SERVICE_COMMAND_FAILED|APP_STOPPING/,
  );
  await new Promise((resolve) => setTimeout(resolve, 40));
  await runtime.cancelActiveCommands();
  await rejected;
  await assert.rejects(
    runtime.run(process.execPath, ["-e", "process.exit(0)"]),
    /APP_STOPPING/,
  );
  assert.equal(
    await runtime.run(
      process.execPath,
      ["-e", "process.stdout.write('cleanup-ready')"],
      { allowAfterCancel: true },
    ),
    "cleanup-ready",
  );
});

test("omitting an optional model key keeps live AI off while retaining worker readiness checks", () => {
  const empty = newProfile({
    username: "merchant",
    password: "synthetic-password",
    modelKey: "",
  });
  const doc = composeDocument(
    empty,
    "/synthetic-runtime",
    "http://127.0.0.1:27880",
  );
  assert.equal(
    doc.services.worker.environment.GIGMATE_EXTRACTION_PROVIDER,
    "disabled",
  );
  assert.equal(doc.services.worker.environment.GIGMATE_LLM_LIVE, "0");
  assert.equal(
    doc.services.worker.environment.GIGMATE_LLM_ALLOW_LIVE_ORIGIN,
    "0",
  );
  assert.ok(doc.services.worker.healthcheck);
  const enabled = composeDocument(
    {
      ...empty,
      modelKey: "sk-synthetic-no-real-key",
      aiEnabled: true,
      inputPrice: "0.001",
      outputPrice: "0.002",
      budget: "0.10",
    },
    "/synthetic-runtime",
    "http://127.0.0.1:27880",
  );
  assert.equal(enabled.services.worker.environment.GIGMATE_LLM_LIVE, "1");
});
