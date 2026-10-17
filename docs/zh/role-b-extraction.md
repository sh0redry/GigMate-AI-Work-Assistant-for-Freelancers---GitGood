# Role B 抽取子系统

## 真实文字模型与已核对媒体转工单依据 — 2026-10-17

本批关闭路线图第 3、4 行的启用门槛。上一次已打开 provider 接缝（见下方 2026-10-17 启用记录）；这里只增加拒绝逻辑，不增加任何权限。

### 私有配置与明确授权

真实文字抽取必须同时具备：`GIGMATE_LLM_LIVE=1`、`GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`、DeepSeek key、支持 JSON 输出的模型、`GIGMATE_WORKSPACE_TIMEZONE`，以及至少一个每日预算上限。缺任何一项都在创建 HTTP 客户端前拒绝，内容不出进程、也不计费。`GIGMATE_LLM_LIVE_ACCOUNTS` 可把真实流量进一步收窄到指定账户，名单外账户得到 `llm:account-not-authorized`。凭据与 endpoint 只存在于 worker/服务端环境，不进入请求、提议、调用记录、API 响应或前端。

### 预算

`gigmate.extraction.budget` 汇总该账户当天已提交的 `model_call_traces`（按行计数，不另设计数器，避免用量与证据不一致；本地 `deterministic`/`disabled` 不计数，其他供应商名一律计数），把计数附加到 `ExtractionRequest`。上限由 `GIGMATE_LLM_DAILY_CALL_BUDGET` 和/或 `GIGMATE_LLM_DAILY_TOKEN_BUDGET` 设置。未配置任何上限时，真实流量以 `llm:budget-not-configured` 拒绝；达到上限时以 `llm:budget-exhausted` 拒绝。两种拒绝都在 I/O 之前发生且记录零用量。供应商不返回 token 数时仍占用一次调用预算，沉默不能等于免费。provider 不读数据库，只比较 worker 附加的数字。

### 时间基准

worker 把 inbox 消息的接收时间（UTC，`Z`）与 `GIGMATE_WORKSPACE_TIMEZONE` 附加到每个真实请求，并渲染进 user message；提示词只按该基准解析相对日期。两者缺失任一项即以 `llm:time-basis-missing` 拒绝。输出时间必须满足契约的 UTC-only 时间戳类型；带偏移或只有日期会校验失败并成为 `llm:response-schema-failed`，不会被悄悄当作本地时间重新解释。

### 来源重绑定

模型给出的 `conversation_id`、`base_context_version`、`work_order_id`、`base_work_order_version` 及每个变更的 `sources` 在校验前一律用服务端请求覆盖：

* `conversation_id` 与 `base_context_version` 永远取请求值；
* `work_order_id` 必须在 `candidate_work_order_ids` 内，只有一个候选时强制取该候选；
* `base_work_order_version` 必须等于请求携带的工单版本；
* 每条 `sources` 都替换为产生该请求的确切消息 id/修订号。

若响应指名候选集之外的工单、不同基础版本，或候选列表含未知工单，则记为 `llm:provenance-mismatch` 且不产生变更。消息身份不发给模型，因此模型无法选择归属。调用返回后 worker 会重新读取会话；若调用期间上下文已推进，提议仍保留为成本/证据，但不落地任何 `RequirementChange`，任务记录 `SOURCE_SUPERSEDED`。

### 超时、未知结果与重试

只有可证明尚未开始工作的失败才重试：TCP 连接失败、`408`、`429`。读超时、提交后连接中断、`5xx` 及畸形 2xx 响应分别记为 `llm:result-unknown` / `llm:response-malformed`，`total_tokens` 记为 `NULL`，任务错误码为 `EXTRACTION_RESULT_UNKNOWN`，且绝不自动重发。提议始终只是提议：没有确认、批准或发送，因此未知结果不可能执行业务变更。

诊断只保留稳定错误码与状态类别（`LLM HTTP call failed (status-401); endpoint and credential details are redacted.`）。供应商 URL、异常文本、请求头与密钥不落库、不打日志。

### 真实媒体识别

媒体保留原有 `GIGMATE_MEDIA_LIVE` / `GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN` 传输闸门，并新增两项显式授权：

