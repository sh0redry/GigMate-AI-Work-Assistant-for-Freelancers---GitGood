# Role B 抽取子系统

更新：2026-10-08。[英文对应](../en/role-b-extraction.md)。基于
[团队本地开发](role-a-team-local-development.md)与[交接总览](role-a-waha-handoff.md)。

## 范围

Role B 拥有 AI 抽取流水线：Provider 接口、提示词/模型版本注册、离线评测
工具，以及 Worker 为每个 Job 落库的证据记录。输出只能是提议和草稿，
永远不做确认写或对外发送。约束见英文对应文档中的
[ADRs](../en/adr/README.md)、[架构图](../en/architecture.md)。

本批次交付：

- Provider 接口 `gigmate.extraction.Provider`，以及两个具体实现：
  `DeterministicProvider`（默认发货版）与 `DisabledProvider`（彻底关掉
  AI 提议的环境）。
- Worker 集成：用 provider 取代原先的 `LIVE_EXTRACTION_PENDING` 占位；未知
  live 文本以 `EXTRACTION_NEEDS_REVIEW` 完成，不再悄悄结束。
- 新增 Pydantic 模型：`ChangeProposal`、`ProposalChange`、
  `ProposalCandidate`、`AssignmentResult`、`EvaluationCase`、`EvaluationRun`，
  与既有 domain schema 一同导出。
- 新增持久化表：`proposals`、`model_call_traces`、`evaluation_runs`、
  `evaluation_cases`（迁移 `0005_extraction_evidence`）。
- 离线评测 `scripts/run_evaluation.py`，清单 `contracts/evaluation/manifest.json`。

真实模型接入（Anthropic、OpenAI 或其他具体供应商）是后续单独授权批次。
接缝已经预留好，新增真实 provider 时不必改 worker、合约或既有 Replay
逻辑。

## 边界

- AI 不得把字段标为 `confirmed`；`ChangeProposal.no_executing_authority`
  在类型层强制。
- AI 不得授予执行权限。落库的 `RequirementChange.proposer` 始终是
  `customer` 或 `merchant`（按来源消息作者填写），与 provider 无关。
- 真实流量由 `DeterministicProvider` 在两个独立条件下拒绝：请求的
  `origin` 必须是 `synthetic`（受信 Replay 或评测通道）**且**文本与合成
  样例完全一致。live 来源输入即使文本与样例相同也返回
  `assignment: needs_review`，真实内容绝不可能借固定日期模板被提升为
  提议。非已知文本返回 `assignment: needs_review`、`changes` 为空，并在
  `unresolved_questions` 解释通用抽取尚未启用。这保留了
  `role-a-team-local-development.md` 中“真实内容不得经过虚构固定抽取
  模板”的约束，同时让接缝可读。
- 多工单歧义永不悄悄合并。provider 始终收到 `candidate_work_order_ids`；
  数量不为 1 即返回 `needs_review`。Worker 的 legacy Replay 分支仍上报
  `ASSIGNMENT_NEEDS_REVIEW`。
- 提议只针对当前已接受的 `context_version`；旧上下文不能产生可执行
  提议，因为 `messaging.ingest` 推进上下文时会把 pending 变更降级。

### 来源信任边界

`ExtractionRequest.origin` 由服务端设置，是合成输入与真实输入的信任
边界：

- `origin="synthetic"`——只由受信 Replay legacy 路径
  （`gigmate.understanding.extract`）和离线评测工具设置；固定模板
  provider 只允许对这个来源产出 `matched`。
- `origin="live"`（默认）——Worker 的 WAHA 分支对每条真实连接器事件都
  标记为 live。未标记的请求默认 live，忘记分类的调用方永远不可能被
  当作合成输入。

想让真实内容产出 `matched` 的 provider 属于后续单独授权批次；评测清单
的 `case-007-live-origin-with-fixture-text` 固化了这一行为。

## Provider 接口

`gigmate.extraction.Provider`：

```text
class Provider(Protocol):
    name: str
    model_version: str
    prompt_version: str

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome: ...
```

`ExtractionRequest` 限定范围、仅取白名单内输入。Worker 负责从 Inbox 行、
最新 `MessageRow` 修订、`ConversationRow.context_version`、候选
`WorkOrderRow` 与账号组装；Provider 不读模型、不发起网络请求、也不
碰数据库。

`ExtractionOutcome` 携带已校验的 `ChangeProposal`、provider 名、调用
延迟、可选 `refused_reason`。`ChangeProposal` 在落库前由 Worker 再次
校验，坏 provider 写不进去。

## 选择与覆盖

通过 `gigmate.extraction.provider()` 选择：

