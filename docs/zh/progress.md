# 已完成工作与验证记录

## 接入评审修复 — 2026-10-09

Andy_WAHA_upgrade 已准备未提交修复：配置失效时可缩减授权，多窗口刷新保留有效候选 ID 与原到期时间。新增/重新授权仍校验配置，归属、CSRF 和版本检查保留。控制针对性测试 **27 通过/1 项 PG 专用跳过**，Ruff 和空白检查通过。下游 Andy_WAHA_message_sync 同样修复并验证同步取消/禁止读取区间，**347 项 PG 配置测试**和 **10 个隔离 HTTP 检查点**通过；这是下游证据，不是旧分支全套重跑。无接口/迁移变化、真实授权变更、提交、推送或 PR 更新。

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
