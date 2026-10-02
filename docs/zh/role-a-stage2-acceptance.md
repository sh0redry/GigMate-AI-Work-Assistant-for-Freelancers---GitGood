# A-02 本地连接工具与统一验收记录

日期：2026-10-02。分支：Andy_WAHA。按用户要求，第一阶段已提交为 `908855f`。本批实现[第二阶段路线](role-a-development-roadmap.md)中的独立本地能力验证工具；授权账号扫码及基本真实通知/历史检查现已通过。[英文对应记录](../en/role-a-stage2-acceptance.md)。

用户已授权使用自己的测试账号，并自行扫码。本批只新增文件或更新本轮新建的 A 职责文档，没有修改共享 API、接入服务、数据库、worker、契约、迁移、依赖、前端及公共进度文件。因此进度和证据记录在本文件。用户已要求提交第二阶段，没有授权 push。

## 本批完成内容

| 文件 | 用途 |
| --- | --- |
| [waha_client.py](../../apps/backend/src/gigmate/waha_client.py) | 本地服务端客户端：创建连接、读取安全状态、获取 PNG 二维码、统计白名单聊天的有限历史记录 |
| [waha_probe.py](../../apps/backend/src/gigmate/waha_probe.py) | 独立验证服务：原始请求 HMAC 鉴权、授权/会话/聊天检查、有限内存统计、重复和冲突检测 |
| [waha_local.py](../../scripts/waha_local.py) | 私有配置初始化和操作命令，不输出密钥及二维码内容 |
| [smoke_waha_local.py](../../scripts/smoke_waha_local.py) | 用合成数据执行九项真实 HTTP 冒烟检查 |
| [test_waha_local.py](../../apps/backend/tests/test_waha_local.py) | 45 项测试，覆盖鉴权、结构、隔离、大小限制、连接/二维码/历史及请求结果不确定 |
| [waha.compose.yaml](../../infra/waha.compose.yaml) / [Dockerfile](../../infra/waha-probe.Dockerfile) | 独立本地部署，只绑定本机端口，使用私有 Docker 会话卷 |

固定 WAHA Core `2026.9.1`、WEBJS 引擎，镜像摘要为 `sha256:41283bd89922ec3f722e5a772b844c451634d4aa72e9c34043c3480184f970fe`。验证服务沿用后端锁定依赖，不改变产品 API 或生成的 OpenAPI。

## 工作流程与职责边界

本地命令读取忽略目录中的密钥，访问 `127.0.0.1:18700` 的 WAHA。WAHA 在 Docker 内部网络向验证服务发送签名通知；验证服务端口 `18701` 也只绑定本机。二维码保存在本机供用户打开，扫码会在用户 WhatsApp 中授权一个关联设备。

验证服务先对原始字节做签名校验，再解析 JSON、匹配配置的单一会话、检查聊天白名单，然后才记录观察结果。不保存聊天正文、消息标识或标准化业务事件。最近 100 个事件身份只保留带密钥的哈希；计数和字段存在标记仅在内存中，重启即丢失。HTTP 200 明确返回 `durable_acceptance: false` 和 `X-GigMate-Probe-Only: true`，表示观察成功，不能当作业务事件已可靠入库。WAHA 文档的正文签名没有包含时间戳请求头，所以不能把时间戳头当成已鉴权的新鲜度证据；内存去重也不是持久防重放。

默认聊天白名单为空：可以观察连接状态通知，所有业务聊天通知均拒绝。历史查询必须显式允许该聊天且连接状态为 WORKING，禁用媒体下载，只输出条数，不输出或保存正文。不保证获取完整旧历史。本地 account UUID 只是测试绑定，不代表产品用户登录、多用户归属校验。

本批没有实现发送、AI、审批、业务写入、持久队列或数据库连接状态。第一阶段仍是合成适配器；收到一次真实状态通知不能证明编辑、撤回、ACK 身份及全部消息结构兼容。后续真实业务接入和第三阶段持久化需要另行授权修改共享模块。

## Windows 启动与扫码

在仓库根目录执行，先启动 Docker Desktop 的 Linux 引擎：

```powershell
# 仅首次配置；已有配置时拒绝覆盖密钥：
.venv\Scripts\python.exe scripts/waha_local.py init
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml up --build -d --wait
# 仅 default 会话不存在时创建；失败后先查询状态，勿盲目重复：
.venv\Scripts\python.exe scripts/waha_local.py create
.venv\Scripts\python.exe scripts/waha_local.py status
# 状态为 SCAN_QR_CODE 时获取或刷新：
.venv\Scripts\python.exe scripts/waha_local.py qr
```