* `GIGMATE_MEDIA_MODALITIES` 列出允许发送真实字节的模态（`ocr`、`asr`、`pdf`、`text`）。为空时即使 live 开关打开也一律 `MEDIA_MODALITY_NOT_AUTHORIZED` 拒绝，验收 OCR 不会顺带打开语音转写或文档外发。
* `GIGMATE_MEDIA_VISION_VENDORS` 列出实际验证过图片输入的供应商。OCR 发给其他供应商会在创建客户端前以 `MEDIA_VISION_VENDOR_UNVERIFIED` 拒绝；不假设 DeepSeek chat-completions 支持图片。

ASR 仍需 `GIGMATE_MEDIA_AUDIO_VENDOR`（OpenAI 兼容）；PDF/text 保留本地解析与上限检查。本批不引入新供应商，本环境也未做真实供应商调用。

### 附件成为工单依据

`POST /api/v1/work-orders/{id}/evidence` 把一份已通过来源核对的附件保留为该工单依据。命令回显被核对的绑定（`attachment_id`、`expected_attachment_version`、`expected_context_version`、`expected_result_job_id`），服务端重新校验账户归属、连接/来源有效、授权、到期、核对记录及原始文件字节。附件所在会话必须已关联该工单，否则 `MEDIA_ORDER_LINK_REQUIRED`。结果比核对时更新会以 `MEDIA_RESULT_CHANGED` 拒绝；文件/版本/上下文变化以 `MEDIA_SOURCE_CHANGED` 拒绝。

映射行（迁移 `0015_work_order_evidence`）快照附件版本、上下文版本、结果任务 id 与 SHA-256，并按 `(work_order_id, attachment_id, attachment_version)` 唯一，重复提交同一绑定是幂等的。后续变化不会改写历史：`GET /api/v1/work-orders/{id}/evidence` 在读取时计算 `stale` 与稳定的 `stale_reason`。该提升不写 `RequirementChange`、不确认客户事实、不授予批准或发送权限；它记录的是"该已核对文件支持此工单"的商家决定。商家批准仍需另行绑定收件人、内容、版本、到期与动作修订。

## PDF 资源隔离

供应商调用前的 PDF 解析已改为私有子进程，不在业务 worker 内运行 pypdf。默认墙钟 20 秒、内存 512 MiB、每个 worker 同时一个解析进程、输入 20 MiB、序列化输出 1 MiB。可信服务端设置 `GIGMATE_PDF_TIMEOUT_SECONDS`（1–60）与 `GIGMATE_PDF_MEMORY_MIB`（128–1024）由媒体 Compose 覆盖传给 API/worker，不接受 HTTP 修改。原页数、片段、文字上限及 partial 校验保留。

Windows 挂起启动实际底层解释器，先绑定带已提交内存、CPU、进程数量限制及关闭即终止的私有 Job Object，再恢复执行；不能把限额只设在 venv 启动器上。Linux 使用硬性 RLIMIT_AS/RLIMIT_CPU、关闭 core dump、限制描述符，并绑定父进程生命周期。启动响应确认实际 PID 后才传 PDF 字节。原生 macOS 明确返回 MEDIA_PDF_LIMIT_UNAVAILABLE，后端使用项目 Linux Docker 镜像，不宣称不可靠的原生内存兜底。

子进程通过管道收发，不落临时原文件；固定 UTF-8，不继承模型/WAHA/数据库环境或 worker PYTHONPATH，只加载固定 pypdf 路径。父进程再验输出结构、数量、页码及文字长度。超时、输出超限会终止并回收私有进程、关闭管道；崩溃不视为成功。模型请求前的 PDF 错误码写入媒体任务，不再误报处理器未配置。worker 解析/模型等待期间由独立线程维持心跳；无需新迁移。

本地准备可能耗时。A 新增私有 `MediaInput.before_submit` 回调，当前 B 处理器在解析完成、创建客户端前调用，在短事务中重验账户/连接/授权、原租约、来源/上下文/控制版本及附件版本/到期。准备期间取消会阻止后续模型提交。回调不进入提示词、HTTP 或持久证据，第三方处理器须遵守该交接；最终检查之后的变化不能撤回已经开始的外部 I/O。墙钟预算包含启动与 IPC，有限的进程回收可能增加几秒。

这是资源隔离，不是完整文件系统/网络沙箱或恶意文件扫描。限额按 worker 生效，部署时仍需控制 worker 数量和主机资源。扫描件 OCR、真实模型与共享 AI 服务不在本批；原部署与会话没有改变。Linux/Windows/macOS CI 检查保护机制，其中 macOS 验证原生明确拒绝，不代表原生解析成功。Apple Silicon Docker、真实文件及编解码仍需队友自己的账号验收。

