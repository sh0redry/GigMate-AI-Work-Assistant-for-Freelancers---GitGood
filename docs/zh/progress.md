# 已完成工作与验证记录

## 状态按钮文案、变更计数与审批筛选 — 2026-10-17

工单进度按钮改为描述「要做什么」（开始处理／标记等待客户／完成工单／取消工单），不再直接显示结果状态。此前处于待确认的工单只出现一个写着「已取消」的按钮，看起来像结果而不是唯一可执行的动作。

变更标题同时显示待确认提议数与已记录变更总数，已确认的变更不再和「0 项提议」并排出现。审批列表在选中草稿被筛掉并继续保留时，不再同时显示「此筛选下没有草稿」。

验证：前端 **176 通过**，含新增回归（动作文案不得与状态名重复）；TypeScript 与 Prettier 通过。未改接口、契约、迁移与后端，属实现层验证，不代表组员或真机验收。

## PR35 与 main 集成验证 — 2026-10-17

按 Kyrie 本轮处理冲突并合并 PR35 的指示，把 main `0b665f0`（已合入 PR36）接入 PR35 修复版。冲突仅在这两份进度文档，保留 PR35 和 PR36 双方记录；接口、业务代码和迁移没有需要另写实现的冲突。Linux、锁定依赖及新建隔离 PostgreSQL 的集成全量后端 **1090 通过 / 1 跳过**；前端 **175 通过**，API 类型、Ruff 检查与格式、契约导出、基线及空白检查均通过。这是集成验证，不代表新增组员批准或真实模型／WhatsApp 验收。

## PR35 草稿绑定与配置检查修复 — 2026-10-17

Kyrie 授权在 William 的 PR35 上直接修复，由 William 独立复审本提交。创建草稿时，AI 提议必须明确属于当前工单、工单版本仍有效，提议的会话也必须归属正确、仍获授权并确实关联该工单。同一工单关联多个聊天时不再随便选第一条：有提议则按提议确定；纯手写草稿无法指明聊天时拒绝歧义。读取和取用共用归属、会话／工单版本、授权、关联及提议检查。尚未取用的失效草稿显示 `revoked`，取用返回 409；读取不改数据库，`revoked_at` 只记录显式撤销。已取用历史保留。有效提议重复提交时可在每日上限后取回原草稿，不会从另一工单返回错误记录。

私密配置检查改为识别实际选中的 `reviewed_llm`，复用该入口的可用性检查，不再拿永久关闭的旧 `llm` 入口误报。部署准备状态还要求人工核对的价格、真实来源开关和时区；支持直接值和文件凭据，只报存在性，不打印 key、不调用供应商。旧入口、离线／未知入口及缺失／关闭配置仍明确失败。模型每日调用／token 配额及模型账号白名单尚未实现，检查器和启用清单不再把它们写成已生效限制；原有单次费用和 token 限制不变。

证据：用 **37 项新增回归**覆盖此前实测的五个失败反例及相关边界。SQLite 草稿／配置测试 **43 通过 / 1 项 PostgreSQL 专用跳过**；Linux、锁定依赖及新建隔离 PostgreSQL 全量后端 **1073 通过 / 1 跳过**，并发取用只有一次 200、另一次 409。Alembic 升至 `0023_agent_drafts` 和结构漂移检查通过；前端 **175 通过**，API 类型、格式、TypeScript／Vite、Ruff、生成契约和基线均通过。保留已有打包体积提示。未改数据库结构、迁移或前端；未调用真实模型或 WhatsApp，未提交私密配置，未重启或重置日常本地服务／数据库。以上是开发验证，仍待 William 独立复审。

## PDF 隔离用例标记为仅 Linux（基线收尾） — 2026-10-17

**原因。** PDF 子进程隔离依赖 Linux 独有的 `RLIMIT_AS` 与 `prctl(PR_SET_PDEATHSIG)`，因此在原生 macOS 上所有真实解析用例都会以 `MEDIA_PDF_LIMIT_UNAVAILABLE` 失败；这 12 条失败在未改动的 `main` 上完全一致，长期作为"已知噪声"掩盖真实回归。

**改动。** 这 12 条（`test_media_processor.py` 10 条、`test_pdf_limits.py` 1 条、`test_media_review.py` 的 `pdf` 参数）统一加上 `LINUX_PDF_ONLY = pytest.mark.skipif(sys.platform != "linux", reason=...)`；拒绝语义本身没有任何改动，Linux 运行器仍会完整执行它们。

**验证。** 后端全量（SQLite）**1044 通过 / 40 跳过 / 0 失败**；三个改动文件 `ruff check`、`ruff format` 均干净；`scripts/export_contracts.py --check` 已同步；`scripts/check_baseline.py` **PASS：95 个 Markdown、1041 条本地链接、3 个 schema、14 个有效 fixture、8 个被拒 fixture、12 个合成验收场景**。仍未验证：PDF 隔离套件在 Linux 容器里的重跑（本机无 Linux 运行器），以及 PostgreSQL 行锁语义（本机未安装 PostgreSQL，也没有 `TEST_DATABASE_URL`）。

## PR #35 CI 卡死的 PostgreSQL 专属缺陷修复 — 2026-10-17

**现象。** PR #35 上除一项外所有检查都已完成：`backend` job 停在最后一步 `pytest apps/backend/tests -q`（`2026-10-17T05:03:50Z` 开始，始终没有结束）；同一个 job 在 `main` 上约五分钟就跑完了。

**根因（有证据，不是猜测）。** `POST /api/v1/work-orders/{id}/evidence` 声明的是 `db=Depends(database, scope="function")`，而 `actor` 依赖用的是请求级 `Depends(database)`。FastAPI 的依赖缓存键是 `(call, scopes, computed_scope)`，因此一次请求拿到了**两个** Session，也就是**两条 PostgreSQL 连接**。`identity.authenticate` 在变更请求里对商户行加 `SELECT ... FOR UPDATE`（`identity.py:47`）；第二个事务的 `INSERT INTO work_order_evidence` 因为指向 `accounts` 的外键，必须拿到同一行的 `KEY SHARE` 锁，而这把锁只有身份事务提交后才释放，身份事务又要等 endpoint 返回 —— 自死锁；PostgreSQL 没有设置 `lock_timeout`，于是请求永远等待。本地用 `postgres:17.9` 容器复现：`pg_stat_activity` 显示 INSERT 正在等待 `transactionid` ShareLock，阻塞者是处于 `idle in transaction` 的身份认证会话，Python 栈停在 `work_evidence.py:160 db.flush()`。SQLite 完全看不到，因为 pysqlite 每线程复用一条连接，两个 Session 共用同一个事务。

**改动。**

- `api.py`：evidence endpoint 改回请求级依赖，身份锁与写入落在同一个事务里（同资源的 `GET` 路由本来就是这样）。
- `work_evidence.attach`：在 PostgreSQL 上设置有界等待（`SET LOCAL lock_timeout = '3s'`、`SET LOCAL statement_timeout = '5s'`），与 `waha_ingress`、`waha_sync`、`waha_recovery`、`waha_media` 已有的做法一致，使将来任何跨事务等待都明确失败，而不是无限占用 HTTP worker 或 CI job。
- `tests/test_waha_media.py::test_media_bookkeeping_does_not_require_new_tables_for_existing_pause`：先丢弃 `work_order_evidence` 再丢弃 `waha_attachments`。新表的外键让这个"旧 schema（没有依据表）"用例只在 PostgreSQL 上失败；SQLite 不检查 DROP 依赖，所以本地一直是绿的。
- 护栏：每个 workflow job 都显式声明 `timeout-minutes`（`backend` 20、`pdf-isolation` 15、`frontend_platforms` 25、`frontend` 5、`documentation-and-contracts` 10），并且 `apps/backend/pyproject.toml` 增加 `faulthandler_timeout = 300`；将来若有卡死的用例，会先 dump 全部线程栈再退出，而不是挂到平台超时。

**第二轮：草稿路由上的同一个缺陷。** 推送后 `backend` job 4 分 29 秒就结束（不再挂死），说明 CI 超时护栏生效，但这一批第一次在 PostgreSQL 上完整跑，发现另外三个路由是同样的写法：`POST /work-orders/{id}/drafts`、`POST /drafts/{id}/revoke`、`POST /drafts/{id}/consume` 同时声明 `account=Depends(actor)` 与 `db=Depends(database, scope="function")`，于是草稿 INSERT 又去等身份会话持有的同一行 `accounts` 锁（栈：`agent_drafts.py:227 db.flush()`，阻塞在 `psycopg ... cursor.execute`）。`logout` 也是混合声明，只是后面没有写操作。四处统一改为请求级依赖，与 `setup_actor`／`sending_io_actor`（刻意让 `database` 和身份认证都处在 function scope）保持一致。这两条新路由还遗留了「文件改名为 `0022`、文件内 `revision` 仍写 `0021_work_order_evidence`」的不一致；`test_agent_drafts` 用随机 `event_id` 组提案，SQLite 不查外键而 PostgreSQL 拒绝。两者都已修。

**合并 main。** `main` 已前进到 `c516656`（PR #34），在 `0020_business_model_heads` 之上新增 `0021_reviewed_product`；本分支的 `0022_work_order_evidence` 指向同一个父节点，于是出现两个 Alembic head（`test_waha_migration.py` 报 `assert 2 == 1`，共 22 项失败）。现在 `0022` 挂在 `0021_reviewed_product` 上，形成单链 `0020 -> 0021 -> 0022 -> 0023_agent_drafts`。`.env.example`、`contracts/openapi.json`、`apps/web/src/generated/api.d.ts` 三个冲突都用重新生成解决（`export_contracts.py`、`npm run generate:api`），没有手改生成文件；两份状态文档同时保留双方的带日期段落。

**证据。** 本地 `postgres:17.9` 容器 + `TEST_DATABASE_URL` 复现：修复前该用例永不返回，`-o faulthandler_timeout=60` 会 dump 出上面两个等待；修复后 `pytest apps/backend/tests/test_work_evidence.py` **8 项通过，5.24s**，`test_agent_drafts.py` 与 `test_work_evidence.py` 一起 **16 项通过，9.46s**（此前会挂住）。合并 main 之后后端全量：PostgreSQL **1058 通过、14 跳过、12 失败**，SQLite **1045 通过、27 跳过、12 失败**，两边的 12 个失败都是已记录的 macOS PDF 资源隔离用例（`pdf_child` 在非 Linux 平台拒绝）；`test_waha_migration.py` **21 项通过**。`alembic upgrade head` + `check`：临时 SQLite 与 PostgreSQL 上均无新操作，head 唯一为 `0023_agent_drafts`。`ruff check` / `ruff format --check apps/backend`：干净。`export_contracts.py --check`：同步。`check_baseline.py`：PASS（95 个 Markdown、1041 个本地链接）。

**仍待确认。** 推送后的第一次 Linux 运行把 `backend` job 压缩到 4 分 29 秒（不再挂死）但依旧失败，正是它暴露了草稿路由缺陷与双 head。下一次运行需要在 Ubuntu 上端到端确认整个 PostgreSQL job；本地两套都是 macOS，能证明锁行为但证明不了 Linux 的 PDF 沙箱。

## 媒体分模态授权与已核对附件转工单依据（B/C）— 2026-10-17

本批在 PR #31 合入后重建于 main 之上。它原先携带的文字模型门槛（来源重绑定、时间基准、token/成本记账、重试分类、`SOURCE_SUPERSEDED`）在 main 上已有更严格的实现，因此**丢弃了重复的 provider 实现**，`extraction/llm.py` 原样采用 main 版本；`0014_llm_usage` 已删除，因为 `0017_model_call_request_id` / `0018_model_call_cost` 已经加上请求 id、token 与成本列。保留的是 main 真正没有的部分。

**媒体**

- **分模态授权：** `GIGMATE_MEDIA_MODALITIES`（`ocr,asr,pdf,text`）默认为空；在 live 开关之后、创建客户端之前以 `MEDIA_MODALITY_NOT_AUTHORIZED` 拒绝，验收 OCR 不会顺带打开 ASR 或文档外发。
- **视觉供应商白名单：** `GIGMATE_MEDIA_VISION_VENDORS` 之外的供应商收到 OCR 内容前以 `MEDIA_VISION_VENDOR_UNVERIFIED` 拒绝；不假设 chat-completions 供应商能看图。
- **接缝保持锁定：** 没有任何真实 OCR/ASR/PDF 验收记录，因此 `_ENABLED` 仍为 `False`。适配器与闸门只在测试里临时打开验证；`test_default_seam_flag_stays_locked` 断言即使 live 开关、凭据与全部模态都导出的情况下，锁定的接缝依然拒绝。

**工单依据（商户决定）**

- 迁移 `0022_work_order_evidence`（`(work_order_id, attachment_id, attachment_version)` 唯一）、`gigmate/work_evidence.py`、`POST/GET /api/v1/work-orders/{id}/evidence`。
- attach 重新校验账户归属、连接/来源有效、授权、到期、核对记录、原始字节（`waha_media.evidence`），以及附件会话已关联该工单（否则 `MEDIA_ORDER_LINK_REQUIRED`）；结果更新为 `MEDIA_RESULT_CHANGED`，版本/上下文变化为 `MEDIA_SOURCE_CHANGED`。重复提交同一绑定幂等，返回已存行，绝不会被刷新成更新的结果。
- 行内快照附件版本、上下文版本、结果任务、SHA-256 与来源指纹；读取时计算 `stale`/`stale_reason`，历史不被改写。不写 `RequirementChange`、不确认字段、不授予批准或发送权限。

**测试：** 新增 `tests/test_work_evidence.py` 8 个用例（未核对拒绝、幂等提升、未关联会话、更新结果、他人账户、上下文变化后 stale、CSRF、仅可下载附件），在合并后的基线上全部通过。`tests/test_media_processor.py` 新增 4 个模态/视觉用例与锁定接缝断言；`tests/test_media_injection.py` 的 fixture 改为显式授权模态（因为默认是拒绝）。

**真实探测（运营方自备 key，从未提交）：** `scripts/smoke_deepseek.py` 一次真实 `deepseek-chat` 调用返回 matched 提案，延迟 1729 ms、1707 tokens，"下周四下午三点"按 `Asia/Hong_Kong` 正确解析。另两次裸探测（64x64 纯绿/纯红 PNG）分别回答 "Green"/"Red"，各 202 prompt tokens，响应 `model` 为 `deepseek-flash`。这说明该账号路由确实处理图像，但 OCR 仍只能经显式白名单启用，不因一次探测而默认打开。

**如实记录未做之事：** 未发出真实音频/ASR 请求，也没有端到端处理真实附件；真实 OCR/ASR 准确率、prompt 注入防护、供应商限流与长期成本仍未验证。12 个 macOS PDF 资源隔离用例仍在本机失败（`pdf_child` 在非 Linux 平台拒绝），预期在 CI 通过；SQLite 不证明 PostgreSQL 锁。

证据：`pytest apps/backend/tests` **981 通过、25 跳过、12 失败**（12 个均为已记录的 macOS PDF 用例）。`ruff check` / `ruff format --check apps/backend`：干净。`export_contracts.py --check`：同步。`check_baseline.py`：PASS（89 个 Markdown、1037 个本地链接）。临时 SQLite 上 `alembic upgrade head` + `check`：head `0022_work_order_evidence`，无新操作。`apps/web` 已重新生成 API 类型。
## PR36 复审加固：使用持久保存的决策记录 — 2026-10-17

C 角色已批准原改动，并建议反方向也核对 `ProposalDecision`。现在消息一旦通过建议建单，即使以后任务错误码被重置为两种待复核状态，也不能再归单或忽略；待复核列表同样排除已建单消息。原请求的成功回执仍可正常重取。新增四种测试先复现了错误的 200，修复后归单和忽略均返回 409，不改任务、归属、审计或命令回执。SQLite 业务与归单测试 **53 通过 / 4 项 PostgreSQL 专用跳过**；Linux 加隔离 PostgreSQL **57 通过**。Ruff 检查与格式、契约导出及基线检查通过。未改数据库结构、迁移或前端，未调用模型或 WhatsApp。

## 后续修复：建议建单与人工处理互斥 — 2026-10-17

基于已合入 PR34 的 main `c516656`，按 C 复审复现两条遗漏：先忽略再采纳建议、先归单重处理再采纳建议，旧代码都会错误返回 201。列表和建单现在共用一个条件：该消息所属账号的任务必须已完成、仍待人工决定且没有归单记录。已忽略／已归单的建议不再显示，旧页面直接提交也返回 409；归单重新处理后也不能重用建议。反方向仍由 `NEW_ORDER_REVIEWED` 拦截；成功原编号重试仍返回原回执。竞争请求沿用账号锁，只保留一种处理。无迁移或 API 结构变化；同步修正归单 docstring 和接口说明，区分普通手动建单与消费建议。

证据：Linux＋独立 PostgreSQL 全后端 **1011 通过、1 跳过**（部分夹具自身使用 SQLite）；新增 13 个用例，含两种顺序、归单待处理／重处理完成、任务缺失或不再待复核、建单与归单／忽略同时请求。SQLite 产品＋归单两组 **49 通过、4 项要求 PostgreSQL 而跳过**。前端 **175 通过**；API 类型、格式、TypeScript／Vite、Ruff 检查／格式 132 文件、契约导出和基线通过。本地基础／文字服务已重建启动。全部为合成输入，无真实供应商调用或 WhatsApp 发送。下方旧日期证据保留为历史。

## PR34 独立复审修正 — 2026-10-17

修复日期输入导致渲染白屏、复核／恢复文字二次翻译和旧成功提示残留；归单、行动、回执状态改为可读译文。建议消费增加事务内唯一约束兜底，冲突为 409，失败整单回滚，保留账号串行处理；查询在 SQL 排除无建议和已消费消息。未知调用恢复／重试耗尽也记录完成耗时。业务管理读取全部关联会话，拒绝过期、撤回、混合及旧修订来源。

证据：Linux／锁定依赖＋独立 PostgreSQL **998 通过、1 跳过**；产品专项 **37 通过**，包括同步起跑的真实并发 HTTP 建单、签名接入及正式暂停／恢复接口。SQLite 产品专项 **35 通过、2 项要求 PostgreSQL 而跳过**。前端 **175 通过**；TypeScript、格式、契约和构建通过。新旧代码对照复现日期、复核文字、提示、唯一约束兜底、耗时记录的旧失败。正常 HTTP 并发本来已有账号锁：不同编号为 201／409，同编号返回相同结果，不将它描述为已复现的 500。授权和证据边界见[交付说明](bcd-product-delivery.md)；不代表付费模型或 WhatsApp 实机验收，配置仍留本地。

## 当前 BCD 文字产品候选 — 2026-10-17

PR31／32／33 已合并；基线 main `14aa34e`。接口、缓存、玻璃设计三份提交后，补齐商户核对 AI 建单建议、待办决定、可选隔离进程文字入口、统一业务类型和中／英／粤界面。Linux＋隔离 PostgreSQL：**987 通过、1 跳过**；新产品测试 **26 通过**，包括真实子进程访问本机假 HTTP 供应商。0021 升级／结构校验、默认关闭 Compose 文字配置校验通过。没有真实供应商、手机或部署验收。见[范围、证据与限制](bcd-product-delivery.md)；下方旧日期结论为历史。


## 交付前检查清单、归档与审批分页（C）— 2026-10-16

方案 §4.6（按已确认要求生成检查清单，提醒未完成事项，商户确认后关闭业务并归档）和 Issue #28。`GET /work-orders/{id}/checklist` 列出要核对的已确认项和未完成项；有未完成项时完成工单返回 409 `CHECKLIST_OPEN`，除非商户设置 `acknowledge_open_items`。`POST /work-orders/{id}/archive` 把已关闭的工单从默认列表隐藏（`include_archived=true` 可显示）。`GET /actions` 改为在数据库端按 id 分批读取分页，不再一次加载整份历史；按计算状态筛选、`reissuable` 和只读过期判断保持不变。证据：`test_checklist.py` **3 项通过**；新增分页回归（121 条合成审批记录，不重不漏，过期只显示不写库）；审批与发送测试 30 项通过。

## 每日摘要与规则建议（C）— 2026-10-16

方案 §4.6 每日摘要，以及业务建议中可以用规则算出的部分（资料不齐、任务依赖、工作量可能超出时间安排；建议依据必须可见）。`GET /daily-summary` 把现有记录汇总为今天要做的、等待客户确认的、即将到期的、需要商户决定的，并附上建议；每一项都带对应记录的 ID。这个接口只读，不推送任何东西；静默时段和提醒频率属于推送与发送（A 的范围），不在此接口内。自然语言提问仍属 B。证据：`test_daily_summary.py` **3 项通过**。

## 草稿编辑与客户未回复跟进（C）— 2026-10-16

方案 §4.5（编辑后发送）和契约 §3 "No reply"。`POST /actions/{id}/edit` 编辑待批准草稿，生成新的 revision、snapshot hash 和有效期；旧快照不能再被批准。worker 每小时的维护会运行 `follow_up_unanswered`：发送网关已接受的待确认项问题，若 24 小时内没有收到客户来信，就为剩余项目生成跟进待办和新草稿（最多两次，记在 `task_links.no_reply_N`），之后给工单加上 `attention: ["customer_not_replying"]`。客户一回复就停止。证据：`test_business_send.py` 9 项通过（新增 2 项），`test_approvals.py` 20 项通过（新增 1 项）。

## 业务细节字段、需求条目与承诺待办（C）— 2026-10-16

方案 §4.3（服务内容、数量与规格、约定日期、所需资料、双方承诺、未决问题）和 §4.4（从承诺生成待办，具有负责人、到期时间和原文依据）。`WorkOrderFields` 新增 `specification`、`quantity`、`deadline`（默认缺失）；确认接口支持这几项和 `summary`，不影响关键项规则；确认后的交付期限生成一条交付待办（`WorkOrder.task_links.delivery`），期限改动时替换。`WorkOrder.requirements` 支持新增和关闭；资料和承诺生成备忘录式待办。重新确认关键项时只取消与时间挂钩的准备待办，不再误取消交付、需求或跟进待办。证据：`test_requirements.py` **4 项通过**；C 的测试 109 项通过。

## 工作时间设置、候选时间与排期风险（C）— 2026-10-16

方案 §4.4（工作时间、休息时间、任务时长和缓冲；检查时间重叠、缺少准备时间；提出可用时间）、§5.1 和附录 A（候选时间必须来自已核对的可用时间）。新增 `scheduling.py` 和表 `schedule_settings`（迁移 **0018_schedule_settings**）。`GET/PUT /settings/schedule`（默认：周一至周六 09:00–19:00，休息 12:30–13:30，时长 60 分钟，缓冲 30 分钟，准备 60 分钟）；`GET /work-orders/{id}/schedule-check` 返回风险和按规则算出的空闲时段；撞期草稿会给出第一个同样长度的空闲时段；准备待办按商户设置的提前量生成。证据：`test_scheduling.py` **5 项通过**；C 的测试 93 项通过。

## 契约接口清单里的列表过滤（C）— 2026-10-16

`GET /work-orders?status=`、`GET /tasks?work_order_id=`、`GET /calendar-events?start=&end=`（带时区的 ISO 时间；返回与时间窗重叠的事件，只有日期的条目覆盖当地整天；格式错误或起止颠倒返回 422）。证据：`test_list_filters.py` **3 项通过**。`.ics` 下载由 D 的 #30 交付，这里不重复。

## 客户延期与跟进待办（C）— 2026-10-16

契约 §3 "Customer defers"。B 目前还识别不了"还未确定，之后再确认"，所以先由商户记录：`POST /work-orders/{id}/defer`（`DeferItemCommand`：`field`、可选 `until`、客户消息 `sources`、`expected_version`）。工单保持 `pending_confirmation`；`WorkOrder.deferred[field]` 记录日期、来源和跟进待办；这一项不再被追问（若没有其他未完成项，待批准的问题以 `deferred` 原因撤回）；自动生成待办 `MM/DD HH:MM 跟进 {summary}：确认地址`，到期时间取客户给的日期，否则为 3 天后香港时间 10:00。只接受待确认工单里未完成的项、未来的日期和当前的客户来信。之后该项经客户确认，延期解除、待办标为完成。证据：`test_deferral.py` **3 项通过**，新建工单测试 30 项通过。

## 人工归单（C）— 2026-10-16

方案 §4.2（"无法确定时放入待归类队列，由商户选择或拆分"）和契约 §1。D 的待复核列表（#30）负责读取队列；这里补上商户的决定：`POST /review-items/{job_id}/assign`（`AssignMessageCommand`：`action` 为 assign/dismiss、`work_order_id`、`expected_context_version`）。归单会把选择存进新表 `job_assignments`（新增迁移 **0017_job_assignments**，接在 0016 之后；如果 #31 的 0017 先合并，需要补一个合并迁移），并把消息重新排队；worker 只把这张单交给提取，结果是普通的提议。忽略则把该项标为 `DISMISSED_BY_MERCHANT`。只接受会话中最新的一条消息、同一会话里未关闭的工单，以及已授权的会话。证据：`test_message_assignment.py` **3 项通过**；迁移测试 18 项通过。

## 业务审批接通发送网关，以及拒绝提议（C）— 2026-10-16

叠在状态命令 PR 之上。设计依据：方案 §4.5（批准后发送、取消计划、查看结果）、§6.2（服务端审批校验后 `sendText`、幂等记录、未知状态先核对）、§7（批准绑定具体内容和版本，旧批准失效）；Issue #29 第 1 节。

