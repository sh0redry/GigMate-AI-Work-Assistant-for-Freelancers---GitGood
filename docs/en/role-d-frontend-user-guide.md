# GigMate frontend user guide

**D-03 review follow-up (2026-10-14):** the approval candidate includes reconciled #24/main and a safe-storage fix. If the browser rejects storage access, the page still reads drafts but cannot submit. If a verified response returns but journal cleanup fails, the saved intent is retained and new submissions remain blocked; restore storage, reopen and explicitly reconcile the original key. Current D-03 frontend suite: 105 passed. #23 has updated its upload/main compatibility; C/A sending still remains pending.

**PR #24 compatibility update:** the D-02 branch now includes accepted main e066b0c (#21). Its private attachment adapter follows the selected environment for reads, previews, downloads and original-key requests; model activation remains disabled by default. Main still does not contain D-02 until #24 merges.

Updated 2026-10-14, Hong Kong time. [中文版](../zh/role-d-frontend-user-guide.md). For code explanations, read [Kyrie's beginner guide](kyrie-learning-guide.md).

This guide now describes `codex/d03-approvals`, composed from the unmerged D-02 PR #24 and C approval PR #22; it is **not merged main**. The approval dependency still needs its repeated-reissue fix. Main has advanced to `e066b0c` through #21, which does not itself add C approvals. The consolidated D-02 changes are now prepared for PR submission under Kyrie’s updated instruction. A PR asks teammates to review; it does not put the feature into main. The ordinary main checkout can still show old demo controls. Locate D with `git worktree list`; do not reset your WhatsApp session to fix a frontend version mismatch.

## 1 Current pages and capability

Before login there is only the GigMate account form, with blank inputs and a public development hint (`merchant` / `demo-only-change-me`; changed passwords take precedence). GigMate sign-in is separate from phone WhatsApp login. After login, **业务工作台** is the default. The isolated environment has **业务工作台** and **回复审批**, with fictional data; **WhatsApp 连接** appears only in the actual connection environment (or the published deployment). Isolated use never mounts the connection page or issues its connector requests.

D-01 preview, simulated pairing/disconnection and work-order replay controls have been removed from user UI, including their simulator implementation. Synthetic fixtures remain in developer tests without a user entry. Existing seeded records are not deleted by removing buttons.

Kyrie reports team WAHA connections are working; this update did not retest all phones. Connection and consent do not establish extraction/automatic creation/sending. Order creation, lifecycle mutation and sending remain unavailable. Reply approval is available only with the matching C API and stores a local decision; it does not send WhatsApp messages.

## 2 Switch environments in one click

The persistent banner names the current environment and offers **切换到真实连接 / 切换到隔离测试**. Click once; no frontend restart or code change is needed. Navigation opens a fresh login form and clears page account/password/business/QR state. Sign in again. Session cookies and uncertain request metadata are separated; orders, chats and consent are not copied. Switching is not server logout or cancellation of accepted jobs. Use **退出** before switching if server logout is required; return to the original environment to reconcile unknown results rather than create a new request. Switching is blocked while an operation is busy.

| Environment | Data and effect | Purpose |
| --- | --- | --- |
| **真实连接（本机开发）** | Your own WAHA, local business database and authorized chats; operations affect these records | Verify actual connection/consent and existing business. Still local development, not a production release |
| **隔离测试（虚构数据）** | A separate test database with fictional orders/messages/calendar/tasks | Practice and verify business flows without real WhatsApp chats |

The initial default is isolated. `/environments/real/` or `/environments/isolated/` preserves selection on reload. The banner shows its backend address; a failed backend never silently falls back to the other environment.

**First-time setup still requires two backends.** The switch routes requests; it does not provision databases or start services. Prepare the actual connection backend with [team local setup](role-a-team-local-development.md), and a separately migrated/seeded database or schema with deterministic worker using [getting started](getting-started.md). Never reuse real data or a WAHA session for fictional fixtures. Different ports can still mistakenly share a database; the maintainer must establish isolation. The frontend cannot inspect that configuration and rejects identical backend ports.

In the **D worktree's apps/web**, using Node 24.15.x/npm 11.12.x:

```bash
npm ci
npm run dev
```

Defaults: actual connection backend `http://127.0.0.1:18702`, isolated backend `http://127.0.0.1:18000`. Configure alternate ports once at startup, then switch in the page:

```bash
GIGMATE_REAL_API_URL=http://127.0.0.1:18702 GIGMATE_ISOLATED_API_URL=http://127.0.0.1:18012 npm run dev
```

Windows PowerShell:

```powershell
npm ci
$env:GIGMATE_REAL_API_URL = "http://127.0.0.1:18702"
$env:GIGMATE_ISOLATED_API_URL = "http://127.0.0.1:18012"
npm run dev
```

18012 is this preview's disposable backend; use your prepared port on another machine. `GIGMATE_DEFAULT_ENV=real` changes the initial default. Legacy `GIGMATE_API_URL` now aliases the **isolated target only**; old WAHA-target commands must migrate to `GIGMATE_REAL_API_URL` to avoid incorrect labels. Restart Vite after address changes. Both backends' `TRUSTED_ORIGINS` must allow the actual frontend origin, e.g. `http://127.0.0.1:5178`; origin/session/CSRF checks remain enforced.

The public hint applies to default development installations, not WAHA administration or phone credentials. Changed installation passwords take precedence. Production provisioning remains pending. Published `npm run build` output uses its deployment's `/api` and excludes local switching/development-password hints; these are Vite development features.

Developer self-check exception: `python scripts/check_waha_setup.py --run --frontend` creates a disposable synthetic provider and database. Its **合成连接自检（虚构数据）** page has connection controls for testing, a non-scannable fixture QR, and no environment switch. The runner supplies `GIGMATE_SYNTHETIC_PROVIDER=1`, an explicit 18802 connector target and `GIGMATE_DEFAULT_ENV=real`; Vite rejects this mode without an explicit target/default and disables the second proxy. The route name `real` selects the connector workflow, while the label states that all resources are fictional. This is not the ordinary isolated business workspace and does not connect a real phone. Do not set this flag for your actual WAHA installation.

## 3 Connection and chat consent

This page is available in **真实连接（本机开发）** only. If you are in isolated testing, use the top environment switch and sign in again first.

1. Sign in and choose **WhatsApp 连接**. A fresh connected state needs no new pairing, but processing still requires explicitly saved conversation authorization.
2. Missing connection records require account provisioning review and **刷新连接**. Read failure is different from an unconfigured account.
3. If pairing is required, use the available **开始连接** or **重新连接并获取二维码**, then phone WhatsApp → Linked devices. Wait for the durable operation. A displayed QR is not successful phone pairing; inspect fresh state.
4. QR stays in memory, hides after 30 seconds, and refreshes about every 20 seconds while visible; provider rotation can be earlier. Pause, logout, navigation and unreliable reads clear it. Refresh state before retry, without reusing stale images.
5. **载入会话与授权** reads saved choices. While connected, **发现最近会话** loads up to 100 candidates per batch, with explicit load-more. Discovery is not complete history import.
6. Check and **保存会话授权** to grant processing. Search/type filters and 8/16/24-row pages use loaded choices, preserving hidden selections. **已授权** filters saved facts, not unsaved checks.
7. Uncheck/save to reduce consent; **撤销全部授权** covers all pages. Existing consent remains readable/withdrawable while disconnected, paused or provider configuration is unavailable. **放弃更改** restores saved facts.
8. New candidates normally expire after ten minutes. Expiry, changed authority, read failure or a lost save response requires reload/review before another save. Rediscovery may refresh labels but cannot guarantee recovery of an upstream-missing nickname; number-only labels explain it.
9. **暂停消息接收** suspends reception; **恢复消息接收** restores existing consent without promising gap import. Read/process permission is not automatic reply permission or formal order confirmation.

Lost response: **使用原请求核对** keeps the original command/parameters/identity. A server `result_unknown` requires **核对未知操作（不重发）**; do not substitute a fresh restart. Provider connectivity, processing health and history completeness are separate.

After a fault recovers, inspect its interval and explicitly confirm no history import is needed before **清除已恢复故障**. It removes a pending marker while retaining audit, cannot clear active faults, and imports/deletes no messages. Timeline/sync progress and media metadata do not prove work-order extraction or attachment parsing.

## 4 Business workspace

Search and filter order status. A hidden selected order remains open with a notice, without automatic selection changes. Empty orders can be truthful; a connection does not create them. The page explains unavailable automatic/manual creation and supplies no fake-data button.

Details show version, schedule, address and field state; missing address remains missing. Sources identify exact message revisions. Choose all or one linked conversation; switch to all if a source target is hidden. Missing revisions remain labeled for review rather than silently replaced with newer text.

Proposal cards separate proposer, customer confirmation and merchant approval. Only schedule confirmation is enabled: **核对并确认安排**, compare old/new/source/versions, check explicit consent, then **确认并同步安排**. Conflict, invalidation, missing/revoked/ambiguous provenance, stale reads, terminal orders and unsupported fields are blocked. Refreshed changes invalidate the old review rather than transfer consent to new content.

Success updates formal order, internal calendar and generated preparation tasks through the backend, cancelling old generated tasks with history retained. It sends no customer message and synchronizes no phone calendar. Account calendar distinguishes current/other orders and tentative/formal entries; timed values display in Hong Kong and all-day dates retain their original zone. Day filtering includes overnight overlap.

Tasks default to pending/blocked; **全部（含历史）** includes completed/cancelled with deadlines, dependencies and sources. **刷新业务数据** rereads. Failed reads visibly mark retained data stale and disable confirmation until recovery. Unknown writes are reconciled by reading, without automatic resend.

## 5 Logout and troubleshooting

Logout/expiry clears account UI, QR and request-attempt metadata; the form does not retain password. Full reload requires sign-in, while saved facts remain backend-owned. A failed logout request is reported rather than claiming success.

| Symptom | Check |
| --- | --- |
| Login fails | GigMate account, configured password, backend destination/readiness |
| Old demo controls | Whether an old/main checkout is serving; restart from D checkout |
| No orders | Account ownership and unavailable creation, without seeding real data |
| Stale connection/business data | Restore service, refresh and review before acting |
| Authority changed | Reload and compare the other window's saved state |
| Timeout/unknown result | Read original server facts; avoid repeat clicks/new request identities |
| Phone refuses pairing | Provide sanitized actual feedback to integration maintainer; QR display is not success |

Narrow layouts may require vertical scrolling. Physical devices and native Windows remain independent acceptance; cleanup neither retests pairing nor changes real consent.

## 6 Developer checks

In apps/web: `npm run check:api`, `npm run format:check`, `npm run build` (behavior tests, types and build). Fixed replay code and backend `/replay` remain for isolated developer verification, without user UI. No backend source/generated contract/migration changed. This preview adds its loopback frontend origin to the existing ingress API through an ignored Compose override. The API was restarted; the original worker-owned database target was restored after a temporary incorrect target, then health/login rechecked. Provider/consent configuration was preserved. Removing controls does not establish final product completion.

## D-03: review a reply before approving it

Open **回复审批**, choose a draft and check the entire body, recipient conversation, original message revision, expiry and order/chat versions. Click **核对这份草稿**, then tick the explicit review checkbox before approving. The current recipient is a canonical conversation ID; real WhatsApp mapping/send bridging remains pending. **已批准，尚未发送** means your decision is saved, not that the customer received a message.

Reject/cancel requires a reason and exact reviewed snapshot. It is local, so unavailable conversation content blocks approval/reissue but does not prevent closing a draft. Changed data clears the review. Expired/stale/revoked/missing-source drafts cannot be approved. **全部历史** retains closed and approved drafts; filtering does not silently change the selection.

Unknown results retain the original request key and command in tab session storage, separated by environment/account. Refresh only reads. After reviewing the original snapshot, **核对后重试原请求** repeats the same intent/key/versions explicitly; it can complete an initially unreceived request. Never submit a new approval as a substitute. Authentication/CSRF rejection of that lookup does not erase the preceding uncertainty. Logout/remount/environment switching clears visible data but preserves this journal for that account/environment. If storage is unavailable or malformed, new writes fail clearly before dispatch.

**重新生成待审批问题** creates a fresh draft requiring fresh review. C PR #22 still has a repeated-expiry uniqueness defect; this UI blocks another same-source reissue at the same context. That guard does not repair the backend. No automatic generation, message editing, real sending or send reconciliation endpoint is added here. See [D-03 acceptance](role-d-stage3-acceptance.md).
