# 合并 #4、#5、#9 后的 WAHA 与提取模块统一联调验收

2026-10-08 · Andy_WAHA_upgrade · main d31aa7d 已通过 20611ce 合入。[English](../en/role-a-integration-acceptance.md)。

2026-10-09 更新：main d6e70eb（PR #9）已通过 f166084 合入；此前整批成果已提交检查点 **0e22486**。后续批次汇合迁移并修复 Windows 测试兼容，不增加真实模型。

这一批把 D 的工作台接到 A 的持久后端，并保留 C 的任务标题功能。通用 AI 提取、对外发送、完整历史导入和生产接入尚未实现；Cloud API 不在计划中。旧验收文档保留当时证据，当前联调以本文为准。

## 统一后的工作方式

页面通过已登录的 `/api/v1` 接口完成状态查看、连接/恢复/发现聊天、临时二维码、聊天授权、暂停/恢复和未知结果核对。原先 Vite/Python 本机桥接及独立重启记录已经退役，Vite 只转发后端请求，不再需要 `GIGMATE_LOCAL_PAIRING`。密钥和 WhatsApp 原始聊天 ID 留在服务端；变更仍需登录、CSRF、归属、版本和明确授权校验。

查看状态、发现聊天使用当前控制版本，不再递增版本；连接/恢复和授权变更才推进版本。这样页面轮询不会让正在选择的聊天无故版本过期。发现/保存后重新读取 setup/chats，获得当前版本及持久授权 UUID。操作请求丢失响应时保留同一请求体、版本和请求键；正在执行或结果未知的操作阻止另一次控制操作。明确核对只读 provider，不会盲目重启。

新迁移 `0006_waha_provider_sample` 保存 provider 原始状态和采样时间，并继续保留标准连接健康状态。后台查询和已验签回调都可更新采样，旧查询不能覆盖新回调。页面分别显示 WhatsApp 是否连接、是否允许接收、采样是否过期、处理链路是否就绪。暂停隐藏二维码并拒绝接收；恢复需明确操作，并保留已有聊天选择。

停止的 WEBJS 会话可能没有 engine 字段。只有 STOPPED 且缺少该字段时，适配器额外查询 `/api/server/version`，确认固定 Core 2026.9.1/WEBJS 后才接受状态。错误引擎/版本、运行中缺少引擎仍拒绝，避免误报不兼容和随意信任未知安装。

新增 `POST /api/v1/connectors/{id}/recovery-issues/review`：提交不重复的 `issue_ids` 和 `confirmed_no_import: true`。后端一次性校验归属和是否已恢复，记录 `reviewed_no_import`，保留历史；混入未恢复项时整体失败，不部分清除。暂停期间也可以核对历史故障；该操作不会恢复接收、补拉或删除消息。

## 原有安装怎么升级

当前唯一迁移终点为 **0007_merge_waha_extraction**。A 的 `0005_waha_controls → 0006_waha_provider_sample` 与 B 的 `0005_extraction_evidence` 都从 0004 分出，新合并迁移依赖两条分支。没有改名或重写已有迁移；从任一分支 `upgrade head` 都会补齐另一分支再汇合。不要用 stamp 冒充表已升级。降级检查仅针对可丢弃测试数据库。

1. 保留私有配置、数据库和 WAHA 登录卷，不要对真实安装运行 `down -v`。团队安装使用现有 `up` 流程完成迁移和重建；旧安装需先把自己的数据库迁移到 head，再重建 API/worker/monitor，最后启动新页面。
2. 原 D 桥接的 `local-data/d01-operations/restart-{应用连接UUID}.json` 如果是 submitting/unknown，团队启动会导入为后端阻塞的未知操作，并保留、标记原记录。已有其他活动操作或证据无效时明确失败。旧安装需设置正确 DATABASE_URL，打开页面前运行 `python scripts/waha_team.py import-legacy`。命令读取本机私有 binding，不需要在页面输入原始账号标识或密钥。
3. 在 `apps/web` 设置 `GIGMATE_API_URL` 为本机 ingress API 后运行 `npm run dev`；常见地址为 `http://127.0.0.1:18702`，团队自定义端口以本机配置为准。旧桥接开关和命令不再适用。
4. 登录该安装绑定的工作台账号，先检查状态。已 WORKING 无需重新扫码；需要时本人在本机扫码。载入聊天并明确保存测试会话，联系人名称和二维码不外传。CLI provision 会从本机配置替换数据库授权，不要与页面选择随意混用。