## PDF 集成与在途模型中止 — 2026-10-12

PR #21 包含 PDF 分支的 `0d91ad1`。有文本层 PDF 在创建客户端前本地解析，模型不能替换本地绑定的页面文字。缺页文字时 complete 降为 partial，全文超限后不再解析下一页。扫描件仍不支持；输出上限不是硬性 CPU/内存沙箱，解析资源隔离仍需在真实启用前完成。

取消、暂停/撤权及内容到期时，在途处理或未解决的核对保留附件/请求身份。晚到模型内容及 review 不会保存，重新授权也不恢复。原租约可记录确定返回或提交前明确拒绝，从而解除占用但不恢复内容；结果不确定则保留 result_unknown，阻止新请求。原租约有效时不能开始核对，核对只读；中止尚未开始的核对也保留原不确定状态。恢复授权不允许重发；来源变更/过期可能阻止自动核对，需要人工处理，没有新增强制清除或盲重发接口。

该批次中模型保持 `_ENABLED=False`，已被上方 2026-10-17 小节取代；日期依据、预算、来源绑定与分模态授权在那一节实现。共享 DeepSeek 部署、真实视觉/语音凭据与能力、供应商验收仍需运营方自行验证。本次不实现扫描件 OCR 或 WhatsApp 发送。

## 真实 PDF 解析器与两层提取 — 2026-10-12

`gigmate.media.pdfparse` 用真实本地解析器（`pypdf==6.20.0`，已加入 `pyproject.toml` 与 `requirements.lock`）替换 `MEDIA_PDF_PARSER_PENDING` 桩。PDF 处理现在是两层：

1. **本地解析（确定性，先于任何厂家调用）。** 逐页原文抽取并施加有界 I/O：至多 200 页（`WahaMediaSegment.page` 上界）、每页文本按至多 4000 字符分块且保留页码、总文本至多 100000 字符（契约上界）。超限输入以 `MEDIA_PDF_PAGE_LIMIT` / `MEDIA_PDF_TEXT_LIMIT` 拒绝——绝不静默截断。不可读字节以 `MEDIA_PDF_NOT_PARSEABLE` 拒绝；无文本层的扫描件以 `MEDIA_PDF_NO_TEXT_LAYER` 拒绝，而不是把像素塞给文本模型。这些拒绝都发生在厂家请求之前，因此处理器映射为 `ProcessingUnavailable`（没有产生任何计费）。可读 PDF 中无文本的页以未决问题形式呈现（"N of M pages carried no extractable text"），不冒充完整覆盖。
2. **业务提取（厂家）。** 抽取出的页与专用 prompt `role_b_media_pdf_v1.txt`（版本头 `1.0.0`，可用 `GIGMATE_MEDIA_PDF_PROMPT_PATH` 覆盖）一起发给 chat 模型。模型只产出 coverage、summary、suggestions 与 unresolved_questions；其输出中的任何 `segments` 键都被忽略，因为最终 `WahaMediaResult` 的 segment 由本地解析器绑定。模型永远无法重打、合并或捏造页面文本；suggestion 的 `source_indices` 由契约对照本地 segment 校验。

验证：`test_media_processor.py` 新增 9 个 PDF 用例（两页真实解析并在模型输出注入 `segments` 键证明本地绑定、无文本层、乱字节、201 页上界、文本总量上界、长页分块、空白页未决问题、解析成功后厂家 5xx、非法 `source_indices`）——该文件 50 例全过，后端全套复跑通过。Ruff check/format 干净；契约导出与基线检查无变化。

这关闭了 2026-10-11 修正清单中的"真实 PDF 解析器"一项。清单中仍开放的项：显式模型能力与按路由凭据核验、时间戳/时区对齐、prompt-injection 测试、真实厂家/编解码验收——实现仍以未激活状态交付（`_ENABLED=False`），没有发起真实模型请求。

## PR #21 媒体集成安全修正 — 2026-10-11

媒体实现以**未激活**状态交付（`_ENABLED=False`），尚未对真实厂家验证。`a5aa0a1` 的工厂契约修复保留。PDF 路由可识别但处理以 `MEDIA_PDF_PARSER_PENDING` 拒绝；把 PDF 二进制当文本解码不是解析。默认 DeepSeek 图像路由以 `MEDIA_VISION_VENDOR_UNVERIFIED` 拒绝；显式的 OpenAI/custom fake-client 形态不能证明模型具备视觉能力。custom 厂家必须显式给出 endpoint。TXT 必须是 UTF-8 且至多 90,000 字符；更长的文件需要后续分块，不允许静默截断。

