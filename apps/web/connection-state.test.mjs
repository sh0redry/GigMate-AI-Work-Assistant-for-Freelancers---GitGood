import assert from "node:assert/strict";
import { test } from "node:test";
import {
  choiceExpired,
  connectionState,
  pendingIssues,
} from "./src/connection-state.ts";

test("stale and failed reads override even a previously connected provider", () => {
  const view = connectionState({
    enabled: true,
    uncertain: true,
    connected: true,
    state: "WORKING",
  });
  assert.equal(view.action, "refresh");
  assert.match(view.title, /暂时无法确认/);
  assert.equal(view.tone, "warning");
});
test("fresh failed, scanning, connected and paused states guide different actions", () => {
  for (const [state, connected, action, title] of [
    ["FAILED", false, "restart", /已断开/],
    ["STOPPED", false, "restart", /已断开/],
    ["SCAN_QR_CODE", false, "qr", /扫描二维码/],
    ["WORKING", true, "refresh", /✓ WhatsApp 已连接/],
    ["STARTING", false, "refresh", /正在确认/],
  ]) {
    const view = connectionState({
      enabled: true,
      uncertain: false,
      connected,
      state,
    });
    assert.equal(view.action, action);
    assert.match(view.title, title);
  }
  assert.equal(
    connectionState({
      enabled: false,
      uncertain: false,
      connected: true,
      state: "WORKING",
    }).action,
    "refresh",
  );
});
test("follow-up remains pending even if a historic acknowledgement exists", () => {
  const rows = [
    { acknowledged_at: null, resolution: null },
    { acknowledged_at: "synthetic", resolution: "needs_followup" },
    { acknowledged_at: "synthetic", resolution: "reviewed_no_import" },
  ];
  assert.deepEqual(pendingIssues(rows), rows.slice(0, 2));
});

test("new choices expire at their server deadline while persistent choices remain valid", () => {
  const deadline = Date.parse("2026-10-09T10:00:00Z");
  assert.equal(choiceExpired({ expires_at: null }, deadline), false);
  assert.equal(
    choiceExpired({ expires_at: "2026-10-09T10:00:00Z" }, deadline - 1),
    false,
  );
  assert.equal(
    choiceExpired({ expires_at: "2026-10-09T10:00:00Z" }, deadline),
    true,
  );
});