C 的任务准备时间改为：先从 UTC 开始时刻减去实际一小时，再把同一时刻转换为当地时间用于标题。测试覆盖纽约两次夏令时切换和香港跨午夜，确保标题时间与数据库截止时刻一致。

B 的 live WAHA 消息现经默认 deterministic provider 保存 `proposals`/`model_call_traces`，仍拒绝真实通用提取：任务状态 completed、错误码 EXTRACTION_NEEDS_REVIEW，不写确认业务变更。这表示提取待复核，不是消息接入失败。旧 completed 任务不会自动重跑；编辑/撤回仍使来源和上下文过期。B 的提案证据审核页面尚待开发，连接故障审阅不代表批准提案。

Windows 提取测试改用 pytest tmp_path 管理数据库文件，并在 finally 关闭引擎，替代 SQLite 无法再次打开的未关闭 NamedTemporaryFile；临时 manifest 同样由 pytest 管理。其他平台可继续运行；这些 SQLite 夹具不证明 PostgreSQL 锁。

## 一次性验收

`python scripts/check_waha_setup.py --run --suite` 使用临时 PostgreSQL、真实 HTTP API/worker 和合成 provider，验证持久操作、重启 worker、归属/CSRF、二维码缓存、聊天选择、版本冲突和暂停/恢复，再执行 PostgreSQL 全套测试。`--frontend` 提供 18803 上的 30 分钟临时浏览器环境；其中一像素 PNG 仅测试图片传输，不能扫码登录。自动样例用于开发自检，组员真实联调仍使用自己的账号。

更新后的工具还经 HTTP 提交 HMAC 签名合成 live-origin 消息，确认接收及 worker 完成后保存待复核提案/调用证据、不写业务变更；暂停期间签名消息应拒绝且不新增证据。评估 CLI 在该临时 PostgreSQL 中执行并保存七个合成案例。迁移测试覆盖从 0004、B 已有分支、A 已有分支升级，核对原回放行、暂停连接/计数、A 采样/版本及 B 评估记录保留；设置 TEST_DATABASE_URL 时使用隔离 PostgreSQL schema，否则使用可丢弃 SQLite 文件。

隔离浏览器已检查发现聊天、授权撤销/保存、暂停/恢复、经 worker 恢复 STOPPED、待扫码图片展示及明确核对未知操作。数据库核对确认：已恢复故障被审阅，两条历史都保留，未恢复故障未被清除。前端测试覆盖原请求重试、不透明聊天标识、版本冲突、未知结果不自动重发及统一后端入口。

最终命令结果和数量见[完成记录](progress.md)。Apple Silicon 真机扫码、手机真实消息变更及 E 的独立评审仍需分别验收，自动检查不代替这些证据。

## 给组员的框架和人工步骤

A 维护接入/控制/监控；B 从已授权消息修订生成提案；C 基于出处确认内部任务/日历变更；D 使用生成的接口类型开发页面；E 独立检查权限、并发、过期上下文和未知结果。B/C 不直接调用 WAHA，不新增另一套授权来源。连接成功不代表 AI 或外发功能已经实现。

每位组员在自己的授权测试安装中一次性完成：登录并查看状态 → 需要时扫码 → 发现并保存正确测试聊天 → checkpoint → 手机上发送、编辑、为所有人撤回新文字 → verify → 撤销聊天授权并确认拒绝 → 明确重新授权 → 暂停并确认拒绝 → 恢复后发送新文字。全程检查状态新鲜度及处理链路。只审阅确实核对过的已恢复故障；需要调查缺失消息时保持未处理。自然 STOPPED/FAILED 时明确重连；结果未知时使用核对按钮。不要为了二维码证据破坏已配对会话，报告不要包含真实消息、联系人 ID、二维码或凭据。

## 自动检查后，只需人工完成这些步骤

