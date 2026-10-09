# GigMate frontend user guide

## Chat types, names and pages — 2026-10-10

The chat-list follow-up is based on Andy's [PR #14](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/14), on `codex/d01-chat-list`, with `Andy_WAHA_message_sync` as the PR base. It depends on that branch's canonical chat-kind metadata. PR #15's October 9 delivery below has already merged into main; the original `Kyrie_Frontend` / `c702f0c` remains separate.

Rows show **个人聊天** (direct), **群聊** (group) or **类型未提供** (missing type). Search applies to loaded names/numbers. **会话类型 → 已授权** filters saved server authorization; pending checkbox changes are counted separately. Page controls offer 8/16/24 rows with previous/next and result counts. Filtering, paging or changing the page size retains all pending selections, including hidden ones. **保存会话授权** saves the full pending selection; **撤销全部授权** includes all pages. **放弃更改** reloads saved authorization. Search is local to the loaded catalog. If more server choices are available, explicitly use **载入更多会话（每批最多 100 个）**, then browse the expanded catalog with the page controls.

Names come from the integration service. A phone-only direct label shows **未提供昵称**; the frontend does not manufacture a nickname. **发现最近会话** refreshes labels provided by the server and may be unavailable while disconnected/paused. In the current upstream adapter, only provider `name` is used, so an available nickname elsewhere is not necessarily returned. The integration owner must fix that server mapping; rediscovery alone is not guaranteed to restore nicknames. Saved authorization may show an explicit unnamed/authorized fallback after candidate metadata expires. Neither paging nor discovering grants processing permission until you save.

For a safe preview, choose **D-01 演示预览 → 模拟扫码成功 → 发现最近会话**: 24 fictional choices cover three default pages. It does not connect a real account; leaving/reloading clears demo state. Native Windows and real nickname acceptance remain unverified in this batch.

Role D, 2026-10-09. [中文版](../zh/role-d-frontend-user-guide.md). D-01 uses main `5f9df37` / Andy's PR #11. Work in the attached `d01-pr11` worktree; the original `Kyrie_Frontend` / `c702f0c` checkout has not been merged. Replay still needs independent review; do not merge this batch yet.

## Environments and startup

| View | Purpose | Persistence |
| --- | --- | --- |
| D-01 演示预览 | Simulated scan, selection, pause/resume and revocation without login | Browser memory; leaving/reloading resets it |
| 工单回放 | Fictional messages, conflicts, merchant confirmation, internal calendar/tasks | Replay database; reload/logout do not reset it |
| WhatsApp 连接 | Your preprovisioned local connection; authenticated setup, QR, consent and issue review | Backend database and durable worker; consent survives reload |

One frontend process selects one backend. WAHA team setup creates a development login but no fictional orders. Check the environment rather than seeding fictional data into the WAHA database. Use the latest-main worktree for this frontend; an older backend without PR #11's routes must be upgraded by its maintainer before connection testing.

For replay, use the existing repository-root setup:

```text
docker compose --env-file .env.example -f infra/compose.yaml up --build -d --wait
```

Workspace: http://127.0.0.1:18080/ . Replay API: 18000; PostgreSQL host port: 54329. Existing data persists. Backend preparation is in [onboarding](getting-started.md). Do not reset another installation's database or volumes for these frontend tests.

For frontend development use Node 24.15.x/npm 11.12.x. Run `npm ci`, `npm run dev` from this worktree's `apps/web`, then open http://127.0.0.1:5173/ . The default proxy targets replay API 18000. Preview needs no Docker/API; login/replay require them.

For your already upgraded and running Andy team setup, use only the backend URL:

macOS/Linux:

```bash
GIGMATE_API_URL=http://127.0.0.1:18702 npm run dev
```

Windows PowerShell:

```powershell
$env:GIGMATE_API_URL = "http://127.0.0.1:18702"
npm run dev
```

