# Role B 抽取子系统

2026-10-10 媒体第二批：A 已提供固定的供应商发送时间/商户本次选择时区及已核对只读证据。B 须单独实现 MediaProcessor.process/reconcile，不能把文本提取接口当作媒体实现；C 须约定附件来源并在业务晋升前重新校验。时间不足保留待确认，本批不启用外部发送。见[媒体协议](role-a-media-ingestion.md)。

2026-10-10 媒体对接：[A 的媒体协议](role-a-media-ingestion.md)提供权限范围内字节、不可变请求/来源/哈希标识、绑定来源/上下文的结果存储及核对。真实 OCR/ASR/解析/GenAI 工厂和只读核对由 B 实现。A 没有新增真实适配器，原 deterministic 拒绝 live 输入的边界保留。不能把媒体快照冒充 canonical 消息修订或直接写成已确认工单变化。核对还绑定 expected_result_job_id，防止新结果继承旧核对。

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

## 媒体处理器（WAHA 附件的 Role B 实现）

更新日期：2026-10-10。本节交付填充 [WAHA 媒体摄取批次](role-a-waha-handoff.md)
所留接缝的真实模型处理器。A 拥有存储、租约、授权与审核；B 通过本处理器
拥有 OCR / ASR / 解析 / GenAI。处理器只产出 `WahaMediaResult` 提案——
商家确认由下游 `WahaMediaEvidence.business_confirmation_required` 强制，
B 侧永不把字段标为 `confirmed`、永不授予执行权限。

### 接缝契约

`gigmate.media_processing.MediaProcessor`（Protocol）定义两个方法：

* `process(request: MediaInput) -> WahaMediaResult` —— B 用 `request_id`
  做厂家侧幂等与对账；输出仅为提案。
* `reconcile(request_id) -> WahaMediaResult | None` —— 只读查询，永不
  重新提交。`None` 表示结果仍未知，worker 必须下次再调而不是重发
  `process()`。

A 通过环境变量
`GIGMATE_MEDIA_PROCESSOR_FACTORY="gigmate.media.processor:MediaProcessorImpl"`
加载实现。`MediaInput` 故意不暴露 `api_key`、`provider_url`、
`authorization` 属性；`test_waha_media.py` 中的接缝测试与
`test_media_processor.py` 中的类型测试共同锁定这一约束。

### 两闸门安全网

处理器联系任何厂家前必须同时打开两个闸门：

1. **`apps/backend/src/gigmate/media/processor.py` 模块级 `_ENABLED` 标志**
   —— 本批次为 `False`。在 `False` 时，处理器在读取任何环境变量**之前**
   以 `ProcessingUnavailable` 拒绝所有调用。这是防止未来贡献者单靠导出
   运维开关就把接缝打开的安全网。
2. **`GIGMATE_MEDIA_LIVE=1`** —— 运维开关。即便类标志翻为 `True`，处理
   器仍然拒绝所有调用，除非导出该变量。检查顺序：类标志 → 运维开关 →
   API key 是否设置 → live-origin 闸 → 厂家调用。当类标志为 `False` 时
   在读取任何配置之前就拒绝，配置错误的部署不可能意外发出真实网络请求。

附加守门：

* 必须设置 `GIGMATE_MEDIA_API_KEY`，否则抛 `ProcessingUnavailable`。
* 真实客户附件要送达模型必须有 `GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN=1`；
  没有时处理器拒绝 `request.origin == "live"`、只允许 `synthetic`。
* 处理器绝不接受经 HTTP 传入的凭据或模型端点。工厂字符串只来自服务端
  环境变量，由 `importlib` 解析；HTTP 参数无法注入代码。

### 厂家路由与配置

| 变量 | 用途 |
| --- | --- |
| `GIGMATE_MEDIA_CHAT_VENDOR` | chat-completions 厂家（`deepseek`/`openai`/`custom`）。默认 `deepseek`。 |
| `GIGMATE_MEDIA_CHAT_MODEL` | chat-completions 模型 ID（如 `deepseek-chat`、`gpt-4o-mini`），厂家默认。 |
| `GIGMATE_MEDIA_AUDIO_VENDOR` | 转写厂家（`openai`/`custom`）。默认 `openai`。 |
| `GIGMATE_MEDIA_AUDIO_MODEL` | 转写模型 ID（如 `whisper-1`）。 |
| `GIGMATE_MEDIA_ENDPOINT` | 可选基地址覆盖。 |
| `GIGMATE_MEDIA_PROMPT_PATH` | 可选 prompt 文件覆盖。 |