响应校验保留每个 segment 和来源索引：无效/超长的结果按不确定处理，不静默缩短或重排索引。厂家 segment 未能逐字复现全文时，ASR 全文被拆成有界 segment；coverage 保持 unknown，不支持的时间不臆造。客户端在成功与失败后都会关闭；不确定日志不含原始厂家异常/响应文本。畸形 UTF-8 prompt 在提交前拒绝。smoke 拒绝/未知结果以非零退出。

启用真实媒体前，B 仍需：真实 PDF 解析器、显式的模型能力与按路由的凭据核验、时间戳/时区对齐、prompt-injection 测试、有界 I/O 以及真实厂家/编解码验收。A 的请求身份与来源/版本绑定仍由服务器持有；厂家 request-id 对账未实现，`reconcile()` 保持只读返回 None。未知结果不会被自动或盲目重发。商户证据核对与 C 的业务批准保持分离。本次修正没有访问真实模型、账号、媒体或部署。


2026-10-10 媒体第二批：A 已提供固定的供应商发送时间/商户本次选择时区及已核对只读证据。B 须单独实现 MediaProcessor.process/reconcile，不能把文本提取接口当作媒体实现；C 须约定附件来源并在业务晋升前重新校验。时间不足保留待确认，本批不启用外部发送。见[媒体协议](role-a-media-ingestion.md)。

2026-10-10 媒体对接：[A 的媒体协议](role-a-media-ingestion.md)提供权限范围内字节、不可变请求/来源/哈希标识、绑定来源/上下文的结果存储及核对。真实 OCR/ASR/解析/GenAI 工厂和只读核对由 B 实现。A 没有新增真实适配器，原 deterministic 拒绝 live 输入的边界保留。不能把媒体快照冒充 canonical 消息修订或直接写成已确认工单变化。核对还绑定 expected_result_job_id，防止新结果继承旧核对。

2026-10-09 联调更新：[WAHA/提取统一验收](role-a-integration-acceptance.md)记录控制与 worker 交接。当前 Alembic head 是 `0007_merge_waha_extraction`，汇合未改动的 B 证据迁移和 A 控制/采样分支。Windows 测试使用 pytest 管理临时文件；默认 provider 仍拒绝真实提取，没有增加真实模型或网络调用。

更新：2026-10-10（合并 #18 的闸门/prompt 修复与 #20 的未激活 HTTP 实现
及常闭骨架标志）。[英文对应](../en/role-b-extraction.md)。基于
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

真实模型默认对接 DeepSeek，任何 OpenAI 兼容供应商（`deepseek` /
`openai` / `custom`）都用同一套调用形态。接缝已经预留好，新增真实
provider 时不必改 worker、合约或既有 Replay 逻辑。

`llm` provider 现已**接通真实调用**：`LLMProvider._SKELETON_SEAM` 为
`False`，`_invoke_model` 会发起真实的 OpenAI 兼容 chat-completions POST。
是否到达供应商由 `GIGMATE_LLM_LIVE=1` 与非空 `GIGMATE_LLM_API_KEY` 决定，
二者缺一则分别以 `llm:live-gate-off` / `llm:not-configured` 拒绝且不构造
客户端。下文"真实启用前验收门槛"**尚未清空**——尤其是一次真实供应商
请求都还没有发出，因此供应商/端点语义、真实编解码行为与 prompt 注入
防护仍属未验证。已验证与未验证的实际证据见
[实施状态](../en/implementation-status.md)。

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
| `GIGMATE_EXTRACTION_PROVIDER=llm` | 真实模型 provider（默认 DeepSeek）。配好 `GIGMATE_LLM_LIVE=1` 与 `GIGMATE_LLM_API_KEY` 才真正调用；否则返回带 `llm:live-gate-off` 或 `llm:not-configured` 的 `needs_review`。 |
| 未知名称 | 启动时直接报错，绝不悄悄回落。 |

测试通过 `gigmate.extraction.registry._reset_provider_for_testing` 注入
provider，不污染进程级缓存。

### `llm` provider（DeepSeek / OpenAI 兼容）

`gigmate.extraction.llm.LLMProvider` 就是真实模型 provider。它同样遵守
`ExtractionRequest.origin` 信任边界，读取 `gigmate/extraction/prompts/`
下的版本化 prompt 文件，并把配置好的模型与 prompt 版本写入
`ModelCallTrace`，便于人工核对为何被拒绝。

