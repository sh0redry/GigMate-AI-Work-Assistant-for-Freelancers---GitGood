# ADR 0011 Bounded merchant assistant

- Date: 2026-11-24
- Status: Accepted 2026-11-24 (owner decisions O1/O2 below). Batch 0 (this ADR, contracts, threat model) batch 1 (durable turns, read-only tools, offline rule planner) batch 2 (date-range availability and order answers) and batch 3 (reply/polish drafts, invalidation, adoption) are implemented; batches 4–5 are targets.
- Related: [ADR 0003](0003-approval-and-execution.md) (approval and execution), [ADR 0007](0007-owned-waha-sending.md) (owned sending), [ADR 0008](0008-vendor-selection-and-private-configuration.md) (vendor and credentials), [design and threat model](../assistant.md).

## Context

Merchants want to ask GigMate directly, for example "Which days next week can I fit this customer in?" or "Reply to this message for me." Main has no merchant-to-AI path. `agent_drafts.py` deliberately records "No free-form question answering … no 'ask the model anything' path", and `POST /workspace-query` answers four keyword intents without a model. This ADR amends that boundary without removing it: the assistant is not free-form Q&A, and it never gains execution authority.

## Decision

1. **Bounded intents, not open chat.** Version 1 supports `availability`, `order_status`, `reply_draft` and `polish`, plus `clarify` (ask the merchant which chat/order) and `unsupported`. Other requests are declined and point to the normal pages.
2. **The model plans; the server executes read-only tools.** The model returns `AssistantPlan` 1.0.0 ([schema](../../../contracts/ai/assistant-plan.schema.json)) with at most three calls from a fixed allowlist: `find_free_slots`, `list_work_orders`, `get_work_order`, `read_conversation`. Each intent has its own subset. Tools address data only through the merchant's explicit selection (`target: "selected"`), never through IDs the model supplies. Every tool re-checks account ownership, allowlisted consent and versions on the server.
3. **No write, confirm, approve or send tool exists.** The only thing the assistant can create is a proposal: an assistant draft for reply/polish (its own `assistant_drafts` table, mirroring agent-draft rules, because a reply may concern a chat with no order yet) bound to conversation, optional order version, context version and the exact customer message revisions it answers, with `execution_authority: false`. Sending still requires the separate sending permission, an explicit merchant approval and the existing gateway (ADR 0003/0007).
4. **Facts come from tools, not from the model.** Slot times, counts and order facts in `availability`/`order_status` answers are rendered by the server from tool results. In a reply draft (`AssistantComposition` 1.0.0, [schema](../../../contracts/ai/assistant-composition.schema.json)) the model must list facts the tools did not establish (`unverified_claims`) for highlighted review.
5. **Context is explicit and versioned.** A turn carries the merchant's selection (`AssistantContext`: conversation + expected context version, order + expected order version, selected message revisions). Ambiguity, for example several open orders and none selected, produces a `clarify` turn, never a guess. New, edited or revoked customer messages invalidate an unconsumed generated draft, as for every other proposal.
6. **Durable turns.** A turn is persisted with an idempotency key and runs as a worker job with a lease (queued → running → completed / failed / unknown / superseded). An interrupted model call becomes `unknown` and is not retried automatically. Logs carry IDs, stage, latency and stable codes, never question text, customer content or model output.
7. **Fallback without a model.** When the reviewed model gates are closed, the offline rule planner (keyword intents, deterministic date/duration parsing) and the deterministic free-window computation answer (`engine: "rules"`); reply drafts say they need the model. The older `POST /workspace-query` keyword endpoint is unchanged.
8. **Spend and abuse bounds.** The existing ADR 0008 gates and per-call cost/token caps apply. Batch 1 adds a per-account daily turn ceiling and a per-turn cap of two model calls (plan, then compose for reply/polish only).

## Owner decisions (accepted 2026-11-24)

- **O1 — Version 1 intent scope: accepted.** Availability, order status, reply draft and polish, plus `clarify` and `unsupported`. No open conversation.
- **O2 — What may reach the model vendor: accepted as recommended.** Only the bounded, consent-checked context `message_context.py` already allows (five minutes, eight messages, 8000 UTF-8 bytes) for the selected allowlisted chat, plus the merchant's question and server-computed tool results. Phone numbers and provider chat IDs are replaced by opaque handles before any model call. The merchant interface must disclose that this content is sent to the configured vendor before the model-backed assistant is enabled (batch 4), and the assistant can be turned off. Redacted-summary-only mode is not adopted.

## Consequences

- Batch 0 adds source models and generated schemas only. `AssistantTurnCommand`, `AssistantTurnView` and related domain models appear in the domain schema; no route serves them, so OpenAPI and generated frontend types are unchanged.
- JSON Schema cannot express the intent-to-tool allowlist or several pairing rules; the Pydantic validators are authoritative and tested. Independent schema validation is necessary but not sufficient.
- Version 1 cannot do multi-step agent work, cross-chat search, creating or changing orders, or sending. Each would need a superseding ADR.
- `scheduling.free_slots()` currently returns the first three slots in fourteen days; `availability` needs a bounded date-range variant (batch 2).

## 中文决策摘要

商户可以直接问 AI，但这不是开放式闲聊，也永远没有执行权。第一版只支持：查空闲时段、查工单状态、生成回复草稿、润色，外加反问商户（`clarify`）和拒绝（`unsupported`）。模型只负责规划：输出 `AssistantPlan` 1.0.0，最多调用三个白名单内的只读工具（查空闲、列工单、看所选工单、读所选会话），每个意图有各自的工具子集；工具只能作用于商户明确选中的对象（`target: "selected"`），不能使用模型给出的 ID，服务端每次都重新校验归属、授权和版本。没有任何写入、确认、批准或发送工具；唯一产出是绑定会话、工单版本、上下文版本和客户原文修订的草稿，`execution_authority: false`，发送仍走单独授权、商户批准和现有网关。时间、数量和工单事实由服务端根据工具结果生成，回复草稿中工具无法证实的内容必须列入 `unverified_claims` 供人工核对。上下文有歧义时反问商户，不替他选；新消息、编辑或撤回会作废未采用的草稿。每轮问答持久化、带幂等键、由 worker 执行，结果未知不自动重试，日志不含问题原文或客户内容。模型未开启时退回现有规则查询和确定性空闲计算。业主已于 2026-11-24 确认：O1 第一版只做上述四类意图，不做开放式闲聊；O2 按建议执行——只把所选已授权会话中 `message_context.py` 允许的有界上下文（5 分钟、8 条、8000 UTF-8 字节）、商户问题和服务端工具结果发给模型，电话号码和平台聊天 ID 在调用前换成不透明标识；启用模型版助手前界面必须明示内容会发给所配置的供应商（第 4 批），且可关闭助手；不采用仅发脱敏摘要的方案。第 0 批只新增源模型和生成的 schema，不新增路由，OpenAPI 与前端类型不变。