当前机器已经初始化并创建会话，无需再次 init/create。打开 `local-data/waha-a02/qr.png`，在手机 WhatsApp 中选择“关联设备 → 关联设备”扫码。如果过期，重新执行 qr 命令并重新打开图片。不要把二维码、凭据、会话文件或聊天内容发到对话里或提交进 Git。没有开放控制台页面；手机可能要求额外身份验证。

扫码后执行：

```powershell
.venv\Scripts\python.exe scripts/waha_local.py status
.venv\Scripts\python.exe scripts/waha_local.py observations
.venv\Scripts\python.exe scripts/smoke_waha_local.py
```

状态应为 `WORKING`、`connected: true`，容器健康或 API 能访问不代表 WhatsApp 已连接。状态输出不包含个人资料、配置或密钥；观察输出只有安全计数和字段存在标记。

如需验证一个明确授权的测试聊天，优先使用下方本地选择工具。也可仅修改本地被忽略的 `local-data/waha-a02/config.json`：把已知的 provider chat identifier 加入 `allowlisted_chats`，不要采集无关聊天历史。重启验证服务加载配置后查询：

```powershell
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml restart probe
.venv\Scripts\python.exe scripts/waha_local.py history --chat '<已授权的provider聊天标识>' --limit 10 --offset 0
```

使用对方同意的测试聊天，从手机发送、编辑、撤回合成文本，再看 observations。不要把真实通知复制进测试夹具。观察服务只显示结构标记；精确身份与版本映射仍需后续私有验证流程。删除白名单项并重启验证服务，可撤销该聊天的本地观察权限。

## 运维和故障处理

### 在本地选择真实聊天 ID

用户已明确要求发现近期聊天并自行选择，因此本地元数据发现与业务内容接入分别授权。执行：

```powershell
.venv\Scripts\python.exe scripts/waha_local.py select-chats --limit 20
```

终端会按序号显示近期一对一/群组聊天的名称和真实 ID。输入 `1,3` 将这两行加入白名单，直接回车取消。工具保留已有白名单和其他配置，以原子方式保存；检测到期间配置发生变化会拒绝覆盖。不自动重启验证服务，保存后执行终端提示的 Compose restart 命令。下一页使用 `--limit 20 --offset 20`；每次都是实时查询，不是冻结的完整快照。只选择已授权测试的聊天，不要把含真实名称和 ID 的终端输出发给模型或提交进仓库。