`_invoke_model` 发起真实的 OpenAI 兼容 chat-completions POST（30 秒超时、
重试 1 次），`_parse_response` 把 JSON 严格校验成 `ChangeProposal`。实现
闸门 `LLMProvider._SKELETON_SEAM` 为 `False`，调用路径可达；
`GIGMATE_LLM_LIVE` 与 `GIGMATE_LLM_API_KEY` 才是一个部署真正要开的闸门。
模块只读 `GIGMATE_LLM_API_KEY`，刻意忽略 `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY`，让模型密钥继续留在运维显式控制之下。

每个 outcome 都带 `usage`——供应商的 token 用量归一化为 `prompt_tokens` /
`completion_tokens` / `total_tokens`（丢弃 DeepSeek 缓存计数等厂商专属字段）——
`persist_proposal` 会把它写入 `model_call_traces.prompt_tokens` /
`completion_tokens` / `total_tokens`（迁移 `0014_llm_usage`）。所有拒绝路径
保持 `NULL`："没有请求到达供应商"与"这次调用免费"是两个不同的事实。

配置（环境变量）：

| 变量 | 用途 |
| --- | --- |
| `GIGMATE_LLM_PROVIDER` | 供应商名（`deepseek` / `openai` / `custom`），写入 `model_version`，并校验该 build 是否真正支持。 |
| `GIGMATE_LLM_MODEL` | 模型标识（如 `deepseek-chat`、`gpt-4o-mini`）。未配置时记为 `skeleton:pending`。 |
| `GIGMATE_LLM_API_KEY` | 仅服务端使用；provider 每次调用都重新读取，绝不存到实例上，也绝不写日志。 |
| `GIGMATE_LLM_ENDPOINT` | 可选 base URL 覆盖。未设置时端点按 vendor 取：`deepseek` -> `https://api.deepseek.com`、`openai` -> `https://api.openai.com`、`custom` -> 以 `llm:not-configured` 拒绝（必须显式配置）。 |
| `GIGMATE_LLM_PROMPT_PATH` | 可选 prompt 文件覆盖。 |
| `GIGMATE_LLM_LIVE=1` | 显式运维闸门，真实调用必需。闸门关闭时 Provider 层直接拒绝所有调用并写 `llm:live-gate-off`（即便已配置供应商与模型），trace 中立即可见，绝不悄悄回落。 |
| `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` | 显式允许 `request.origin == "live"` 进入模型的开关，默认关闭。 |

#### 双闸门安全网

调用 `_invoke_model` 前必须同时打开两道闸门：

1. **类标志 `LLMProvider._SKELETON_SEAM`**——现为 `False`（接缝已实现）。
   只要它是 `True`，无论环境变量如何配置、运维闸门开关与否，都直接返回
   `llm:seam-pending`，连 HTTP 客户端都不会构造。这是防止"某个 build 的
   `_invoke_model` 退化成桩却悄悄进入真实调用模式"的兜底。
2. **`GIGMATE_LLM_LIVE=1`**——运维开关。没设这个变量时仍以
   `llm:live-gate-off` 拒绝。

执行顺序：prompt 异常检查 → 实现闸门（仅当 `_SKELETON_SEAM` 回到 `True`
时才出 `llm:seam-pending`）→ 配置完整性（vendor/model/key
缺失或 vendor 未知 → `llm:not-configured`）→ live 闸门
（`llm:live-gate-off`）→ 接线检查（vendor 已知、key 已设）→ live 来源
gating 门（未开 `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` 时
`llm:origin-live-refused`）→ `_invoke_model`。两个方向都有测试固化：开通
路径用假客户端（`test_llm_provider_live_gate_on_sends_fake_client_request`），
关闭路径用测试子类
（`test_llm_provider_implementation_gate_still_refuses_when_closed`）。

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
`except Exception`，也不会触发 `PROCESSING_FAILED` 重试风暴（空版本与非
UTF-8 原先会直接抛出 `ValidationError` / `UnicodeDecodeError` 进入 worker
失败路径）。prompt 文件正文固化了几条硬规则——不得把字段标为
`confirmed`、不得授予执行权限、遵守来源信任边界——下一批次只需与闸门
翻转一起编辑这一个文件。

