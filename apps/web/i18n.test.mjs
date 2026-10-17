import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { readFile, readdir } from "node:fs/promises";
import ts from "typescript";
import { t, setLocale, localized } from "./src/i18n.ts";
import { english, cantonese } from "./src/locales.ts";
afterEach(() => setLocale("zh"));
const placeholders = (s) =>
  [...new Set([...s.matchAll(/\{(\d+)\}/g)].map((m) => m[1]))].sort();
test("both catalogs cover the same UI keys and preserve every dynamic placeholder", () => {
  assert.deepEqual(Object.keys(english).sort(), Object.keys(cantonese).sort());
  for (const [key, value] of Object.entries(english)) {
    assert.deepEqual(placeholders(value), placeholders(key), key);
    assert.deepEqual(placeholders(cantonese[key]), placeholders(key), key);
    assert.ok(value.length && cantonese[key].length, key);
  }
});
test("UI literals and static UI dictionaries have English and Cantonese entries", async () => {
  const missing = new Set();
  for (const file of (await readdir(new URL("./src", import.meta.url))).filter(
    (f) => /\.(ts|tsx)$/.test(f) && !["i18n.ts", "locales.ts"].includes(f),
  )) {
    const source = await readFile(
      new URL("./src/" + file, import.meta.url),
      "utf8",
    );
    const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
    function visit(node) {
      if (ts.isStringLiteral(node) && /[\u3400-\u9fff]/.test(node.text)) {
        const direct =
          ts.isCallExpression(node.parent) &&
          node.parent.expression.getText(sf) === "t" &&
          node.parent.arguments[0] === node;
        let inDictionary = false,
          parent = node.parent;
        while (parent) {
          if (
            ts.isCallExpression(parent) &&
            parent.expression.getText(sf) === "localized"
          )
            inDictionary = true;
          parent = parent.parent;
        }
        if ((direct || inDictionary) && !(node.text in english))
          missing.add(node.text);
      }
      ts.forEachChild(node, visit);
    }
    visit(sf);
  }
  assert.deepEqual([...missing], []);
});
test("labels follow language changes and formatted UI messages can change language later", () => {
  const labels = localized({ status: "已确认" });
  const old = t("内容更新于：{0}", "synthetic:10:00");
  setLocale("en");
  assert.equal(labels.status, "Confirmed");
  assert.equal(t(old), "Content updated: synthetic:10:00");
  assert.equal(
    t("已保存 {0} 个会话授权，自动回复未开启。", 3),
    "Saved permission for 3 chats. Automatic replies remain off.",
  );
  setLocale("yue");
  assert.equal(t("今天有什么安排"), "今日有咩安排");
  setLocale("zh");
  assert.equal(t("Confirmed"), "已确认");
});
test("format substitutions preserve raw customer text including HTML and UI-label matches", () => {
  const raw = "业务工作台 <img onerror=synthetic> {0}";
  setLocale("en");
  assert.equal(t("{0}：{1}", "Address", raw), "Address: " + raw);
  assert.equal(t("{0}", raw), raw);
});
