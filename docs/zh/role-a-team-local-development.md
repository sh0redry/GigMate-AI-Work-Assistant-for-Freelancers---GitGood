# 团队本地 WAHA 联调与后续开发框架

更新：2026-10-06。[英文对应](../en/role-a-team-local-development.md)，[当前能力](role-a-waha-handoff.md)。本批提供开发工具，不实现生产接入、AI 或发送；Cloud API 不纳入计划。

## 环境归属

每位组员使用自己的机器/克隆、自己控制的测试号码和双方同意的测试聊天，不复制 Andy 的配置、二维码、会话或数据库。GigMate 本地开发登录 `merchant` / `demo-only-change-me` 与手机 WhatsApp 是两个身份，扫码不等于浏览器登录；公开开发凭据仅限本机，不是生产鉴权。WAHA 是非官方连接，使用非关键测试号码。

每台机器支持一个安装：固定 `gigmate-waha-a02` 项目、18700/18701/18702 端口，以及独立 `gigmate-waha-team` PostgreSQL 17.9、54349 端口。配置/绑定/会话卷属于该开发者。同机器第二份克隆不会仅因目录不同就隔离：init 拒绝已有资源，up 要求原工作区配置；不同机器可以使用相同名字和端口。未实现同机多实例。

## 全新克隆，用自己的账号启动

自动测试的模块路径由 apps/backend/pyproject.toml 明确包含后端 src 和仓库根目录，pytest 与 python -m pytest 均可导入共享 scripts 工具，不依赖某一种启动入口碰巧加入根目录。

安装 Python 3.12.10 与 Docker Desktop/Linux 引擎，启动 Docker，在仓库根目录执行：

### macOS（Intel 或 Apple Silicon）

安装 Python 3.12 和对应芯片的 Docker Desktop。主机工具是 Python 脚本，不是 Windows 可执行程序：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r apps/backend/requirements.lock
.venv/bin/python scripts/waha_team.py init
.venv/bin/python scripts/waha_team.py up
.venv/bin/python scripts/waha_team.py doctor
.venv/bin/python scripts/waha_team.py run local create
.venv/bin/python scripts/waha_team.py run local status
.venv/bin/python scripts/waha_team.py run local qr
open local-data/waha-a02/qr.png
```

后续命令把 `.venv\Scripts\python.exe` 换成 `.venv/bin/python`，不需要 PowerShell。每台机器重建环境，不复制 Windows .venv、私有 profile/配置或 Docker 会话；已有安装使用原流程，不重复 init。

team up/stop 读取 Docker 引擎架构，不按主机 Python 架构猜测（Python 可能运行在 Rosetta 下）。arm64/aarch64 自动追加 `infra/waha-arm64.compose.yaml`，固定原生 arm-2026.9.1、摘要 b4216daddb7d5c1eb3ab99e608b76a005ec7523e766f923939d229718df4aafb，继续 WEBJS；x86 保留此前已测镜像。手动 Compose 在 ARM 也须追加该覆盖文件，并保留正确数据库环境。不能随意换未固定的 :arm 或引擎解决 manifest 报错。已核对镜像架构及配置，尚未在实体 Mac 上验证账号扫码。

Docker 不等于自动 CPU 转换：原固定镜像索引只有 linux/amd64（另一个是证明材料），Apple Silicon 缺少 ARM 覆盖/模拟时可能拉取失败。WAHA 提供独立 [ARM 镜像](https://waha.devlike.pro/docs/how-to/engines/)，[Docker 多平台说明](https://docs.docker.com/build/building/multi-platform/)区分原生与模拟。后端/配置助手 Python 镜像支持多平台。本地路径要求 Docker Desktop，其他 Docker 引擎的宿主网络不默认算已验证。

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r apps/backend/requirements.lock
.venv\Scripts\python.exe scripts/waha_team.py init
.venv\Scripts\python.exe scripts/waha_team.py up
.venv\Scripts\python.exe scripts/waha_team.py doctor
.venv\Scripts\python.exe scripts/waha_team.py run local create
.venv\Scripts\python.exe scripts/waha_team.py run local status
.venv\Scripts\python.exe scripts/waha_team.py run local qr
```