- **`POST /actions/{id}/send`**（`SendApprovedActionCommand`：`connection_id`、`expected_control_version`、`expected_permission_version`、`expected_action_revision`、`snapshot_hash`）。只接受已批准的业务回复，并重新核对批准时绑定的一切；在服务端按该连接解析会话对应的 WhatsApp 聊天（没有则 404 `SEND_CHAT_NOT_LINKED`）。用批准的原文创建并排队唯一一个手动发送任务，绑定批准时的工单和上下文版本，沿用 A 的发送授权、控制版本和有效期检查（未授权 403 `SEND_NOT_AUTHORIZED`）。请求键 `c-action:<id>` 保证一一对应：重复调用返回同一发送任务，不会发两次。
- **结果回写到业务行动：** 排队/派发中为 `executing`，之后为 `succeeded`（附 `delivery_status`）、`failed`、`cancelled` 或 `result_unknown`（送达状态 `unknown`，绝不重发）。`send_action_id`、`send_state`、`send_error` 关联发送记录。读取不写库。
- **撤回：** 对 `executing` 的行动调用 `POST /actions/{id}/cancel`，发送任务还在草稿/排队/准备时可撤回；一旦开始派发返回 409 `SEND_ALREADY_DISPATCHED`。
- **失效：** 新消息（上下文变化）、工单任何改动（确认、拒绝、状态，版本加一）或撤销发送授权，都会在 A 的派发前复核中拦下未派发的任务。
- **`POST /work-orders/{id}/changes/{change_id}/reject`**（`RejectCommand`）：提议变为 `rejected` 并记录 `rejection_reason`；工单值不变、版本加一；撤回为它生成的撞期问题（`proposal_rejected`）；刷新待确认项问题。`RequirementChange.status` 改用 `ChangeStatus`（字段状态加 `rejected`）。

证据：`test_business_send.py` **7 项通过**（合成聊天与发送方），`test_change_reject.py` **3 项通过**；审批与发送测试 82 通过、3 跳过；前端 119 通过，另有 3 项与改动前相同的环境相关失败；契约导出和基线通过。未进行任何真实 WhatsApp 发送。

## Role B 真实启用前评审修正第二轮（PR #31） — 2026-10-17