MIME 路由（`gigmate.media.routing`）：

| MIME | 派发键 | 厂家适配器 |
| --- | --- | --- |
| `image/png`、`image/jpeg`、`image/webp` | `ocr` | chat-completions 视觉输入 |
| `audio/ogg`、`audio/mpeg`、`audio/wav`、`audio/mp4`、`audio/x-m4a` | `asr` | `/v1/audio/transcriptions` |
| `application/pdf` | `pdf` | chat-completions 文本抽取 |
| `text/plain` | `text` | chat-completions |

集合外的 MIME 在联系厂家前以 `ProcessingUnavailable` 拒绝。A 的白名单
仍是权威，B 仅消费规范化类型。

### 异常语义

处理器遵循 `gigmate.media_processing` 中记录的契约：

* `ProcessingUnavailable` —— 未提交任何厂家请求。闸门未开、厂家未知、
  API key 缺失、prompt 文件异常或 MIME 不支持时抛出。worker 翻译为
  `MEDIA_PROCESSOR_NOT_CONFIGURED`，下载产物保留供重试。
* `ProcessingUncertain` —— 厂家调用可能已提交（已计费）。4xx / 5xx、
  超时、网络错误、厂家侧 schema 失败时抛出。worker 翻译为
  `MEDIA_PROCESSING_RESULT_UNKNOWN`，走 `reconcile()` 而非自动重发。
* `MediaIntegrationPending`（私有）—— 配置未完成时厂家适配器内部抛出；
  处理器翻译为 `ProcessingUnavailable`。
* `MediaVendorRejected`（私有）—— 4xx / 5xx 时厂家适配器内部抛出；
  处理器翻译为 `ProcessingUncertain`。

本批次 `reconcile()` 一律返回 `None`，因为 chat-completions 厂家一般
不暴露基于 request-id 的查询。需要厂家侧查找的运维必须显式扩展处理
器；默认永不静默重发。

### prompt 加载失败模式

prompt 默认从 `apps/backend/src/gigmate/media/prompts/role_b_media_v1.txt`
加载（可经 `GIGMATE_MEDIA_PROMPT_PATH` 覆盖）。匹配 `prompt_version: X.Y.Z`
的第一行被读入结果的 `prompt_version` 字段。所有失败模式都被显式捕获：

* 文件缺失 / `OSError` → `ProcessingUnavailable` 拒绝。
* 非 UTF-8 字节（`UnicodeDecodeError`）→ `ProcessingUnavailable` 拒绝。
* `prompt_version:` 头行缺失 → `ProcessingUnavailable` 拒绝。
* 头存在但值为空 → `ProcessingUnavailable` 拒绝。

任意失败下 worker 记录为 `MEDIA_PROCESSOR_NOT_CONFIGURED`，不会用错误
prompt 重试。

### 运维 smoke

`scripts/smoke_media.py` 是运维侧手动 smoke（不在 CI）。需要两闸门
同时打开，并打印解析后的提案 JSON：

```text
.venv/bin/python scripts/smoke_media.py --mime image/png --file path/to/sample.png
.venv/bin/python scripts/smoke_media.py --mime audio/ogg --file path/to/sample.ogg
```

未打开接缝标志时脚本打印拒绝原因并以 `0` 退出。CI 不跑本脚本；真实调用
需要运维侧的厂家密钥。

## 验证

本批次权威检查：

```text
.venv/bin/python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/smoke_media.py scripts/run_evaluation.py
.venv/bin/python -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/smoke_media.py scripts/run_evaluation.py
.venv/bin/python scripts/export_contracts.py --check
.venv/bin/python -m alembic -c apps/backend/alembic.ini upgrade head
.venv/bin/python -m alembic -c apps/backend/alembic.ini check
.venv/bin/python -m pytest apps/backend/tests/test_media_processor.py apps/backend/tests -q --basetemp=local-data/pytest
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
- 媒体侧的厂家 `reconcile()`：chat-completions 厂家一般不暴露基于
  request-id 的查找，当前实现返回 `None`，worker 需等待人工重试。
  后续批次可在接缝标志开启后追加厂家特定查找。
- B 侧的 prompt-injection 回归套件（图像 OCR + 音频 ASR + PDF 解析）。
  当前处理器只信任捆绑的 prompt、对格式异常输入拒绝调用；后续授权
  批次应加入对抗输入夹具。
