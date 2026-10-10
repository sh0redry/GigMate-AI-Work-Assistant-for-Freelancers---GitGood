# 已完成工作与验证记录

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