[PR #31](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/31) 的五个评审线程在分支 `william/role-b-preactivation-gates` 上用假传输与假时钟重新复现，证明第一批修正对其中四项并不充分；五项全部重新修正，**仍不翻接缝**（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`）：(1) 剩余时限预算改为分摊到 `httpx` 各操作 —— 标量超时是按操作分别套用的，单次尝试可以先花 30 秒连接再花 30 秒读取，假时钟实测由 **60.0 秒**降到 **45.0 秒**；(2) 非正费用预算在任何计价算术**之前**即拒绝，堵住「单价为 0 时 `0 > 0` 为假、零预算仍发请求」的角落；(3) 模型回显的 `base_context_version` 必须是与请求相等的 `int`（且非 `bool`），因为 `7.0 == 7`；(4) `candidates` / `unresolved_questions` 及建议块的 `missing_fields` / `unresolved_questions` 与已有的 `changes` / `sources` 一样，在 Pydantic 之前先做形状检查；(5) 时间依据守卫改为按**字段**判定，`schedule` / `deadline` 上以自由文本或裸数字写出的日期在无依据时不再被晋升为 `matched`。完整理由与新的稳定码见 [role-b-extraction.md](role-b-extraction.md)。无迁移、契约或 API 表面变更。

全部使用合成夹具：`apps/backend/tests/test_extraction_gates.py` **62 通过**（本轮之前 39）；启用前套件（gates + batch2 + batch3 + batch3_provider + extraction）**169 通过**；后端全套 **829 通过／25 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`），未改动的 main 上同样失败。Ruff 检查／格式 **105 文件**、`scripts/export_contracts.py --check` 一致、`check_baseline.py` **84 Markdown／993 本地链接**、Alembic 唯一 head `0018_model_call_cost` 且 `alembic check` 干净、离线评测 **7 通过／0 失败**（prompt 1.2.0）。没有真实模型、密钥、供应商请求、网络调用或部署操作。未验证：PostgreSQL 并发／行锁（未配 `TEST_DATABASE_URL`）、Linux 容器内 PDF 复跑，以及真实供应商是否尊重分摊后的超时。

## PR #31 分支合并 main `e912977` — 2026-10-17

把 `origin/main` `e912977`（#26/#27/#30：C 的工单状态命令、D-04 交付前端、Andy 的来源/列表评审修正）合入 `william/role-b-preactivation-gates` 以解除 PR #31 的冲突；迁移未动，唯一 head 仍为 `0018_model_call_cost`。冲突处理：`apps/backend/src/gigmate/worker.py` 两侧在同一位置各加了一条导入，两条都保留（batch 2 启动审计用的 `validate_provider_config` 与 C 的开放工单过滤用的 `CLOSED`，各自调用点都在）；两份进度文档两侧都在顶部追加条目，条目全部保留、PR #31 评审修正条目置顶；`apps/web/src/generated/api.d.ts` 通过 `npm run generate:api` 从合并后的 `contracts/openapi.json` 重新生成（不手改生成文件）。合并后证据（全部合成／本地）：启用前套件 **106 通过**；后端全套 **808 通过／25 跳过／12 失败**（12 项仍是既有 macOS PDF 拒绝 `MEDIA_PDF_LIMIT_UNAVAILABLE`）；前端 `check:api`、`format:check`、`build`（node 测试 + `tsc --noEmit` + Vite）全部通过；Ruff 检查／格式 **107 文件**；`check_baseline.py` **84 Markdown／993 本地链接**；`alembic check` 干净；离线评测 **7 通过／0 失败**。未验证：PostgreSQL 并发／行锁、Linux 容器内 PDF 复跑、真实供应商行为。

## Role B 真实启用前评审修正（PR #31） — 2026-10-16

独立评审在 `a4e6b8a` 上针对 [PR #31](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/31) 提出五项 P2 问题，每一项都由评审者用合成数据、假传输与假时钟复现，不是静态推断。五项全部在分支 `william/role-b-preactivation-gates` 上修正完成，**仍不翻接缝**（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`），本条记录只覆盖这部分工作：(1) 总墙钟时限现在同时是每次尝试的预算 —— 每次尝试只继承**剩余**时间作为自己的超时（`min(_REQUEST_TIMEOUT_S, remaining)`），剩余不足 `_MIN_REQUEST_TIMEOUT_S = 1s` 的尝试不发出，截止之后才到达的响应用 `llm:deadline-exceeded` 拒绝而非晋升；(2) 每次调用的费用上限在花钱**之前**生效 —— `_cost_plan` 把 `GIGMATE_LLM_COST_BUDGET_USD` 按 `_MAX_RETRIES + 1` 次尝试分摊，并为单次尝试的有界最坏情况（估算 prompt token + 输出上限）计价，超出的以 `llm:cost-budget-exceeded` / `llm:cost-input-too-large` 拒绝且不花钱；请求体携带该输出上限作为 `max_tokens`，调用后的检查保留为第二道防线；(3) `base_context_version` 先按请求校验绑定，再由服务端赋值；(4) 遍历前先检查 `changes` / `sources` 的类型，非列表 JSON 不再能从 `propose` 抛出未捕获的 `TypeError`；(5) 时间依据守卫覆盖 `kind: instant`（`InstantDeadline`），old 与 new 值都检查。新增两个运维设置 `GIGMATE_LLM_MAX_INPUT_TOKENS` / `GIGMATE_LLM_MAX_OUTPUT_TOKENS`（默认 4000 / 1000）与启动码 `llm:cost-tokens-invalid`，已写入 `.env.example`。完整理由与新的稳定码见 [role-b-extraction.md](role-b-extraction.md)。无迁移、契约或 API 表面变更。

全部使用合成夹具：五个反例现已成为回归测试 —— `apps/backend/tests/test_extraction_gates.py` **39 通过**（`a4e6b8a` 时为 27）、`test_extraction_batch2.py` **50 通过**（`a4e6b8a` 时为 40）；在当前工作树（同时含进行中的 batch 3 文件）测得启用前套件 **106 通过**。后端全套 **745 通过／25 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`），未改动的 main 上同样失败。五项修正还在一棵隔离的 `a4e6b8a` 工作树中单独验证过：**88 项中 87 项通过**，唯一失败项是隔离树刻意不含 batch 3 的 `new_work_order` 契约所致 —— 那是把修正与在编 batch 3 分离的假象，不是修正本身的缺陷。Ruff 检查／格式 **100 文件**、契约 `--check` 一致、`check_baseline.py` **82 Markdown／965 本地链接**、Alembic 唯一 head `0018_model_call_cost` 且在 SQLite 上完成升级→回退→升级往返无漂移、评测工具 **7 通过／0 失败**（prompt 1.2.0）。没有真实模型、密钥、供应商请求、网络调用或部署操作。未验证：PostgreSQL 并发／行锁（未配 `TEST_DATABASE_URL`）、Linux 容器内 PDF 复跑，以及真实供应商单价与行为。

## Role B 真实启用前第四批 — 媒体附件注入回归集 — 2026-10-16

仍在分支 `william/role-b-preactivation-gates` 上，**两处接缝仍未翻**（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`）。附件内容由攻击者可控，因此媒体接缝获得与文字接缝同样的待遇：新增纯分类器 `gigmate.media.injection`，扫描一个媒体结果的每个不可信面 —— 商户/攻击者提供的 caption、OCR 或本地解析出的段落文本、ASR 转写文本，以及供应商自己的 `summary` / `suggestions` / `unresolved_questions` —— 对照一套收紧的双语模式（忽略先前指示、角色篡改、权力声索、绕过复核、提示词外泄、指令性动词）。命中记为稳定的 `media:instruction-text-detected:<field>` 标记，写入新的可选字段 `WahaMediaResult.injection_markers`（默认空，随既有 JSON 列落库，**无需迁移**），并以 `MEDIA_INJECTION_DETECTED` 只记录模式 id 与字段名，绝不记录载荷原文。检测是标记而非裁决：不阻断、不改写、不采信内容，也不授予或剥夺任何权限 —— `WahaMediaEvidence.business_confirmation_required` 仍是 `Literal[True]`，测试断言即使是被标记的结果，把它改成 `False` 也会被拒绝。`contracts/evaluation/media_injection.json` 提供九个合成案例：图片 caption 与 OCR 文本注入、语音转写中的口头指令、PDF 隐藏文字层、既试图改写正文又向业务层夹带指令的 PDF 模型、藏在 `unresolved_questions` 里的指令，以及三个对照案例 —— 一旦普通商户内容被误标，套件即失败。PDF 路径同时重新钉住「页文本始终来自本地解析，模型永远无法改写」。

全部使用合成夹具：新增 `apps/backend/tests/test_media_injection.py` **18 通过／3 跳过**；后端全套 **745 通过／25 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`）—— `test_media_processor.py` 在本批次前后都是 10 失败／40 通过，无回归。Ruff 检查／格式 **98 文件**；契约重新生成（`contracts/domain/models.schema.json` 与 `contracts/openapi.json` 带上新字段）且 `--check` 一致；`check_baseline.py` **82 Markdown／967 本地链接**；Alembic head 仍为 `0018_model_call_cost`（无 schema 变更）。3 项跳过是 PDF 端到端变体：本地解析器在原生 macOS 上以 `MEDIA_PDF_LIMIT_UNAVAILABLE` 拒绝，因此套件以解析器产出的数据结构驱动 `coerce_pdf_extraction`，完整路径留给解析器可用的环境。没有真实图片、音频、PDF、供应商响应、密钥或网络调用。未验证：真实 OCR／ASR／PDF 行为、模式集在真实商户内容上的误报率（运维应先读标记再行动）、Linux 上的 PDF 端到端，以及任何真实供应商行为。

## Role B 真实启用前第三批（第一部分）— 新建工单识别契约、未知结果处置、评测分类 — 2026-10-16

仍在分支 `william/role-b-preactivation-gates` 上，**仍不翻接缝**（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`），再落地 issue #29 中 B 侧三项。本提交只落地**不触碰 `gigmate/extraction/llm.py`** 的部分 —— 该文件正被并发修改以修复 PR #31 评审发现（P2-1..P2-5）：(1) **`new_work_order` 识别契约** —— `ChangeProposal` 新增可选 `NewWorkOrderSuggestion` 块（summary、绑定来源的识别字段、`missing_fields`、`unresolved_questions`、`confidence`），仅为识别输出：不建单、不确认、不授予执行权，禁止与 `matched` 归类或非空 `work_order_id` 同时出现，未知值保持缺失；该块随既有提案 JSON 落库，无需迁移，也永不生成 `RequirementChange` 行；(2) **文字提取的未知供应商结果处置**，现已成文并由测试钉住 —— 总预算内一次有界重试且两次携带同一持久化 request id，随后产出 `needs_review` 提案与 `llm:http-failed:timeout`，request id 保留在 trace 行用于与供应商日志对账，不再重复提交；(3) **评测分类输出** —— `EvaluationCase.expected_new_work_order`、逐例 `actual_new_work_order` / `refused_reason` / `notes`，以及 `scripts/run_evaluation.py` 的 `classification` 块（按期望归类的通过／失败、建议数、拒绝码、失败案例 id）。prompt 升到 1.2.0 并写明新输出块；`case-001` 与 `case-004` 钉住「确定性 provider 不产生误报建议」。

留到下一个提交、与 `llm.py` 一起落地：出处重绑定（门槛一）与时间依据门槛（门槛四）扩展到建议字段，以及 `inj-010` 注入夹具。两处防护已写好且本地通过（由 `apps/backend/tests/test_extraction_batch3_provider.py` 三个待落地测试钉住），但在 `llm.py` 携带这些防护之前提交会让分支变红。

全部使用合成夹具：新增 `apps/backend/tests/test_extraction_batch3.py` **14 通过**；后端全套 **727 通过／22 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`），未改动的 main 上同样失败；Ruff 检查／格式通过、契约重新生成且 `--check` 一致、`check_baseline.py` **82 Markdown／965 本地链接**、评测工具 **7 通过／0 失败**（prompt 1.2.0，含新的分类块）、Alembic 仍为唯一 head `0018_model_call_cost`（本批无 schema 变更）。没有真实模型、密钥、供应商请求、网络调用或部署操作。未验证：PostgreSQL 并发／行锁、真实供应商单价与行为、真实目标准确率，以及与 C 的 revision/版本联合核验。注意：工作区同时带有 PR #31 评审修复对 `llm.py`、`test_extraction_batch2.py`、`test_extraction_gates.py`、`.env.example`、`contracts/evaluation/injection.json` 与 `role-b-extraction.md` 的并发改动，均不属于本提交；两个既有测试（`test_gate3_exhausted_time_budget_stops_retrying`、`test_matched_response_over_budget_refuses_with_stable_code`）当前因这些未提交改动而失败，交由该批次处理。

## Role B 真实启用前第二批 — 费用边界、启动校验、注入回归 — 2026-10-16

在分支 `william/role-b-preactivation-gates` 上继续，落地 [role-b-extraction.md](role-b-extraction.md) 记录的剩余启用待办中的三项，**仍不翻接缝**：(1) **费用边界** —— 内置千 token 单价表（键为 `(vendor, model)`），可用 `GIGMATE_LLM_COST_INPUT_USD_PER_1K` / `GIGMATE_LLM_COST_OUTPUT_USD_PER_1K` 覆盖；每次调用预算来自 `GIGMATE_LLM_COST_BUDGET_USD`（默认 `0.10` 美元），响应费用超预算时在调用**之后**以 `llm:cost-budget-exceeded` 拒绝，完全无法计价时在调用**之前**以 `llm:cost-pricing-missing` / `-partial` / `-invalid` 拒绝；供应商缺失或畸形的 `usage` 块记为 `llm:cost-usage-missing` / `llm:cost-usage-invalid`，而不是静默当零；(2) **Provider 配置启动校验** —— 纯审计函数 `gigmate.extraction.llm.validate_provider_config()` 由 worker 启动时经 `gigmate.worker.audit_provider_config()` 调用，报告 `llm:vendor-unknown`、`llm:endpoint-invalid`、`llm:vendor-endpoint-mismatch`、`llm:endpoint-required`、`llm:prompt-path-invalid`、`workspace-timezone-invalid`、四个费用码以及（`GIGMATE_LLM_LIVE=1` 时）`llm:api-key-missing`；活门打开时任何问题都拒绝启动，活门关闭时仅记 warning；(3) **Prompt-injection 回归集** —— `contracts/evaluation/injection.json` 提供九个合成案例，每例把含注入指令的客户消息与被诱导模型会返回的 `compromised_response` 配对，断言任何案例都不会产出 `matched`，且各自命中 `llm:response-provenance-failed`、`llm:response-schema-failed` 或 `llm:time-basis-missing`。新增迁移 `0018_model_call_cost` 为 `model_call_traces` 增加 `input_tokens`、`output_tokens`、`cost_usd`；`ExtractionOutcome` 与 `persistence.persist_proposal` 同步携带这四个字段。

全部使用合成夹具：新增 `apps/backend/tests/test_extraction_batch2.py` **40 通过**（费用核算、启动审计、九个注入案例）；`test_extraction_gates.py` 仍 **27 通过**；合并的启用前套件 **67 通过**。后端全套 **688 通过／22 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`），未改动的 main 上同样失败。Ruff 检查／格式 **96 文件**、`scripts/export_contracts.py --check` 一致、`check_baseline.py` **82 Markdown／965 本地链接**、Alembic 唯一 head `0018_model_call_cost` 且在 SQLite 上完成升级→回退→升级往返（`alembic check` 无漂移）、评测工具 **7 通过／0 失败**（prompt 1.1.0）。接缝仍关闭（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`），新费用与启动路径只通过测试子类开闸验证：没有真实模型、密钥、供应商请求、网络调用或部署操作，今日写入的每条 `cost_usd` 行按构造即为 null。未验证：PostgreSQL 并发／行锁（未配 `TEST_DATABASE_URL`）、Linux 容器内 PDF 复跑、真实供应商单价（内置表是文档化上界，运维须对照自己的合同确认）、以及任何真实供应商行为。

## Role B 真实启用前验收门槛 — 2026-10-16

基于已合入 main `53991dc`（分支 `william/role-b-preactivation-gates`），实现 [role-b-extraction.md](role-b-extraction.md) 记录的五项启用前验收门槛：(1) `_parse_response` 把模型返回的全部身份字段——`conversation_id`、`work_order_id`（必须是 `candidate_work_order_ids` 成员）、`base_work_order_version` 以及每条 `sources[].message_id` / `message_revision`——重新绑定回实际发出的请求，不匹配以 `llm:response-provenance-failed` 拒绝，绝不会变成 `matched`；(2) 明确 vendor／endpoint 语义——每个 vendor 自带文档化默认端点，`custom` 必须显式配置 `GIGMATE_LLM_ENDPOINT`，未知／错配／非 URL 端点一律拒绝；(3) 重试只对瞬时类（超时、连接／重置、`5xx`）且有 45 秒总预算，每次调用带同一个持久化 `X-Gigmate-Request-Id` 头，该 id 经新增迁移 `0017_model_call_request_id` 落库到 `model_call_traces.request_id`；(4) 服务端附上的日期依据——`ExtractionRequest.message_received_at` 与 `workspace_timezone`（`GIGMATE_WORKSPACE_TIMEZONE`），prompt `role_b_extraction_v1.txt` 由 `1.0.0` 升到 `1.1.0` 并要求输出 UTC `Z`，依据缺失时含日期的变更以 `llm:time-basis-missing` 拒绝，worker 在调用后丢弃上下文／工单版本已变更或自身租约已过期的结果；(5) 稳定脱敏诊断码（`llm:http-failed:timeout`、`llm:http-failed:status-5xx`、`llm:response-schema-failed:<字段路径>` 等），不再回显端点、vendor、密钥或异常文本。

全部使用合成夹具：新增 `apps/backend/tests/test_extraction_gates.py` **27 通过**；后端全套 **648 通过／22 跳过／12 失败**，12 项失败是原生 macOS 上既有的 PDF 拒绝（`MEDIA_PDF_LIMIT_UNAVAILABLE`，role-b-extraction.md 已记录），未改动的 main 上同样失败。Ruff 检查／格式 **92 文件**、`scripts/export_contracts.py --check` 一致、`check_baseline.py` **82 Markdown／963 本地链接**、Alembic 唯一 head `0017_model_call_request_id` 且在 SQLite 上完成升级→回退→升级往返（当前版本 `0017_model_call_request_id`，无漂移）、评测工具 **7 通过／0 失败**（prompt 1.1.0）。`tests/test_waha_migration.py` 改为动态取 head，不再写死 `0016_d03_sending_heads`。接缝仍关闭（`_SKELETON_SEAM = True`、媒体 `_ENABLED = False`）；没有真实模型、密钥、网络请求、WhatsApp 消息或部署操作。未验证：PostgreSQL 并发／行锁（未配 `TEST_DATABASE_URL`）、Linux 容器内 PDF 复跑、以及任何真实供应商行为。

## 2026-10-16 功能冻结：AI 识别新生意并提议建单，记为后续（C）— 2026-10-16

仅文档记录，**冻结后没有新增任何功能**。本条记录的**范围只有一项**：从 AI 新建提议创建工单（`contracts/api-v1.md` §1–§2，`from_proposal_id`），按事实记为后续而非已完成。它不是 C 全部工作的总结：其余 C 项（例如 #32 里仍在评审的归单/延期与业务发送）另行记录。

- **冻结时、以当前 main 为准的状态：** main 上没有任何「从提议建单」的实现。`CreateWorkOrderCommand` 没有 `from_proposal_id`，`AssignmentResult` 仍只有 `matched` / `needs_review`，`new_work_order` 在后端源码和生成契约里都不存在。商户手动建单已实现（`POST /api/v1/work-orders`，返回 201；`CreateWorkOrderCommand` 含 `conversation_id`、`summary`、可选 schedule/address 及其来源引用、`confirm_additional_order`），**demo 用的就是手动建单**，不存在缺兜底的问题。
- **为什么不能写成「只等 B 给格式」：** PR #31（B 侧，分支 `william/role-b-preactivation-gates`）里已经有提议形状——`contracts.py` 的 `ExtractionOutcome.new_work_order: NewWorkOrderSuggestion | None`——但**冻结时未合入 main**。未合入分支上的提议不等于已交付的契约；即使 #31 合入，C 自己的工作仍然独立未完：`from_proposal_id` 命令路径、带 used/superseded 状态的提议持久化、以及每个 job 的合并判断。B 有提议格式不等于自动建单闭环已完成。因此这条记录应在 #31 合入后重新阅读，而不是继续把 B 的格式写成未交付。
- 本条未改动：运行代码、生成契约、迁移都没动。既有工单的变更抽取、撞期校验、商户确认、工单状态流转与审批闭环，仍按下方主干较新条目所记录的实现为准。

证据：`apps/backend/src/gigmate/api.py` 注册了 `GET /api/v1/work-orders` 与 `POST /api/v1/work-orders`（201）；生成的 `contracts/openapi.json` 里 `/api/v1/work-orders` 有 `get` 和 `post`；在本分支头上 `grep -rn "from_proposal_id\|new_work_order" apps/backend/src contracts/domain/models.schema.json` 无命中，而同样的标识符出现在 #31 的头 `038ae3b`（`contracts.py`）里，说明上述结论针对 main、而非所有分支。本批只改两份进度记录和 `contracts/api-v1.md` 里的一句状态说明；`.venv/bin/python scripts/check_baseline.py` PASS（84 个 Markdown、983 个本地链接、3 个 schema、13 个合法样例、7 个拒绝样例、12 个合成场景），`scripts/export_contracts.py --check` 保持同步。Ruff 与 pytest 不覆盖纯文档改动，未重跑；未涉及真实 WhatsApp、模型、发送或部署。

## PR #30：处理 Andy 的来源／列表评审 — 2026-10-16

先在 988127f 复现 Andy 的两项 P2，再修改实现：新增边界用例原先 **12 失败／1 正常对照通过**。日历导出现在实际查询时间及导出地点背后的客户最新消息，核对账号、工单关联且仍授权的会话、消息版本与撤回状态。依据缺失、编辑、撤回、他人、未关联、暂停或来自商户自己的消息时，返回 APPROVAL_STALE 并停止导出；保留既有工单／预约历史，不自动回滚或删除。网页用通俗提示说明需要核对原文。提案列表只对“时间安排＋具体起止时间”计算冲突，地址／仅日期能正常经历真实 GET 列表 → 核对来源 → confirm，不再读取崩溃；保留 C 的具体时间撞期及确认规则。没有更改接口形状、生成文件或迁移。

本轮原生 SQLite 相关业务／交付回归 **83 通过／1 PostgreSQL 专项跳过／1 已有 Starlette/httpx 警告**，其中新增 **13 项来源／列表回归全通过**。前端 **143 通过，零失败／跳过**，含来源失效下载提示；API／Prettier／类型／Vite、Ruff、生成契约及基线检查通过。本轮 Docker daemon 不可用，没有重新验证本机 Linux／PDF 或 PostgreSQL 锁；精确提交 GitHub CI 另核实。未操作真实模型／WAHA／手机／发送、原数据库或部署。同步双语手册／学习笔记／接口／验收，主目录原有未提交文档保持原样。

## PR #30 接入已合并 C 并处理 Lena 评审 — 2026-10-16

把 main **71de8d9**（#26／#27）合入 D 候选，解决源码、生成接口和进度冲突，不改写迁移。开放正式手工建单、状态和时间／地址确认，使用 C 的生成类型及真实缺项原因。商户接受成功不等于客户已确认：核对归属、工单、版本和值后，接受 confirmed 或 proposed；兼容服务端地址去空白及旧时间操作记录。修复 Lena 的 P1：后端正常返回 200 时，不再误判未知并锁住后续操作。新增绑定账号／原编号／原内容的只读保存记录核对；只有查到确切已完成记录且再次勾选，才可结束本地记录。未找到、他人记录或无法联网时，保留原编号，不据此重发。排队重试的处理失败标明自动重试；全历史扫描保留为非阻塞后续项。

导出和前端日历允许只更新地址／状态后的较新工单版本，仍严格核对时间及原文版本；时间／来源改变、日历版本超前、暂定或已结束均拒绝导出。无新表／迁移，不启用真实模型／外发。同步双语手册、大一入门学习笔记、文件地图、模块计划和验收。实际组合证据：前端 **143 通过，零失败／跳过**，类型／Vite／API／Prettier；本机临时 PostgreSQL 相关测试 **108 通过**，一项已有 Starlette/httpx 警告；支持的 Linux＋PostgreSQL 配置后端全套 **704 通过／1 平台跳过／1 已有警告**，固定 pypdf 6.20.0 且 pip check 通过。部分夹具仍用 SQLite，不能据这些数字声称所有 PG 锁路径已验证。Ruff 检查／格式 **99 文件**、源契约、前端 API／格式、基线 **84 Markdown／983 本地链接** 和空白检查通过，Alembic 仍为唯一 head **0016_d03_sending_heads**。真实 HTTP／浏览器用全新临时 schema：按来源建成已确认 v1，商户接受待客户核实时间后 v2 正常保存（字段仍是提议、日历暂定），再成功取消到 v3，无未解决操作阻塞、无浏览器错误日志。已清理自建进程及两个自建临时 schema。主目录 main 快进到 71de8d9，原有十份未提交文档已从保留的备份／stash 恢复，不纳入本 PR。未操作原数据库／WAHA／手机／模型／外发／会话／部署或原生日历导入。当前提交 CI 和独立批准仍需核实，下方旧候选证据为历史。

## D-04 到最终网页交付候选 — 2026-10-16

在独立代码工作区基于已接纳 #25／main **53991dc**，保留主目录学习文档／手册改动和既有服务数据。实现单服务交付界面、客户来源建单／复核和生命周期待接控件（修复后的 C #26／#27 交付前关闭保存）、原编号业务命令保存／核对、缺项追问说明、人工复核、内部月历／全部安排／全账号待办、自己当前正式预约 `.ics`、功能状态／帮助、手机键盘适配、网页安装信息／图标和无需 Python 的网页容器编译。没有伪造 A/C 发送关联或 B／归单／地址命令，没有启用真实模型／外发。只读辅助接口、契约／类型按源模型生成，无表／迁移改动；双语手册、学习／文件地图／模块计划和 A 现行启动说明同步。见[最终候选验收](role-d-final-acceptance.md)。

提交前实际证据：前端 **137 通过，零失败／跳过**，API 类型、Prettier、TypeScript／Vite 通过；本机临时 PostgreSQL 审批／发送／业务／迁移／交付／启动工具 **130 通过**，含 **11** 项新增交付测试。最终支持的 Linux 容器＋PostgreSQL 配置后端全套 **665 通过／1 平台跳过／1 已有 Starlette/httpx 警告**；已有镜像除缺 pypdf 外均匹配锁，安装固定 6.20.0 后 pip check 通过。部分提取夹具仍是 SQLite，不能声称所有 PG 锁路径都已证明。Ruff 检查／格式 **97 文件**、源契约、基线 **84 Markdown／983 本地链接** 和空白检查完成。交付网页镜像无需 Python 即可构建，当前静态烟测见 PR 证据。真实本机 HTTP／浏览器／临时 schema 验证日历下载 UTC／标题／地点、来源绑定的禁用建单复核、原文／工单跳转、键盘与 390px 无横向溢出；虚构截图／夹具／日志仅在被忽略本地目录。未重置／迁移原数据库／会话，未操作手机／模型／外发／二维码／生产部署／原生安装／实体日历导入。最终提交 CI 和独立复核另行确认，#12／#29 留待设备／跨角色验收。

## 工单状态命令（C）— 2026-10-14

叠在新建工单 PR 之上。新增 `POST /work-orders/{id}/status`（`SetWorkOrderStatusCommand`：`status`、`expected_version`；必须带 `Idempotency-Key`）。

- **状态流转：** 已确认 → 进行中 / 等客人 / 已完成 / 已取消；进行中 ↔ 等客人，两者都可 → 已完成 / 已取消；待确认或未分类只能 → 已取消（工单只能通过确认流程变成已确认）；已完成和已取消是终态。其他情况返回 409 `INVALID_TRANSITION`，附当前状态和允许的目标；版本过期返回 409 `VERSION_CONFLICT`。每次变更版本加一并写审计。
- **关闭（已完成或已取消）：** 日历时段不再占用；未发送的草稿取消（`order_completed` / `order_cancelled`，契约第 4 节）；自动生成的未完成待办标为完成或取消；待确认的提议退回 `needs_review`。不删除任何数据，也不发送任何消息。
- **新消息：** worker 只把会话中未关闭的工单交给提取，已取消的工单不再接收改动，改动会落到会话中仍在进行的工单。

证据：`test_order_status.py` **5 项通过**；C 的测试（状态、新建、审批、工作流）同步 #26 日历修正后在本地 PostgreSQL 16 上 75 项通过；SQLite 全套 678 通过、12 跳过；Ruff/格式、契约导出、前端接口检查和类型检查通过。未触碰真实 WhatsApp、发送、模型或部署。

评审跟进（2026-10-16）：合并已修正的新建工单分支（来源方向、只有日期、空白地址）和 main `53991dc`；错误码表 409 行补上 `INVALID_TRANSITION`。本轮 SQLite 全套 **676 通过、12 跳过**；Alembic 只有一个 head `0016_d03_sending_heads`；Ruff/格式、契约导出、baseline、前端接口检查和类型检查通过。本 head 未重跑 PostgreSQL。

## PR #25 开放并兼容已合入的发送功能 — 2026-10-14

队友评审已将 #25 开放为 Ready。之后 main 通过 #24／#23 更新到 **4177d1a**，产生迁移测试与双语进度冲突。本轮合入该 main，保留两边测试／记录及全部已发布迁移，新增无表结构变更的 **0016_d03_sending_heads** 汇合 **0015_d03_approval_heads** 与 **0014_merge_approval_send**。验证从两个最新 head 升级，保留审批记录、发送授权／取消标识和回放数据，Alembic 检查唯一 head 且无结构漂移。继承 main 的发送接口固定环境地址，App 测试同时加载审批／发送模块。后端生产源码／契约与 main 相同，未新增 C/A 审批执行桥接或真实发送。

新组合前端 **122 通过**，API／Prettier／类型／Vite 通过，Python 使用项目路径且无覆盖变量；原生 PostgreSQL 审批／发送／迁移 **96 通过**，一项已有 Starlette/httpx 警告。Ruff 检查／格式 **94 文件**、源契约、基线 **82 Markdown／957 链接** 与空白检查通过。Linux 后端全套及三平台前端以最终 head CI 为准，旧 c80a224 结果为历史。未操作原数据库／会话／运行服务／部署或真实手机／模型／发送。保持 Ready，交给队友合并；基础分支／提交改变后，分支保护要求队友批准当前版本。

## PR #25 跟随 #24 的前端验收兼容性修复 — 2026-10-14

同步 #24 的 Python 路径选择、PATH 空目录真实子进程回归、覆盖／缺失路径检查、旧别名警告和双语安装说明，保留 D-03 审批测试及原迁移历史。CI 明确准备固定 Python，并在 Linux／Windows／Mac 测前端；通过全平台成功汇总保留分支保护要求的 `frontend` 检查名。新组合前端 **115 通过**，类型／Vite／API／Prettier 通过，使用仅 Node／系统 PATH、无 Python 覆盖或激活；被忽略的 worktree .venv 使用已有项目解释器。Ruff／格式（87 文件）、源契约、基线及空白检查完成；后端／迁移／契约未改，旧全套 583／1 不冒充本次重跑。原生 Windows／跨平台证据以当前 head CI 为准。无模型／发送／真实数据／部署改动，#25 保持 Draft，等待 #24 和独立评审。

## PR #23 清理修复独立复审与 D-02 兼容 — 2026-10-14

独立复核 Andy 的 d6f3acd 清理／发送修复。旧 PostgreSQL 复现只调整候选编号查询，成功和未知响应两项均通过，只提交一次且不自动重发；发送／审批／迁移专项 90 项通过。真实手机验收属于作者的证据，语音那条仍保持未知，本轮没有真实发送。

main 已通过 #24 更新到 40614a4。解决 main.tsx 和两份进度文档冲突，保留 D-02 App 和双方记录；保留消息页发送入口，发送适配器固定环境地址，App 测试补发送模块，中英现行启动指令更新。回归覆盖换路径后上传／预览／原编号核对。前端兼容是本轮编写的调整，后端生产源码／契约／迁移保持 d6f3acd。组合前端 97 项通过，API／格式／类型／构建、Ruff 检查与格式 91 文件、源契约、基线 80 Markdown／935 链接和空白检查通过。Linux 全套仍在安装依赖，尚无结果，合并前核实最终组合 CI。未操作真实数据／模型／手机／发送／二维码、原数据库或部署。

## PR #23 过期清理串行化 — 2026-10-14

使用合成 PostgreSQL 交错复现新 P1：已提交一次的任务被旧清理状态覆盖为取消。清理现使用发送的 Account/Connection 锁，并重新核对状态、有效期及发送标记。独立 PostgreSQL 发送测试 **59 项通过**，覆盖两种先后顺序及成功/未知结果保留，不再次提交。完整 PostgreSQL 后端 **646 项通过 / 1 项平台跳过**；加强测试回调断言后，六项相关清理测试再次通过。前端 **63 项通过**，类型/构建、API 类型检查、格式、适用 Ruff、生成契约与基线（**69 Markdown / 414 链接**）检查通过。详见[发送证据](role-a-waha-sending.md)。原真实语音的未知结果保持不变，仍需独立评审。

## PR #23 真实发送验收 — 2026-10-14

用户在 Windows/原生 x86 环境的 `863bd09` 上，通过网关操作十一种声明的消息类型及引用/手动/建议稿/固定政策入口；手机效果为用户报告，数据库仅核对状态元数据。文字/图片/PDF/普通音频/贴纸/位置/联系人/投票/表情/视频存在已接受记录；原语音虽报告可播放，但无 ID，仍保持未知。人工承认可能已发送后仅放行后续任务，没有重放原消息。已观察上下文过期取消、手动取消、政策撤销，以及总发送权限撤销导致未批准草稿取消。固定 Chrome 切换后用户确认 MP4 正常播放。实际范围与限制见[发送说明](role-a-waha-sending.md)，不表示所有回执/编码/Agent/生产能力认证。

原私有数据库已备份并升级/检查到 0014，原会话卷保留；仅准备原接入 API/worker/监控和视频浏览器。私有验收资料与用户无关的 Oracle 规划文件不进入本提交。本轮仅补文档，运行 baseline/链接及源契约检查；此前 `863bd09` 后端全套 634 通过/10 跳过、最终迁移 12 通过及前端 63 通过保留为历史证据，不冒充本轮重跑。最终 PR head 仍需独立复核，Ready for review 不会撤销 CHANGES_REQUESTED，也不授权合并。

视频播放后最终核对：总发送权限**关闭，版本 4，授权聊天数为零**；唯一固定政策已撤销，保留一次使用。18 条验收动作中 14 条已接受、3 条提交前取消，1 条已人工核对的语音仍保持未知，没有待发送任务。统计不含正文或接收人身份。

## PR #23 兼容审批 main — 2026-10-14

在隔离工作区将 main `c5c22ef`（#22）合入发送 head `4917d3c`；用户独立的 Oracle 部署规划分支及全部未提交文件保持原样。最新 Role B 评审认可上一轮修复，仅有流程备注，没有新增代码缺陷。其他评审者的状态与评论由其本人更新，本次不删除重复评论。

解决 worker、迁移测试及双语进度冲突，保留 Replay/真实提取生成审批草稿与全部发送路径。API 回流继续抑制提取/回复，诊断码统一为 main 的 `OWN_SEND_ECHO`；上下文推进、C 旧草稿失效，以及 A 已派发结果不被追溯取消仍由两侧回归覆盖。C 审批与 A 发送权限/outbox 独立，未新增执行桥接或启用模型。

新增 **0014_merge_approval_send**，汇合未改写的共享 `0013_merge_approval_media` 与 `0013_merge_media_send`。迁移回归覆盖两条合并 head，保留 C 已批准记录、发送权限版本/取消标识及既有数据。从合并后的源码重新生成 domain/OpenAPI/前端类型。重建新代码前升级 `head` 并执行 Alembic `check`；本次不升级私有安装。

实际本地验证：Windows 后端全套 **634 通过、10 跳过**（9 项 PostgreSQL 依赖、1 项不适用平台）；补充已批准记录保留断言后的最终迁移专项 **12 通过**。前端 **63 通过**，API/格式/TypeScript/Vite build 通过。适用 Ruff/格式（**46 文件**）、源契约检查、baseline（**69 篇 Markdown、410 个链接**）、空白检查及隔离 SQLite 升级/结构检查通过，唯一 head 为 0014。Windows 检出换行仅在隔离副本规范，无内容格式改写。SQLite 不证明 PostgreSQL 锁；新 CI 与独立复核仍需确认，PR 保持 Draft。保留已有 Starlette/httpx 警告。未操作真实手机/发送/媒体/模型、凭据、二维码或部署。

## PR #23 评审恢复说明 — 2026-10-14

最新两条 Role B 评论内容相同，均为不阻塞的建议。确认每轮处理一个动作、未知结果需要核对是刻意的安全设计，无需改成自动重发。补充中英文恢复说明：已登记文件删除失败与孤立文件清理回滚的区别、文件系统与数据库清理不能原子提交、每小时 worker 维护，以及有准确 ID 和无 ID 时的回执核对边界。发送页面已有查询与未知结果核对，独立 C/D 业务桥接仍待接入。

新增两项合成 HTTP/数据库回归：删除失败时保留过期引用，恢复后重试清除；文件已删除但数据库回滚时，下一轮清理解除缺失文件引用。两项都确认过期附件仍拒绝读取。生产代码、契约、迁移不变。发送专项 **55 通过、1 项 PostgreSQL 跳过**；适用 Ruff/格式、契约导出检查、baseline（**69 篇 Markdown、410 个链接**）及空白检查通过。未操作真实发送、手机、服务商、模型或部署；不新增 PostgreSQL 锁或崩溃持久性结论。前端未改，本轮未重跑。PR 保持 Draft，用户原有未提交诊断段落不进入本次提交。

## PR #23 兼容已合入的 #21 — 2026-10-13

发送分支已合并 main `e066b0c`（#21 最终提交 `e7a2b8f`），保留双方代码、测试和进度历史，解决迁移测试及双语文档冲突。媒体处理接缝、PDF 隔离解析和不可清除的停止决定均保留；模型任务与发送 outbox 的身份/授权独立。B 真实模型仍关闭，C 动作桥接及真实发送验收仍待后续完成。

新增 **0013_merge_media_send** 合并未改写的 0011/0012，形成唯一迁移 head。测试覆盖任一分支升级，以及回放记录、发送授权版本/取消标识、旧媒体停止原因的保留。运行新代码前升级 head/check；本次未迁移、启用用户数据库、会话或安装。

修复独立复现的上传竞态：落文件和记录前，在账户/连接锁内重新核对归属、白名单及发送授权；收流还绑定原控制/授权版本，拒绝暂停后恢复和撤销发送后恢复的旧上传。五个失败回归验证零记录/零文件，正常上传保留。公开契约结构不变，已按源模型重新导出和检查。

实际本地证据：Windows 后端全套 **607 通过、10 跳过**（9 项 PostgreSQL 依赖检查及 1 项不适用平台检查）；最后补充迁移保留断言前，发送/媒体停止/迁移重点回归 **79 通过、1 项 PostgreSQL 跳过**。前端 **63 通过**，类型/格式/TypeScript/build、适用 Ruff/格式、baseline（**69 篇 Markdown、410 个链接**）及隔离 SQLite 升级 0013/check 通过。SQLite 不证明 PostgreSQL 锁，新提交 CI 和独立复核仍需确认；保留已有 Starlette/httpx 警告。仅使用合成字节、假传输/模型和 DOM；无真实发送、媒体、模型、二维码、部署或私有配置操作。集成后 PR 目标改为 main，保持 Draft；用户未提交的诊断段落不进入 PR。

## PR #24 补上漏处理的 Python 兼容性反馈 — 2026-10-14

首轮矩阵 CI 的 Windows 90 项测试全部通过（含 PATH 无 Python），Mac／Linux 前端检查也通过；Windows 格式检查发现 `.mjs`／`.html` 缺少 LF 规则。本次补仓库明确属性，并移除未解决该问题的全局检出设置；保留分支要求的 frontend 汇总检查。跨平台全绿以重跑结果为准。

Will 上一轮已指出默认依赖 PATH 中的 `python`，我当时验证时把项目虚拟环境加进 PATH，漏掉了这条反馈。本次修复 a90a9b6 上重申的 P2：测试明确选择当前工作目录的 `.venv/bin/python`（Mac／Linux）或 `.venv/Scripts/python.exe`（Windows），也保留 `GIGMATE_TEST_PYTHON` 明确覆盖；缺少／不可用时给平台安装提示并失败，不依赖系统别名、不跳过。四条回归包含真实 Node 子进程：PATH 指向空目录、无覆盖变量，仍跑完环境七项测试；另测有效覆盖、缺虚拟环境提示和错误覆盖拒绝。本机用被忽略的 worktree `.venv` 链接使用已有项目环境。双语手册说明工作目录／worktree 配置；CI 明确创建固定 Python 3.12.10 环境，在 Linux／Windows／Mac 检查前端并保持 LF 检出。

同时处理旧别名 P3：只有旧 GIGMATE_API_URL 实际选中隔离地址时，才警告其含义并提示换成 real／isolated 明确变量，原代理／分离保护保留。本机 **90 项前端通过**，含 PATH 空目录子进程；正常 npm 构建／检查仅使用 Node／系统工具 PATH，未设 Python 覆盖或激活虚拟环境。类型／Vite／API／Prettier、Ruff 检查／格式（85 文件）、源契约、基线（77 Markdown／909 链接）及空白检查通过；不能把 Mac 结果冒充新 head 的跨平台 CI。未改后端／迁移／生成源码或真实 provider／模型／发送／部署，未重跑后端全套／Docker／手机。将同步本次 helper／CI／手册进 #25，仍需独立复审。



## PR #25 同步已合并的 C 审批及修复后的 D-02 — 2026-10-14

同步 #24 **a90a9b6** 与已接纳 main **c5c22ef**，含 C 已独立验收的重复再提问修复。保留双方迁移测试和中英记录；已发布 **0013_merge_approval_media**、**0014_media_approvals** 保持原样，新增无表结构改动的 **0015_d03_approval_heads** 合并它们。迁移回归增加从两个已有合并点升级，保留回放／连接／评测记录、无漂移且唯一 head。更新双语当前依赖／操作／验收说明，旧日期证据保留为历史。C 后端问题已修复，前端同来源／上下文的保守重复操作限制仍保留，其余审批／存储／来源核对行为不变。

新组合证据：前端 **110 通过**，TypeScript／Vite／API／Prettier、Ruff 检查／格式（**87 文件**，含自检工具）、生成契约、基线（**79 Markdown／928 链接**）及空白检查通过。原生 PostgreSQL 迁移 **10 通过**；支持的 Linux Docker／PostgreSQL 配置后端全套 **583 通过／1 平台跳过**，有已有 Starlette/httpx 警告，部分提取夹具仍为 SQLite。后端生产源码／契约与已接纳 main 一致，仅本候选版新增迁移兼容点。无真实 WhatsApp／模型／发送、浏览器／隐私／实体设备验收、原数据库升级或部署；既有本机运行实例未升级。#22 已合并，因此 #25 改以 main 为目标，保持 Draft，等待 #24 和独立评审。


## PR #25 同步 D-02 启动入口修复 — 2026-10-14

合入 #24 **2564182**，保留两侧双语父分支／存储评审证据，以及既有审批界面、原请求恢复和迁移合并点。A 的现行启动命令及合成自检前端现在使用父分支的明确地址／默认选择和虚构数据标签。组合后新跑：**110 项前端通过**，TypeScript／Vite／API／Prettier、Ruff 检查／格式（**85 文件**）、生成契约、基线（**79 Markdown／928 链接**）、两项工具环境 Python 定向测试及空白检查通过；已有 Starlette/httpx 警告保留。本次同步未改后端生产源码／迁移／契约或审批存储行为；之前 Linux／PostgreSQL 全套 576 通过／1 跳过是历史证据，本次未重跑。未验证完整 Docker 自检／真实手机／模型／发送／部署。#25 仍保持叠加 Draft，等待 #22／#24 和独立评审。


## PR #24 现行 WAHA 启动入口迁移 — 2026-10-14

修复 c0a0d96 上的独立评审 P2：A 的现行联调／消息同步说明改用 `GIGMATE_REAL_API_URL` 加 `GIGMATE_DEFAULT_ENV=real`，同步中英及 Mac／PowerShell 命令；隔离后端仍需另行准备。保留 D-01 带日期的旧验收记录。自动自检工具的前端固定访问临时 18802 接入，并从前端子进程环境过滤后端／模型私有配置；开发模式新增明确的合成服务标签。这个特别自检保留连接导航，但明确提示虚构数据／二维码不能扫码，关闭切换及第二个代理，必须明确指定地址／默认选择，不会无声访问维护者的真实后端。普通隔离测试仍仅业务导航；同端口／远程地址保护与发布版 `/api` 行为保留。

新跑证据：**85 项前端通过**，覆盖现行手册启动命令、自定义接入端口、工具实际环境构造函数、合成代理限制及实际 App 标签／导航／请求路径。TypeScript／Vite、API／Prettier、Ruff 检查／格式（**81 文件**，含修改的工具）、生成契约、基线（**77 Markdown／906 链接**）及空白检查通过。工具环境 Python 定向测试 **2 项通过**，有已有 Starlette/httpx 警告。未改后端领域／路由／迁移或生成契约；未重跑完整 Docker 自检、后端全套、原生 Windows、真实手机／模型／发送或部署，旧证据按日期保留。发布前把本次父分支同步进 #25，仍需独立复审。

## PR #25 存储评审修复与父分支同步 — 2026-10-14

#25 已同步解决冲突后的 #24 c0a0d96，包含已接纳 main e066b0c；三处剩余迁移／进度冲突保留双方内容。修复 sh0redry 的 issuecomment-6145958029 P2：获取默认存储对象移入函数体保护，分别处理 journal 读取／写入／清理。禁止存储时仍可读取草稿，但不能提交，不以纯内存替代。已核实响应后清理失败保留原记录、阻止新意图；恢复存储并重新打开后，才能按原编号明确核对。不会误删另一页面的新记录。新增九项 API／真实组件回归，覆盖 getter／getItem／setItem／removeItem 拒绝、保留旧未知请求、只读页面零 POST 及原编号恢复。

组合后 A 媒体与 C 审批迁移同时存在，新增无业务操作的 **0014_media_approvals**，合并未修改的 0012_waha_media_stop 和 0009_approval_actions；保留 C 尚未修复的再提问逻辑，不修改 #22 分支。迁移保留测试补两边已存在 leaf 升级，验证唯一 head、原回放／连接／评测／媒体停止记录及 Alembic 无漂移。domain／OpenAPI／前端类型从组合源码重生成，不手改生成文件。若父分支随后改变迁移，合 main 前需再兼容。

证据：**105 项前端通过**，类型／Vite／API／Prettier、适用 Ruff／格式（83 文件）、生成契约、基线（此记录加入前 79 份 Markdown／928 个本地链接）及空白检查通过。支持的 Linux Docker＋PostgreSQL 配置全套后端 **576 通过／1 平台跳过**，一项既有 Starlette/httpx 警告；最后追加漂移断言后，受影响 PostgreSQL 迁移 **6 通过**。提取夹具部分仍用 SQLite，不能说全部锁路径证明了。未实际改变浏览器隐私设置／验收实体设备，无真实模型／聊天／发送／既有数据库／部署操作。#23 最新 99228ca 已有队友评审并记录上传／main 兼容修复，旧竞态报告是历史，C/A 发送桥接仍待完成。#22 未更新且已有队友评审，按要求不重复评论／评审他人的 PR。#25 继续 Draft，待 #22 再提问修复及 #24 落地后独立复审。


## D-03 审批候选与仓库审核 — 2026-10-13

在 `codex/d03-approvals` 组合待合并 C #22（`8ef89ac`）和 D-02 #24（`5ba294a`），完成 [D-03 的审批部分](role-d-stage3-acceptance.md)：完整收件会话／正文／原文／有效期／版本核对、明确勾选、带原因本机拒绝／取消、历史、保守再提问，以及按账号／环境保存原编号的未知结果核对。批准仍未发送；C/A 发送桥接和完整外发验收待完成。D-03 提交不改后端／模型／生成文件／迁移，同步双语操作／学习／文件地图／路线／索引／验收。

新证据：**91 项前端通过**，零失败／跳过；TypeScript／Vite、API／Prettier、生成契约、基线（此证据加入前 76 份 Markdown／893 个本地链接）和空白检查通过。全新专属 PostgreSQL schema 升级 0009／无漂移，认证合成撞期＋确定性 worker＋真实 HTTP／Vite 浏览器核对明确勾选、已批准／not_submitted、历史及刷新／重登录持久保留。默认 749 像素无横向溢出、无控制台警告／错误。无真实聊天／模型／发送／二维码，未改既有部署或数据库。

#21 最新 `e7a2b8f` 独立 Linux Docker／PostgreSQL 配置全套 **559 通过／1 跳过**，含旧三条独立复现；原生中断／资源定向 **32 通过／11 平台跳过**。原生全套 12 个 PDF 拒绝失败对应已声明不支持 macOS 原生解析，不能说该全套通过。Ruff／格式（79 文件）、契约／基线及 head 六项 CI 通过。[独立批准](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/21#pullrequestreview-5501660753)，核实后解决原两条反馈，在 Kyrie 明确授权“可接受 PR 合并”的范围转 ready 并合入 `e066b0c`。真实模型默认关闭，真实账号／原生／实体设备验收仍待完成。本地 main 已快进到该远端 head；原未提交学习／手册／进度已保留，忽略目录备份和限定文件 stash 可恢复。

#22 `8ef89ac` 原 PostgreSQL 配置 **390 通过**，契约／基线通过；新增“重新提问又过期再提问”回归因 trigger 唯一约束 **返回 503 而失败**。原回显／未知提取自动提问、过期 GET 写回、撞期依据问题已修正。[新修改请求](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/22#pullrequestreview-5501636922)，未合并。#23 `6e01279` 源码／依赖审核确认上传开始检查白名单，但保存前未重新检查授权聊天；尚未同步新 #21／桥接 C 动作／最终统一检查。[请求修改](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/23#pullrequestreview-5501637234)，保留 Draft；不宣称新跑 #23 全套或真实发送。#24 留给 Andy 合并。GitHub 连接器评审写入返回 integration 403，已有授权的本机 gh 身份成功发布。

四个开放 issue 已只读审阅，未冒充完成／关闭，也未发 issue 评论：

| Issue | 结论／依赖 |
| --- | --- |
| [#1 入门验收](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/1) | 仍需另一位队友独立 fresh clone 的报告，代理测试不能代替。#24 后需把旧回放按钮步骤改为开发夹具流程。 |
| [#7 新建工单](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/7) | 重要 P0 提议：先 C 手动保存接口，再 D-04 表单；B 预填可后补。计划契约不等于已实现；本次 D-03 不加建单／状态接口。 |
| [#10 启动校验／评测 CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/10) | 评测脚本已在现 CI 两条 Ruff 命令里；worker 入口仍无 provider 启动校验，只完成一半，不关闭。 |
| [#12 手机日历导出](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/12) | P0 后可选；需 C 的账号所属只读 .ics 接口，再加 D 按钮。先约定正式安排／时区／缺地址／重复导入行为，再测设备及账号隔离；本批不实现或外部同步。 |


## PR #22 审批动作评审跟进（C）— 2026-10-13

## PR #24 兼容已合并的审批后端 — 2026-10-14

把已接纳 main **c5c22ef**（#22）合入 D-02。仅中英进度文档冲突，保留 C 的轮次修复／main 兼容记录及 D 的旧证据。后端生产源码／迁移及生成契约与 main 一致，未另改后端。新跑前端 **85 通过**，TypeScript／Vite／API／Prettier、Ruff 检查／格式（**85 文件**，含自检工具）、源契约导出、基线（**77 Markdown／906 链接**）、工具环境 Python 定向 **2 通过**及空白检查通过。刚完成的 C 全套 577／1 是上一轮独立评审证据，本次未重跑。无真实手机／模型／发送／数据库／部署操作。将同步本父分支进 #25，保留已发布迁移并新增合并点以兼容已落地的 C 合并迁移；仍需独立评审。


不在本批、未改动：审批页面（D）、真实发送以及 C 动作到 A 发送网关的桥接（`ActionRow(state=approved)` 不是发送授权，会话 UUID 也不是 provider 聊天 ID）、工单取消/完成命令。迁移 `0009_approval_actions` 接在 `0008` 后；若 #21（0009/0010）先合并，需要补加性合并迁移。

证据：`pytest apps/backend/tests/test_approvals.py` 在 SQLite 和本地 PostgreSQL 16 上均 **18 项通过**；SQLite 全套通过；PostgreSQL 全套在该本地环境下出现与未改动 main 相同的 WAHA 计时相关失败，审批/工作流测试无失败。Ruff/格式、契约导出、前端接口检查和双语基线通过。未触碰真实 WhatsApp、发送、模型或部署。

## PR #24 现行 WAHA 启动入口迁移 — 2026-10-14

修复 c0a0d96 上的独立评审 P2：A 的现行联调／消息同步说明改用 `GIGMATE_REAL_API_URL` 加 `GIGMATE_DEFAULT_ENV=real`，同步中英及 Mac／PowerShell 命令；隔离后端仍需另行准备。保留 D-01 带日期的旧验收记录。自动自检工具的前端固定访问临时 18802 接入，并从前端子进程环境过滤后端／模型私有配置；开发模式新增明确的合成服务标签。这个特别自检保留连接导航，但明确提示虚构数据／二维码不能扫码，关闭切换及第二个代理，必须明确指定地址／默认选择，不会无声访问维护者的真实后端。普通隔离测试仍仅业务导航；同端口／远程地址保护与发布版 `/api` 行为保留。

新跑证据：**85 项前端通过**，覆盖现行手册启动命令、自定义接入端口、工具实际环境构造函数、合成代理限制及实际 App 标签／导航／请求路径。TypeScript／Vite、API／Prettier、Ruff 检查／格式（**81 文件**，含修改的工具）、生成契约、基线（**77 Markdown／906 链接**）及空白检查通过。工具环境 Python 定向测试 **2 项通过**，有已有 Starlette/httpx 警告。未改后端领域／路由／迁移或生成契约；未重跑完整 Docker 自检、后端全套、原生 Windows、真实手机／模型／发送或部署，旧证据按日期保留。发布前把本次父分支同步进 #25，仍需独立复审。


## PR #24 与已合并 main 兼容 — 2026-10-14

已 fetch，主目录 main／origin/main 均为 e066b0c，保留原本地文档。#22 仍是 8ef89ac，#23 更新到 99228ca，但均已有队友评审；按 Kyrie 要求，不重复评论／评审或修改这些 PR。#24 合入已接纳 #21 的 main，不重写源码／迁移／生成文件。四处冲突保留双方环境／媒体测试夹具与双语记录，App 测试补齐媒体依赖。继承的媒体适配器在创建时固定 apiBase，私有预览／下载及原编号重试也跟随该地址，真实环境不再错误回退到隔离 root 代理。新增一项有意义的地址绑定回归；**80 项前端**、类型／Vite／API／格式、适用 Ruff（79 文件）、生成契约／基线及空白检查通过。后端源码与已接纳 main 相同，无真实 provider／模型／发送／数据库／部署操作。#25 发布存储修复前将同步本次 #24；C 审批集成仍等 #22。


## 完整 D-02 PR 准备 — 2026-10-12

Kyrie 现要求推送已完成的 D-02 前端分支并创建 PR，取代之前“只 commit”的要求；下方按日期保留的“无 PR”记录描述当时状态。本次统一提交有来源的业务核对／日历／待办、移除用户演示入口、开发环境切换、隔离环境仅业务导航及双语入门／操作／文件参考文档。提交前重新验证：**75 项前端测试通过**，TypeScript／Vite 构建、API 一致性、Prettier、生成契约、基线（**74 份 Markdown／873 个本地链接**）和差异空白检查通过。无后端／schema／迁移修改；下方后端 pytest 为历史证据，本次未重跑。独立评审与合入 main 仍待完成。

## 隔离前端只保留业务工作台 — 2026-10-12

移除隔离测试的 WhatsApp 导航，禁止挂载连接页；真实连接与发布部署保留。隔离登录说明改为练习虚构业务。现有 App 回归补充业务单导航／无连接查询，真实环境回归仍核对连接请求。**75 项前端测试**、类型／构建、API／格式及双语基线通过，浏览器确认隔离登录后没有 WhatsApp 按钮。同步双语操作／学习手册。仅前端更改，无后端／契约／迁移／运行配置或 WAHA 操作；只本地 commit，无 PR／push。

## D-02 开发环境一键切换 — 2026-10-12

恢复公开默认开发账号／密码提示，输入仍为空。常驻区域区分真实本机 WAHA／业务与虚构隔离数据，显示本机后端地址；一次点击换后端并回登录页，处理中禁止切换，各适配器固定地址。Cookie 分名称／路径，只转发当前环境凭据；待核对请求分环境保留，切换不删除未知请求或重发。远程／相同端口／无效配置明确失败。发布构建使用部署 `/api`，无开发切换／默认密码内容。未改后端源码／契约／迁移，未恢复用户回放按钮；同步双语操作／学习／验收文档。只本地 commit，无 PR／push／main 合并。

证据：**75 项前端通过**，含双合成 HTTP 后端 Cookie／退出隔离、拒绝旧 Cookie、保留 CSRF／Origin、适配器地址绑定、换环境空登录、处理中禁止切换与来源拒绝说明。TypeScript／Vite、API／格式、生成契约、双语基线及空白检查通过。浏览器核对隔离 18012 登录／原虚构 v4 工单、真实 18702 登录、往返切换清空输入／无旧账号页面、749 像素无溢出／控制台错误。忽略的本机 Compose 覆盖配置仅给 ingress 加入 5178 本机来源；初次重建漏带安装数据库变量，短暂指向不可用默认数据库，已恢复原 worker 使用的 54349 目标并复核健康／登录。已有 worker／monitor／provider 服务及连接／会话／授权配置保持，未执行手机扫码／连接控制／发现／授权操作或业务写入。不同端口无法证明不同数据库，仍需维护者准备隔离安装。后端未改，之前 pytest 不是新跑证据。

## 前端成品界面整理与 Kyrie 入门手册更新 — 2026-10-12

在 `codex/d02-workspace`／`4665692` 之后移除 D-01 预览、模拟连接按钮、内存模拟服务／参数／样式及用户工单回放入口。App 使用空账号／密码、登录后的业务／连接导航，默认业务页，清除密码，空数据及未开放功能说明真实。后端回放／夹具留作隔离开发测试；未删数据，未改后端／生成契约／迁移／真实配置。这是 D-05 的部分体验整理，不是最终成品验收。Kyrie 提供团队扫码成功进展，本轮未重新验收真实手机。

更新双语[使用手册](role-d-frontend-user-guide.md)、[从零学习手册](kyrie-learning-guide.md)、[文件地图](kyrie-file-atlas.md)与入口。用预约故事、六个入门概念、小代码课、练习／答案及后置术语查询代替开头堆缩写；保留七张有日期的公开原截图和完整参考，1.1 原稿备份到忽略的 local-data。明确 main 与未合并 D 工作目录的差别。

实际证据：**67 项前端测试通过**，新增两项真实 App／模拟 HTTP 回归，覆盖空登录／无演示绕过、登录拒绝不读业务、真实空工单、所属连接请求、CSRF 退出／清空密码。原跨页授权、未知结果、多会话来源／核对失效及冲突仍通过。TypeScript／Vite、`check:api`、`format:check`、生成一致性、双语基线和空白检查通过。保留的隔离 PostgreSQL／API／worker 浏览器验证空登录、默认业务双导航、保留 v4 数据、无连接空态、无演示入口、退出／重登录及窄屏。DOM／隔离运行不证明真实 WAHA／手机／Windows 或模型／发送；未改后端，之前 372 项 PostgreSQL 配置测试是前一轮证据，不是新跑。仅本地 commit，无新 push／PR／main 合并。 仓库 CI 规定的 Ruff 范围通过（56 个文件）；额外全 scripts 扫描发现未改动的 check_baseline.py 原有未使用 sys／格式问题，留在本批前端范围之外。


## D-02 业务工作台 — 2026-10-12

将 Kyrie 的 D 任务明确为 D-01 至 D-05，在 main `bbb0074` 上实现 D-02：有来源的详情／全部关联会话、搜索／状态筛选、绑定版本的明确排期核对、内部日历与待办／历史筛选，固定回放独立显示。未改后端／契约／迁移。[验收及实际证据](role-d-stage2-acceptance.md)、[模块计划](role-d-development-roadmap.md)、[桌面可行性](role-d-desktop-feasibility.md)。桌面仅评估，未打包。

证据：**65 项前端测试**、TypeScript／Vite、前端 API／格式、适用 Ruff、生成契约检查、基线及空白检查通过；未改动后端 **372 项 PostgreSQL 配置测试通过**，有一项已有警告（部分提取夹具仍用 SQLite）。一次性 schema 迁移／无漂移与浏览器／API／独立 worker 验证冲突阻止、明确确认 v3→v4／日历／待办、来源跳转、取消历史、重读持久化、账号隔离及 320／375／1280 响应式。未改变真实 WhatsApp／模型／发送／原安装。独立 PR／E 评审、实体／原生设备仍待验收。

审核 #21（`d000b26`，原 **500 项通过**）及 #22（`e79ef7b`，原 **387 项通过**），每个 head 新增的一项 PostgreSQL 回归均失败。#21 在取消时丢失已提交模型请求的不确定性并接受再次提交；#22 因 outgoing API 回声重新生成回复工作。均已提交 `REQUEST_CHANGES`，未合并。已有测试／CI 通过不能消除这些问题。本地 main 原已与 origin/main 同为 `bbb0074`，保留原有本地文档修改及 D 工作树。



## PR #22 第二轮评审：重新生成轮次与 main 兼容（C）— 2026-10-14

- **重复重新生成（P2，Andy 和 Kyrie）：** 过期 → 重新生成 → 没有新消息又过期 → 再次重新生成会返回 503，因为第二轮生成了相同的 `<change>@<context>` trigger，撞上唯一约束。现在每轮重新生成都有持久的独立身份 `<change>@<context>~<被替换的草稿 id>`；一条草稿只能被重新生成一次（之后它就不是最新的），所以轮次不会冲突。同一个幂等键重放返回原结果，同键换内容返回 409 `IDEMPOTENCY_CONFLICT`，旧轮次返回 409，每单仍只有一条活动草稿。回归测试：`test_repeated_expiry_rounds_can_each_be_reissued`（未修复时得到 503）。
- **#21 合并后与 main 兼容：** 合并 `main`（`e066b0c`），不改写任一分支。新增只做合并的迁移 **0013_merge_approval_media**（父迁移为 `0009_approval_actions` 与 `0012_waha_media_stop`，不改表结构）。`test_merge_revision_joins_approval_and_media_branches` 从任一父迁移、带数据的数据库升级到唯一 head，并检查数据和双方的表都保留。`test_waha_migration.py` 和中英文进度记录的冲突按保留双方解决；契约和前端类型按源模型重新检查，无漂移。

证据：SQLite 全套 **569 通过、9 跳过**；审批和迁移测试在本地 PostgreSQL 16 上也通过；Ruff/格式（main 上已有的 `scripts/check_baseline.py` F401 与本 PR 无关）、契约导出检查、前端接口检查和基线通过。未触碰真实 WhatsApp、发送、模型或部署。

## 新建工单与关键项规则（C）— 2026-10-13

叠在 PR #22 之上。新增 `POST /work-orders`（`CreateWorkOrderCommand`）以及契约第 3 节的关键项规则。

- **新建：** 商户在自己名下、已授权的会话里新建工单；`summary` 1–120 字（空白拒绝）。填写的每个值都要标出客人在哪条消息里说的（`schedule_sources`、`address_sources`），来源必须是本会话里当前、未撤回的修订，而且是客人发来的消息（`direction: incoming`）；商户自己的回复或我们发送的回显会返回 422。只有空格或制表符的地址返回 422，绝不算已确认。没填的值保持 `missing`。具体时间必须在未来，且不能与已确认预约重叠（409 `SCHEDULE_CONFLICT`，附 `work_order_ids`）。没有 `confirm_additional_order` 时，会话已有未完成工单会返回 409 `OPEN_ORDER_EXISTS` 并列出这些工单。按账号串行、幂等，并写审计。
- **关键项规则：** 只有具体时间和地址都**经商户确认且客人确认**后，工单才是 `confirmed`。商户确认一条 `customer_confirmation` 不是 `confirmed` 的提议（例如 AI 换算出来的相对日期）时，值会写入，但字段保持 `proposed`，这一项仍未完成；已确认的工单如果关键项变成等客人确认，或时间被换成只有日期，会回到 `pending_confirmation`，日历变为暂定，自动生成的准备待办取消（只有日期的情况之前会返回 500）。商户新建时填写的值引用了客人自己的消息，视为客人已确认；只有日期的值保持 `proposed`。只有时间时，正式日历占住时段，但工单保持待确认、不生成准备待办；只有日期（新建或确认时）都是暂定日历，不参与撞期检查（之前确认只有日期的提议会出错）。规则生效前已确认的工单（演示数据缺地址）不降级。
- **待确认项草稿：** 工单新建或确认后仍是 `pending_confirmation` 时，生成一条 `send_text` 草稿（trigger `open_items`，原因代码在 `open_items` 中：`missing_schedule`、`verify_schedule`、`missing_time`、`missing_address`、`verify_address`），只问未完成的项，并复述待客人核对的值，例如「你好，想跟你确认一下：你说的是 10/17 吗？几点方便？见面地址是？」。它会替换旧的未发送草稿（`superseded`）；最后一项确认后关闭（`resolved`）。收到新消息后沿用现有的暂停/重新生成规则；重新生成会按工单当前的未完成项重新组织问题（已无未完成项则 409）。trigger 身份为 `open_items:<工单>:v<版本>:<原因代码>`，重新生成轮次为 `open_items:<被替换的草稿>:r<上下文版本>:<原因代码>`，多轮不会冲突，长度也在 128 字符的列宽以内。
- **撞期：** 已取消或已完成的工单不再占用时段。
- 未实现：`from_proposal_id`（B 尚无 `new_work_order` 归属）、按单识别、延后及其跟进待办（需要 B 标出延后项）、取消/完成工单时作废草稿（随计划中的状态命令）、用 AI 的 `draft_text` 作正文（B 的 prompt v1 把它定义为给商户的摘要）。

证据：`test_create_order.py` **30 项通过**（原 24 项 + #26 第一轮评审的 4 条回归：拒绝商户发出的来源、拒绝空白地址、已确认改为只有日期时回到待确认而不是 500、从 trigger 右侧解析原因代码；+ 10/16 评审的 2 条：客人未确认的具体时间改期，日历为暂定、不占时段；客人确认后恢复为正式）。本地 PostgreSQL 16 上 `test_create_order.py`、`test_approvals.py`、`test_workflow.py` 共 70 项通过。合并 main `53991dc`（#23、#25）后：SQLite 全套 673 通过、12 跳过；Alembic 只有一个 head `0016_d03_sending_heads`（本 PR 无新迁移）；Ruff/格式、契约导出、baseline、前端接口检查和类型检查通过。PostgreSQL 只跑了这三个文件，没有测并发请求。未触碰真实 WhatsApp、发送、模型或部署。

## PR #22 审批动作评审跟进（C）— 2026-10-13

PR #22（`lena/approval-actions`，head `e79ef7b`）新增 C 的审批动作：改期提议与已确认预约撞期时，生成一条 `send_text` 草稿（`pending_approval`、固定模板、24 小时过期）；GET /actions、GET /actions/{id}、批准（202，核对快照哈希、版本和来源）、拒绝和取消（只改本地状态，保留原因）。批准只记录决定，不发送。已按 Kyrie（要求修改）和 Andy 的评审修正：

- **自身 API 发送回显（P1/P2）：** `source=api` 的受信任 WAHA 事件仍推进上下文、在接收时作废旧草稿，但 worker 以 `OWN_SEND_ECHO` 完成、不进入提取，因此不会产生回复。
- **看不懂不等于问题仍未回答（P1）：** 去掉自动“原样再问”。新消息之后只有明确结果自动处理（新撞期 → 新草稿；空闲时间 → `answered`）；其他情况把最新的已作废/已过期问题标为 `reissuable`，由商户用 POST /actions/{id}/reissue（带当前 `expected_context_version`）重新生成。
- **过期后来源被改（P2）：** 接收时把来源已变的过期草稿标为 `source_changed`；重新生成会再核对来源并拒绝。
- **GET 写回覆盖批准（P2）：** GET 列表和详情只计算 `expired` 视图；过期只在已加锁的行上写入（命令与接收，接收现在会锁住它要更新的动作）。
- **撞期依据已变化：** 批准和重新生成都会再查触发提议是否仍与已确认预约重叠，否则 409 `APPROVAL_STALE`。

不在本批、未改动：审批页面（D）、真实发送以及 C 动作到 A 发送网关的桥接（`ActionRow(state=approved)` 不是发送授权，会话 UUID 也不是 provider 聊天 ID）、工单取消/完成命令。迁移 `0009_approval_actions` 接在 `0008` 后；若 #21（0009/0010）先合并，需要补加性合并迁移。

证据：`pytest apps/backend/tests/test_approvals.py` 在 SQLite 和本地 PostgreSQL 16 上均 **18 项通过**；SQLite 全套通过；PostgreSQL 全套在该本地环境下出现与未改动 main 相同的 WAHA 计时相关失败，审批/工作流测试无失败。Ruff/格式、契约导出、前端接口检查和双语基线通过。未触碰真实 WhatsApp、发送、模型或部署。
## PR #21 新评审修复：持久化停止使用决定 — 2026-10-13

通过四个合成场景独立复现新增 P2：取消或暂停/恢复后，立即核对成功或连续未知后成功，都会因核对清除唯一停止标记而重新公开结果。现在将首次停止原因单独持久化为 `content_stop_reason`，不依赖状态、临时错误或控制版本。后续核对保留停止决定，不重新调用 process、不公开原任务结果、不恢复核对记录。未知结果仍阻止新任务；确认有效结果后以取消状态解除占用，仅允许另行明确创建新意图。

新增 **0012_waha_media_stop**，接在未改写的 0010 后，编号避开独立发送分支的 0011。新代码运行前需升级 head/check。迁移保留可见停止原因，并保守标记可能已被旧核对擦除决定的未知/核对任务；无法撤销旧实现已公开的结果，这类数据需操作人员复核。#21 合入后 #23 要兼容迁移祖先关系。公开契约结构不变，双语媒体说明及 API 文档同步记录限制。

实际自动验证：Windows 后端全套 **548 通过、9 跳过**（8 项 PostgreSQL 依赖检查及 1 项不适用平台检查），包含迁移/回填/降级及原有媒体/PDF 回归；最后补充明确新意图断言后，四项新增回归再次通过。隔离 SQLite 升级 0012/check 无漂移，不能据此证明 PostgreSQL 锁。前端 **57 通过**，生成类型、格式、TypeScript/build、适用 Ruff/格式、契约导出及 baseline 通过。新提交的 CI 还需确认 PostgreSQL 和系统矩阵；保留已有 Starlette/httpx 警告。无真实模型/媒体/发送、二维码、部署或用户数据库/会话操作；发送分支及两处未提交文档段落未改动。PR 保持 Draft，等待独立复核与人工验收。

## PR #21 PDF 资源隔离批次

生产 PDF 解析已移到私有子进程，默认墙钟 20 秒、内存 512 MiB，限制输入/输出并每个 worker 同时一个解析。Windows 将限制绑定到挂起启动的实际底层解释器，不是 venv 启动器；Linux 使用硬内存/CPU 限制并绑定父进程生命周期。PID 握手确认后才传数据。不继承模型/接入/数据库环境，不落临时原文件，固定 UTF-8 并重验 IPC 输出。原生 macOS 明确拒绝，使用 Linux Docker 后端。这是资源隔离，不是文件系统/网络沙箱或恶意文件扫描。

PDF 明确拒绝码在供应商调用前写入任务；worker 心跳独立于解析/模型等待。私有提交前回调在本地准备后重验授权/租约/来源，阻止解析期间取消后的模型调用。无需新结构/迁移。媒体 Compose 向 API/worker 提供可信限额，CI 增加 Linux/Windows/macOS 资源检查，其中 macOS 验证原生拒绝，不代表原生解析成功。

实际 Windows 证据：超过 128 MiB 的真实分配被拒绝；超时终止并回收私有进程；崩溃、超量输出、错误协议失败；PID 不符不传数据；不继承密钥；Unicode IPC 和心跳连续通过。最终提交前回调加入前全套 **542 通过、9 跳过**（8 个 PostgreSQL 检查及不适用平台测试）；最终受影响解析/任务/授权用例 **40 通过、1 平台跳过**，其它媒体兼容用例 **124 通过、1 项 PostgreSQL 跳过**。前端 **57 通过**，类型/格式/TypeScript/build、Ruff/格式、契约导出及隔离 SQLite 升级 0010/check 通过。保留已有 Starlette/httpx 警告；新矩阵 CI 及独立审核须在最终提交上确认。无真实媒体/模型/发送、二维码、部署或原数据库/会话操作；发送分支及用户未提交进度段落原样保留。

## PR #21 PDF 集成与模型中止修复 — 2026-10-12

已将队友 PDF 分支 `0d91ad1` 集成到原媒体 PR，保留本地解析器、独立业务提示词、依赖固定及文档 Unicode 修正。补上缺页文字强制 partial 和全文超限后不再读取下一页；修正片段数上限说明，它独立于全文字符上限。扫描件仍拒绝，未声明硬性 CPU/内存沙箱或真实模型已启用。

修复独立评审 P1：取消/撤权及到期保留可能已提交的处理/核对请求身份与附件占用；晚到不确定结果仍阻止新请求，重新授权也不保存晚到内容。原租约有效时不能并行核对；取消排队中的核对也保留原不确定状态。只有原尝试确定返回或提交前明确拒绝，才可解除占用，但不会恢复内容。到期清理与任务修改/完成使用相同的账户/连接锁顺序。无需新字段、迁移或强制重发接口；E 仍需独立验证 PostgreSQL 交错及来源上下文变化导致的核对限制。

实际自动证据：最终到期锁调整前后端全套 **520 通过、8 项 PostgreSQL 依赖检查跳过**，最终受影响媒体测试 **70 通过、1 项 PostgreSQL 检查跳过**。前端 **57 通过**，契约类型/格式/TypeScript/Vite 构建、适用 Ruff/格式、契约导出及隔离 SQLite 升级 0010/check 通过。新增回归覆盖未知/成功/提交前拒绝、取消、暂停后授权、来源变化、到期、排队/在途核对、部分覆盖及提前停止。模型仍关闭，未访问真实媒体/模型/发送、二维码、部署或用户数据库/会话。发送分支及用户两处未提交进度修改原样保留；仅更新 #21，不合 main、不改 #23。

## 真实 PDF 解析器：两层提取 — 2026-10-12

`gigmate.media.pdfparse` 用真实本地解析器（`pypdf==6.20.0`，已加入 `pyproject.toml` 与 `requirements.lock`）替换 `MEDIA_PDF_PARSER_PENDING` 桩。第一层在本地逐页抽取并施加有界 I/O：至多 200 页、每页文本按至多 4000 字符分块且保留页码、总计至多 100000 字符。`MEDIA_PDF_PAGE_LIMIT`、`MEDIA_PDF_TEXT_LIMIT`、`MEDIA_PDF_NOT_PARSEABLE` 与 `MEDIA_PDF_NO_TEXT_LAYER`（扫描件无文本层）全部在**任何厂家请求之前**拒绝，因此映射为 `ProcessingUnavailable`，不会产生计费；不做任何静默截断。第二层把抽取出的页与专用 prompt `role_b_media_pdf_v1.txt`（版本头 1.0.0，可用 `GIGMATE_MEDIA_PDF_PROMPT_PATH` 覆盖）发给 chat 厂家；模型只产出 coverage / summary / suggestions / unresolved_questions，其输出中的任何 `segments` 键都会被忽略——页面文本由本地绑定，模型永远无法重打、合并或捏造，suggestion 的 `source_indices` 由契约对照本地 segment 校验。可读 PDF 中的空白页以未决问题呈现，不冒充完整覆盖。本批同时修复了 2026-10-11 条目在 `docs/zh/role-b-extraction.md` 与 `docs/zh/progress.md` 留下的乱码（受腐蚀段落已按中文原文恢复）。

**测试**：`test_media_processor.py` 新增 9 个 PDF 用例——在模型响应里注入 `segments` 键证明本地绑定；无文本层 / 乱字节 / 201 页 / 超总量拒绝均验证**未发起**任何厂家调用；9000 字符长页分块；空白页未决问题；解析成功后厂家 5xx → `ProcessingUncertain`；非法 `source_indices` → 不确定。该文件 50/50 通过；后端全套复跑通过；Ruff check/format 干净；契约导出与基线检查无变化。

**如实限制**：实现仍以未激活状态交付（`_ENABLED=False`），没有发起真实模型请求。扫描/纯图像 PDF 直接拒绝而不是偷偷 OCR（那需要视觉厂家，仍未验证）。显式模型能力 / 按路由凭据核验、时间戳/时区对齐、prompt-injection 用例与真实厂家/编解码验收仍是 2026-10-11 修正清单上的开放项。

## PR #21 队友媒体集成与 main 兼容 — 2026-10-11

复核了队友的评论：工厂 process/reconcile 可调用性与构造函数异常处理已在 `a5aa0a1` 修复。集成了 B 的 `b5d7e84` 未激活媒体接缝，随后合入最新 main `bbb0074`；进展文件的冲突已合并，A/B 历史都保留。未包含 `Andy_WAHA_multitype_sending` 的发送侧改动。

附加边界修复：PDF 处理显式置为 pending 而非二进制转文本；默认未验证视觉路由与 custom 缺失 endpoint 在创建客户端前拒绝；UTF-8/90k TXT 预检；未知 origin 拒绝；prompt 编码回退；客户端关闭；不确定日志稳定；严格的输出/来源索引校验，不做有损截断或重排；ASR 全文保留且 coverage 为 unknown；smoke 拒绝/未知以非零退出。测试补丁经 monkeypatch 恢复客户端工厂，并使用真实 UTF-8 合成 TXT 而非标记为 TXT 的 PNG 字节。新增 14 个评审用例与 B 测试合计 **54 通过**。最后两项 smoke 回归/小边界编辑之前的整套后端运行为 **490 通过、8 跳过**；受影响的最终测试已复跑。前端 **57 通过**，API/格式/TypeScript/Vite 构建、适用的 Ruff/format、契约导出、基线与空白检查通过。一次性 SQLite 升级到 0010/check 无漂移。未执行 PostgreSQL 锁与真实模型/手机验收；仍存在一个既有的 Starlette/httpx 警告。

B 保持 `_ENABLED=False`；PDF 解析、真实视觉/音频模型能力、按路由凭据、时间戳对齐、prompt-injection 与厂家 request-id 对账属于激活工作。未访问真实媒体/模型/客户/二维码/部署。PR #21 保持 Draft；仅更新其自身分支。发送分支上所有者两处未提交的进展文件编辑已保留。


## PR #20 复核合并与发送分支兼容同步 — 2026-10-10

独立复核 PR #20 的 `1dc716f`：42 项提取测试通过，覆盖合并后的 #18 提示词/证据修复、常闭 skeleton 锁、隔离的 operator/live-origin 开关、假客户端请求、smoke 退出码及元数据序列化。GitHub 必需检查全绿。批准后合入 main，提交为 `bbb0074`；实现仍未启用，来源、endpoint、重试/租约、日期及诊断方面的启用门槛仍需完成。

当前 `Andy_WAHA_multitype_sending` 通过合并 `e7cdcfb` 包含该 main；解决冲突时保留双方中英文进度历史。同步前 48 个开发文件均已备份并恢复，发送批次仍未提交、未推送。组合验证：**后端 490 通过、9 项 PostgreSQL 依赖测试跳过**，**前端 63 通过**，TypeScript/Vite 构建、前端契约/格式、适用 Ruff 检查/格式、契约导出、基线及空白检查通过。隔离 SQLite 升级到 0011 并 check 无漂移；保留一项已有 Starlette/httpx 警告。未调用真实模型、发送真实 WhatsApp 消息、修改部署或验证 PostgreSQL 锁。本地备份及安全 stash 保留。

## WAHA 多类型发送第一批 — 2026-10-10

从媒体 PR #21 的 `a5aa0a1` 新建 `Andy_WAHA_multitype_sending`；独立复核 PR #20 后，已通过兼容合并 `e7cdcfb` 包含最新 main `bbb0074`。实现独立发送授权、11 种发送适配、请求头传递文件名的私有上传/预览、不可变审批/outbox、固定内容自动政策及商户批准的工单关联、所有关联工单版本/引用修订绑定、队列/频率/存储限制、原请求取消记录、未知结果核对与回执。不可变提交标识保留租约回收后原尝试晚到的成功响应。已兼容真实 payload.source、SDK ID 对象及表情空响应；Chromium 视频在提交前拒绝。固定 Chrome 覆盖需明确选择，Apple Silicon 使用模拟，不自动改变环境。完整步骤见[发送协议与统一验收](role-a-waha-sending.md)。

最终自动证据：后端 **467 通过、9 跳过**（SQLite，未执行 PostgreSQL 依赖检查）；前端 **63 通过**，TypeScript/Vite 构建、前端契约/格式、适用 Ruff 检查/格式、契约导出、基线（**69 个 Markdown / 408 个本地链接 / 13 正例 / 7 反例 / 12 合成场景**）及空白检查通过。隔离 SQLite 升级到 0011 并 check 无漂移。仅只读查验 Chrome 公开镜像清单，没有拉取/运行。合成 HTTP/worker/DOM/MockTransport 覆盖权限、固定审批、上下文/C 版本/来源变化、未知/晚到回执、不重发/不循环及重载后恢复；媒体签名不是编码器或手机证明。保留一项已有 Starlette/httpx 弃用警告。

Docker Desktop Linux engine 当前不可用，当前版本的隔离 PostgreSQL、真实 socket/WAHA、浏览器/Apple Silicon 及 E 独立验收待完成。没有真实模型、自主 Agent 触发或 WhatsApp 实际发送。B 负责真实生成/触发，C 的业务确认独立处理。本批没有升级或启用原私有安装、数据库、会话、白名单及容器。重建 API/worker 前需要迁移 0011，并明确授予发送权限。本开发批次未 commit/push/提 PR，媒体 PR #21 保持独立。

## PR #21 处理器工厂评审修复 — 2026-10-10

工厂加载在模型提交前校验 process/reconcile 均可调用，并将构造函数异常与配置错误分开，保留原始构造异常。验证：20 项工厂隔离测试通过；52 项媒体及证据测试通过，未配置测试数据库，跳过 1 项 PostgreSQL 并发测试。Ruff 检查及格式、契约导出检查、基线和空白检查通过。没有真实模型请求、真实媒体读取、部署或前端修改。

## B 媒体处理器：真实模型接缝实现 — 2026-10-10

在 A 的 WAHA 媒体摄取分支（`pr-21-review` →
`william/role-b-media-processor`）之上落地。实现 PR #21 故意留空的
`MediaProcessor` 接缝，使 A 可独立合并不依赖 B。按 `LLMProvider` 的双闸门
安全模式交付真实模型处理器：

* 模块级 `_ENABLED` 标志（默认 `False`）—— 默认在读任何环境变量之前
  拒绝所有调用。
* `GIGMATE_MEDIA_LIVE=1` 运维开关——除标志外仍必须设置才能联系厂家。
* 必须设置 `GIGMATE_MEDIA_API_KEY`，否则抛 `ProcessingUnavailable`。
* 真实客户附件要送达模型需 `GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN=1`；
  `synthetic` 来源绕过此闸。

路由覆盖四种允许类型：PNG / JPEG / WebP → OCR（视觉输入 chat
completions）、Ogg / MP3 / WAV / M4A → ASR（音频转写）、PDF → chat
completions、纯文本 → chat completions。集合外一律在联系厂家前
拒绝。

`scripts/smoke_media.py` 为运维侧手动 smoke（不在 CI）。需要两闸门
同时打开，打印解析后的提案 JSON。

**测试**（`apps/backend/tests/test_media_processor.py` 共 41 例）：
按轴拆分的两闸门（接缝标志、live 开关、API key、live origin）安全、
MIME 路由、按厂家调用形态、coercion 校验、4xx / 5xx →
`ProcessingUncertain`、网络异常 → `ProcessingUncertain`、坏 JSON →
`ProcessingUncertain`、`reconcile()` 在闸门关闭或无厂家查找时返回
`None`、安全边界（`MediaInput` 不带凭据；处理器不修改入参）、
工厂入口经标准 `module:AttrName` 解析。

**PR #21 回归覆盖**：落地实现后跑 `test_waha_media.py`、
`test_waha_media_evidence.py`、`test_waha_migration.py`，56 通过 /
1 跳过，与 PR 描述一致；A 侧行为未改变。

**Lint / format / 契约 / baseline**：

* `ruff check apps/backend/src/gigmate/media scripts/smoke_media.py` —
  通过。
* `ruff format --check apps/backend/src/gigmate/media scripts/smoke_media.py` —
  通过。
* `scripts/export_contracts.py --check` —— 未改生成文件；处理器复用
  既有 `WahaMediaResult` / `WahaMediaSegment` / `WahaMediaSuggestion`
  契约，未新增契约。
* `scripts/check_baseline.py` —— 通过。

**如实记录的限制**：

* 真实厂家来回未执行；测试套件基于 `_FakeClient` mock。真实调用需运维
  把 `_ENABLED` 翻为 `True` 并提供 `GIGMATE_MEDIA_API_KEY` 与厂家端点。
* ASR 默认厂家是 `openai`，因为 DeepSeek 不暴露转写端点；仅配 chat
  凭据时 ASR 路径以 `ProcessingUnavailable` 拒绝。
* `reconcile()` 一律返回 `None`，因为 chat-completions 厂家一般不暴露
  基于 request-id 的查找；worker 必须等待人工重试。
* 媒体附件的 prompt-injection 回归套件尚未补齐，列为开放待办。
* 本分支未重跑 PostgreSQL / 隔离 HTTP-worker 套件；本次只验证 SQLite。

**本批次附带修复**：`apps/backend/src/gigmate/extraction/evaluator.py` 的
`_resolve_manifest_path` 原本用 cwd 相对路径，从 `apps/backend/` 跑 pytest
时 `test_extraction.py` 必然失败。修复后 manifest 路径固定到仓库根
（`parents[5]`），不影响其他语义。这是个隔离的小改动，没有改变
evaluator 的行为。

## A 媒体第二批：时间依据与已核对交接 — 2026-10-10

基于 `cb11935`，保留最新 main/PR #16。A 已实现独立的供应商消息发送时间（不从事件/观察时间补造）、商户本次明确选择的合法 IANA 时区、持久固定处理上下文和 B DTO 扩展；新增 0010 接在未改的 0009 后。来源核对绑定版本/哈希/确切结果任务，新增受保护只读 WahaMediaEvidence 0.1.0 接口。建议可定位到来源片段，页面解释日期未知，核对后才提供交接资料，版本/上下文不一致时抑制展示。旧未绑定核对需要重新核对，不重新提交模型。收据身份/指纹语义保留。B 真实 OCR/转写/解析/GenAI 和 C 工单晋升/发送仍待接入，没有引入 PR #18 实现或执行权限。[协议与整批人工步骤](role-a-media-ingestion.md)。

自动证据：后端全套 **395 通过 / 8 跳过**，使用 SQLite（不证明 PostgreSQL 锁），含新增 17 个媒体证据场景及 0009→0010 升级保留旧发送时间/任务上下文为空的回归。原迁移分支升级/降级不丢数据。初期测试夹具选到了其他合成会话、损坏文件断言与原有 HTTP 码不同，已改为本附件归属会话及既有 MEDIA_INTEGRITY_FAILED/503，随后全套通过。前端 **57 通过**，含挂载真实媒体组件的来源链接/核对/交接版本不匹配/暂停清理回归（合成 API），以及丢失响应时保留时区；TypeScript/构建、生成 API、格式、后端 Ruff/format、源契约导出及 baseline 通过。另用一次性 SQLite 完成 Alembic upgrade/check。不声称真实手机/浏览器/模型/解析或网络锁行为通过。

Docker Desktop Linux 引擎不可用（命名管道不存在），未能执行 PostgreSQL/隔离 HTTP 全套。未修改真实数据库/WAHA 部署/会话/授权/附件/模型/发送。当前源码需要 0010；此前记录的部署仍为 0009。四种真实格式预览、B 真实处理器、C 消费与 E 独立验收仍待完成。本开发批次未 commit/push。

## PR #16 与媒体分支兼容同步 — 2026-10-10

PR #16 已合并到 main（`d6b298f`），将最新 main 同步到 `Andy_WAHA_media_ingestion`，保留全部媒体实现。三处重叠文件同时保留聊天分页与媒体的完整 CSS 规则，以及两边的中英文进度记录。真实工作台 DOM 测试增加 WahaMedia/waha-media-api 的模块编译，否则新增分页测试无法加载启用媒体的工作台。本次同步没有修改后端、迁移、生成契约或模型行为；PR #18 仍未合并。

独立隔离兼容验证：前端 **56 项通过**，TypeScript、生产构建、生成 API 漂移及格式检查通过。Windows 检出产生的 CRLF 统一为仓库 LF 后进行格式检查，换行规范化没有改变功能内容。媒体后端 **35 项通过 / 1 项 PostgreSQL 专用测试跳过**（SQLite），适用后端 Ruff/format、契约导出与双语 baseline 通过（66 篇 Markdown、377 条本地链接）。Docker Desktop Linux 引擎不可用，本轮不声称完成新的 PostgreSQL/HTTP 或真实手机/浏览器验收。没有操作真实账号、二维码、聊天、附件、模型或部署。

## A 附件读取 / B 协议交付 — 2026-10-10

Andy_WAHA_media_ingestion 从 56e482e 建立，保留之前未提交的运行恢复文档。用户明确确认 B 尚无真实适配器，先完成 A 管道/协议。实现权限范围内图片/音频/PDF/TXT 的明确下载同意、私有受限文件/哈希、受保护预览/下载、附件版本、持久阶段/租约/重试/取消、不确定模型结果只读核对、刷新恢复任务及绑定附件/上下文/确切结果任务的来源核对。来源/权限变化抑制结果和缓存读取，完整缓存复用、损坏缓存仅在明确同意下重新获取。真实 OCR/ASR/解析/GenAI 由 B 提供，A 仅交付服务端工厂接口和严格片段/建议结构，不授予业务权限；B 未设置时明确失败，无假 AI 成功。新增 0009、源生成契约/类型、可选 Compose/非 root 私有共享卷及双语交接/ADR 0006。

最终自动证据：**385 项 PG 配置测试通过**，含三条迁移路径及双媒体 worker 单次发布；B 部分夹具仍为 SQLite，不当作锁证据。**15 个实际隔离 HTTP/API/worker/评估检查点**（四种媒体传输/预览及 B 未配置处理）、评估 **7/7**、Alembic 检查和专用清理通过。合成音频/PDF 仅证明传输/签名门槛，不证明解码/解析。最终 SQLite 媒体模块 **35 通过/1 项 PG 专用跳过**。前端 **48 通过**，契约漂移/格式/TypeScript/生产构建、后端 Ruff/格式、导出、基线/空白/私有值扫描通过。初期夹具导入/状态/头部断言已修正，再跑最终套件通过。浏览器工具两次无法启动 Node runtime，不声称页面视觉/真实格式自动验收完成。

自有账号本地准备：原数据库升级 0009/check 通过，前后 enabled/control_version/授权聊天 ID 完全相同。API/worker 用 --no-deps 重建、媒体启用/B 工厂未设置，保留原 provider/会话/绑定/数据库/监控。新卷初始需 appuser 权限（0700），已纠正并验证实际非 root 写入/移除，镜像也补初始化供新安装。部署媒体模块哈希与最终源码一致。工作台/登录/capabilities 都 200，enabled=true、processor_configured=false；provider WORKING、pipeline_ready=true、授权版本 9、一个授权聊天，**真实媒体任务/文件为零**。原 provider 全局下载仍关闭。没有读取真实文件/聊天/二维码、发送、provision、确认故障或模型调用。真实图片/音频/PDF/TXT、B 真实模型及 E 独立评审仍待完成；未 commit/push。

## 原本地 WAHA 运行恢复 — 2026-10-10

后续页面过期排查：provider 仍为 WORKING，connected/pipeline_ready 采样新鲜；直接 ingress 的 setup 和最近操作为 200/succeeded，用户后续操作后的 control_version 为 9。5173 前端监听已停止，浏览器保留旧页面却无法刷新状态，授权视图也标记待重载。已把 Vite 以隐藏后台进程在 apps/web 启动，代理到 18702。启动命令结束后，localhost:5173 的页面/登录/setup/最近操作均 200；setup 为 WORKING、sample_stale=false、available=true、无活动操作。用户页面需刷新/重新登录/重新载入已有授权；不得盲目清除待核对原请求。本次没有应用源码或真实授权修改。

按用户要求修复原安装：Docker 重启/恢复时五个 WAHA 服务统一记录退出 255，restart=no 使其保持停止，原数据库则按 unless-stopped 恢复。provider FAILED 采样早于容器退出窗口；安全日志分析发现反复 WEBJS null.on 初始化异常，但未确定最初触发原因。启动相同容器、保留会话/绑定/数据库后，STARTING 转为 WORKING，无需二维码、升级镜像、替换回调或修改授权。仅将原本机这五个容器改为 unless-stopped，私有 local-data/waha-a02/restart-policy.override.yaml 用于以后 Compose 重建；共享默认配置不变，本安装重建时需把该私有覆盖加在 waha.compose.yaml 和 waha-ingress.compose.yaml 后。明确 stop 仍由操作者控制。

运行证据：provider WORKING/WEBJS、connected、enabled/live_connected/pipeline_ready 为 true、四项健康、待处理/处理中/失败任务为零，**7 项不读取内容的 HTTP 检查通过**。授权版本仍为 7、授权聊天数仍为 1。保留原 DB/会话卷，未读取原文件/聊天/二维码、发送、provision、确认故障或修复历史数据库。26 项历史故障待核对，恢复健康不证明漏消息已恢复。原前端已在 5173 启动并指向 ingress18702；WAHA 用 localhost:5173，独立工单演示用 127.0.0.1:18080，分开主机名作用域的浏览器 cookie。无实现代码/迁移/依赖/共享重启默认变更，仅文档及配置检查；未 commit/push。

## PR #18 llm 骨架评审跟进 — 2026-10-10

负责人对 PR #18（`WillW27/role-b-llm-skeleton`，head `78151a6`）的审查要求合并前修正两处代码并校正 PR 描述。两处代码修正已落在 PR 分支上；PR 正文属于 GitHub 侧编辑，仍需作者自行更新。

- **提示词配置回退（P2）：** `LLMProvider._read_prompt_version` 现在在文件缺失、`OSError`、非 UTF-8 字节、缺少 `prompt_version:` 头部行或头部值为空时统一回退 `0.0.0-skeleton`，并把可读原因记入 `_prompt_load_error`；`propose` 以 `llm:prompt-malformed` 备注返回 `needs_review`。此前空版本（`ValidationError`）与非 UTF-8（`UnicodeDecodeError`）会逃逸到 worker 的 `PROCESSING_FAILED` 重试路径且无证据；新增 worker 回归断言任务以 `EXTRACTION_NEEDS_REVIEW` 结束并持久化 proposal/trace。
- **真实调用闸门反转：** 闸门改为正向开关。`GIGMATE_LLM_LIVE` 关闭时 Provider 层直接拒绝并写 `llm:live-gate-off`（即便已配置供应商与模型）；只有闸门开启才会进入 `_invoke_model`（仍是 stub，返回 `llm:seam-pending`）。此前开启闸门被提前拒绝、关闭闸门反而进入接缝，仅补全 `_invoke_model` 会在闸门关闭时调用模型。来源信任边界改为最先校验，效果不变。
- 内置提示词仍读取 `prompt_version: 0.1.0`；`case-007-live-origin-with-fixture-text` 与评测清单语义不变。

实际证据（`78151a6` 的独立 worktree）：`pytest apps/backend/tests/test_extraction.py` **33 项通过**（原 25，新增 8 项回归：覆盖/缺失/空值/缺头/非 UTF-8 提示词、闸门关与开两个 spy、畸形提示词的 worker 证据）；完整 `pytest apps/backend/tests` **356 项通过、7 项跳过**。Ruff check/format、`scripts/export_contracts.py --check`、`scripts/check_baseline.py` 通过。测试运行在 SQLite 上，7 项跳过为仅 PostgreSQL 的锁测试，故此处不能证明 PostgreSQL 锁。未调用真实模型、未读取真实密钥、未触碰真实流量。PR 描述修正在 git 差异之外。

## D01 会话列表评审跟进 — 2026-10-10

Kyrie 明确授权合并 Andy PR #14，并将 D 文档范围扩展到这两份共享中英文进度记录。以 D 账号独立复查并批准 PR #14 的 `56e482e` 后，它已合入 main，合并提交 `ab52d3e`；本地 main 已快进。下方 Draft 描述属于历史记录。PR #16 现以 main 为目标，同步该 main 没有冲突；差异只含前端测试／依赖锁、D 文档及本进度记录，不改 Andy/WAHA、B/C、生成文件或契约。原 `Kyrie_Frontend`／`c702f0c` 保持完整。

- **D01-CHAT-TYPE：** 继续以规范 direct/group 为准显示和筛选。当前源码实际为“个人聊天”，评审引用的 `ConnectionWorkspace.tsx:934` 不是会话行文案。
- **D01-CHAT-PAGE：** 新增三项自动 DOM 集成回归，挂载真实 `ConnectionWorkspace`、`ChatChoices` 和 live HTTP 适配器，连接有状态的合成 fetch 夹具。覆盖跨页／群聊筛选勾选、每页数量变化、完整 PUT 授权／版本／同意参数、服务端重读、组件重新挂载、全局撤权、分页／筛选不自动发现，以及明确载入更多保留 offset=100 和隐藏勾选；另验证未命名兜底背后的真实 ID 仍可选择和撤权。这是组件／API 夹具集成回归，不是真实浏览器／后端端到端或磁盘持久化测试。固定 `jsdom` 为仅测试依赖，本次评审跟进不改生产依赖或产品行为。
- **D01-CHAT-NAME：** 在归属受控、已鉴权的工作区中，个人号码标签仍显示服务端提供的号码并提示“未提供昵称”，不把号码宣称为昵称。本批未引入号码遮罩，也不声称恢复缺失名称。未命名／已授权兜底名称仍对应真实规范 UUID，会话选项并非虚构空 ID；缺少名称不能阻止撤权。真实 provider 昵称解析仍属于上游工作，夹具和跟踪文件不含真实联系人或配对资料。

实际证据：前端 **53 项通过**（原 50 + 新增 3 项 DOM 回归），`check:api`、`format:check`、全部六个测试文件格式、TypeScript、Vite 构建通过；依赖锁安装／审计、源契约一致性、基线、空白／范围检查通过。PR #14 合并前用未修改的工具独立验证：**349 项 PostgreSQL 配置测试**、**10 个隔离 HTTP/worker/评估检查点**、评估 **7/7**、Alembic 检查及专用资源清理通过，适用 Ruff／格式通过。B 部分夹具仍用 SQLite，不等于所有 PostgreSQL 锁路径均有证据。未操作真实账号／会话／授权／历史／媒体或更新部署。Windows 原生验收、真实昵称恢复仍未验证。PR #16 已准备好独立复审；复审请求／评论不是批准，在取得独立批准且适用检查通过前不合并。

## PR #14 媒体撤回修复 — 2026-10-10

基于 59b8e14 的独立 P2 评审在当前 691567b 仍可复现：撤回归一化把已解析 canonical ID 覆盖为短别名，导致原说明文字仍显示。修复前完整 ID 对照通过，短 ID 因出现两行而失败。撤回现沿用 existing.provider_message_id，无 schema/接口/迁移变化。参数化回归验证一个已撤回快照、稳定单条 HTTP 时间线、后续受限历史读取不能恢复说明文字、重复收据/撤回不推进上下文或产生业务任务。额外别名重放断言验证同一收据的完整/短引用指向同一快照。

证据：PG 配置全套 **349 通过**，隔离 HTTP/worker **10 个检查点**、评估 **7/7**、Alembic 检查及专用清理通过。SQLite 同步模块 **30 通过/1 项 PG 专用跳过**；最终追加的别名重放断言在 SQLite **2 通过**。B 部分夹具仍用 SQLite，不新增锁证据。适用后端 Ruff/格式、源契约导出、双语基线及空白检查通过。前端无修改，沿用上一批 **45 项通过**及构建/类型/契约/格式证据。没有修改真实媒体/历史/授权/二维码/部署或修复私有数据库。此修复防止新撤回创建别名 tombstone，已受影响安装需另行限定范围核对。PR #14 保持 Draft，等待自有账号人工验收和修复独立评审。

## D01 / 消息同步兼容 — 2026-10-10

发布结果：PR #15 按受保护 main 的正常审批/检查要求合并为 1336c60。已验证兼容提交 33ebacd 保留在 Andy_WAHA_message_sync，包含最新版 main 且未覆盖消息同步功能。本地 main 快进至 origin/main。同步后 PR #14 转向 main，仅保留新增消息同步/兼容工作；下方早期依赖分支描述按日期保留为发布历史。

在隔离工作区组合 PR #15 的 1d198e9 和消息同步 59b8e14，解决两处前端冲突。保留 D01 授权载入/撤销、版本/到期校验、原请求持久恢复及回放 store；保留消息同步分页、已载入搜索/类型筛选、时间线及媒体/同步后端。恢复发现请求保留原 offset/limit/version/key，并返回选项/下一页游标；页面不重置现有未保存勾选、不自动提交下一页。新增后续分页响应丢失、客户端重建、待核对时阻止新分页、原样重试、继续下一页、自定义保存 limit 和非法分页存储的回归。

实际证据：**45 项前端测试通过**，接口契约、源码/测试格式、TypeScript 和生产构建通过；**347 项 PG 配置后端测试**、**10 个隔离 HTTP/worker 检查点**、评估 **7/7**、Alembic 检查及专用清理通过。B 的部分夹具仍是 SQLite，不当作 PG 锁证据。后端 Ruff/格式、契约导出、双语基线和空白检查通过。首次 runner 因 Docker 未运行而停止，启动已安装 Docker Desktop 后完成；未改文件的 checkout CRLF 导致格式警告，仅规范审核副本换行（无语义/索引差异）后格式通过。未读取真实二维码/内容或修改真实授权/配置。真实手机/Apple Silicon/群聊/媒体及 E 独立验收仍待完成；随后按此已验证集成执行远端 #15 合并和当前分支同步。

## WAHA 评审修复 — 2026-10-09

已修复配置失效阻止撤权、刷新会话替换有效候选 ID 两项问题。保留/缩减授权不再依赖 provider 配置，新增/重新授权仍会校验。刷新仅更新名称，保留有效 ID 和原到期时间，不删除未出现在本页的有效选项，过期选项生成新 ID。保留归属/CSRF/版本和上下文失效检查；配置失效撤权仍取消同步并记录禁止读取区间。无迁移或契约变化。检查点 c1b638f 在修复之前，当前修复提交为 7dc1bf0。基线修复已作为 99e73b1 推送至 PR #11，未包含消息同步依赖。新增消息同步 PR 在 PR #11 合并前以 Andy_WAHA_upgrade 为目标，评审差异仅包含额外功能。

最终 PostgreSQL 配置全套 **347 通过**，隔离 HTTP/worker **10 个检查点**、评估 **7/7**、Alembic 检查及清理通过。SQLite 全套 **339 通过/7 跳过**，该次全套早于最后新增的同步撤权测试；最终同步模块另跑 **28 通过/1 跳过**，控制模块 **27 通过/1 跳过**。旧分支工作区控制模块也 **27 通过/1 跳过**（PG 并发项跳过）。前端 **12 通过**，契约漂移/格式/TypeScript/构建、后端 Ruff/格式、契约导出、基线及空白检查通过。合成回归覆盖真实缺失配置、密钥不匹配、全部/部分撤权、拒绝重新授权、CSRF/旧版本、双浏览器窗口、固定到期时间和过期 ID 替换。未修改真实授权或配置。本次修复无需手机操作；真实历史/群聊/媒体及 E 独立评审仍是后续验收内容。

## WAHA 有界消息同步批次 — 2026-10-09

从 ebf9398 创建 Andy_WAHA_message_sync，未新 commit/push。已实现聊天分页/已载入搜索分类、归属隔离时间线（稳定展示 ID 与标准来源 ID 分开）、持久历史/故障/来源查询、取消/进度/重新发起、分页租约退避和权限复查、暂停/撤权排除区间、群参与者/引用出处、媒体元数据/说明文字/ACK/编辑撤回及验证后的私有旧安装 DB profile。新增 0008、更新源模型及生成契约/类型，原 0.1 文字事件链路保留。用户明确暂不读取原文件或做媒体 GenAI；不向页面/模型传二进制、下载地址、引用正文或接入密钥。[完整范围和人工步骤](role-a-message-sync-acceptance.md)，[ADR](../en/adr/0005-bounded-waha-observations.md)。

最终 PG 配置全套 **340 通过**，三条迁移路径和同步并发认领使用隔离 PG schema；B 提取夹具仍用 SQLite，不当锁证据。SQLite 全套 **333 通过/7 跳过**；前端 **12 通过**，生成类型/漂移、TypeScript/生产构建、格式通过。隔离真实 HTTP/API/worker 工具 **10 个流程检查点**通过，包含有界历史/媒体元数据、来源查询不伪造修订/Job/清除故障、worker 重启及评估 CLI **7/7**；Alembic 模型检查及专用资源清理通过。期间夹具注册和媒体错误转换问题已修复后全套通过。合成浏览器验证实时/历史/音频时间线、明确同意和重复查询去重、撤权清除已显示正文/选择及恢复；仅合成截图留忽略目录。限定范围 Ruff/契约/基线/空白/私有值扫描通过。

真实本机准备：原 DB 16433 从 0007 升到 0008，模型检查通过，前后连接授权/版本/聊天元数据完全一致。保留 provider/登录卷、不重启 provider，使用 --no-deps 重建 ingress/worker/monitor。doctor 健康；登录后只读 setup/sync-jobs/source-gaps 都 200；新鲜 connected/pipeline_ready=true、队列/失败为零。真实同步任务为零，没有自动发现联系人、读取时间线/历史/文件/二维码、修改授权或确认故障。真实历史/群聊/媒体格式、长查询暂停重启、Apple Silicon 和 E 独立评审仍需人工。PR #11 基线保留，后续新 PR 应在同步 main 后仅包含新分支工作。

## PR #9 同步及整批兼容验收 — 2026-10-09

main d6e70eb 已通过 f166084 合入 Andy_WAHA_upgrade，本地 main 与 origin/main 一致。保留 stash c2d6d15 并恢复原修改后，按用户要求提交此前成果检查点 **0e22486**。后续修复随本次 PR 提交，真实账号人工验收仍待完成：新增 0007_merge_waha_extraction，依赖两条现有迁移终点，不重写已共享迁移；Windows 提取夹具使用 pytest 管理文件并保证关闭引擎；同步 A/B 双语交接及旧安装/团队人工步骤。实际合并后生成契约仍一致。

自动证据：TEST_DATABASE_URL 指向临时 PostgreSQL 17.9 的全套 **310 通过**；迁移测试在三个隔离 PG schema 中验证从 0004、B 的 0005 证据分支、A 的 0006 采样分支升级，保留回放行、暂停连接/计数、A 控制版本/采样和 B 评估记录。SQLite 全套 **304 通过/6 跳过**；Windows 提取+迁移针对性 **22 通过**。B 提取单测在 PG 配置全套中仍用独立 SQLite 夹具，不当作锁证据。八个 HTTP/worker/评估流程检查点通过，含 HMAC live-origin 接收→持久待复核提案/调用证据且不写业务、暂停拒绝、worker 重启、归属隔离及评估 CLI **7/7 合成案例**落库。Alembic check 通过，只清理测试资源。前端 **9 通过**，接口类型/格式/TypeScript/构建通过；Ruff、契约导出、基线、空白检查通过。

起初 Windows 错误已确认是未关闭且默认关闭即删除的 NamedTemporaryFile 文件锁，不是 WAHA 运行失败。首次 PG 复测发现迁移测试沿用 SQLite JSON 字符串断言，PG 实际返回对象；改为语义相等后全套通过，没有修改应用数据。已为测试启动 Docker Desktop；没有升级用户真实安装、接管 provider、获取真实二维码/发送、变更授权或确认故障。真实手机扫码/消息变更、真实撤权/暂停恢复、Apple Silicon 配对和 E 独立评审仍需人工。[准备及整批人工步骤](role-a-integration-acceptance.md)。

## 合并 PR 后统一适配 — 2026-10-08

在 Andy_WAHA_upgrade、main d31aa7d/合并 20611ce 基础上，D 页面已接入持久鉴权后端，完成连接/二维码/聊天发现与授权/暂停恢复/故障审阅；删除第二条 Vite/Python 控制路径，旧未知重启记录通过持久迁移承接。新增 0006 provider 采样迁移，只读控制不再推进授权版本；STOPPED 缺少引擎时仅在固定版本/WEBJS 二次校验后接受。C 的任务准备标题和截止时刻在夏令时及跨午夜保持一致。已同步生成契约/类型和双语交接，保留原有人工证据修改。本批尚未 commit/push。

实际证据：**PostgreSQL 288 通过**；**SQLite 282 通过/6 项 PostgreSQL 专用跳过**；六个隔离真实 HTTP API/worker 流程、Alembic 模型检查及测试资源清理通过。前端 **9 项测试通过**，生成接口、TypeScript、格式和生产构建通过；契约同步、基线、限定范围 Ruff、Git 空白检查通过。合成浏览器检查发现/保存/撤销授权、暂停恢复、STOPPED 恢复/图片展示和明确核对未知操作；数据库确认已恢复故障已审阅，两条历史保留，活动故障未清除。一像素测试图片不是真机扫码证据；真实手机测试、Apple Silicon 真机配对和 E 独立评审仍需人工。本批没有真实发送、授权修改或故障确认，没有删除真实数据库/会话卷。[升级和整批验收步骤](role-a-integration-acceptance.md)。

## 已提交协议与真实本地环境复查 — 2026-10-07

已提交 cf14815，未 push。独立 PostgreSQL 全套现 **273 通过**，含新增五项架构测试；实际独立 HTTP API/Worker 六个流程及清理通过。保留 gigmate-replay_postgres-data 和原 WAHA 会话/配置卷，用忽略的 Compose 覆盖恢复 localhost 16433 数据库，原 gigmate_waha_a03 升级 0005、Alembic check 通过；重建 live API/Worker/监控，内部 DB 端口 16433。四项健康、pipeline_ready=true，供应商 WORKING/回调匹配，七项 HTTP 通过。真实 setup/inspect/discover、同键重投、CSRF 和其他账号拒绝已验证，仅输出安全元数据；已连接 session 的 connect 成功，不覆盖回调。发现联系人产生过期私有元数据，但未改白名单、实际暂停、取二维码、发送消息或确认故障。15 条历史核对记录仍保留。手机文字变化及新二维码/人工授权移除/暂停仍需本人做；双语接入验收已记录准确步骤及本地客户端。测试后文档更新留本地，未包含于 cf14815。

## Apple Silicon 兼容性排查 — 2026-10-07

队友确认 Apple Silicon，尚无失败命令/日志。确认两项问题：命令示例仅 Windows，以及固定 WAHA 2026.9.1 镜像索引只有 linux/amd64 加证明材料、没有 ARM64。注册表实查同版本原生 arm-2026.9.1 摘要 b4216daddb7d5c1eb3ab99e608b76a005ec7523e766f923939d229718df4aafb 含 linux/arm64，Python 3.12.10-slim 含 ARM64。增加明确 ARM Compose 覆盖、team up/stop 按 Docker 引擎架构选择（不受 Python Rosetta/远程引擎误判）、私有文件 UTF-8 读取及双语 Mac 命令。不换引擎/版本、不迁移会话。17 项团队测试通过，含四种架构选择及未知架构拒绝；实际展开 x86/ARM 配置检查镜像/平台/WEBJS，不输出私有值。尚无实体 Mac 扫码/运行实测；队友具体失败仍需命令/错误原文。修复已确认兼容缺口，不证明所有 Mac 环境都通过。未 commit/push。

## WAHA 本地产品接入后端批次 — 2026-10-07

交付[接入 API 协议与统一验收](role-a-setup-api-acceptance.md)：账号/CSRF/版本校验的 setup、异步 connect/recover/inspect/discover、私有二维码、过期不透明聊天选择、明确同意、暂停/恢复及未知结果只读核对。新增迁移 0005_waha_controls，持久独立意图/候选/control_version；生成领域/OpenAPI/前端类型。Worker 先提交租约再调供应商，不自动重试不确定写操作，拒绝旧持有者、过期待执行意图、清理过期联系人元数据。只读鉴权不占账号写锁，变更仍串行归属校验；CLI 授权推进接入/上下文版本。Compose 给 API/Worker 私有控制配置。组员框架及双语入口更新；无页面、AI/发送/历史导入、生产/任意多商户注册或 Cloud API。

验证：独立 PostgreSQL 17.9 全套 **268 通过**（check_waha_setup --run --suite）；SQLite **262 通过、6 跳过**（`local-data/pytest-setup-final-sqlite`），跳过项需 PG 锁，保留现有 Starlette/httpx 警告。控制测试覆盖归属/CSRF、幂等/冲突、不透明/过期选择、严格同意、未知结果/不重试、过期/待执行/旧租约和并发唯一。迁移升降再升保留旧 Replay 数据。实际 HTTP API/Worker + 合成供应商的六个流程检查点及独立清理通过，Worker 重启保留待处理意图，空测试库 Alembic check 通过。Ruff/格式、契约同步、baseline/diff、前端生成/类型/格式/构建通过（Vite 初次沙箱 EPERM，在允许环境构建成功）。

环境限制：Docker 未运行，恢复后 Windows 保留 54261–54360，原 PG 54329 无法绑定。未修改系统保留端口、未删除真实数据库/会话卷；独立验收改用 16432，仅清理自己的资源。真实账号供应商探测不可用，因此本批新浏览器扫码/发现流程尚未在真实 WhatsApp 账号独立验收；不声称已升级/部署原 live 数据库或生产可用。此前真实文字证据为历史，新合成供应商运行验证不等于真实 WhatsApp 测试。E/人工步骤已明确；未 commit/push/合并 main。

## main 保护落地 — 2026-10-06

用户授权后已配置 GitHub main 保护并回读核验：PR 一位批准、旧批准随新提交失效、分支最新、三项 documentation-and-contracts/backend/frontend 检查绑定 GitHub Actions app 15368、讨论解决、管理员同样遵守、禁止强推/删除，无指定合并人/CODEOWNERS/绕过门槛。变更前无已有保护规则或 ruleset。PR #3 检查通过、独立批准零、未合并，GitHub 状态 blocked。管理动作仍待另一组员复核，未执行破坏性绕过测试。双语规则/进度已在本地记录；本次仅配置授权，不自行 commit/push。

## PR 后端 CI 导入路径修复 — 2026-10-06

PR #3 的 backend run 37432110763 在 test_waha_team.py 收集阶段报 `ModuleNotFoundError: No module named 'scripts'`。CI 使用 pytest 命令，PYTHONPATH 只有后端 src；此前本地使用 python -m pytest，额外把仓库根目录放入搜索路径。已用命令入口在本地复现。现于后端 pytest 配置明确加入 src 和仓库根目录（相对 apps/backend 为 ../..），统一两种启动方式，不跳过任何测试。这是测试环境问题，不是 WAHA/数据库运行故障。双语文档同步，实际复查和线上结果完成后记录。

本地复查移除 PYTHONPATH：pytest 命令的 PostgreSQL 全套 **253 通过**（`local-data/pytest-ci-console-fixed-pg`）；命令与模块两种入口的团队子集均 **12 通过**。Ruff/格式、生成契约、baseline/diff 通过。现有 Starlette/httpx 警告不是失败原因。修复提交推送后线上 CI 重新运行，实际结果须另行确认，不能由本地通过代替。

## 团队自己账号本地联调批次 — 2026-10-06

最终交付检查还核对 Compose 展开后 API/Worker/监控均指向团队数据库，在允许访问 Docker 的环境确认 doctor 的 Docker/数据库/绑定/API 全部健康；14 个变更/新文件扫描本地凭据与聊天标识，无匹配。Docker 不可用或无权限统一明确提示，不误判为一定未启动。

交付[团队本地 WAHA 框架](role-a-team-local-development.md)：waha_team 的 init/up/doctor/run/stop/checkpoint/verify、54349 独立 PostgreSQL Compose、按工作区配置控制的容器数据库覆盖（保留旧默认）。全新启动只建开发应用账号与空授权连接，不种 Replay 工单；再次启动保留暂停/白名单。工作区/资源/端口检查拒绝自动认领，绑定路径检查保护私有写入；验收工具不输出正文/provider ID，核对真实消息身份/修订，不完整返回退出码 2。B/C/D/E 已有具体接入位置、依赖和检查要求。本批没有新增领域模型/迁移/前端行为，不开发 Cloud API、发送或通用 AI。

自检：PostgreSQL 全套 **253 通过**（`local-data/pytest-team-final-pg`）；SQLite **248 通过、5 跳过**（`local-data/pytest-team-final-sqlite`），保留现有 Starlette/httpx 警告。12 项团队测试覆盖初始化、身份/未完成/撤回/缺失/范围、工作区/环境/资源隔离、安全错误及暂停保留，最终保护检查子集再次通过。首次测试存在导入别名隔离遗漏，覆盖了主机私有绑定；核对原配置/数据库归属后从保留原文件恢复，修正测试路径注入并增加运行路径检查。容器/供应商会话及业务数据库内容未受影响；恢复后 doctor 和 7 项 HTTP 检查通过。

真实独立 PostgreSQL 17.9 空库升级至 0004_waha_recovery，一条应用账号、会话/工单/任务均零，Alembic check 通过；确认原本无同名项目/卷后，仅清理本次创建资源。新验收工具用 10 月 6 日 UTC 07:07 已有真实新建/编辑/撤回验证身份一致、任务完成；新空 checkpoint 正确不通过。Ruff/格式、契约同步、baseline/diff 通过。前端未变，保留此前构建证据。尚未执行另一真实账号的全新 init/up/扫码端到端：启动编排用隔离替身测试，空库迁移是真实 PG，已有账号元数据是真实证据。新组员独立扫码流程仍需实际执行，不能冒充新成员验收。未自动确认故障，未 commit/push/合并 main。

## WAHA 交接文档审计与提交准备 — 2026-10-06

新增[WAHA 当前实现与团队交接](role-a-waha-handoff.md)，集中说明能力边界、命令/接口、B/C/D/E 对接和剩余 WAHA 依赖；修正中英文入口、职责、演进和连接流程中“真实接入待实现”的过时描述。按用户要求，官方 Cloud API 暂停且不列入当前计划。根目录 `start.txt` 保留本地并加入忽略。提交前 PostgreSQL 全套再次 **241 通过**（`local-data/pytest-waha-precommit-pg`），保留现有 Starlette/httpx 警告；Ruff/格式、生成契约、baseline/diff、7 项 HTTP 和前端 check:api/format:check/build 通过。前端首次因沙箱 spawn EPERM 失败，在允许创建子进程的环境通过。SQLite/故障测试保留此前日期证据，本次文档审计不修改运行代码。44 个变更/新文件核对本地私有值，无匹配，备忘录排除。用户已授权将剩余批次 commit/push 到 Andy_WAHA，不向 main 推送。

## 修复后真实文字变更验收 — 2026-10-06

用户 UTC 07:07 再次复测，已按账号/连接限定只读核对 PostgreSQL：计数 34 到 35 为较早 ACK，不创建任务；35 到 38 为同一条新消息的新建/编辑/撤回，修订 1/2/3、内部/供应商标识一致，最终已撤回。三个任务均尝试一次并完成；7 项 HTTP 检查再次通过，链路健康、无积压/失败。最后拒绝时间 UTC 06:48:08 早于这轮变更，期间没有新增拒绝。11 条核对记录保留。文档 baseline/diff 检查通过，无运行代码修改、commit 或 push。

按账号/连接限定的 PostgreSQL 只读元数据确认：10 月 6 日一条独立新消息，以及另一条消息的新建/编辑/撤回，修订依次为 1/2/3。同一内部/完整供应商标识贯穿后三条，最新版本已撤回。接收计数 30 到 34，四个可测量任务完成，状态样本无积压/失败。四个本地样本处理 8–12 毫秒、完成延迟 75–539 毫秒，不构成性能保证。LIVE_EXTRACTION_PENDING/SOURCE_SUPERSEDED 终态符合当前不调用模型、不发送的范围。私有配置卷修复后的新文字变更验证通过；此前待验证说明为历史。11 条故障未自动确认，不能据此证明遗漏消息已恢复。无运行代码变更、commit 或 push。[详细证据](role-a-recovery-acceptance.md)。

## 本地重启排查 — 2026-10-06

`waha_ingress.py status` 返回 `LOCAL_INGRESS_OPERATION_FAILED`。确认 Docker Desktop 未运行，54329/18700/18702 端口不可达；新终端没有 DATABASE_URL，CLI 因而使用默认 SQLite，而非已经注册连接的 PostgreSQL。主机私有配置与绑定 JSON 可读。启动 Docker Desktop 并恢复已有数据库/WAHA/接入/Worker/监控服务，保留所有数据卷及会话。指定原本的 `gigmate_waha_a03` 数据库后 status/diagnose 成功，四项健康、pipeline_ready=true，任务积压/处理中/失败均为零，7 项安全 HTTP 检查通过。连接恢复期间接收计数由 28 到 30，但正文同步仍为 10 月 2 日，不作为新消息验收证据。11 条核对记录未确认。本次没有运行代码变更、迁移、commit 或 push；仅服务恢复与文档记录，不重复全套测试。

每次新开主机 PowerShell 终端，执行操作命令前须设置 `$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'`。激活 `.venv` 不会恢复环境变量。先启动 Docker Desktop 和文档中的 Compose 服务；不要通过重新 provision 或删除会话卷解决数据库不可达。

## A-03 运行监控与异常恢复批次 — 2026-10-02

手动验收跟进：UTC 13:24–13:25 用户报告 WAHA connecting；13:27 直接查询及诊断为 WORKING，agent 未重启/重新扫码。接收 28 条中 22 条为连接通知，另 6 条是此前正文/ACK，最近正文同步仍为 09:18，因此新手动正文验收尚未通过。1 个已选择聊天与数据库白名单同步一致；较早来源未匹配为 ACK，另有较早创建被白名单拦截，暂未确定 connecting 诱因。后续配置挂载故障的确认与修复见下文；未 commit/push。

用户授权在 `83aa75e` 后继续：新增迁移 `0004_waha_recovery`、分组件健康和 Worker 心跳、签名拒绝安全指标、持久故障/来源核对、diagnose/issues/人工核对命令、终态耗时/租约指标及有上限的崩溃恢复。领域/OpenAPI/前端类型从源重新生成。[完整范围、E 用例、命令与边界](role-a-recovery-acceptance.md)。

后续确认：Windows Docker 配置挂载不可读（`ENODEV`），旧 API 健康信号遗漏依赖，实际接收被阻断。现改用 Docker 私有配置卷，健康检查验证绑定及归属，新增同步/迁移命令保留私有配置和会话。服务重建后四项健康、pipeline_ready=true，9 条人工核对记录保留；修复后 7 项 HTTP 检查及独立故障测试 8 个检查点通过。真实新文字验收尚待完成；本次有运行代码修复，未 commit/push。

- PostgreSQL 17.9 最终全套 **241 通过**，无跳过（`local-data/pytest-recovery-volumes-final-pg`）；SQLite 最终全套 **236 通过、5 跳过**（`local-data/pytest-recovery-volumes-final-sqlite`），跳过项需要 PostgreSQL 锁。保留一个现有 Starlette/httpx 弃用警告。新增迁移升级/降级/再升级测试覆盖旧 Inbox/Job；两个本地数据库已升级 head，Alembic check 通过。新增开始发送响应时登录会话已提交的证据；开发登录/退出使用函数作用域事务。
- 一次性 Docker 故障脚本 **8 项检查通过**：独立真实 PostgreSQL/API/Worker 停止恢复、真实 HTTP 并发接收、数据库失败 503、提交重投去重、积压处理、实际进程崩溃心跳过期、显式合成过期租约及不执行导入的人工核对。只清理 `gigmate-waha-recovery` 测试资源，未外发；安全结果位于忽略的 local-data/waha-recovery/result.json。
- 首次真实 WAHA 中断发现共享网络空间问题，监控也失去 API/数据库连接；已修复独立网络及固定内部 provider 地址。重测停止/恢复通过：WAHA unavailable 时 API/Worker/监控仍 healthy、pipeline_ready=false；恢复后四项 healthy、pipeline_ready=true，无需重新扫码。连接通知使计数从 10 到 12，不宣称真实遗漏正文已补回；MONITOR_GAP/PROVIDER_UNAVAILABLE 核对证据保留给用户。
- backend 与本次脚本 Ruff/格式、源生成契约、baseline/diff 检查通过；前端 generate:api/check:api/format:check/build 通过。Vite 初次因沙箱 spawn EPERM 失败，在允许的进程环境重试成功。最终签名检查失败已定位为私有绑定不可读，不推断其他早期失败原因。最终 smoke 新增故障列表（**7 项 HTTP 检查**），配置卷修复后通过。当前 pipeline_ready=true、四组件 healthy、无积压/失败，9 条故障仍待人工核对，诊断未输出凭据或正文。
- 真实数据/标识/凭据保留本地。本记录是开发者验证，不代表 E 独立验收。路由器/Internet 中断、注销后扫码恢复、完整历史补回、前端健康展示、生产鉴权/告警与对外执行仍待完成。本批未 commit/push。

## A-03 真实文字变更验证 — 2026-10-02

用户于 UTC 09:18 用新消息依次发送、编辑、撤回，接收计数 **6 → 7 → 8**。安全元数据确认创建、修订 2 的编辑、修订 3 的撤回使用同一内部/完整 provider 标识，最新版本已撤回。队列无积压/失败，数据库等待锁数为 0，六项 HTTP smoke 通过。中英文已补充证据，baseline 和 diff 检查通过。此前待完成的本地文字变更验证现已完成，不代表 E 独立评审、生产可用或断网恢复已通过。本次未 commit/push。[详细证据](role-a-stage3-acceptance.md)。

## A-03 回调事件循环阻塞修复 — 2026-10-02

用户明确已完成三步真实操作后，检查发现 API unhealthy，异步事件循环中同步接收发生阻塞，PostgreSQL 有等待锁的连接。已将接收移至线程池，保留成功响应前提交事务。新增同一事件循环中健康接口响应的回归测试通过。PostgreSQL 全套 **204 通过**（`local-data/pytest-loop-full-pg`）；SQLite 接入子集 **33 通过、1 跳过**（`local-data/pytest-ingress-loop-sqlite`）；保留原有 Starlette/httpx 警告。Ruff/格式和 export 检查通过。重新构建后服务健康，六项 HTTP smoke 通过，等待锁数为 0，监控恢复刷新。真实接收计数仍为 5，新消息编辑/撤回验证待完成。本次未 commit/push。[详细记录](role-a-stage3-acceptance.md)。

## A-03 短目标 ID 修复 — 2026-10-02

真实新文字已入库；编辑/撤回因 WAHA 短目标 ID 与创建时完整 ID 格式不同而匹配失败。已增加按授权会话及方向限定的短 ID 匹配、歧义拒绝和新增版本迁移 `0003_waha_stanza_identity`，回填已有映射。两个本地 PostgreSQL 数据库均升级至 head，迁移检查通过。API/worker/monitor 已重新构建，六项 HTTP smoke 通过。最新全套：PostgreSQL **203 通过**（`local-data/pytest-stanza-full-pg`），SQLite **201 通过、2 跳过**（`local-data/pytest-stanza-full-sqlite`），保留现有 Starlette/httpx 警告。backend 与本次修改脚本的 Ruff/格式检查及 export 检查通过；扩大扫描 scripts 时发现未修改的 `scripts/check_baseline.py` 存在原有未使用 import/格式问题，已保留文件。真实编辑/撤回仍需用户新消息复测；接收 3 条且无积压只证明当前接收/处理状态。本次未 commit/push。[详细记录](role-a-stage3-acceptance.md)。

基线：v0.2 回放工程骨架；最新授权扩展为 A-03 持久 WAHA 接入/监控，记录日期为2026年10月2日。下面早期证据保留为历史。后续实现必须持续更新本记录及英文 implementation-status，注明实际完成、测试证据和未完成范围。

## 已完成内容

| 任务 | 当前结果 | 代码与配置位置 |
| --- | --- | --- |
| SKEL-01 环境及锁定 | Python 3.12.10、Node 24.15.0、PostgreSQL 17.9，依赖锁与 Compose 完成 | apps、infra、.env.example |
| SKEL-02 数据与权限 | 13张业务/运行表、初始迁移、两套隔离开发账号、登录会话与 CSRF | backend/migrations、identity.py、api.py |
| SKEL-03 消息与后台 | 白名单校验、去重、编辑/撤回版本、持久任务、领取租约、有限重试、断库恢复 | messaging.py、worker.py |
| SKEL-04 工作台与确认 | 原文、待确认变更、冲突提示、显式确认、日历/待办及重启持久化 | web、workorders.py、planning.py |
| SKEL-05 契约与 CI | Pydantic 生成 domain schema/OpenAPI，生成前端类型及漂移检查，新增代码 CI | contracts、scripts、.github/workflows |

已完成的是回放骨架，不是完整 P0。固定桩只识别“冲突改期”和“可用时段”两段虚构文字，不调用模型服务。数据库、前端和 worker 使用真实实现；没有连接 WhatsApp，也没有任何外发执行。

正式改期必须由商户显式确认。后端检查账号、白名单、工单/会话版本及来源消息，再检查时间重叠，最后在一个事务内更新工单、日历、相关自动待办和审计。取消仅影响系统生成的待办，无关人工待办保留。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| Windows 开发环境及 Linux 容器构建 | 通过；运行时与依赖均锁定 |
| Compose 全套启动与健康检查 | 通过；迁移正常退出，API/数据库健康，worker/web 运行 |
| Alembic 初始迁移与模型漂移检查 | 通过，无额外迁移差异 |
| PostgreSQL 测试 | 26项通过：18项行为与8项旧契约样例兼容检查，含并发领取、失败三次终止、数据库短断恢复 |
| 原契约正反样例及生成漂移检查 | 通过 |
| Ruff、前端格式、类型及生产构建 | 通过 |
| 实际浏览器操作 | 冲突不能确认；16:30可确认，版本3升4，日历更新、旧自动待办取消、新待办生成，地址仍缺失 |
| 实际 HTTP 冒烟 | 登录、回放、确认/已有结果、日历待办、重复输入及退出检查通过 |
| 服务重启 | 数据库/API/worker 重启后已确认安排与任务仍保留，重复冒烟通过 |

测试使用虚构数据和隔离的临时 PostgreSQL schema，不清空工作台数据库。测试工具有一个 Starlette/httpx 上游弃用提示，未造成失败；未进行真实新成员计时测试。

恢复工作时 Docker Desktop 未运行；启动引擎并执行 Compose up --wait 后，服务恢复，已有确认结果的 HTTP 冒烟再次通过。文档基线和生成契约同步检查也再次通过。

## COLLAB-01：团队共享基线冻结（2026年10月1日）

- 已发布骨架提交：[3231810](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/commit/3231810b7e17f7f3dd052eb8084fdd7b87d3c827)。开始整理冻结记录时，本地与 origin/main 一致，工作区干净，无需重复提交骨架。
- [文档与契约基线 CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/runs/36853663964)通过。
- [回放骨架 CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/runs/36853664016)通过：后端 PostgreSQL 测试、迁移、契约与代码检查，以及前端依赖安装、类型生成检查、格式与生产构建。
- 整理基线期间，本地再次通过 Ruff、格式、契约同步、文档/正反样例及前端检查。
- 本次额外的本地 PostgreSQL/迁移与 HTTP 复测未完成：Compose 启动后 Docker 引擎不可用，已中断等待中的原生迁移检查。冻结时最新 PostgreSQL 证据采用上述云端后端运行结果，之前的本地通过记录仍为历史证据。
- 单人自审：本次追加提交仅修改文档，未改运行时契约或共享迁移，中英文记录一致、文档检查通过、未加入私人数据。
- 基线标签为 v0.2.0，注释标明经过测试的实现提交；后续冻结记录只修改文档，不扩大运行时范围。团队不得移动已发布标签，修复用新提交和后续版本标识。
- 冻结范围仅为虚构回放工程骨架，不代表生产发布、真实 WhatsApp 连通或通用 AI 准确率。

后续依次完成：队友全新克隆独立启动、GitHub 主分支保护与必需检查、轮换模块联系人、首批边界明确的任务。当前尚未配置主分支保护，CI 通过与版本标签不等于合并门槛已经生效。

## COLLAB-02/03：入门材料与平等协作准备（2026年10月1日）

已准备[中文入门清单](onboarding.md)、[实测报告模板](onboarding-report-template.md)、[平等协作规则](team-governance.md)、对应英文说明和 ADR 0004。Issue 新增 Onboarding verification 模板，PR 模板新增入门证据与同伴评审要求；检查脚本要求这些入口存在。

清单覆盖全新克隆、固定环境、启动、ONB-01 至 ONB-08 回放/隔离/持久化/首个 PR、检查范围、故障反馈与文档修复。已核对 Compose 固定项目名可能复用数据库卷、API 镜像不包含 scripts/docs、示例密码不随环境变更重置等实际配置限制。

平等协作已作为文档规则落地：任何合适队友都可以评审，任何成员满足条件后都可以合并；模块联系人可轮换，无独占审批权；管理员同样遵守保护目标，不设置创建者绕过。当前个人仓库不能授予多个成员 owner 等价权限；目标为组织仓库中的全员相同 Admin，组织 Owner 权限另需明确。尚未迁移组织、邀请成员或配置保护。

本次变更仅为文档、模板及文档检查所需文件列表，未改业务实现或迁移。文档/链接/正反样例检查通过；单人自审核对了中英文规则、实际启动配置与未完成状态。没有代填任何成员报告、没有宣称队友独立实测或首个同伴批准 PR 已完成。COLLAB-02 实测及 COLLAB-03 平台设置继续待完成。

材料已发布在分支 docs/equal-team-onboarding，初始材料提交 6f84983；已建立[队友实测任务 #1](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/1)与[文档草稿 PR #2](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/2)，尚未合并 main。任务未指派，等待实际成员参与；这份材料 PR 不是队友的首个验收 PR。GitHub API 实际核对 main 的 protected=false，当前登录有仓库管理权限，但没有执行权限或保护变更。

## 启动与复查入口

详见[英文开发文档](../en/getting-started.md)，启动后访问 http://127.0.0.1:18080，开发账号 merchant / other，示例密码 demo-only-change-me。账号仅供本地回放；初次 seed 后修改环境密码不会自动重置已有账号。

关键验证命令：scripts/check_baseline.py、scripts/export_contracts.py --check、pytest apps/backend/tests、前端 check:api/format:check/build、scripts/smoke_replay.py。完整环境变量和命令在开发入口中，不能脱离环境直接宣称检查通过。

## A 的职责、技术演进和批次开发规则 — 2026-10-02

- 新增中英文 A 职责说明与技术开发演进文档，覆盖当前能力边界、事件映射、鉴权、可靠任务、连接监控、跨角色交接、四个开发批次和八组计划异常用例。
- 将用户对当前及后续开发的要求写入 AGENTS.md 和中英文协作规则：已授权里程碑内一次尽可能完成更多相关任务，开发中自行检查修复，完成后统一验收；保留独立评审、范围限制和外部阻塞的真实记录。
- 两个文档入口新增导航。本次只改文档，无运行代码、schema、生成文件、迁移或根 README 改动；未实现真实接入，未提交或推送。
- 实际验证：`.venv/Scripts/python.exe scripts/check_baseline.py` 通过，检查 30 个 Markdown 文件、91 个本地链接、3 个 schema、11 个合法样例、6 个拒绝样例及 12 个合成验收场景，jsonschema 4.26.0；`git diff --check` 通过。这些结果不证明应用行为或真实接入。本次文档变更未重跑 Ruff、pytest、迁移或前端检查。
- 自查已核对导航、中英文规则/阶段一致性、已实现与计划的区分及无私密数据；其他角色实际认领和真实验收仍待完成。

## 本地文档合并冲突修复 — 2026-10-02

- 解决本地 main c71cc6a 与拉入 main 50c989f 在同一位置新增内容的冲突：保留 A 文档和团队协作入口，保留两份完成记录。自动合并的协作规则同时保留批次统一验收和平等同伴评审。
- 实际验证：`.venv/Scripts/python.exe scripts/check_baseline.py` 通过，36 个 Markdown 文件、122 个本地链接、3 个 schema、11 个合法样例、6 个拒绝样例及 12 个合成场景；工作区和暂存区 `git diff --check` 通过；仓库内容扫描无残留冲突标记。
- 仅文档修复，未重跑应用/真实接入测试。解决冲突本身不代表合并提交或推送已完成；本任务未提交或推送。

## WhatsApp 连接与消息获取说明 — 2026-10-02

- 新增中英文产品/技术流程：GigMate 登录、账号所属 WAHA session、二维码关联、会话白名单、鉴权实时事件和有限可用历史；同步两个入口及 A 职责/演进导航，引用官方文档。
- 明确设备关联与逐会话处理授权不同，历史快照需要与实时事件核对；扫码、历史和真实接入仍待实现。无运行代码或契约变更，未提交或推送。
- 实际验证：`.venv/Scripts/python.exe scripts/check_baseline.py` 通过（38 个 Markdown、134 个本地链接、3 个 schema、11 个合法/6 个拒绝样例、12 个合成场景）；`git diff --check` 通过。自查中英文一致性和实现边界。未重跑应用、前端或真实接入测试；官方外链已查阅，不属于 baseline 校验范围。

## 尚待实现

- LIVE-01：完整持久文字/编辑/撤回/ACK、断网恢复和 provider 缺口/历史核对实测。固定版本/引擎、扫码及本地基础能力已验证。
- 通用 AI 抽取、真实样本标注与独立评测；当前桩不证明准确率。
- 多工单人工归类页面、其他需求字段、拒绝/编辑业务命令。
- 对外审批、outbox、代发、发送结果未知核对、API echo 和发送并发测试。
- 完整工作时间/缓冲规则、生产身份/密钥系统、完整账号及备份删除；WAHA 30 天正文清理已实现。
- 媒体、外部日历和其他增强模块。
- 截至 2026-10-16 冻结仍缺（见首条记录，仅本条记录范围内）：从 AI 新建提议创建工单——`from_proposal_id` 以及 C 侧提议持久化、每个 job 的合并判断；因此 demo 用手动建单。C 的其他在评审中的工作另行记录。

后续先完成持久真实接入与独立统一验收，再规划对外审批执行闭环。真实使用仅限明确授权的本地测试账号/聊天，不用于生产或宣称完整 P0。所有新增工作按协作检查表交付，持续记录完成证据，不能把回放成功写成真实接入成功。

## A-03 持久接入/监控 — 2026-10-02

在离线适配器 `908855f` 和本地能力工具 `016a679` 后，用户明确允许修改共享模块。本批新增私有绑定的签名事务接收、三张映射/状态表及 Inbox 连接外键（新增 `0002_waha_ingress`）、本地已接收版本顺序、持久去重/ACK/连接状态、账号隔离的状态/队列指标、注册/暂停/核对/清理命令、30 秒状态监控、每小时执行的30天正文清理、worker 租约及授权检查。真实内容不经过虚构提取桩，没有加入模型、外发、审批/outbox 或历史导入。领域/OpenAPI/前端类型从源码重新生成。[详细范围、步骤与边界](role-a-stage3-acceptance.md)。

- PostgreSQL 17.9：Replay 开发库与独立 `gigmate_waha_a03` 的迁移 upgrade/check 通过，原 `0001` 不变；一次性 SQLite 升级/降级/再升级测试保留既有回放 Inbox 数据。
- 使用文档中的 TEST_DATABASE_URL 执行 `.venv/Scripts/python.exe -m pytest apps/backend/tests -q --basetemp=local-data/pytest-ingress-delivery-pg`：**200 项通过**，无跳过，保留一个现有 Starlette/httpx 警告；覆盖并发接收/认领、提交失败/回滚/提交后响应丢失、来源顺序/方向、授权、租约、核对竞态、保留期和注册。
- SQLite 全套：**198 通过、2 跳过**（PostgreSQL 接收/worker 并发）；只证明兼容性，不证明行锁。
- Ruff/格式、export_contracts.py --check、baseline、前端 generate:api/check:api/format:check/build 通过。原生 Vite 初次遇到沙箱 spawn EPERM，在授权的进程权限环境重试 build 成功。
- 独立本地 API/worker/monitor 构建运行成功，provider 配置回调后无需再次扫码恢复 WORKING，两条真实 HMAC 状态通知持久入库且不创建任务。`scripts/smoke_waha_ingress.py` **六项 HTTP 检查通过**，不读取实际正文；API/worker/monitor 重启保留连接/映射/事件，再次 smoke 通过，监控刷新新鲜度。
- 私有绑定、密钥、二维码和 profile 保持忽略/不跟踪。业务回调现已切到可靠接入，不再由内存 probe 接收。真实新文字/编辑/撤回/ACK 持久接入和更完整断网恢复仍待授权聊天及 E 的一次独立统一评审。本批未 commit/push。

## Role B 抽取子系统 — 2026-10-08

分支 `william/role-b-extraction-prompts-eval`（本地，未推送）。交付默认 deterministic 抽取 provider、离线评测工具、持久提议证据，并用 provider 钩子取代原先的 `LIVE_EXTRACTION_PENDING`。范围、合约和评测格式见 [docs/zh/role-b-extraction.md](role-b-extraction.md) 及英文对应。

- 新增 Pydantic 模型 `ChangeProposal`、`ProposalChange`、`ProposalCandidate`、`AssignmentResult`、`EvaluationCase`、`EvaluationRun`；`python scripts/export_contracts.py --check` 通过，`contracts/domain/models.schema.json` 已从源重新生成。OpenAPI 与前端类型未变。
- 迁移 `0005_extraction_evidence` 新增 `proposals`、`model_call_traces`、`evaluation_runs`、`evaluation_cases`。`0001..0004` 不改。`alembic upgrade head && alembic check` 通过。
- `gigmate.extraction` 子包交付 `DeterministicProvider`（默认）与 `DisabledProvider`；通过 `GIGMATE_EXTRACTION_PROVIDER={deterministic,disabled}` 选择，未知名启动时直接报错。Replay 分支仍调用 `gigmate.understanding.extract`，`test_workflow` 的 monkey patch 不受影响。
- Worker 的 WAHA 分支在同一事务中落库 `proposals` + `model_call_traces`。未知 live 内容以 `EXTRACTION_NEEDS_REVIEW` 完成，替代 `LIVE_EXTRACTION_PENDING`；不会写 `requirement_changes`。`test_waha_ingress::test_real_content_worker_never_calls_fictional_extractor` 改断言新错误码。
- `scripts/run_evaluation.py` + `contracts/evaluation/manifest.json`（7 条合成用例：已知改期、已知可用、未知 live、无工单关联、多工单歧义、prompt-injection、live 来源且文本与样例一致）。一次性 SQLite 跑出 7/7 通过；清单为空时直接报错。

临时 SQLite 验证（A-03 迁移已升级到 head）：

- `python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py`：0 错。
- `python -m ruff format --check ...`：50 文件已格式化。
- `python scripts/export_contracts.py --check`：同步。
- `python -m alembic -c apps/backend/alembic.ini check`：无新迁移操作。
- `python -m pytest apps/backend/tests -q --basetemp=/tmp/extraction_full`：262 通过、5 跳过（PostgreSQL 行锁测试需要真实 PG 实例，SQLite 不证明）。
- `python scripts/check_baseline.py`：52 个 Markdown、253 个本地链接、3 个 schema、11 合法 / 6 拒绝样例、12 个合成场景。

未证明：生产级模型接入、对真实 provider 的 prompt-injection 回归、负载下的延迟预算、新 provider 的真实 WhatsApp 流量、E 的独立签字。deterministic provider 默认拒绝未知 live 内容是设计，放开是下一个授权批次。


## Role B review 修复 — 2026-10-08

针对评审人在 PR head `7de6042`（GitHub 分支 `WillW27-patch`）提出的四个问题逐一修复；全部只用合成输入验证。

- P1 落库：`persist_changes_for` 不再对 Literal 字符串取 `.value`，也不再让 Pydantic 对象过 `json.dumps`；改为直接构造 `RequirementChange` 并用 `model_dump(mode="json")` 序列化。回归测试 `test_matched_waha_proposal_persists_evidence_then_merchant_confirms` 覆盖 matched 输入 → proposal/trace/change 落库 → 商家确认。
- P1 保留：`waha_ingress.purge_expired` 现在按 trace → proposal → 收据的顺序删除，`proposals.event_id` 外键不再让 30 天清理整笔回滚；结果新增 `deleted_proposals` / `deleted_traces` 计数。证据与收据共享保留窗口；工单上已确认的业务变更有意保留。回归测试 `test_waha_ingress::test_retention_removes_extraction_evidence_with_receipts` 覆盖接收 → worker → 过期清理全链路（外键在 PostgreSQL 下强制；SQLite 验证删除逻辑）。
- P1 来源信任：`ExtractionRequest.origin`（`synthetic` | `live`，默认 `live`）是服务端信任边界。Worker 的 WAHA 分支一律标记 `origin="live"`；deterministic provider 对 live 来源即使文本与样例一致也拒绝，固定日期模板只作用于受信 Replay/评测输入。新增清单用例 `case-007-live-origin-with-fixture-text` 及单元/worker 回归测试固化。
- P2 provider 开关：legacy Replay 路径改经 `gigmate.extraction.provider()` 解析，不再硬编码 `deterministic`；`GIGMATE_EXTRACTION_PROVIDER=disabled` 同时作用于两条路径（Replay → `STUB_UNSUPPORTED_INPUT`，live → `EXTRACTION_NEEDS_REVIEW`）；未知名直接报错。双语文档已同步。
- 小项：`scripts/run_evaluation.py` 导入补 `# noqa: E402`，并把该脚本纳入 `.github/workflows/skeleton.yml` 的 `ruff check`/`ruff format --check` 范围。

验证：`ruff check`/`ruff format --check`（ruff 0.15.6，CI 范围含 `run_evaluation.py`）通过；`pytest apps/backend/tests -q`：268 通过、5 跳过（PostgreSQL 套件需要真实 PG 实例；两条新的外键敏感测试在 SQLite 上执行同一代码路径）；`export_contracts.py --check` 同步；`check_baseline.py` 通过；评测 7/7 通过。本轮无迁移改动（`0005` 已随 PR 交付）。
## Role B llm provider 骨架（含 P2 review 修复）— 2026-10-09/10

本地分支 `william/role-b-llm-skeleton`（未推送）基于 `d6e70eb`，把真实模型 provider 的接缝作为不发请求的骨架交付。下一授权批次必须**同时**补齐两个接缝方法并把类标志 `LLMProvider._SKELETON_SEAM` 翻为 `False`，否则 provider 仍然拒绝所有请求。本批不动 worker、合约、注册表选择或 Replay 路径。

本批实际新增（与 diff 对齐，无夸大）：

- 新增 `gigmate.extraction.llm`：`LLMProvider`（注册表名 `llm`）与 `LLMIntegrationPending`。Provider 遵守 `ExtractionRequest.origin` 信任边界（live 来源在 `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1` 之前一律拒绝），从 `gigmate/extraction/prompts/role_b_extraction_v1.txt` 读取版本化 prompt，并把配置的模型与 prompt 版本写入 `ModelCallTrace`。配置通过 `GIGMATE_LLM_PROVIDER`、`GIGMATE_LLM_MODEL`、`GIGMATE_LLM_API_KEY`、`GIGMATE_LLM_ENDPOINT`、`GIGMATE_LLM_PROMPT_PATH`、`GIGMATE_LLM_LIVE`、`GIGMATE_LLM_ALLOW_LIVE_ORIGIN`。模块**只读** `GIGMATE_LLM_API_KEY`；刻意不读 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`，也不为它们抛 typed configuration error。
- 双闸门安全网（P2 review 修复）：
  1. **类标志 `LLMProvider._SKELETON_SEAM = True`**——无论环境变量如何配置都拒绝所有调用。本批保持 `True`，下一批次必须把它翻为 `False` 的同时实现真实 `_invoke_model`。
  2. **`GIGMATE_LLM_LIVE=1`**——真实调用所需。开关关闭时在 provider 层阻止调用，即使 provider/model/key 全部配置；未来真实实现的 `_invoke_model` 也无法在开关关闭时被触达。
  Spy 测试 `test_llm_provider_off_gate_blocks_at_provider_layer`、`test_llm_provider_on_gate_blocks_at_provider_layer_when_seam_unimplemented`、`test_llm_provider_skeleton_flag_is_required_to_reach_invocation` 固化两种状态。
- prompt 加载容错（P2 review 修复）：`_read_prompt_version` 同时捕获 `OSError` *与* `UnicodeDecodeError`，校验版本字符串非空，并把失败原因记入 `LLMProvider._prompt_load_error`。所有失败模式（文件缺失、编码错误、缺版本行、空版本头）都返回 `llm:prompt-malformed` outcome，并落库 `Proposal` 与 `ModelCallTrace`——worker 不会再把这些情况冒到宽口径 `except Exception` 触发 `PROCESSING_FAILED` 重试。新增 `test_llm_provider_missing_override_prompt_records_prompt_malformed`、`test_llm_provider_non_utf8_prompt_records_prompt_malformed`、`test_llm_provider_empty_prompt_version_records_prompt_malformed`、`test_llm_provider_no_prompt_version_header_records_prompt_malformed`、`test_llm_provider_worker_evidence_when_prompt_malformed`（最后一条端到端跑 worker 并断言 `job.error_code == EXTRACTION_NEEDS_REVIEW` 加落库的 `Proposal` / `ModelCallTrace`）。
- deterministic provider 的 `prompt_version` 属性同样捕获 `UnicodeDecodeError` 并拒绝空版本头（`test_deterministic_provider_prompt_version_handles_malformed_files`）。
- 新增清单用例 `case-008-llm-skeleton-needs-review`（`provider` 字段为 `llm`）固化骨架行为。评测器现在跳过 `provider` 字段与当前 provider 不匹配的用例，所以默认 deterministic 运行仍 7/7 通过。用 `--provider llm` 跑清单会执行这条定向用例加五条通用 needs_review 用例（3、4、5、6、7）；matched 用例（1、2）在 `llm` 下预期失败，文档中已说明。
- `EvaluationCase` Pydantic 模型新增可选字段 `provider: Text | None`；通过 `python scripts/export_contracts.py` 重新生成 `contracts/domain/models.schema.json`，`--check` 同步。
- 清单路径解析（cwd 安全网）：`_resolve_manifest_path` 现在把相对路径锚定到仓库根（`evaluator.py` 文件的 `parents[5]`），不再依赖当前工作目录。绝对路径保持原行为；文件仍缺失时抛 `FileNotFoundError` 并带上解析后的路径。CI 之前能通过只是因为 pytest 总是从仓库根启动，但 `scripts/run_evaluation.py` 在其他 cwd 下执行会直接 `FileNotFoundError` 崩溃。修复后用 `/tmp` 作为 cwd 跑两条 evaluation-manifest 用例均通过。
- 测试：原有 6 个用例上再补 8 个，extraction 全套 34/34；后端全套在 SQLite 上 325 通过、6 跳过（PostgreSQL 锁测试）。
- `scripts/run_evaluation.py --provider llm` 端到端运行生成的 JSON 报告：6 通过（用例 3-8）、2 失败（用例 1-2 符合预期）——骨架行为如设计。
- CI：`.github/workflows/skeleton.yml` 的 `ruff check` 与 `ruff format --check` 范围已恢复包含 `scripts/run_evaluation.py`（上次合并因网页上传绕过被去掉）。
- 双语文档：`docs/{en,zh}/role-b-extraction.md` 新增 `llm provider 骨架` 章节并补充 `双闸门安全网` 与 `prompt 加载失败模式` 小节，provider 选择表新增 `llm` 行；“待办”条目改写为下一批次必须完成三件事：(a) 真实 SDK 调用、(b) `_SKELETON_SEAM = False`、(c) 真实授权 + live-origin 通道走独立审查。

本批**未做**（诚实地划清范围）：

- 没有真实模型接入、没有真实模型凭据（OPENAI_API_KEY/ANTHROPIC_API_KEY 未读、相关 typed configuration error 未实现）；`GIGMATE_LLM_API_KEY` 仅作为后续服务端配置记录。
- 没有媒体处理适配器。A 的附件链路（OCR/ASR/PDF）仍需独立 `MediaProcessor.process/reconcile` 实现；本 PR 不能作为这三项已完成的依据。
- `scripts/smoke_deepseek.py` 是手动运维脚本，需要 `GIGMATE_LLM_LIVE=1` 加真实 key 才会发请求；CI 用进程内 `httpx.Client` 测试 seam。
- PostgreSQL 全套、HTTP 集成与完整 Docker 重跑在本轮 reviewer 环境中未跑（Docker Desktop Linux engine 不可用）；上述 SQLite 结果仅作为条件兼容性证据，不作锁证据。

验证（ruff 0.15.6，锁定版本见 `apps/backend/requirements.lock`）：`ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py` 通过；`ruff format --check` 通过；`export_contracts.py --check` 同步；`check_baseline.py` 通过；`pytest apps/backend/tests -q` 325 通过、6 跳过；LLM 评测 6/8（两条 matched 用例按预期失败）。无迁移改动；合约仅新增 `EvaluationCase.provider` 可选字段。分支尚未提交或推送，等用户选择上传方式。

## Role B 独立复核修复 — 2026-10-10

本批次对 PR head `e44d8ec`（远端 `WillW27/role-b-deepseek-integration`）的独立复核作出响应。复核者明确区分了**有意设计**（保持原样）、**当前可复现缺陷**（在本 PR 修复）、**真实启用前验收门槛**（仅在 role-b-extraction 文档中记录，本 PR 不实现）。骨架锁、操作员闸、live-origin opt-in、空 prompt 兜底、UTF-8 兜底、活门行为、有限模型调用重试均被认可为设计选择，**未改动**。

当前可复现缺陷（P2）已修复：

- **smoke 退出码。** `scripts/smoke_deepseek.py` 此前对所有 `needs_review` 输出都返回 0，除非 `notes == ("llm:not-configured",)`。配置 / 传输 / 解析 / Schema / 锁失败（`llm:seam-pending`、`llm:http-failed`、`llm:response-malformed`、`llm:response-schema-failed`、`llm:prompt-load-failed`）全部静默返回绿色。现通过 `_classify_exit_code` 分类：matched → 0；模型主动的 `llm:needs-review` → 0；任何 infra-failure note → 1；其他 `needs_review` note → 1（保守）。复测：默认骨架锁 + 活门开时脚本退出 1；活门关时脚本在到达模型前就退出 2（env check）。
- **registry 元数据 JSON 序列化。** `gigmate.extraction.registry.list_provider_metadata()` 此前读 `cls.prompt_version`。`DeterministicProvider` 把 `prompt_version` 改为实例级 `@property`（让 deterministic 与 LLM provider 与 prompt 文件锁步）后，从类上读这个 property 会返回 `property` 对象本身，`json.dumps(...)` 抛 `TypeError: Object of type property is not JSON serializable`。现在该 helper 构造一次 provider 读 `instance.prompt_version`；若构造失败（未来 provider 可能要运行时配置）则回落到类属性。新增回归测试验证可往返。

新增回归测试（合成，无网络）：

- `test_list_provider_metadata_is_json_serialisable` —— 断言 helper 对三个注册 provider 都返回纯字符串并能 `json.dumps` 往返。
- `test_smoke_classify_exit_code_marks_infra_failures_as_nonzero` —— 用 `importlib` 加载 `scripts/smoke_deepseek.py`，逐个传入文档化的 notes 元组，断言退出码。

启用前验收门槛（仅文档化、不实现）：复核者列出的 5 项（可信身份与出处重新绑定、vendor / endpoint 语义、与 worker 锁和租约一起设计的重试、带真实时间依据的日期解释、稳定脱敏的错误码）记入 `docs/{en,zh}/role-b-extraction.md` 新增的"Pre-activation acceptance gates / 真实启用前验收门槛"小节。每一项都是独立批次、独立评审，不在本 PR 范围。

验证（沿用上一批次的可丢弃 SQLite 库，A-03 分支迁移已升级至 head）：

- `python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py scripts/smoke_deepseek.py`：0 错误。
- `python -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py scripts/smoke_deepseek.py`：53 files already formatted。
- `python scripts/export_contracts.py --check`：同步。
- `python -m pytest apps/backend/tests/test_extraction.py -q --basetemp=/tmp/extraction_full`：36 通过。
- `python -m pytest apps/backend/tests -q --basetemp=/tmp/extraction_full`：327 通过、6 跳过（PostgreSQL 行锁测试）。
- `python scripts/run_evaluation.py --manifest contracts/evaluation/manifest.json`：7/7 通过（deterministic 默认）。
- `python scripts/run_evaluation.py --manifest contracts/evaluation/manifest.json --provider llm`：7 通过（用例 3-9）、2 失败（用例 1-2 预期失败；matched 合成 fixture 需真实模型）。
- `python -c "import json; from gigmate.extraction.registry import list_provider_metadata; json.dumps(list_provider_metadata())"`：往返正常。
- `bash -c "GIGMATE_LLM_PROVIDER=deepseek GIGMATE_LLM_MODEL=deepseek-chat GIGMATE_LLM_API_KEY=sk-fake GIGMATE_LLM_LIVE=1 python scripts/smoke_deepseek.py >/dev/null 2>&1; echo $?"`：输出 `1`（seam-pending → infra failure）。

骨架锁、操作员闸、live-origin opt-in 全部保留。**未调用任何真实模型、未读取任何真实 API key、未接触任何真实流量。**

## PR #20 合并最新 main（#18 之后）——2026-10-10

PR #18（`llm:live-gate-off` + malformed-prompt/证据修复）以 `cc2ac8e` 合入 main 后，把最新 main 合入 PR #20 head `fb7f4db` 时在 `apps/backend/src/gigmate/extraction/llm.py` 与 `docs/{en,zh}/role-b-extraction.md` 出现文本冲突——这是两次修复批次之间的真实分叉，不是 #20 的缺陷。解决方案**两侧都保留**：

- 常闭骨架门仍然在最前：`_SKELETON_SEAM=True` 期间所有调用（运维闸门开或关、配置与否）一律返回 `llm:seam-pending`，且绝不构造 HTTP 客户端（#20 语义；**没有**为了让冲突消失而打开生产骨架锁）。
- 骨架标志翻开之后，#18 语义完整保留：vendor/model/key 缺失或 vendor 未知 → `llm:not-configured`；运维闸门关闭 → `llm:live-gate-off`；未开 `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1` 的 live 来源 → `llm:origin-live-refused`。
- #18 的全部 malformed-prompt/证据修复保留：每种 prompt 失败模式都记录带 `_prompt_load_error` 原因的 `llm:prompt-malformed`；worker 持久化 `Proposal` + `ModelCallTrace` 而不是失败。
- #20 的未激活 HTTP 实现（`_invoke_model` / `_call_chat_completion` / `_parse_response`，30 秒超时、重试 1 次）保留在门后。`_refusal_reason` 统一改为返回 `(note, reason)` 元组，不再混用 raise/元组两种风格；`_parse_response` 对模型主动 `needs_review` 的回复补默认 `candidates`，最小化回复不再误报 `llm:response-schema-failed`。

`apps/backend/tests/test_extraction.py` 组合调整（现 42 项，此前 36 项；#18 的四个重复 prompt-malformed 单测由更强的 #20 版本取代，文件内已注明）：

- 骨架门开启：运维闸门开/关两种状态都断言 `llm:seam-pending`，并用陷阱式 `_client_factory` 证明从未构造客户端。
- 仅隔离测试子类翻转 `_SKELETON_SEAM=False`：闸门关仍以 `llm:live-gate-off` 拒绝且无客户端；闸门开发出文档化的假客户端请求（URL、bearer 头、`json_object`、temperature 0）并解析罐头响应；live 来源未开 opt-in 时拒绝、开启后放行。

`scripts/smoke_deepseek.py` 现在也把 `llm:live-gate-off` 与 `llm:origin-live-refused` 归类为 infra 失败（退出 1），覆盖翻门之后的正确性；骨架锁注释归属更正为 #20。

验证（仓库 `.venv`，SQLite——仅条件兼容性、不证明行锁；未调用真实模型、未读取真实密钥、未接触真实流量或部署）：

- `python -m ruff check ...` / `ruff format --check ...`（含 `scripts/smoke_deepseek.py`）：通过。
- `python scripts/export_contracts.py --check`：同步。
- `python -m pytest apps/backend/tests -q`：365 通过、7 跳过（PostgreSQL 行锁测试）。
- `python scripts/check_baseline.py`：PASS。
- 前端：`npm run check:api`、`format:check`、`build` 全部通过（本环境用 `npm ci` 安装依赖）。
- `run_evaluation.py`（一次性 SQLite）：deterministic 9/9 退出 0；`--provider llm` 7 通过、2 预期失败（用例 1-2 需真实模型）。

## D 接口接入准备（2026-10-17）

完成主线接口核对并准备 PR32 页面，详见[接口清单与开放条件](role-d-api-audit.md)。新增默认关闭的后端验收标记，候选合同独立生成类型；操作复核和结果未知保留原编号。没有 PR32 的主线可继续使用。后端交付测试本地 12 通过；前端和合同检查将在完成后补充实际结果。未宣称真实发送或模型验收。

接口阶段实际验证：前端 **149/149 通过**、TypeScript/Vite 构建、两份类型检查、两份后端改动的 Ruff/格式、合同导出检查、baseline（86 Markdown、992 本地链接）通过。后端交付测试 **12/12 通过**。候选 PR32 仅用固定合同和测试替身验证，未运行未验收的业务发送。

## D 会话缓存（2026-10-17）

工作台、连接、同步、附件和发送统一使用有界的会话内存 JSON 缓存；主线在完整鉴权/业务读取后计算弱 ETag，没有变化返回空 304。失败不会伪装为缓存读取成功。退出/换账号、权限错误和所有写请求（包括结果未知）清缓存。二维码、文件、ICS 不缓存，无离线写入权限。相同数据保留对象引用；业务轮询改为页面可见时每 5 秒，内容未变不切加载、不改数据更新时间。审批复核只在真实绑定变化时失效。网络错误保留并提示旧内容，私人访问失效则清理。

缓存验证：前端 **157/157 通过**，含刷新不变时保留勾选/焦点及不通知整页更新的回归；TypeScript/Vite 通过。后端条件请求、权限、工作台和附件证据子集 **33/33 通过**。完整 macOS 尝试为 **687 通过、13 失败、22 跳过**；其中 1 项响应头精确断言已修复并在上述子集通过，其余 12 项为 macOS 原生 PDF 限制 `MEDIA_PDF_LIMIT_UNAVAILABLE`。不宣称 PostgreSQL 锁或真实提供方验收。

## D 玻璃视觉语言（2026-10-17）

珍珠白、雾灰、雾蓝替换主界面/连接页/图标/安装信息的绿色；统一线条图标，桌面玻璃导航，手机四个主入口加更多菜单，并提供实色回退、增强对比、减少动态和键盘焦点。浏览器验收使用新建虚构 SQLite 数据库，未启动提供方或 worker；检查 1440px 桌面和 390px 手机，无横向溢出。私人截图不跟踪。最终检查数量稍后记录。

视觉验证：前端 **157 通过**、格式、TypeScript/Vite、baseline 通过。浏览器检查 1440px 业务/日历与 390px 业务/日历/建单；标题不被固定页头遮挡，无横向溢出或可见报错，手机更多菜单可回到页面顶部。不宣称原生 iOS 光学等价或真实提供方验收。
## PR32 独立修复与主线组合 — 2026-10-17

作者提到的 e6ba13f 未出现在远端 PR；按 Kyrie 授权直接修复可见的 d696735 分支。新增 0019_action_send_link：业务审批到准确发送任务的可空、唯一外键。读取/取消核对连接账号、聊天/会话、工单/上下文版本和完整正文；已有占键任务不能被接管。旧记录缺少可信关联时显示结果未知，不猜测回填；旧缓存发送 ID 也重新检查归属。延期、需求新增/关闭、草稿编辑在写入前拒绝暂停或未关联的会话。摘要日期由真实日期类型校验，非法日期 422；最新审批 ID 在 SQL 中计算，无筛选 limit=1 最多实例化 2 条记录。保留 main 的 ICS 来源校验与非时段提案列表修复。

实际 SQLite 验证：新增 20 个边界用例通过；迁移/业务/审批/来源综合回归 91 项通过。保留旧数据库升级，不重置；未宣称真实提供方、发送或 PostgreSQL 行锁验收。随后组合 B 的迁移分支。

## PR31 独立合同修复 — 2026-10-17

最新 d9e1fe7 已通过适配流式假传输的原来源/集合类型/零预算/instant 时间依据探针。额外跨合同检查仍发现：规范 ChangeProposal 的输出（即使 new_work_order=null）都会被公共 AI schema 拒绝。现为独立维护的 AI schema 0.1.1 增加可选、可空的新工单建议，wire schema_version 保持 0.1.0，旧样例兼容。matched 提议不能携带新建建议，禁止执行字段。真实模型开关仍关闭；不表示已经启用或通过供应商验收。

## B/C 组合修复验证 — 2026-10-17

保留两条 0018 迁移历史，在 0019_action_send_link 后新增空操作 merge revision 0020_business_model_heads。worker 同时保留 C 每条消息的归单与 B 调用后的来源/版本校验。补旧缓存/正文关联回归，边界用例共 22 项。最后隔离 Linux/PostgreSQL 全套 **957 通过 / 1 跳过**，覆盖费用、排期、关联三条父版本升级。新 PostgreSQL Alembic upgrade/check：唯一 head、无结构漂移。前端 **143 通过**、TypeScript/Vite、生成合同、后端全量 Ruff/格式（121 文件）通过。跨账号/占键测试没有联系提供方。本 PR 模型开关仍关闭，不宣称真实手机或模型验收。


## 真实供应商、媒体与受限草稿 — 2026-10-17（B 侧，issue #29 第 3–6 项）

独立复核 PR #34 `reviewed_llm`（issue #29 中 B 的第 1 项）：付费调用确实移出了业务事务 —— `worker.py` 在持锁块内分配并持久化 `job.model_request_id`，随后在无 session 的情况下执行 `provider().propose(request)`，回写前重新取锁，并在授权、租约、来源 revision、上下文、候选工单或控制版本变化时拒绝。子进程有 20 秒单一时限（`subprocess.run` TimeoutExpired → kill + wait）、单次请求（`_MAX_RETRIES = 0`）、2 MiB 输入输出上限，以及 `request_id` / `conversation_id` / `base_context_version` 的身份校验；其余情况一律为 `llm:result-unknown` 且不再重投。`configured_for_live()` 向 `_refusal_reason(None)` 传 None 是安全的，因为该方法只读配置。在临时工作树中实跑 PR head 的 `test_reviewed_product.py`：**27 通过**。两条非阻塞观察：超时依赖 `communicate()` 的 kill + wait（没有进程组级 kill）；子进程输出超限会归到通用的 `llm:result-unknown:process`。

**真实质量套件（第 3 项）。** `contracts/evaluation/live_quality.json` 新增八个目标场景 —— 有/无时间依据的相对日期、部分回复、两个在办工单、首次下单、含糊回复、指令注入、过期来源 revision；`scripts/run_evaluation.py --open-seam` 可用真实供应商运行（未设 `GIGMATE_LLM_LIVE=1` 时拒绝，默认路径不花钱）。最后一次真实运行 **8 通过 / 0 失败**。它暴露了一个真实缺陷：供应商把错误标识回写到 `sources[].message_id`（实测每次都写成工单 id），八条里四条以 `llm:response-provenance-failed:source-message-id` 被拒。由于一次请求只携带一条消息及其 revision，服务端改为自己写入来源（`_provenance_problem` 重绑定、在 trace 上记录 `llm:source-rebound`，来源为空仍拒绝），prompt 升到 1.3.0 要求逐字复制标识；新单建议字段同样重绑定。更早一次运行中，模型在注入载荷下提出了地址变更（`proposed`，从未 `confirmed`）—— 这作为真实失效模式记录而非掩盖：契约阻止它变成业务状态，但套件需要重跑。

**真实媒体（第 4 项）。** 接缝开关改为配置所有：`GIGMATE_MEDIA_ENABLED=1` 取代硬编码的 `False`，且只是第一道门 —— 之后仍有 live 开关、密钥、`GIGMATE_MEDIA_MODALITIES` 与 `GIGMATE_MEDIA_VISION_VENDORS`，因此打开接缝本身不授权任何能力（由 `test_media_live_seam.py` 9 条钉住）。一次真实端到端 OCR 对合成图片返回 `segments: ["TUE 3PM"]`、`coverage: partial`、`model_version: deepseek:deepseek-chat`、prompt 1.1.0；一次真实文本附件返回原文与两条合理的 `unresolved_questions`。首个真实响应还暴露第二个缺陷：供应商会输出契约禁止的键（`segments[].index`），在 `extra=forbid` 下导致整条提案失败，现在未知段键在服务端丢弃而不被采信。本构建没有语音供应商：`asr` 在未显式设置 `GIGMATE_MEDIA_AUDIO_VENDOR` 时以 `MEDIA_AUDIO_VENDOR_REQUIRED` 拒绝，填 deepseek 也明确拒绝，不会把对话密钥发到默认 ASR 端点。

**依据人工核对（B/C）。** `work_evidence.attach` 现在还拒绝已禁用连接（`CONSENT_REVOKED`）、已过期字节（`MEDIA_SOURCE_EXPIRED`）与已取消/失败的媒体作业（`MEDIA_RESULT_STOPPED`），迟到结果因此无法复活已被停止或撤权终结的内容（10 条依据用例通过）。

**受限 Agent 草稿（B 第 6 项）。** `gigmate.agent_drafts` 与迁移 `0023_agent_drafts` 提供追问/润色草稿，只有文本：正文来自提取接缝已在自身闸门下产出的提案，或来自商户自己的输入 —— 没有自由问答通道 —— 并受每日上限、TTL（读取时显示 `expired`）、撤销、可选安静时段与一次消费约束。消费只返回文本并标记已用；不发送、不确认字段、不授予执行权（载荷里 `execution_authority: false`）。7 条用例通过。

**运维配置自检。** `scripts/check_model_config.py` 报告本机私密配置是否完整（供应商、模型、live 开关、价格、预算、token 上限、时间依据、媒体闸门），只打印存在性、绝不回显密钥，并声明"配置完整"不等同于供应商、价格或真实验收。

**本批实际证据：** 后端全套（SQLite）**998 通过 / 25 跳过 / 12 失败**，12 项失败是原生 macOS 既有的 `MEDIA_PDF_LIMIT_UNAVAILABLE`（PDF 隔离路径仅 Linux）；Ruff 检查/格式通过；`export_contracts.py` 一致；临时 SQLite 上 Alembic 到 head `0023_agent_drafts` 无漂移。真实调用使用运营方自己的 key，密钥只放在被 Git 忽略的本地 `.env`，从未提交。

**如实记录未做之事：** 未配置语音/ASR 供应商，因此没有真实转写；没有对真实供应商端到端处理 PDF（原生 macOS 上本地解析器按设计拒绝）；真实客户扫描件的 OCR 准确率、真实图片下的注入防护、供应商限流、长期成本与 PostgreSQL 行锁仍未验证；真实质量套件是 8 条合成用例，不构成生产准确率结论。


## 私密配置与剩余媒体接缝 — 2026-10-17（issue #29 第 2、4 项）

**凭据现在可以用文件配置。** `gigmate.secrets` 优先解析 `GIGMATE_LLM_API_KEY_FILE` / `GIGMATE_MEDIA_API_KEY_FILE`（或等价的 secret 挂载），因为值会泄漏到服务器上的 `docker inspect`、进程列表与 shell 历史。文件被指定但不可读时抛 `SecretUnreadable`，而不是退化成"未配置"，运维因此不会看到一个看似正常、实则每次调用都被拒的部署。本地开发仍可用值。`scripts/check_model_config.py` 与 `scripts/smoke_deepseek.py` 走同一个加载器（只报存在性，绝不打印）。

**文件形式确实可用的证据：** 以 `GIGMATE_LLM_API_KEY_FILE` 指向 600 权限文件、值变量清空后重跑真实质量套件 —— **7 通过 / 1 失败**（真实供应商），说明私密配置链路能到达供应商，唯一失败是供应商波动而非配置问题。

**供应商选择已作为决策记录。** ADR 0008（`docs/en/adr/0008-vendor-selection-and-private-configuration.md`，中文版在 `docs/zh/`）记录：文字与视觉用 DeepSeek `deepseek-chat`（视觉仍需 `GIGMATE_MEDIA_VISION_VENDORS=deepseek`，因为图像探测只是账号路由层面的观察）；**音频没有供应商** —— ASR 需要自己的 OpenAI 兼容端点，DeepSeek 用于音频被明确拒绝，对话密钥因此不会发到默认 ASR 端点；并给出九步启用清单，最后一步是 `scripts/check_model_config.py`。

**对真实供应商的 PDF。** `scripts/media_pdf_live_check.py` 生成一页合成 PDF，一次跑完解析器与供应商。解析器沙箱仅 Linux（`media/pdf_child.py` 使用 macOS 无法提供的资源限制），这也是本地 12 项 `MEDIA_PDF_LIMIT_UNAVAILABLE` 按设计失败的原因；脚本会打印该平台限制而不是假装成功。在 Linux 容器（`python:3.12-slim` + `scripts/media_pdf_live_check.py`）中，真实运行返回 `parser_pages: ["Deliver the parcel by TUE 3PM."]`、`segments: ["Deliver the parcel by TUE 3PM."]`、`coverage: partial`、`model_version: deepseek:deepseek-chat`、`prompt_version: 1.0.0`：真实 PDF 确实经过解析器与供应商，并按页返回可追溯的片段。

**仍属运营动作而非代码：** 生产凭据尚未部署；真实价格／预算／token 上限须由维护者按供应商公布价格填写并复查（清单已写明）。未采购音频供应商，因此没有真实转写。issue #29 第 2、4 项在 issue 本体中因此仍保持未勾选。


## 平台与数据库验证，以及音频问题 — 2026-10-17

**Linux 全套：1031 通过 / 12 跳过 / 0 失败。** 在 `python:3.12-slim` 容器中对同一份代码运行。这解答了原生 macOS 上 12 项 `MEDIA_PDF_LIMIT_UNAVAILABLE` 失败留下的疑问：它们是 PDF 隔离沙箱的平台限制（`media/pdf_child.py` 使用 macOS 无法提供的资源限制），不是缺陷 —— 同样的用例在 Linux 上通过。

**PostgreSQL。** 套件也在真实 PostgreSQL 16 容器上运行（`TEST_DATABASE_URL` / `DATABASE_URL`），这正是行锁测试所需。它这次查出一个真实缺陷：`test_agent_drafts.py` 插入 `Proposal` 时用了随机 `event_id`，SQLite 接受而 PostgreSQL 因 `inbox` 外键拒绝；夹具改为先创建事件行。PostgreSQL 结果在运行结束后记录于下。

**音频已确认为该供应商不提供，而不只是未配置。** 两次探测用运营方 key 向 `https://api.deepseek.com/v1/audio/transcriptions` 与 `https://api.deepseek.com/audio/transcriptions` 提交合成 WAV，均返回 HTTP 404。DeepSeek 没有转写端点，因此 ASR 不可能通过"指向对话供应商"来启用 —— 它确实需要另一份凭据，代码在提供之前继续保持拒绝（`MEDIA_AUDIO_VENDOR_REQUIRED`）。

**迁移编号。** `0021_work_order_evidence` 改号为 `0022_work_order_evidence`，`0022_agent_drafts` 改为 `0023_agent_drafts`，本分支不再占用 PR #34 用于 `0021_reviewed_product` 的 `0021` 前缀。链条在临时库上仍可干净升级（head `0023_agent_drafts`），迁移套件通过（21 项）。#34 合入后需要一条 merge revision 合并两个 head —— 与本仓库 `0020_business_model_heads` 的既有做法一致。
