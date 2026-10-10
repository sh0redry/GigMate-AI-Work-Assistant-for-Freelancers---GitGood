import assert from "node:assert/strict";
import { test } from "node:test";
import { choiceKind, choiceDisplay, choicePage } from "./src/chat-choices.ts";

const choices = Array.from({ length: 25 }, (_, i) => ({
  id: `synthetic:${i}`,
  label: `示例会话 ${String(i).padStart(2, "0")}`,
  selected: i === 0 || i === 17,
  expires_at: null,
  kind: i % 2 ? "group" : "direct",
}));

test("chat type follows server kind, never a group-like name or opaque ID", () => {
  assert.equal(
    choiceDisplay({ ...choices[0], label: "Example Group" }).kindLabel,
    "个人聊天",
  );
  assert.equal(
    choiceDisplay({ ...choices[1], label: "Example customer" }).kindLabel,
    "群聊",
  );
  for (const kind of [undefined, null, "unrecognized"]) {
    assert.equal(choiceKind({ ...choices[0], kind }), "unknown");
    assert.equal(
      choiceDisplay({ ...choices[0], kind }).kindLabel,
      "类型未提供",
    );
  }
});

test("provider nicknames and numbers remain intact; empty labels have explicit fallbacks", () => {
  assert.equal(
    choiceDisplay({ ...choices[0], label: " 客户昵称 · 工作 " }).label,
    "客户昵称 · 工作",
  );
  const phone = choiceDisplay({ ...choices[0], label: "+1 202 555 0101" });
  assert.equal(phone.label, "+1 202 555 0101");
  assert.equal(phone.numberOnly, true);
  assert.equal(
    choiceDisplay({ ...choices[1], label: "123456" }).numberOnly,
    false,
  );
  assert.equal(
    choiceDisplay({ ...choices[1], label: "", selected: false }).label,
    "未命名群聊",
  );
  assert.equal(
    choiceDisplay({
      ...choices[1],
      label: "Authorized conversation",
      selected: true,
    }).label,
    "已授权群聊",
  );
});

test("local pages are bounded, ordered and clamp after a catalog shrinks", () => {
  assert.deepEqual(
    choicePage(choices, "", "all", 2, 8).items.map((x) => x.choice.id),
    choices.slice(8, 16).map((x) => x.id),
  );
  const last = choicePage(choices, "", "all", 99, 8);
  assert.equal(last.page, 4);
  assert.equal(last.items.length, 1);
  assert.equal(last.start, 25);
  assert.equal(last.end, 25);
  assert.equal(choicePage(choices.slice(0, 2), "", "all", 4, 8).page, 1);
  assert.equal(choicePage(choices, "", "all", -5, 0).items.length, 8);
});

test("search, type and persisted authorization filters apply before pagination", () => {
  const groups = choicePage(choices, "", "group", 2, 8);
  assert.equal(groups.total, 12);
  assert.equal(groups.items.length, 4);
  assert.ok(groups.items.every((x) => x.kind === "group"));
  assert.equal(choicePage(choices, "  示例会话 1  ", "all", 1, 8).total, 10);
  assert.deepEqual(
    choicePage(choices, "", "selected", 1, 8).items.map((x) => x.choice.id),
    ["synthetic:0", "synthetic:17"],
  );
  const unknown = { ...choices[0], kind: undefined };
  assert.equal(choicePage([unknown], "", "unknown", 1, 8).total, 1);
});

test("zero results are explicit, alternate sizes work and viewing never mutates consent", () => {
  const before = JSON.stringify(choices);
  const empty = choicePage(choices, "missing fixture", "all", 4, 16);
  assert.deepEqual(
    [empty.page, empty.pages, empty.start, empty.end, empty.total],
    [1, 1, 0, 0, 0],
  );
  assert.equal(choicePage(choices, "", "all", 1, 16).items.length, 16);
  assert.equal(choicePage(choices, "", "all", 1, 24).items.length, 24);
  assert.equal(JSON.stringify(choices), before);
});