本地打开忽略的 `local-data/waha-a02/qr.png`，在手机关联设备中扫码。只有 SCAN_QR_CODE 时取二维码；WORKING 时无需重复扫码。create 仅用于新 session；超时后先查状态，不盲目重试供应商写操作。FAILED/STOPPED 有显式 local restart。up 不自动创建/重启供应商 session。

init 生成私有密钥与绑定工作区的 team 配置；up 升级迁移、仅创建本地应用账号、以空白名单注册连接并启动 API/Worker/监控，不种 Replay 工单、不发送消息。每次 waha_team 调用自动读取自己的数据库配置，新终端无需重复 export。若已有不同 DATABASE_URL，会报 DATABASE_ENV_CONFLICT；团队模式先移除该终端旧变量。已有旧安装不要运行 init/up：按恢复文档设置原 DATABASE_URL；doctor/checkpoint/verify/run 可使用这个显式本地 PostgreSQL。

WORKING 后只选择获同意的测试聊天：

```powershell
.venv\Scripts\python.exe scripts/waha_team.py run local select-chats --limit 20
.venv\Scripts\python.exe scripts/waha_team.py run ingress provision
.venv\Scripts\python.exe scripts/waha_team.py run ingress sync-container-config
.venv\Scripts\python.exe scripts/waha_team.py up
.venv\Scripts\python.exe scripts/waha_team.py run ingress configure-live
.venv\Scripts\python.exe scripts/waha_team.py run ingress diagnose
.venv\Scripts\python.exe scripts/waha_team.py run smoke http
```

聊天选择的名称/真实 ID 仅在自己的终端显示，不分享输出。provision 更新数据库权威白名单并启用连接，只在明确授权时执行。up 复用已有绑定，保留暂停和白名单状态；同步主机私有配置并重建服务。configure-live 从易失探测切换持久回调，可能重启 provider，之后查状态。单改本地 consent 标记不能暂停权威连接，暂停用 `run ingress pause`；移除授权先编辑私有白名单，再 provision。尚无产品同意页面。

## 自助真实验收

```powershell
.venv\Scripts\python.exe scripts/waha_team.py checkpoint
# 在同一获授权聊天：新发一条文字，编辑一次，再为所有人删除。
# 每次 run ingress status，等待 Worker 完成。
.venv\Scripts\python.exe scripts/waha_team.py verify
.venv\Scripts\python.exe scripts/waha_team.py run smoke http
```

要求 mutation_sequence_verified=true；序列不完整返回退出码 2，不以成功退出冒充验收通过。工具限定账号/连接，核对新建/编辑/撤回顺序、修订 1/2/3、同一内部标识、完整供应商标识一致、最终持久撤回和任务完成。ACK/会话通知可增加 accepted，却不创建正文任务。工具不返回正文/聊天/provider ID；sample_group 只是临时编号。缺少事件、身份不匹配、任务未完成或没撤回都不能通过。起点后超过 100 事件拒绝验证，不静默截断；重新 checkpoint，用新文字测试。verify 只读数据库；checkpoint 只写忽略的元数据，不清除故障，不证明 AI/业务确认/发送完成。

再次 up 后检查 status/verify，确认重启持久性。用获同意参与者的未选择聊天测试：该聊天不应推进正文同步，拒绝指标可以上升，不把被拒绝正文存为证据。pause 后确认不再接收新业务事件。上述人工检查使用组员真实账号；保留合成自动测试只为重复异常回归，不要求组员通过 Replay 做日常联调。

安全停止用 `waha_team.py stop`，仅停止团队服务并保留卷。不要例行 down -v 或删除会话。up 失败可能已有部分步骤成功，先 doctor 定位再重试；不会把失败报告为启动成功。

## 常见问题