1. **升级并启动自己的安装。** 有 team profile 的安装运行 `python scripts/waha_team.py up`，随后 doctor。Windows 的 python 使用 `.venv/Scripts/python.exe`，Mac 使用 `.venv/bin/python`。旧安装先设置自己的 DATABASE_URL/PYTHONPATH，执行 Alembic upgrade head/check、import-legacy，再沿用私有 Compose 环境和正确内部 WAHA_DATABASE_URL 重建 ingress/worker/monitor；保留数据库、配置和登录卷，不重新 init。本操作者的 DB 覆盖端口仍是 16433，新组员以自己 profile 的端口为准。
2. **打开真实页面。** 在 apps/web 把 GIGMATE_API_URL 设为实际 ingress（通常 http://127.0.0.1:18702），运行 npm run dev，打开终端打印的本机地址。Windows：`$env:GIGMATE_API_URL='http://127.0.0.1:18702'`；Mac：`GIGMATE_API_URL=http://127.0.0.1:18702 npm run dev`。登录本地工作台，分别看采样新鲜度和链路就绪。仅需要时用手机扫码，已 WORKING 不重新扫码；Apple Silicon 配对由对应组员记录。
3. **明确授权测试聊天。** 载入会话，在本机根据名称确认双方同意的测试聊天，勾选并保存。组员使用自己的号码和聊天，不分享联系人列表。
4. **验证同一条新文字的完整变化。** 回仓库根目录执行 `python scripts/waha_team.py checkpoint`。手机发送新文字，查询 `python scripts/waha_ingress.py status`；编辑同一条再查询；为所有人撤回同一条再查询。每步等 worker 完成，再执行 `python scripts/waha_team.py verify`，要求 mutation_sequence_verified=true。accepted 也可能因 ACK/状态增加，verify 才核对同一消息的 1/2/3 修订序列。真实模型未实现前，提取 needs_review 属正常预期。
5. **核验撤权与暂停。** 页面取消测试聊天并保存，再发新文字，应 CONVERSATION_NOT_ALLOWED，不能因这条消息推进正文同步。重新发现并明确恢复授权。暂停消息接收，再发新文字，应 CONSENT_REVOKED、enabled=false，不能因这条文字推进正文同步。等待有界回调重试结束后恢复，再发新文字确认接入。恢复授权/接收不保证导入期间被拒绝的消息。
6. **核验恢复与历史。** 自然断开时明确重连；结果未知时用“不重发”核对按钮。只对真正核对过的已恢复故障确认无需导入后审阅，未恢复故障保留。刷新/重新打开页面确认状态持久，暂停或退出时二维码消失。路由器断网、WhatsApp 注销和缺失正文恢复是另外的真实验收门槛，本批不为了证据破坏配对。
7. **由 E 独立复核。** 记录 SHA、系统/芯片和安全 status/verify 元数据，与 A 的自动证据分开；检查归属、过期授权/上下文、迁移保留和未知结果。不要附真实正文、联系人 ID、二维码或密钥。本人手机操作和独立同伴身份不能由 A 自动代替。

## 你当前旧 Windows 安装的准备命令

下面专用于原数据库已覆盖到 **16433** 的本机安装。组员有 team profile 的安装使用 waha_team.py up，不套用这组端口。这里密码是仓库公开的本地开发默认值，不是 WhatsApp 凭据。保留已有 database-port override、私有 .env 和登录/配置卷；升级代码不要额外运行 provision/init/configure-live，它们可能替换授权或回调。

```powershell
# 仓库根目录，先启动 Docker Desktop。
docker compose --env-file .env.example -f infra/compose.yaml -f local-data/waha-a02/database-port-override.yaml up -d --wait db
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:16433/gigmate_waha_a03'
$env:WAHA_DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@host.docker.internal:16433/gigmate_waha_a03'
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini check
.venv/Scripts/python.exe scripts/waha_team.py import-legacy
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml up --build -d --wait ingress ingress-worker ingress-monitor
.venv/Scripts/python.exe scripts/waha_team.py doctor
.venv/Scripts/python.exe scripts/waha_ingress.py status

# 另开终端，进入 apps/web：
$env:GIGMATE_API_URL = 'http://127.0.0.1:18702'
npm run dev
```

doctor 健康、status 为新鲜 connected/pipeline_ready=true 后再开始手机测试。历史故障保持待核对，检查后再审阅。自然停止或未配对时可能需要页面明确连接/核对及本人扫码。每个新终端运行 checkpoint/verify/status 前保持相同数据库环境；缺少 DATABASE_URL 是准备问题，不代表消息接入失败。
