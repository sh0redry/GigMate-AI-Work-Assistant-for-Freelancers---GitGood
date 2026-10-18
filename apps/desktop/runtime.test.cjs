const test = require("node:test"),
  assert = require("node:assert/strict");
const {
  localDockerHost,
  newProfile,
  composeDocument,
  cleanOwnedDocker,
  OWNER,
  isOwnedResource,
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
test("an unlabelled similarly named project is not a deletion target", () => {
  assert.equal(
    isOwnedResource({
      "com.docker.compose.project": "gigmate-customer-project",
    }),
    false,
  );
  assert.equal(
    isOwnedResource({ "com.docker.compose.project": "gigmate-waha-a02" }),
    true,
  );
  assert.equal(isOwnedResource({ [OWNER]: "true" }), true);
});
test("clean installation deletes inspected GigMate resources and preserves unrelated data", async () => {
  const deleted = [];
  const execute = async (_, args) => {
    if (args[0] === "ps") return "ours\nlegacy\nunrelated\n";
    if (args[0] === "inspect") {
      const labels =
        args[1] === "ours"
          ? { [OWNER]: "true" }
          : args[1] === "legacy"
            ? { "com.docker.compose.project": "gigmate-waha-a02" }
            : { "com.docker.compose.project": "customer-database" };
      return JSON.stringify([{ Config: { Labels: labels } }]);
    }
    if (args[0] === "volume" && args[1] === "ls")
      return "ours-data\nother-data\n";
    if (args[0] === "volume" && args[1] === "inspect")
      return JSON.stringify([
        {
          Labels:
            args[2] === "ours-data"
              ? { [OWNER]: "true" }
              : { "com.docker.compose.project": "customer-database" },
        },
      ]);
    deleted.push(args);
    return "";
  };
  await cleanOwnedDocker("synthetic-docker", { execute });
  assert.deepEqual(deleted, [
    ["rm", "-f", "ours"],
    ["rm", "-f", "legacy"],
    ["volume", "rm", "ours-data"],
  ]);
  assert.equal(
    deleted.some((args) => args.includes("prune")),
    false,
  );
});
