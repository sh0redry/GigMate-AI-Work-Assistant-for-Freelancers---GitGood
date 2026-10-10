# Role B 抽取子系统

2026-10-09 联调更新：[WAHA/提取统一验收](role-a-integration-acceptance.md)记录控制与 worker 交接。当前 Alembic head 是 `0007_merge_waha_extraction`，汇合未改动的 B 证据迁移和 A 控制/采样分支。Windows 测试使用 pytest 管理临时文件；默认 provider 仍拒绝真实提取，没有增加真实模型或网络调用。

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
逻辑。本批次交付一个不发请求的 `llm` provider 骨架：注册表选择、
配置、prompt 版本与调用形态都已接好，下一批次只需补全
`gigmate.extraction.llm.LLMProvider._invoke_model` 即可。

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
| `GIGMATE_EXTRACTION_PROVIDER=llm` | 真实模型骨架；接缝补全前始终返回 `needs_review`，并在 `unresolved_questions` 中写明原因。 |
| 未知名称 | 启动时直接报错，绝不悄悄回落。 |

测试通过 `gigmate.extraction.registry._reset_provider_for_testing` 注入
provider，不污染进程级缓存。

### `llm` provider 骨架

`gigmate.extraction.llm.LLMProvider` 是后续单独授权真实模型批次的非发请求
接缝。它同样遵守 `ExtractionRequest.origin` 信任边界，读取
`gigmate/extraction/prompts/` 下的版本化 prompt 文件，并把配置好的模型
与 prompt 版本写入 `ModelCallTrace`，便于人工核对为何被拒绝。

本批次刻意把它交付为骨架：下一批次替换 `_invoke_model` 与
`_parse_response` 的同时，必须把类标志 `LLMProvider._SKELETON_SEAM` 置为
`False`，否则仍然不发网络请求。期间模块只读 `GIGMATE_LLM_API_KEY`，
刻意忽略 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`，让模型密钥继续留在运维
显式控制之下。

配置（环境变量，骨架阶段全部可选）：

| 变量 | 用途 |
| --- | --- |
| `GIGMATE_LLM_PROVIDER` | 供应商名（`deepseek` / `openai` / `custom`），写入 `model_version`，并校验该 build 是否真正支持。 |
| `GIGMATE_LLM_MODEL` | 模型标识（如 `deepseek-chat`、`gpt-4o-mini`）。未配置时记为 `skeleton:pending`。 |
| `GIGMATE_LLM_API_KEY` | 仅服务端使用；provider 每次调用都重新读取，绝不存到实例上，也绝不写日志。 |
| `GIGMATE_LLM_ENDPOINT` | 可选 base URL 覆盖（默认 `https://api.deepseek.com`）。 |
| `GIGMATE_LLM_PROMPT_PATH` | 可选 prompt 文件覆盖。 |
| `GIGMATE_LLM_LIVE=1` | 显式 live 闸门。`_SKELETON_SEAM` 翻开后还必须开它才能真的发起调用；本批次它是骨架标志之后第二道防线。 |
| `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` | 显式允许 `request.origin == "live"` 进入模型的开关，默认关闭。 |

#### 双闸门安全网

调用 `_invoke_model` 前必须同时打开两道闸门：

1. **类标志 `LLMProvider._SKELETON_SEAM`**——本批次为 `True`。只要是
   `True`，无论环境变量如何配置都直接返回 `llm:seam-pending`。这是
   防止"下一批次只填 `_invoke_model` 就意外进入真实调用模式"的兜底。
2. **`GIGMATE_LLM_LIVE=1`**——运维开关。即便类标志已翻为 `False`，
   没设这个变量时仍然拒绝。

执行顺序：骨架标志 → live 闸门 → 配置完整性（vendor 已知、key 已设）→
live 来源 gating 门 → `_invoke_model`。骨架标志为 `True` 时调用在读取
环境变量前就被拒绝，因此配置错误的生产环境不可能发出真实网络请求。