[WAHA 聊天列表接口](https://waha.devlike.pro/docs/how-to/chats/)可能同时返回消息字段；客户端立即丢弃这些字段，只向本地选择界面提供 ID 和名称，不保存或记录原始响应。发现流程不调用消息历史接口。固定版本实际接受的排序字段为 `conversationTimestamp`，不同于当前在线文档的 `messageTimestamp`；WEBJS 的 ID 是包含 `_serialized` 标准字符串的对象。这两点已对运行中的服务核实。工具直接使用真实标识，不根据手机号猜测或转换，保留 @lid；过滤广播和状态项。

补充证据：账号目前 WORKING，真实有限列表查询返回 **20 个可选聊天**；代理验证只输出条数，没有输出真实名称或 ID，也没有替用户选择白名单。**55 项专项测试通过**，覆盖元数据过滤、WEBJS ID 提取、无效/重复 ID、选择输入及取消、原子合并、配置变更检测；Ruff/格式和基线检查通过。聊天事件及历史能力仍待用户选择后验收。

`local-data/waha-a02/config.json`、`.env`、`qr.png` 已被 Git 忽略，配置包含本地 API 和 HMAC 密钥。Docker 卷 `gigmate-waha-a02_waha_sessions` 包含关联设备凭据，必须保密。已禁用 dashboard、Swagger、控制台二维码、apps 和媒体下载；端口仅绑定 localhost。该配置适用于个人开发机，不是多用户部署方案。

初次使用 Windows 绑定目录保存 Chromium 配置，发生浏览器/会话锁错误。改为 Docker Linux 命名卷后恢复，进入 SCAN_QR_CODE。旧忽略目录保留，没有删除用户会话文件；命名卷避免此宿主机文件系统锁问题。

执行 `docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml down` 可停止工具并保留会话卷，不要随意加 `-v`。要解除测试设备授权，请在 WhatsApp 的关联设备中移除。保存的二维码会过期，状态需要扫码时再刷新。创建超时返回 `WAHA_RESULT_UNKNOWN`，应先查状态，客户端不会自动重复写请求；409 可能表示会话已经存在。重启保留 provider 会话文件，但扫码后的已连接重启恢复尚未实测。

## 已验证与待验收

恢复补充（2026-10-02）：会话随后变为 FAILED，WAHA 日志报告 WhatsApp Web 页面已关闭；页面关闭的底层原因尚未确定。新增 `restart` 命令，在查询到 FAILED 或 STOPPED 后调用[官方会话重启接口](https://waha.devlike.pro/docs/how-to/sessions/)，保留会话文件，不退出登录、不删除或重新创建会话。连接正常时拒绝恢复操作，结果不确定时不自动重试。专项测试现为 **48 项通过**，新增失败恢复、正常连接保护和超时不重复请求测试。二维码返回 WAHA_NOT_WAITING_FOR_QR 时按如下顺序处理：

```powershell
.venv\Scripts\python.exe scripts/waha_local.py status
# 仅 FAILED / STOPPED 时执行：
.venv\Scripts\python.exe scripts/waha_local.py restart
# 等 STARTING 变为 SCAN_QR_CODE 后获取：
.venv\Scripts\python.exe scripts/waha_local.py status
.venv\Scripts\python.exe scripts/waha_local.py qr
```

若状态已是 WORKING，说明配对完成，不需要二维码。若恢复返回 WAHA_RESULT_UNKNOWN，先查状态，再决定是否请求。不要重复创建现有会话或删除数据卷。下方保留原批次的历史验证证据。

- Docker Engine 28.3.3：固定镜像拉取成功、两个服务健康；创建成功，达到 SCAN_QR_CODE，PNG 二维码获取成功。真实 WAHA 签名状态通知已抵达验证服务。
- 九项真实 HTTP 检查通过：WAHA 缺少密钥被拒绝；验证服务健康接口明确非持久模式；统计接口要求授权；错误 HMAC 被拒绝；签名合成事件被接受；识别重复；同一身份内容变化被拒绝；错误会话被拒绝；非白名单聊天被拒绝。
- 完整后端测试：SQLite 下 **157 passed、1 skipped**，其中本批新增 45 项。跳过 PostgreSQL 并发认领测试，不能证明数据库行锁；保留一个现有 Starlette/httpx 弃用警告。
- Ruff 检查和格式检查、生成契约漂移检查、仓库基线检查通过。
- 已确认配置、环境密钥和二维码被 Git 忽略。没有共享迁移、schema、产品 API 或前端变化，因此迁移和前端检查不适用于本批。

## 最终真实验证证据与下一批目标

用户提供的安全命令输出已确认：WEBJS 为 WORKING/connected；白名单聊天历史查询返回四条记录，complete_history 为 false；收到 message.created、带撤回目标字段的 message.revoked、带编辑目标字段的 message.edited。最终观察计数为六，该内存统计窗口中重复和身份冲突均为零。这些证明能力观察成功，不能证明持久入库、原消息身份映射或版本正确。本记录不保存实际聊天 ID、名称或正文；普通消息含 ACK 字段不能证明独立 message.ack 事件通过。

提交前最终验证：SQLite 后端 **167 passed、1 skipped**；Ruff 检查/格式、生成契约检查、基线和九项合成数据真实 HTTP 冒烟检查通过。PostgreSQL 行锁测试仍跳过，现有弃用警告保留。本独立批次不涉及迁移/前端检查。

下一阶段组合完成 A-02 剩余可靠接入与 A-03 核心监控：持久保存可信账号/session/聊天/消息映射及修订版本；把鉴权和白名单后的标准事件接入事务 Inbox/Job；重启后仍能去重、识别冲突并正确处理编辑/撤回；持久连接状态并处理顺序、新鲜度和账号隔离查询；在 PostgreSQL 上验证数据库故障、提交后响应丢失、worker 崩溃和重连。独立 ACK、provider 身份/版本兼容、断线重连及已连接重启仍待验证。按用户文件限制，修改共享 messaging/db/API/contracts/worker 前必须取得明确许可；新增迁移使用独立版本。AI 和发送不在本阶段范围内。继续整批完成相关开发和检查后，由 E 统一验收。
