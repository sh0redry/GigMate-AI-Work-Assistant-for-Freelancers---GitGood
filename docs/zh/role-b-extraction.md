# Role B 抽取子系统

## 真实启用前评审修正（PR #31） — 2026-10-16

独立评审在 `a4e6b8a` 上针对 [PR #31](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/31) 提出五项 P2 问题，每一项都由评审者用合成数据、假传输与假时钟复现，不是静态推断。五项全部在此修正，**同样不翻接缝**：`LLMProvider._SKELETON_SEAM` 仍为 `True`、`gigmate.media.processor._ENABLED` 仍为 `False`，没有真实供应商请求、凭据、网络调用或客户消息。这一批只是正确性修正，不构成启用授权。

- **P2-1：总时限落实到每次请求。** 原来每次尝试都拿固定的 30 秒单次超时，总预算只在失败后才检查，于是「30 秒超时 + 重试 30 秒」实际跑 60 秒，超过声明的 45 秒。现在每次尝试只继承**剩余**总预算作为自己的超时（`min(_REQUEST_TIMEOUT_S, remaining)`）；剩余不足 `_MIN_REQUEST_TIMEOUT_S = 1s` 的尝试根本不发出；超过 `_TOTAL_DEADLINE_S` 才返回的响应以稳定码 `llm:deadline-exceeded` 拒绝 —— worker 租约早已过期，迟到的成功毫无价值，且绝不重试。
- **P2-2：费用上限在花钱之前生效。** 原来的费用检查发生在钱已经花掉之后，只能拒绝提案而不能阻止支付；预算设为 0 时仍会发出一次调用。现在 `_cost_plan` 先算：预算按 `_MAX_RETRIES + 1` 次尝试分摊，单次尝试的有界最坏情况（估算的 prompt token + 配置的输出上限）必须装进自己那一份，否则以 `llm:cost-budget-exceeded` 拒绝且不发出；prompt 本身超过 `GIGMATE_LLM_MAX_INPUT_TOKENS` 时以 `llm:cost-input-too-large` 拒绝，而不是截断。请求体携带该输出上限作为 `max_tokens`，让供应商收到与预算同源的约束；非正的 token 上限在启动时报 `llm:cost-tokens-invalid`。调用后的检查保留为第二道防线：账单超出预算的响应仍然无法晋升提案。
- **P2-3：上下文版本也由服务端绑定。** 出处守卫校验了 `base_work_order_version` 却没校验 `base_context_version`，后面的 `setdefault` 也覆盖不了模型自带的值，于是 `base_context_version=999` 对上 `context_version=7` 的响应仍能变成 `matched`，错误版本随后流入 `Proposal` / `RequirementChange`。现在值不一致即以 `llm:response-provenance-failed:base_context_version` 拒绝，之后再写入服务端自己的值。
- **P2-4：遍历前先检查集合类型。** 出处守卫运行在 Pydantic 之前，直接遍历未校验的 `changes` / `sources`，于是 `changes: 17`、`changes: true` 这类合法 JSON 会从 `propose` 抛出未捕获的 `TypeError` —— worker 会把整个作业重试一遍并重复付费，而不是记录一个稳定 `needs_review`。现在这些形状返回 `llm:response-provenance-failed:changes-shape` / `:source-shape`（建议字段同理）。
- **P2-5：时间依据守卫覆盖 `instant`。** 原检查只认 `timed` / `date_only`，`InstantDeadline`（`kind: instant`，即「明天交稿」的形状）—— 客户最常输入的相对日期 —— 可以带着模型捏造的时间戳直接穿过门槛四。现在所有含日期的契约 kind 都被守卫，old 与 new 值都检查。

验证证据（全部合成）：五个反例现已成为回归测试。`apps/backend/tests/test_extraction_gates.py` **39 通过**（`a4e6b8a` 时为 27）、`test_extraction_batch2.py` **50 通过**（`a4e6b8a` 时为 40）；在当前工作树（同时含进行中的 batch 3 文件）测得启用前套件 **106 通过**。后端全套 **745 通过／25 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`），未改动的 main 上同样失败。Ruff 检查／格式 **100 文件**、`scripts/export_contracts.py --check` 一致、`check_baseline.py` **82 Markdown／967 本地链接**、Alembic 唯一 head `0018_model_call_cost` 且在 SQLite 上完成升级→回退→升级往返无漂移（`alembic check` 干净）、离线评测 **7 通过／0 失败**（prompt 1.2.0）。新增迁移、契约与 API 表面为零：改动全部在 `gigmate.extraction.llm` 内部，外加两个新的运维设置 `GIGMATE_LLM_MAX_*_TOKENS`。未验证：PostgreSQL 并发／行锁（未配 `TEST_DATABASE_URL`）、Linux 容器内 PDF 复跑，以及任何真实供应商行为。

## 真实启用前验收门槛已实现 — 2026-10-16

下文["真实启用前验收门槛"](#真实启用前验收门槛)五项已全部落地，回归测试在 `apps/backend/tests/test_extraction_gates.py`。接缝仍关闭：`LLMProvider._SKELETON_SEAM` 仍为 `True`、`gigmate.media.processor._ENABLED` 仍为 `False`，本批次没有真实供应商请求、真实密钥或真实客户消息，**不构成启用授权**。

- **门槛一：出处重绑定。** `_parse_response` 把 `conversation_id`、`work_order_id`（必须是 `candidate_work_order_ids` 成员）、`base_work_order_version`（必须等于 worker 解析到的版本）、`base_context_version`（P2-3 评审修正新增）以及每条 `sources[].message_id` / `message_revision` 重新绑定回本次实际发出的请求；不匹配返回 `needs_review`、备注 `llm:response-provenance-failed`，原因码 `llm:response-provenance-failed:<字段>`，绝不会变成 `matched`。遍历前先检查集合类型（P2-4），非列表的 `changes` / `sources` 是稳定拒绝，不再是未捕获的 `TypeError`。
- **门槛二：vendor／endpoint 语义。** 每个已知 vendor 自带文档化默认端点（`deepseek` → `https://api.deepseek.com`，`openai` → `https://api.openai.com`）；`custom` 没有默认值，必须显式配置 `GIGMATE_LLM_ENDPOINT`。未知 vendor 以 `llm:vendor-unknown` 拒绝，非 URL 覆盖以 `llm:endpoint-invalid` 拒绝，覆盖值等于另一个 vendor 默认端点时以 `llm:vendor-endpoint-mismatch` 拒绝。
- **门槛三：重试、预算与关联。** 单次抽取总耗时设上限（`_TOTAL_DEADLINE_S = 45s`），只有预算仍有剩余才重试；只对瞬时类重试（httpx 超时／连接错误／重置、HTTP `5xx`），`4xx`、解析与结构错误一律不重试。每次尝试都带同一个持久化 `X-Gigmate-Request-Id` 头，该 id 落库到 `model_call_traces.request_id`（迁移 `0017_model_call_request_id`），便于与供应商日志对齐。P2-1 评审修正让截止时间同时成为每次请求的预算：每次尝试只拿到**剩余**时间，不足 `_MIN_REQUEST_TIMEOUT_S = 1s` 的尝试不发出，截止后才到达的响应用 `llm:deadline-exceeded` 拒绝，不晋升。
- **门槛四：真实时间依据。** `ExtractionRequest` 增加服务端附上的 `message_received_at`（连接器发送时间，UTC `Z`）与 `workspace_timezone`（运维 IANA 配置，`GIGMATE_WORKSPACE_TIMEZONE`）。prompt（`role_b_extraction_v1.txt`，升到 **1.1.0**）要求模型只依据 `time_basis` 解析相对日期并输出 UTC `Z`；依据缺失或不合法时，provider 以 `llm:time-basis-missing` 拒绝任何含日期的变更，而不是猜一个日期；地址／摘要等非日期字段不受影响。P2-5 评审修正把「含日期」扩展到全部契约 kind —— `timed`、`date_only` **与** `instant`（`InstantDeadline`，即「明天交稿」的形状）—— old 与 new 值都要检查。worker 在调用后还会重读会话上下文与工单版本，丢弃基于过期快照的结果；自身租约已过期的结果同样丢弃。
- **门槛五：诊断脱敏。** 失败原因改为稳定码（`llm:http-failed:timeout`、`llm:http-failed:status-5xx`、`llm:response-malformed:json`、`llm:response-schema-failed:<字段路径>`、`llm:prompt-load-failed:…`）。异常类名、异常消息、端点主机、vendor 名称与密钥片段都不会进入 `refused_reason`。

启用前仍缺的不是代码：单独授权的真实凭据／live-origin 通道、真实负载下实测的延迟预算，以及把供应商 I/O 完全移出 worker 行锁（结构性改动，需与 A／C 达成一致）。验证证据记在 `docs/zh/progress.md`。

## 真实启用前第二批 — 费用边界、启动校验、注入回归 — 2026-10-16

本批次落地了剩余启用待办中的三项，**同样不翻接缝**：`LLMProvider._SKELETON_SEAM` 仍为 `True`、`gigmate.media.processor._ENABLED` 仍为 `False`，没有真实供应商请求、凭据或客户消息；新代码路径通过与五项门槛相同的「测试子类开闸」方式验证。回归测试在 `apps/backend/tests/test_extraction_batch2.py`。

- **费用边界。** 每次调用按内置千 token 单价表（键为 `(vendor, model)`）计价，可用 `GIGMATE_LLM_COST_INPUT_USD_PER_1K` / `GIGMATE_LLM_COST_OUTPUT_USD_PER_1K` 覆盖。预算来自 `GIGMATE_LLM_COST_BUDGET_USD`（默认每次 0.10 美元）。P2-2 评审修正让它在花钱**之前**就成立：`_cost_plan` 把预算按 `_MAX_RETRIES + 1` 次尝试分摊，单次尝试的有界最坏情况（估算 prompt token + 配置的输出上限）必须装进自己那一份，否则以 `llm:cost-budget-exceeded` 拒绝且不发出；prompt 超过 `GIGMATE_LLM_MAX_INPUT_TOKENS` 时以 `llm:cost-input-too-large` 拒绝，而不是截断。请求体携带该输出上限作为 `max_tokens`（`GIGMATE_LLM_MAX_OUTPUT_TOKENS`），非正的 token 上限在启动时报 `llm:cost-tokens-invalid`。调用后的检查保留为第二道防线：计算费用超预算的响应仍以 `llm:cost-budget-exceeded` 拒绝；完全无法计价的调用则在发出**之前**就以 `llm:cost-pricing-missing`（模型未知且无覆盖）、`llm:cost-pricing-partial`（只配了两个覆盖之一）或 `llm:cost-pricing-invalid` 拒绝。供应商省略 `usage` 时不静默当免费：trace 记录 `llm:cost-usage-missing`（结构非法时 `llm:cost-usage-invalid`），`cost_usd` 保留为 null。`model_call_traces` 新增 `input_tokens`、`output_tokens`、`cost_usd`（迁移 `0018_model_call_cost`），运维可直接还原花费。调用后的检查仍放在 HTTP 与解析门槛**之后**，因为 `4xx` 响应没有 usage 数据，解析失败也不能计入预算；留给它抓的是无视 `max_tokens` 的供应商。
- **Provider 配置启动校验。** `gigmate.extraction.llm.validate_provider_config()` 是纯审计函数，不取会话、不开 socket，worker 启动时经 `gigmate.worker.audit_provider_config()` 调用。报告项包括 `llm:vendor-unknown`、`llm:endpoint-invalid`、`llm:vendor-endpoint-mismatch`、`llm:endpoint-required`、`llm:prompt-path-invalid`、`workspace-timezone-invalid`、上述四个费用码，以及（仅 `GIGMATE_LLM_LIVE=1` 时）`llm:api-key-missing`。策略：活门打开时任何问题都让 worker 拒绝启动 —— 一个即将发出真实供应商调用的进程，不能带着已知错误的配置运行；活门关闭时同样的问题只记 warning，因为关闭的接缝本就拒绝所有调用。传入 `env` 映射即可让测试在不改动真实环境的前提下驱动审计。
- **Prompt-injection 回归集。** `contracts/evaluation/injection.json` 提供九个合成案例，每个案例把一条含注入指令的客户消息与「被诱导的模型」会返回的 `compromised_response` 配对。由 `test_extraction_batch2.py::test_injection_regression_suite` 驱动，断言任何案例都不会产出 `matched` 提案，且各自命中预期稳定码：`llm:response-provenance-failed`（外来 `work_order_id` / `conversation_id`、过期 `base_work_order_version`、伪造的 source 消息）、`llm:response-schema-failed`（AI 把字段标为 `confirmed`、夹带额外键）与 `llm:time-basis-missing`（用模型自己的「现在」凭空造日期）。这是纯文字回归集；媒体附件（OCR／ASR／PDF）的同类套件仍是单独授权批次。

启用前仍待：带独立评审的真实凭据／live-origin 通道、真实负载下的延迟预算、媒体附件注入套件，以及把供应商 I/O 移出 worker 行锁。

## 真实启用前第四批 — 媒体附件注入回归集 — 2026-10-16

附件内容由攻击者可控，因此媒体接缝获得与文字接缝同样的待遇。新增纯分类器 `gigmate.media.injection`，扫描一个媒体结果的每个不可信面 —— 商户/攻击者提供的 caption、OCR 文本或本地解析出的页面文本、ASR 转写文本，以及供应商自己的 `summary` / `suggestions` / `unresolved_questions` —— 对照一套收紧的双语模式（忽略先前指示、角色篡改、权力声索、绕过复核、提示词外泄、指令性动词）。命中记为稳定的 `media:instruction-text-detected:<field>` 标记，写入新的可选字段 `WahaMediaResult.injection_markers`（默认空；结果随既有 JSON 列落库，无需迁移），并以 `MEDIA_INJECTION_DETECTED` 只记录模式 id 与字段名，绝不记录载荷原文。

检测是标记而非裁决：不阻断、不改写、不采信内容，也不授予或剥夺权限 —— `WahaMediaEvidence.business_confirmation_required` 仍是 `Literal[True]`，测试断言即使结果已被标记，把它改成 `False` 也会被拒绝。取舍是写明的：一个标记只是让人多看一眼，漏掉一条指令却会产出错误工单，因此偏向「宁可标」；正因这种偏向可能扰民，`contracts/evaluation/media_injection.json` 为每个攻击案例都配了干净的对照案例 —— 一旦普通商户内容被误标，套件即失败。九个合成案例覆盖图片 caption 与 OCR 文本、语音转写中的口头指令、PDF 隐藏文字层、既试图改写正文又向业务层夹带指令的 PDF 模型，以及藏在 `unresolved_questions` 里的指令。PDF 路径同时重新钉住「页文本始终来自本地解析」。

启用前仍待办：真实媒体内容。这里没有见过任何真实图片、音频、PDF 或供应商响应 —— 字节是合成占位、载荷是脚本化的 —— 因此模式集在真实商户内容上的误报率未知，运维应先读标记再行动。PDF 端到端变体在原生 macOS 上是**跳过**而非通过：本地解析器以 `MEDIA_PDF_LIMIT_UNAVAILABLE` 拒绝，因此套件以解析器产出的数据结构驱动 `coerce_pdf_extraction`。

## 真实启用前第三批 — 新建工单识别契约、未知结果处置、评测分类 — 2026-10-16

再落地 issue #29 中 B 侧三项待办，**仍不翻接缝**（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`）。回归测试在 `apps/backend/tests/test_extraction_batch3.py`。

- **`new_work_order` 识别契约。** `ChangeProposal` 新增可选 `new_work_order` 块（`NewWorkOrderSuggestion`）：`summary`、识别到的关键 `fields`（每项含值、绑定本次服务端发出消息 revision 的 `sources` 与 `reason`）、`missing_fields`、`unresolved_questions` 与 `confidence`。它只是识别输出 —— 不建单、不确认任何字段、不授予执行权；商户仍需手动建单，客户提出、客户确认与商户批准保持独立。契约禁止它与 `matched` 归类或非空的 `work_order_id` 同时出现，因此模型无法在改期旁边夹带一个新单。未知值保持缺失：客户没给的字段不进 `fields`（或值为 null）并列入 `missing_fields`。建议随既有提案 JSON 落库，无需迁移，也永远不会为它生成 `RequirementChange` 行。
  **待 `llm.py` 落地：** 把出处重绑定（门槛一）扩展到建议字段 —— 引用商户从未见过的消息以 `llm:response-provenance-failed:suggested-source-message-id` 拒绝；并把时间依据门槛（门槛四）扩展到建议中的相对日期，与变更中的相对日期同样拒绝。两处防护已写好且本地通过，由 `test_extraction_batch3_provider.py` 与 `inj-010` 注入夹具钉住，但 `llm.py` 正被并发修改（review fix P2-1），因此本提交只落地契约、prompt、评测与文档；provider 侧那一半随 `llm.py` 在下一个提交落地。这就是 C 的 #26 手工建单流程可以消费的契约；`case-001` 与 `case-004` 现已钉住「当前确定性 provider 不产生误报建议」。
- **文字提取的未知供应商结果。** 超时或无人应答的调用属于「未知」，不是静默失败。策略现已成文并由测试钉住：一次有界重试（`_MAX_RETRIES = 1`，且必须在 `_TOTAL_DEADLINE_S` 预算内），两次尝试携带**同一个**持久化 request id，然后产出 `needs_review` 提案、稳定拒绝码 `llm:http-failed:timeout`，并把 request id 存进 trace 行以便与供应商日志对账。之后不再重复提交；由于提取不写入任何客户可见状态，供应商侧即使重复完成也不会产生业务事实，作业保留给人工复核。媒体路径保持既有成文立场（`reconcile()` 返回 `None`），任何情况下都不靠盲目重发解决。
- **评测分类输出。** `EvaluationCase` 新增 `expected_new_work_order`，`evaluate_case` 逐例输出 `actual_new_work_order`、`refused_reason` 与 `notes`，`scripts/run_evaluation.py` 新增 `classification` 块：按期望归类的通过／失败、提出新单建议的案例数、出现的拒绝码以及失败案例 id。这是 E 后续填入真实目标数据的结构；当前运行仍是合成数据，不构成生产准确率。

prompt（`role_b_extraction_v1.txt`）升到 **1.2.0**：写明 `new_work_order` 输出块、「仅无候选工单时使用」的规则、来源绑定与「未知保持缺失」规则。

启用前仍待：带独立评审的真实凭据／live-origin 通道、真实负载下的延迟预算、与 C 联合核验 revision/版本，以及把供应商 I/O 移出 worker 行锁。媒体附件注入套件已在上面的第四批落地，但该套件仍未见过真实媒体内容 —— 真实附件、真实供应商响应与误报率的实测仍是单独授权批次。

## PDF 资源隔离

供应商调用前的 PDF 解析已改为私有子进程，不在业务 worker 内运行 pypdf。默认墙钟 20 秒、内存 512 MiB、每个 worker 同时一个解析进程、输入 20 MiB、序列化输出 1 MiB。可信服务端设置 `GIGMATE_PDF_TIMEOUT_SECONDS`（1–60）与 `GIGMATE_PDF_MEMORY_MIB`（128–1024）由媒体 Compose 覆盖传给 API/worker，不接受 HTTP 修改。原页数、片段、文字上限及 partial 校验保留。

Windows 挂起启动实际底层解释器，先绑定带已提交内存、CPU、进程数量限制及关闭即终止的私有 Job Object，再恢复执行；不能把限额只设在 venv 启动器上。Linux 使用硬性 RLIMIT_AS/RLIMIT_CPU、关闭 core dump、限制描述符，并绑定父进程生命周期。启动响应确认实际 PID 后才传 PDF 字节。原生 macOS 明确返回 MEDIA_PDF_LIMIT_UNAVAILABLE，后端使用项目 Linux Docker 镜像，不宣称不可靠的原生内存兜底。

子进程通过管道收发，不落临时原文件；固定 UTF-8，不继承模型/WAHA/数据库环境或 worker PYTHONPATH，只加载固定 pypdf 路径。父进程再验输出结构、数量、页码及文字长度。超时、输出超限会终止并回收私有进程、关闭管道；崩溃不视为成功。模型请求前的 PDF 错误码写入媒体任务，不再误报处理器未配置。worker 解析/模型等待期间由独立线程维持心跳；无需新迁移。

本地准备可能耗时。A 新增私有 `MediaInput.before_submit` 回调，当前 B 处理器在解析完成、创建客户端前调用，在短事务中重验账户/连接/授权、原租约、来源/上下文/控制版本及附件版本/到期。准备期间取消会阻止后续模型提交。回调不进入提示词、HTTP 或持久证据，第三方处理器须遵守该交接；最终检查之后的变化不能撤回已经开始的外部 I/O。墙钟预算包含启动与 IPC，有限的进程回收可能增加几秒。

这是资源隔离，不是完整文件系统/网络沙箱或恶意文件扫描。限额按 worker 生效，部署时仍需控制 worker 数量和主机资源。扫描件 OCR、真实模型与共享 AI 服务不在本批；原部署与会话没有改变。Linux/Windows/macOS CI 检查保护机制，其中 macOS 验证原生明确拒绝，不代表原生解析成功。Apple Silicon Docker、真实文件及编解码仍需队友自己的账号验收。

## PDF 集成与在途模型中止 — 2026-10-12

PR #21 包含 PDF 分支的 `0d91ad1`。有文本层 PDF 在创建客户端前本地解析，模型不能替换本地绑定的页面文字。缺页文字时 complete 降为 partial，全文超限后不再解析下一页。扫描件仍不支持；输出上限不是硬性 CPU/内存沙箱，解析资源隔离仍需在真实启用前完成。

取消、暂停/撤权及内容到期时，在途处理或未解决的核对保留附件/请求身份。晚到模型内容及 review 不会保存，重新授权也不恢复。原租约可记录确定返回或提交前明确拒绝，从而解除占用但不恢复内容；结果不确定则保留 result_unknown，阻止新请求。原租约有效时不能开始核对，核对只读；中止尚未开始的核对也保留原不确定状态。恢复授权不允许重发；来源变更/过期可能阻止自动核对，需要人工处理，没有新增强制清除或盲重发接口。

模型保持 `_ENABLED=False`。共享 DeepSeek 部署、真实视觉/语音凭据与能力、日期依据、提示注入及供应商验收仍是独立工作；本次不实现扫描件 OCR 或 WhatsApp 发送。

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

真实模型接入（Anthropic、OpenAI 或其他具体供应商）是后续单独授权批次。
接缝已经预留好，新增真实 provider 时不必改 worker、合约或既有 Replay
逻辑。本批次交付**未激活调用实现**的 `llm` provider：注册表选择、
配置、prompt 版本与 OpenAI 兼容的 HTTP/解析调用形态都已接好，但常闭的
`LLMProvider._SKELETON_SEAM` 标志把它们全部挡在网络之外；激活真实模型
只需清空下文"真实启用前验收门槛"并翻转该标志（连同运维闸门），不改
worker、合约或注册表。

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
| `GIGMATE_EXTRACTION_PROVIDER=llm` | 未激活调用实现的真实模型接缝；`_SKELETON_SEAM=True` 期间始终返回带 `llm:seam-pending` 的 `needs_review`。 |
| 未知名称 | 启动时直接报错，绝不悄悄回落。 |

测试通过 `gigmate.extraction.registry._reset_provider_for_testing` 注入
provider，不污染进程级缓存。

### `llm` provider 骨架

`gigmate.extraction.llm.LLMProvider` 是后续单独授权真实模型批次的非发请求
接缝。它同样遵守 `ExtractionRequest.origin` 信任边界，读取
`gigmate/extraction/prompts/` 下的版本化 prompt 文件，并把配置好的模型
与 prompt 版本写入 `ModelCallTrace`，便于人工核对为何被拒绝。

本批次刻意交付**未激活的调用实现**：`_invoke_model` 已能发起真实的
OpenAI 兼容 chat-completions POST（30 秒超时、重试 1 次），`_parse_response`
会把 JSON 严格校验成 `ChangeProposal`，但常闭类标志
`LLMProvider._SKELETON_SEAM` 让所有请求都到不了网络，直到"真实启用前
验收门槛"在各自授权批次清空。期间模块只读 `GIGMATE_LLM_API_KEY`，
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
| `GIGMATE_LLM_LIVE=1` | 显式运维闸门。`_SKELETON_SEAM` 翻开后还必须开它才能真的发起调用；在此之前骨架标志先拒绝。翻开之后，闸门关闭时 Provider 层仍直接拒绝所有调用并写 `llm:live-gate-off`（即便已配置供应商与模型），两种情形都在 trace 中可见，绝不悄悄回落。 |
| `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` | 显式允许 `request.origin == "live"` 进入模型的开关，默认关闭。 |

#### 双闸门安全网

调用 `_invoke_model` 前必须同时打开两道闸门：

1. **类标志 `LLMProvider._SKELETON_SEAM`**——本批次为 `True`。只要是
   `True`，无论环境变量如何配置、运维闸门开关与否，都直接返回
   `llm:seam-pending`，连 HTTP 客户端都不会构造。这是防止"下一批次只填
   `_invoke_model` 就意外进入真实调用模式"的兜底。
2. **`GIGMATE_LLM_LIVE=1`**——运维开关。即便类标志已翻为 `False`，
   没设这个变量时仍以 `llm:live-gate-off` 拒绝。

执行顺序：prompt 异常检查 → 骨架标志 → 配置完整性（vendor/model/key
缺失或 vendor 未知 → `llm:not-configured`）→ live 闸门
（`llm:live-gate-off`）→ 接线检查（vendor 已知、key 已设）→ live 来源
gating 门（未开 `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` 时
`llm:origin-live-refused`）→ `_invoke_model`。骨架标志为 `True` 时所有
调用都先以 `llm:seam-pending` 拒绝，配置错误的生产环境不可能发出真实
网络请求。翻开骨架标志之后的 `llm:live-gate-off`、`llm:origin-live-refused`
与假客户端请求形态，由仅在测试子类上翻转 `_SKELETON_SEAM=False` 的隔离
测试固化；生产标志保持关闭。

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
.venv/bin/python -m pytest apps/backend/tests/test_extraction_gates.py apps/backend/tests/test_extraction_batch2.py -q
.venv/bin/python scripts/check_baseline.py
```

最后一条 `pytest` 是真实启用前套件：五项门槛加第二批（费用边界、启动校验、注入回归）。两个文件都不打开接缝，因此均可离线运行、无需凭据。

PostgreSQL 测试是有意义的运行；SQLite 不证明行锁，只验证条件兼容性。
本批次不合成真实 WhatsApp 流量。

## 真实启用前验收门槛

2026-10-16：下列门槛已实现并有回归测试，见上文[批次说明](#真实启用前验收门槛已实现--2026-10-16)。原文保留，便于评审对照原始要求并确认接缝没有被悄悄打开。

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

- 真实模型 provider 激活：上文门槛已于 2026-10-16 实现；费用边界、启动
  校验与文字注入回归集在同日的「真实启用前第二批」落地，`new_work_order`
  识别契约、未知结果处置与评测分类输出在同日的第三批落地，因此下一单独授权
  批次需要 (a) 把真实授权与 live-origin 通道接入独立的授权审查，并在真实
  负载下实测延迟预算；(b) 把 `LLMProvider._SKELETON_SEAM` 翻为 `False`。
  （当前 live-origin guard 已经在该 provider 中实现，但骨架标志为 `True`
  时不可达；其 `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` 开关由仅测试子类的隔离
  测试固化）。接缝、prompt 版本兜底链、`llm:prompt-malformed` 与
  `llm:seam-pending` trace 备注、`case-008-llm-skeleton-needs-review` 评测
  用例，以及 `_prompt_load_error` 审计字段均已就位。
- C 侧手工建单（C #26）现可消费第三批交付的 `new_work_order` 建议契约：
  该块随提案 JSON 落库、与 `matched` 归类互斥、自身绝不建单。B 侧部分已完成；
  接进商户「从会话建单」流程，以及模型回传 revision/版本的联合核验，仍等 C。
- D 前端面向真实 provider 输出的 `pending_change_ids` 展示；当前
  Replay 卡片已能呈现，但真实 provider 来回之前不更新前端。`new_work_order`
  建议同样需要自己的卡片（「识别到新单，仍缺 X」），理由相同。
- 真实 provider 上线后细化 `unresolved_questions` 给商户的人工核对呈现。
- 媒体侧的厂家 `reconcile()`：chat-completions 厂家一般不暴露基于
  request-id 的查找，当前实现返回 `None`，worker 需等待人工重试。
  后续批次可在接缝标志开启后追加厂家特定查找。
- B 侧的 prompt-injection 回归套件（图像 OCR + 音频 ASR + PDF 解析）。
  当前处理器只信任捆绑的 prompt、对格式异常输入拒绝调用；后续授权
  批次应加入对抗输入夹具。文字套件已在「真实启用前第二批」
  （`contracts/evaluation/injection.json`）落地，可作为范式复用，但媒体的
  攻击面（图像中的对抗文字、音频播放注入、PDF 元数据）不同，需要独立夹具。
