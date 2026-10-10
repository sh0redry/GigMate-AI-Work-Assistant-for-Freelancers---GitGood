# ADR 0007 Owned multi-type sending and exact preauthorization

- Date: 2026-10-10
- Status: Authorized development batch; real-account/B/PostgreSQL/independent acceptance pending.

The owner explicitly requested multi-type WhatsApp sending with manual, Agent-assisted and Agent-automatic modes. Extend ADR 0003's initial P0 exclusion of preauthorized sending only for an exact-content, one-chat, expiring and use-bounded merchant policy. An AI proposal never grants authority: the server checks the policy and freezes an immutable approval for each action against current permission/control/context, source/attachment hashes and optional work-order versions. Variable/ambiguous generated content remains human-reviewed. B real models and autonomous triggers are not supplied by A.

Manual/assisted drafts require merchant approval. A new `WahaSendAction` row is the implemented approval/outbox gateway; legacy generic `ApprovalAction` definitions are not automatically executable. Persist approval and queued execution together. One task sends one message/attachment; no multi-file atomicity or external exactly-once guarantee.

Commit a short serialized dispatch fence after final revalidation; do provider I/O outside business locks. Already-dispatching actions cannot be cancelled retroactively. Recover abandoned GET preflight, but make abandoned/ambiguous POST/PUT outcomes unknown without a retry. Exact returned IDs permit read-only receipt lookup. No-ID uncertainty cannot be resolved by matching equal text. Explicit human review may release later independent actions while preserving uncertainty and the charged policy use. Lost creation requests have owned opaque-key lookup and persistent cancellation fences, so late arrival cannot undo cancellation.

Sending consent is separate and disabled by default. Revocation/cancellation do not depend on provider configuration. Uploads are private/bounded/hash-checked; no arbitrary remote URLs or model/frontend connector credentials. Preserve existing media/connection data and migrations; additive 0011 adds only sending tables. Follow [bilingual delivery/acceptance](../role-a-waha-sending.md).

## 中文决策摘要

用户明确授权手动、Agent 润色后及自动发送。只对商户预先批准的固定内容、单个会话、有效期和次数扩展 ADR 0003 的初期边界；AI 仍只提建议，权限由服务端校验并绑定当前版本。可变生成内容、业务归属不明仍转人工，真实 B 模型及自主触发另行接入。

人工草稿明确批准；每条记录同时保存审批及 outbox。提交 dispatching 是本地外部执行边界，之后不能声称已经取消远端请求。网络 I/O 不占业务锁；未知结果不重发，无返回 ID 不猜测关联。人工核对只解除后续独立任务阻塞，不把原任务改成送达或业务确认。取消未落库请求留下持久标识，阻止晚到的创建。发送单独授权、默认关闭；新增 0011，不改旧媒体/会话数据。