#### prompt 加载失败模式

prompt 默认从
`apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt` 读
取（可通过 `GIGMATE_LLM_PROMPT_PATH` 覆盖）。匹配 `prompt_version: X.Y.Z`
的第一行被读入 `prompt_version`。所有失败模式都被显式捕获，并记入
`LLMProvider._prompt_load_error`：

- 文件缺失 / `OSError` → 占位符 `0.0.0-skeleton` + 拒绝。
- 非 UTF-8 字节（`UnicodeDecodeError`）→ 占位符 + 拒绝。
- 没有 `prompt_version:` 头行 → 占位符 + 拒绝。
- `prompt_version:` 头存在但取值为空 → 占位符 + 拒绝。

以上每一种 outcome 都带 `notes=("llm:prompt-malformed",)` 与可定位的
`refused_reason`，`Proposal` 行记 `prompt_version = "0.0.0-skeleton"`，而
`ModelCallTrace` 行保留描述性原因——worker 不会让 prompt 错误冒到宽口径
`except Exception`，也不会触发 `PROCESSING_FAILED` 重试风暴。

默认 prompt 来自
`apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt`，第一行
`prompt_version: X.Y.Z` 会被读入 `prompt_version`；文件缺失或格式异常时
回退到 `0.0.0-skeleton`，trace 中仍可看出占位状态。文件正文固化了几条
硬规则（不得把字段标为 `confirmed`、不得授予执行权限、遵守来源信任边界），
下一批次只需改这一个文件与两个接缝方法。

评测清单里的 `case-008-llm-skeleton-needs-review` 在使用
`--provider llm` 跑清单时通过；通用 needs_review 用例（3、4、5、6、7）
在 `llm` 下同样通过，因为骨架一律拒绝。matched 用例（1、2）在 `llm` 下
预期失败——骨架没有真实模型可以调用；它们在默认 deterministic provider
下通过。

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

## 真实启用前验收门槛

本批次只交付**未激活的调用实现**：HTTP / 解析 / Schema 路径已经就位，
但 `_SKELETON_SEAM = True` 且活门默认关，所有请求都不会触达网络。
接缝、prompt 版本链、live-origin 守门已落地为可测试代码；下列验收门槛
**不在本 PR 范围内**，必须在接缝打开、真实流量被允许经过真实模型 provider
**之前**（每一项独立批次、独立评审）逐项完成：

- **可信身份与出处不能交给模型决定。** 现行 `_parse_response` 只做
  结构校验，对 LLM 返回的 `work_order_id` / `base_work_order_version` /
  `conversation_id` / `sources` 不会重新绑定到 worker 实际发起的请求。
  启用前必须：
  (a) 把 `work_order_id` 重新绑定到 `request.candidate_work_order_ids`
      之一（若模型一个都没选则为 `None`）；
  (b) 把 `base_work_order_version` 重新绑定到 worker 解析出的版本号；
  (c) 把每条 `source.message_id` / `source.message_revision` 重新绑定到
      请求的 `message_id` / `message_revision`；
  (d) 把 `conversation_id` 重新绑定到请求的 `conversation_id`。
  不一致必须以 `llm:response-schema-failed` + 稳定错误码上报，绝不能
  当作 `matched` 通过。这一项不需要再向模型多发任何 UUID，只需要更严的
  校验后处理。
- **vendor 与 endpoint 语义必须显式。** 现行代码把
  `GIGMATE_LLM_PROVIDER=openai`（或任何 vendor 名）一律视作"使用
  DeepSeek 默认 endpoint，除非操作员另行设置 `GIGMATE_LLM_ENDPOINT`"。
  接缝打开后这是脚枪：为一个 vendor 配置的 worker 可能静默调用另一个
  vendor 的服务。启用前 provider 必须：
  - 拒绝未知的 `GIGMATE_LLM_PROVIDER` 取值；
  - 把每个已知 vendor 与各自文档化的默认 endpoint 绑定；
  - vendor 为 `custom` 时强制要求 `GIGMATE_LLM_ENDPOINT`。
  如果 `openai` 指"任何 OpenAI 兼容协议"而非"OpenAI 这家供应商"，需要
  在配置面和文档里写清楚，避免评审者按较窄含义误读。