评测清单里的 `case-008-llm-skeleton-needs-review` 在使用
`--provider llm` 跑清单时通过；通用 needs_review 用例（3、4、5、6、7）
在 `llm` 下同样通过。matched 用例（1、2）在没有真实 key 时于 `llm` 下
预期失败——provider 以 `llm:not-configured`（或 key 在、闸门未开时的
`llm:live-gate-off`）拒绝，永远得不到 matched；它们在默认 deterministic
provider 下通过。用真实 DeepSeek key 跑清单仍未验证，见上文验收门槛。

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
| `GIGMATE_MEDIA_PDF_PROMPT_PATH` | 可选 PDF 提取 prompt 文件覆盖。 |

MIME 路由（`gigmate.media.routing`）：

| MIME | 派发键 | 厂家适配器 |
| --- | --- | --- |
| `image/png`、`image/jpeg`、`image/webp` | `ocr` | chat-completions 视觉输入 |
| `audio/ogg`、`audio/mpeg`、`audio/wav`、`audio/mp4`、`audio/x-m4a` | `asr` | `/v1/audio/transcriptions` |
| `application/pdf` | `pdf` | 本地逐页抽取（`gigmate.media.pdfparse`）后走 chat-completions 业务提取 |
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

## 真实启用前验收门槛（尚未清空）

**2026-10-17 状态：实现闸门已翻开，但这些门槛一项都没清。**
`LLMProvider._SKELETON_SEAM` 现为 `False`，媒体接缝标志也已打开，因此
只要运维导出 `GIGMATE_LLM_LIVE=1` 和真实 key，真实调用路径就可达。这意味
下列条目不再是"启用前的理论问题"，而是**当前代码里的实际风险**，每一项
仍需各自授权批次与评审，之后才能把真实客户流量交给这个 provider。未配置
key 的运维不受影响：provider 以 `llm:not-configured` / `llm:live-gate-off`
拒绝，且不构造任何客户端。

下列验收门槛**均未清空**：

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
- **vendor 与 endpoint 语义必须显式。** —— **2026-10-17 已清空。**
  `LLMProvider._resolve_endpoint()` 已把每个已知 vendor 与各自文档化的默认
  endpoint 绑定（`deepseek` -> `https://api.deepseek.com`、
  `openai` -> `https://api.openai.com`）；`custom` 未显式配置
  `GIGMATE_LLM_ENDPOINT` 时以 `llm:not-configured` 拒绝；未知
  `GIGMATE_LLM_PROVIDER` 此前即由 `_is_wired_for_live` 拒绝。不支持
  `response_format=json_object` 的模型（`deepseek-reasoner`）在本地以
  `llm:model-unsupported` 拒绝。只剩命名问题：如果 `openai` 指"任何 OpenAI
  兼容协议"而非"OpenAI 这家供应商"，需要在配置面和文档里写清楚，避免评审者
  按较窄含义误读。
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

上述门槛写在这里是为了让评审者看清：调用路径已经打开，而下面这些仍然
未经验证。每一项都是独立批次、独立评审。

## 待办

- 真实模型 provider 激活：实现闸门翻转（`LLMProvider._SKELETON_SEAM =
  False`）与媒体接缝标志已完成，后续授权批次仍必须完成三件事——(a) 清空
  上文"真实启用前验收门槛"（出处重绑定、vendor/endpoint 语义、重试与租约
  设计、日期依据、诊断脱敏）；(b) 用真实 key 发出**至少一次真实供应商
  调用**并留下证据（至今一次都没有）；(c) 把真实授权与 live-origin 通道
  接入独立的授权审查（live-origin guard 现已可达；其
  `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` 开关由隔离测试固化，仍默认关闭）。
  同时补上 prompt-injection 回归与延迟预算。接缝、prompt
  版本兜底链、`llm:prompt-malformed` 与 `llm:seam-pending` trace 备注、
  `case-008-llm-skeleton-needs-review` 评测用例，以及
  `_prompt_load_error` 审计字段均已就位。
- D 前端面向真实 provider 输出的 `pending_change_ids` 展示；当前
  Replay 卡片已能呈现，但真实 provider 来回之前不更新前端。
- 真实 provider 上线后细化 `unresolved_questions` 给商户的人工核对呈现。
- 媒体侧的厂家 `reconcile()`：chat-completions 厂家一般不暴露基于
  request-id 的查找，当前实现返回 `None`，worker 需等待人工重试。
  后续批次可在接缝标志开启后追加厂家特定查找。
- B 侧的 prompt-injection 回归套件（图像 OCR + 音频 ASR + PDF 解析）。
  当前处理器只信任捆绑的 prompt、对格式异常输入拒绝调用；后续授权
  批次应加入对抗输入夹具。