Follow [Andy's local setup](role-a-team-local-development.md), using your own private configuration/session. `GIGMATE_LOCAL_PAIRING` and the Vite/Python bridge are retired. Development and deployed frontends use the same authenticated `/api/v1` routes. Provider credentials, session names and raw provider chat IDs stay server-side. Native Windows frontend runtime acceptance is still pending.

## Login/logout

Development login: `merchant` / `demo-only-change-me`, or the password selected at initial seed. This is separate from WhatsApp on your phone. After login choose connection or replay. Logout/expiry remove account data and transient QR; successful logout also clears saved request-attempt metadata. Reload requires signing in again, but saved authorization/business state remains in the backend. An unresolved request stores only opaque app IDs and its action/version/key in this tab's session storage where available, never credentials or pairing material.

## WhatsApp connection and authorization

1. Sign in and select **WhatsApp 连接**. No connection record means the integration owner must provision your installation; use **刷新连接** afterwards. The browser does not create arbitrary accounts/sessions or request provider credentials.
2. Use **开始连接** for an available initial setup, or **重新连接并获取二维码** for an eligible FAILED/STOPPED session. Wait for the operation result. A completed operation does not prove phone linking; only a fresh WORKING sample shows **WhatsApp 已连接**. Pending operations block another provider action.
3. When waiting for scan, QR loads automatically in memory. Scan it on the phone's linked-devices screen. **刷新二维码** replaces it; an image hides 30 seconds after retrieval and refreshes every 20 seconds while visible. Provider rotation may invalidate it sooner. Failed/stale reads, pause, logout and leaving the workspace clear it. Preview is not scannable.
4. For a lost response use **使用原请求核对**: it keeps the same body/version/key and backend idempotency. For `result_unknown`, use **核对未知操作（不重发）**, which queues read-only verification. Refresh to inspect pending/terminal results; never start a different restart merely because an old response was lost. Backend rejection, lease expiry and reconciliation remain authoritative.
5. **载入会话与授权** reads saved authorization and existing valid options, including when disconnected or paused. **发现最近会话** explicitly discovers up to 100 recent chats while connected. It may omit other/older chats; this is not history import. New choices expire after ten minutes. Labels are plain text and app UUIDs remain opaque.
6. Check the intended conversations, then **保存会话授权**. The summary shows unsaved vs server-synchronized choices and the saved count. Save obtains persistent selected IDs from the backend. Read consent does not enable automatic replies, send messages or confirm work orders. **放弃更改** restores the loaded choices.
7. Uncheck an existing chat and save to reduce consent, or use **撤销全部授权**. These actions work while disconnected, paused or provider configuration is unavailable, using the last successfully read authority version. A version change/read failure/lost save response disables another save until **重新载入会话**; with dirty choices the button says **放弃勾选并重新载入**. After expired choices, reload and rediscover before granting. Writes are never automatically repeated.
8. **暂停消息接收** denies reception without deleting the session/choices; **恢复消息接收** explicitly restores existing authorization. It does not promise to import missed messages. Reload authorization after its version changes. Keep browser and CLI authorization changes coordinated: CLI provision can intentionally replace the browser-saved allowlist.
9. Check provider connectivity, freshness, receiving permission and processing readiness separately. Review recovered outage intervals only after checking that no history import is needed, then check the confirmation and use **清除已恢复故障（count）**. This retains audit history and imports/deletes no messages. Active faults cannot be cleared.

Real phone linking, independent teammate review and native Windows runtime acceptance remain pending. See [D evidence](role-d-stage1-acceptance.md) and [Andy's implemented setup API](role-a-setup-api-acceptance.md).

## D-01 preview

Select **D-01 演示预览** → **模拟扫码成功** → **载入会话与授权** (or **发现最近会话**). Select fictional chats, save and check the count; edit/discard choices, pause/resume, simulate disconnection and revoke existing consent. A pause/version change requires rereading choices, as in live mode. Leaving/re-entering resets the preview. These operations create no real authorization and issue no business API requests.

## Replay acceptance

Assumes initial order v3. Dates are fixed 2026 examples in Hong Kong time. An existing database may already be v4; repeat/reload never resets it. Wait for each proposal before the next input; rapid different inputs can supersede earlier work before extraction.

| Step | Action | Expected display |
| --- | --- | --- |
| 1 | Login → 工单回放 → 虚构业务预约 | Order v3/context v4; formal 10/07 15:00–16:00, missing address; no proposal, original source and preparation task |
| 2 | Select 另一项已确认预约, return | Formal/source/current-vs-other labels follow selection; other booking 10/08 15:00–16:00 with no task; replay disabled with target guidance |
| 3 | 回放：15:00 冲突改期 | 10/08 15:00–16:00 proposal, conflict/disabled confirmation; formal/calendar/tasks unchanged; context v5, two messages |
| 4 | Repeat input | Already-processed notice; still one card/two messages/order v3 |
| 5 | 回放：16:30 可用时段 | New 10/08 16:30–17:30 proposal awaiting approval; old proposal invalidated/disabled; formal/order v3 unchanged; context v6, three messages |
| 6 | Click source reference | Scrolls to source with suffix, revision and timestamp |
| 7 | Confirm 16:30 card | Order v4; formal/calendar updated; card confirmed/disabled; old task cancelled/new pending; address remains missing |
| 8 | Inspect new task | Current main title like 10/08 15:30 准备 16:30 的虚构业务预约; due 10/08 15:30. Legacy rows may keep old titles; frontend does not rewrite them |
| 9 | Repeat 16:30, navigate, reload/sign in | Already processed; v4/two cards/three messages/two tasks persist; notices do not carry into other views |
| 10 | Logout, wrong password, correct password | Login form without false authentication error; Chinese wrong-password feedback blocks access; correct login succeeds |
| 11 | Optional: other / same development password | Only its own v3 order; no merchant-v4 data/other booking; replay disabled |

Calendar lists all account events and marks the selected order; tasks are filtered to it. Cancelled tasks remain history. Narrow windows may stack calendar/tasks below other panels; scroll to inspect them.

Use 刷新回放数据 to reread. Failed reads mark cached data stale and disable writes; successful recovery clears the error/stale marker. Changed sources/versions require review, never automatic confirmation retry. Restore service and refresh to reconcile uncertain write outcomes.

## Troubleshooting and remaining limits

- Empty list: check for WAHA 18702; use seeded replay.
- No proposal: check API/worker; duplicate fixtures create no fresh proposal. Persistent queued work needs backend-owner investigation.
- WAHA_ENGINE_MISMATCH: the backend could not verify the pinned server/engine. Ask the integration owner to check configuration; do not bypass validation. PR #11 handles its verified STOPPED case.
- Apple Silicon: PR #11 includes Andy's image/platform selection. This frontend batch does not verify actual phone pairing or upgrade the existing private installation.
- Phone rejects linking: retain its actual result for integration-owner review; QR display does not prove linking.

Replay needs further debugging/independent review: multi-conversation orders show only the first conversation; multiple API reads are not an atomic database snapshot; no complete worker-failure/long-queue UI, fixture reset, message-edit/revoke controls or general AI input. Backend remains authoritative for versions, sources, consent/ownership and conflicts. D-01 product consent is now implemented and tested synthetically; real WhatsApp delivery/pairing and automatic replies/sending are not established by this batch. Native Windows acceptance remains pending.

## Developer checks

From `apps/web` run `npm test`, `npm run check:api`, `npm run format:check`, `npm run build`. Also run `npx prettier --check *test.mjs` for test-file formatting. Build runs regressions first. Keep edits in D frontend/companion docs; do not patch Andy/B/C or shared contracts to repair demonstration setup. Actual evidence: [D acceptance log](role-d-stage1-acceptance.md).