| 设置 | 行为 |
| --- | --- |
| `GIGMATE_EXTRACTION_PROVIDER=deterministic`（默认） | 只识别两条合成样例的默认 provider。 |
| `GIGMATE_EXTRACTION_PROVIDER=disabled` | 所有请求返回 `needs_review`，不写变更。 |
| 未知名称 | 启动时直接报错，绝不悄悄回落。 |

测试通过 `gigmate.extraction.registry._reset_provider_for_testing` 注入
provider，不污染进程级缓存。

该开关同时作用于两条路径：Worker 的 WAHA 分支与 legacy Replay 入口
`gigmate.understanding.extract` 都通过 `gigmate.extraction.provider()`
解析 provider。设置 `GIGMATE_EXTRACTION_PROVIDER=disabled` 时，Replay
任务以 `STUB_UNSUPPORTED_INPUT` 结束（无变更行），live 任务以
`EXTRACTION_NEEDS_REVIEW` 结束（保留证据、无变更行）。未知 provider
名称直接报错，绝不悄悄回落。

## Worker 集成

`apps/backend/src/gigmate/worker.py` 仅在 WAHA 分支调用 provider。
Replay 分支保留 legacy `gigmate.understanding.extract`，现有烟测继续
monkey patch `gigmate.worker.extract` 而无需变更。

provider 路径：

1. 重新校验 context 修订、消息修订和 `revoked` 标记。
2. 从 `conversation_orders` 解析候选工单 ID。
3. 用候选工单最新字段快照组装 `ExtractionRequest`。
4. 调用 `provider().propose(request)`。
5. 在同一事务中落库 `Proposal` 和 `ModelCallTrace`。
6. 若 `assignment = matched` 且候选数恰好为 1，调用 `persist_changes_for`
   生成 `RequirementChange` 行并追加到工单的 `pending_change_ids`。
7. Job 状态 `completed`：只有至少写出一条 `RequirementChange` 时
   `error_code = None`，否则 `error_code = EXTRACTION_NEEDS_REVIEW`。

Worker 的 WAHA 分支把每条请求标记为 `origin="live"`，deterministic
provider 对 live 来源一律拒绝（与文本无关），因此当前真实 WhatsApp
内容不会进入步骤 6。放开这道闸是后续单独授权批次，必须配套新增真实
模型 provider 与 prompt-injection 测试。

### 保留策略

`Proposal` 与 `ModelCallTrace` 行引用 inbox 收据
（`proposals.event_id`），与其共享 30 天保留窗口。
`waha_ingress.purge_expired` 按"先 trace、再 proposal、再收据”的顺序
删除，外键始终满足；清理结果同时返回
`deleted_proposals`、`deleted_traces` 计数。已确认的业务变更保存在
工单上（`requirement_changes`），有意在收据窗口之后继续保留。

## 评测工具

`scripts/run_evaluation.py` 读取 `contracts/evaluation/manifest.json`，
逐条运行当前 provider，落库 `EvaluationRun` + `EvaluationCaseRecord`
并写出 JSON 报告。用例断言 assignment、最低置信度和预期变更字段。
七条合成用例当前覆盖：已知改期、已知可用、未知 live 文本、无工单关联、
多工单歧义、prompt-injection、live 来源且文本与样例一致。

```text
.venv/bin/python scripts/run_evaluation.py \
    --manifest contracts/evaluation/manifest.json \
    --database-url "$DATABASE_URL" \
    --json-out local-data/evaluations/run-$(date -Iseconds).json
```

只有全部用例通过时脚本才退出码 0；清单缺失或为空时直接报错，不写空
运行。

## 合成样例与隐私

评测用例位于 `contracts/evaluation/`，遵守与 `contracts/examples/` 相同
的 `data_classification: synthetic` 规范。真实 WAHA 内容、真实聊天 ID
或任何运维相关文本绝不能写进受跟踪样例。模型密钥留服务端；provider
接口 DTO 不接受密钥，日志只写 ID、延迟和稳定错误码。

## 验证

本批次权威检查：

```text
.venv/bin/python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py
.venv/bin/python -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py
.venv/bin/python scripts/export_contracts.py --check
.venv/bin/python -m alembic -c apps/backend/alembic.ini upgrade head
.venv/bin/python -m alembic -c apps/backend/alembic.ini check
.venv/bin/python -m pytest apps/backend/tests -q --basetemp=local-data/pytest
.venv/bin/python scripts/check_baseline.py
```

PostgreSQL 测试是有意义的运行；SQLite 不证明行锁，只验证条件兼容性。
本批次不合成真实 WhatsApp 流量。

## 待办

- 真实模型 provider 接入（Anthropic、OpenAI 或其他单独授权供应商），
  配套 prompt-injection 回归与延迟预算。
- D 前端面向真实 provider 输出的 `pending_change_ids` 展示；当前
  Replay 卡片已能呈现，但真实 provider 来回之前不更新前端。
- 真实 provider 上线后细化 `unresolved_questions` 给商户的人工核对呈现。