| 结果 | 处理 |
| --- | --- |
| EXISTING_SETUP_PRESERVED / EXISTING_DOCKER_SETUP | 旧安装未改，回原克隆/恢复文档，不删卷强行 init。 |
| LOCAL_PORT_IN_USE | 查明占用者，仅停自己的冲突服务，或用独立机器。 |
| TEAM_PROFILE_WORKSPACE_MISMATCH | 回原工作区；移动/复制安装是显式迁移，不自动认领。 |
| Docker 不可用 | 启动 Desktop Linux 引擎，检查 docker version。 |
| 数据库不可用/迁移缺失 | 团队模式 up；旧安装核对原 DATABASE_URL 和迁移 head。 |
| 绑定/数据库不匹配 | 查归属及数据库选择，不重新注册其他人的 session。 |
| API 不可用/绑定错误 | 启动并同步私有配置；绑定不可读/无效时健康检查会拒绝。 |
| pipeline false / review true | 分组件 diagnose；核对标记与就绪独立，恢复不自动确认缺口。 |

## 后续开发的具体入口

运行服务使用构建镜像，不自动挂载主机代码。修改后端后 team up 重建/重新创建，再 diagnose/smoke 并用新消息验收，不能拿旧 completed 任务代替。前端开发先在 apps/web 执行 npm ci，检查 check:api/format:check/build；现可使用[归属隔离的 setup/二维码/聊天接口](role-a-setup-api-acceptance.md)，操作对象由本地操作者预先准备，页面仍由 D 开发。各组员从约定的 main 提交建立功能分支，与 A/C 协调共享契约；工具不自动合并或发送。

入口链路：`api.waha_events` → HMAC → `waha_ingress.receive` → `messaging.ingest` → Inbox/MessageRow/ConversationRow/Job → `worker.run_once`。Pydantic/领域/OpenAPI 从源生成，事件 schema 独立版本。归属来自服务端绑定，不接受 provider 自报账号；不能跳过入口直接调用模型。

| 角色 | 接入位置与后续批次 | 必须保留的规则 |
| --- | --- | --- |
| B | live WAHA Job 现已路由到 `gigmate.extraction.provider()`，落库 `proposals` + `model_call_traces`；未知内容以 `EXTRACTION_NEEDS_REVIEW` 完成，取代原先的 `LIVE_EXTRACTION_PENDING`。范围、合约和评测见 [Role B 抽取子系统](role-b-extraction.md)。沿用 Inbox 标准事件、`MessageRow` 来源修订和 `ConversationRow.context_version`；`gigmate.understanding.extract` 仍是 Replay 入口。 | 多工单归属歧义需复核；仅当前上下文/来源可写提议；模型密钥留服务端。旧 completed 任务不会自动重新抽取，重处理需显式幂等设计。真实模型接入是后续单独授权批次。 |
| C | messaging.ingest 推进上下文并使旧提议失效，workorders.confirm 管现有内部确认。先设计 actions/outbox/执行器/未知结果核对，再要求 WAHA 发送。 | 客户提议/确认/商户批准分开；批准快照、版本、有效期复核；未知结果不盲重发，当前没有外部 adapter。 |
| D | connectors/recovery-issues，加本地 setup/二维码/不透明聊天/控制操作及 api.d.ts 类型。Vite 当前代理 Replay API，切换 ingress 明确验证 origin/鉴权。 | 就绪/核对/操作结果分开展示；轮询 202 意图，保留请求键、刷新 control_version，按接入协议调用，不直接管理 WAHA。 |
| E | team checkpoint/verify、smoke_waha_ingress、check_waha_recovery --run，记录干净克隆 SHA、版本、实际输出与缺陷。 | 独立评审；不提交真实正文/密钥/二维码，SQLite 不证明 PG 锁；Internet/注销/遗漏历史恢复另验。 |

每个已授权里程碑整批完成实现、迁移/契约、测试和双语文档后统一验收；不改共享旧迁移、不手改生成文件。合 main 前独立组员仍需走一次干净环境自己的账号流程，开发者自测不能替代。Cloud API 排除，本页不授权发送、通用 AI 或生产部署。
