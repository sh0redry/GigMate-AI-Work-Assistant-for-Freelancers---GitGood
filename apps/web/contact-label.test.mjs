import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";
import { readFile } from "node:fs/promises";

// contact-label.ts imports the API helpers only for loading; the pure
// formatting functions are compiled on their own with stub dependencies.
async function load() {
  const dir = await mkdtemp(join(tmpdir(), "gigmate-contact-"));
  const source = (
    await readFile(new URL("./src/contact-label.ts", import.meta.url), "utf8")
  )
    .replace(`from "./i18n.ts"`, `from "./i18n.mjs"`)
    .replace(`from "./workspace-api"`, `from "./workspace-api.mjs"`);
  const out = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  await writeFile(join(dir, "contact-label.mjs"), out);
  await writeFile(join(dir, "i18n.mjs"), "export const t = (s) => s;");
  await writeFile(
    join(dir, "workspace-api.mjs"),
    "export async function allPages(api, path) { return api(path); }",
  );
  return import(pathToFileURL(join(dir, "contact-label.mjs")));
}

test("WhatsApp chat ids become phone numbers; others never get a made-up number", async () => {
  const { contactLabel } = await load();
  assert.equal(contactLabel("85291234567@c.us"), "+852 9123 4567");
  assert.equal(contactLabel("8613812345678@c.us"), "+86 138 1234 5678");
  assert.equal(contactLabel("447700900123@c.us"), "+447700900123");
  assert.equal(contactLabel("123456789012345@lid"), "号码未公开的联系人");
  assert.equal(contactLabel("120363000000000000@g.us"), "WhatsApp 群组");
  assert.equal(contactLabel("synthetic:00000000-0000"), "号码未公开的联系人");
  assert.equal(contactLabel(undefined), "未知联系人");
});

test("items are ordered strictly by time, oldest first, ties by id", async () => {
  const { byTime } = await load();
  const items = [
    { id: "b", at: "2026-10-18T06:00:00Z" },
    { id: "c", at: "2026-10-17T23:00:00Z" },
    { id: "a", at: "2026-10-18T06:00:00Z" },
  ];
  assert.deepEqual(
    [...items].sort(byTime((i) => i.at)).map((i) => i.id),
    ["c", "a", "b"],
  );
});

test("contact labels never block the page when the list cannot be read", async () => {
  const { loadContactLabels } = await load();
  const failing = async () => {
    throw new Error("offline");
  };
  assert.equal((await loadContactLabels(failing)).size, 0);
  const ok = async () => [
    { id: "x", provider_conversation_id: "85261234567@c.us" },
  ];
  assert.equal((await loadContactLabels(ok)).get("x"), "+852 6123 4567");
});

test("short time is shown in Hong Kong time", async () => {
  const { shortTime } = await load();
  assert.equal(shortTime("2026-10-18T06:05:00Z"), "10/18 14:05");
  assert.equal(shortTime("not a date"), "");
});