- **重试必须与 worker 锁、租约一起设计。** 现行 `_call_chat_completion`
  对所有 `httpx.HTTPError` 及所有 `KeyError` / `IndexError` / `ValueError`
  各重试 1 次。30 秒超时 + 1 次重试，单次抽取可能持有同账号 / 同工单
  行锁直到完整退避结束；若租约在请求飞行中过期，worker 可能完成并丢弃
  结果，再次执行，费用翻倍、`model_call_traces` 也可能重复。启用前重试
  策略必须：
  - 限定**总**墙钟与上报费用；
  - 仅对明确 transient 类（连接重置、带 `Retry-After` 的 5xx 等）重试，
    不对解析 / Schema / 4xx 错误重试；
  - 签发**持久 request id**，便于与上游供应商日志对账；
  - 把 I/O **放在行锁外**；
  - 调用返回后重新校验候选工单 / context version，避免陈旧重试把老
    数据升级。
  本 PR 不实现上述任何一项；现有测试只断言当前形状（任意错误都重试
  1 次），因此行为不会在无声中漂移。
- **日期解释需要真实时间依据；输出格式必须符合契约。** 现行 prompt 要
  求模型把"今天 / 明天 / 下星期X / next Thursday"等相对日期相对于
  一个未指定的"现在"解析，并输出 `Asia/Hong_Kong` 锚定的 ISO-8601
  字符串。`ExtractionRequest` 不携带原始消息时间戳与工作区时区，而
  契约里的 `TimedSchedule` 要求 `start_at` / `end_at` 为 UTC `Z` 格式。
  启用前请求必须携带服务端附上的 `message_received_at`（或等价字段）
  与 `workspace_timezone`；prompt 必须以此时间戳为相对日期的参照；输出
  必须为 UTC `Z`；provider 必须对任何无法无损解析为 UTC 的 `start_at`
  / `end_at` 以类型化备注拒绝。媒体处理器（OCR / ASR / PDF）批次会
  提供缺失的时间戳来源；本 PR 仅是纯文本抽取接缝，因此不包含。
- **错误码需稳定、脱敏。** 现行 `refused_reason` 字段直接嵌入 Python
  异常类名与原始异常消息。开发时有用，但私有 endpoint 路径 / 供应商
  名称 / 密钥片段可能借下游日志泄漏。启用前错误码必须是稳定字符串
  （例如 `llm:http-failed:timeout`），任何自由文本部分都必须脱敏
  endpoint、vendor、API key 前缀。

上述门槛写在这里是为了让评审者确认本 PR 不会静默打开接缝；每一项都
是独立批次、独立评审。

## 待办

- 真实模型 provider 接入：下一单独授权批次必须完成三件事——(a) 用真实 SDK
  替换 `gigmate.extraction.llm.LLMProvider._invoke_model` 与
  `_parse_response`；(b) 把 `LLMProvider._SKELETON_SEAM` 翻为
  `False`；(c) 把真实授权与 live-origin 通道接入独立的授权审查（当前
  live-origin guard 已经在该 provider 中实现，但骨架标志为 `True` 时
  不可达）。同时补上 prompt-injection 回归与延迟预算。接缝、prompt 版本
  兜底链、`llm:prompt-malformed` 与 `llm:seam-pending` trace 备注、
  `case-008-llm-skeleton-needs-review` 评测用例，以及
  `_prompt_load_error` 审计字段均已就位。
- D 前端面向真实 provider 输出的 `pending_change_ids` 展示；当前
  Replay 卡片已能呈现，但真实 provider 来回之前不更新前端。
- 真实 provider 上线后细化 `unresolved_questions` 给商户的人工核对呈现。
