# A-03 异常恢复与运行监控统一验收

日期：2026-10-02；基线 `83aa75e`，分支 Andy_WAHA。本批是[持久接入](role-a-stage3-acceptance.md)的已授权后续，不是 A-04 对外发送。[英文对应](../en/role-a-recovery-acceptance.md)。

## 本批完成范围

- 新增迁移 `0004_waha_recovery`：安全运行诊断表、Worker 心跳、任务完成时间/耗时及租约恢复计数；保留旧迁移，不给历史已完成任务编造耗时。
- 状态分别显示 API、WAHA、Worker、监控程序健康：healthy/unavailable/stale/unknown。`live_connected` 仍只描述 WhatsApp 会话；`pipeline_ready` 要求连接启用、连接状态新鲜且四项健康。`review_required` 独立表示尚待核对，链路恢复正常也可能仍为 true。
- 监控每 30 秒查询 API `/health` 和可信 WAHA 状态；API/WAHA/监控采样 120 秒后过期，Worker 每 10 秒写心跳，30 秒后过期。这些是本地配置窗口，不是性能或可用性保证。Worker 心跳只表示近期到达循环并成功访问数据库，不代表每个任务正常。
- 监控使用独立 Compose 网络空间，通过固定内部 `http://waha:3000` 访问 WAHA；本机配置仍限定 loopback，禁用跳转/代理，不允许任意内部地址。停止 WAHA 不再同时切断监控到 API/数据库的访问。
- 持久记录 API/WAHA 不可用、Worker/监控中断及已鉴权事件的来源/顺序冲突。恢复只填写 recovered_at，不自动清除人工核对。新表不保存正文、真实聊天/消息标识、凭据或自由文本备注。
- 已签名的业务拒绝在正文事务回滚后，通过独立事务记录账号隔离的安全错误码和计数；伪造来源不写诊断。数据库不可用时无法保存自身写失败，仍运行的监控先记住失败起点，恢复后补记不确定时段。监控也重启时可能丢失这个起点，后续可发现采样缺口；短暂、未采样的故障仍可能无法发现。
- 指标覆盖保留中的任务重试、租约恢复/过期数、最老未完成任务年龄、实际测量的终态处理耗时及接收到完成的延迟。不是终生吞吐量或 AI 准确率；无测量样本时耗时为 null，历史未知值不补成零。
- 崩溃恢复也遵守三次尝试上限；达到上限的过期租约任务转为 failed/RETRY_EXHAUSTED，不再无限认领。旧租约持有者不能提交其他 worker 的结果。真实内容仍不执行虚构抽取、不生成提议或对外执行。
- PostgreSQL 接收/诊断锁等待上限 3 秒、语句上限 5 秒；连接/连接池等待上限 5 秒。接收失败明确返回错误，不虚报持久成功。不能承诺供应商重投覆盖长时间中断。
- 开发登录/退出在成功前提交；回归测试在 ASGI 开始响应时检查登录会话已入库。安全 HTTP smoke 新增账号隔离的故障列表检查，并只报告固定失败步骤，不输出响应内容。

## 操作流程

当前机器已经升级并部署。其他已有本地安装可执行：

```powershell
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv\Scripts\python.exe scripts/waha_ingress.py migrate-binding
.venv\Scripts\python.exe scripts/waha_ingress.py sync-container-config
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml up --build -d --wait ingress ingress-worker ingress-monitor
.venv\Scripts\python.exe scripts/waha_ingress.py diagnose
.venv\Scripts\python.exe scripts/waha_ingress.py issues
```

`status` 读取持久状态，`diagnose` 主动检查本地链路，`reconcile` 保留只核对 WAHA 状态的行为。命令按私有绑定检查服务端归属。新增浏览器只读接口 `GET /api/v1/connectors/{connection_id}/recovery-issues`，登录且账号隔离，只返回运行诊断元数据。未新增前端凭据或 WAHA 管理接口，D 的展示页面仍待对接。

对每个已恢复的故障，与授权参与者在本地核对受影响时段。不要把正文复制到诊断备注或公共样例。使用 `issues` 输出的 issue UUID 选择结果：

```powershell
.venv\Scripts\python.exe scripts/waha_ingress.py ack-issue --id "<issue UUID>" --resolution needs_followup
# 完成核对并决定不执行历史导入后：
.venv\Scripts\python.exe scripts/waha_ingress.py ack-issue --id "<issue UUID>" --resolution reviewed_no_import
```

`needs_followup` 保持待核对，后续可以最终确认；最终确认幂等且不能换成其他结果。组件仍不可用时不允许确认。确认不执行历史导入，也不证明没有漏消息，不能仅因为 connected/pipeline_ready 恢复就清除记录。

未知原消息、歧义/旧编辑目标和缺失版本进入人工核对；历史数量与新鲜连接不能还原已删除修订。本批不做自动补取。审批/outbox/发送和生产鉴权/密钥管理仍在范围之外。

## 给 E 的可复现故障环境

```powershell
.venv\Scripts\python.exe scripts/check_waha_recovery.py --run
```

脚本仅创建[独立 Compose](../../infra/waha-recovery.compose.yaml)的 `gigmate-waha-recovery`：PostgreSQL 17.9 本机端口 54339，API 18712。拒绝已有同名项目容器或测试卷，使用合成正文与忽略目录 `local-data/waha-recovery` 下的私有绑定，只停止/恢复自己的服务。finally 只清理该一次性测试项目及其数据卷，不接触共享数据库、真实 WAHA 会话或聊天。安全结果写入忽略的 `result.json`。端口需要空闲；清理中断时先核对这个命名测试项目再重跑，不要删除真实项目卷。

| 用例 | 预期与证据 |
| --- | --- |
| R-01 并发 HTTP 接收 | 一次持久原事件、其余去重、健康请求可响应；真实测试服务器及 PostgreSQL ASGI 测试 |
| R-02 API 中断/重启 | 健康不可用、已有事件保留、重投不增任务、故障仍待核对 |
| R-03 数据库中断 | 健康/接收返回 503，不返回虚假成功；停止/启动独立真实 PostgreSQL |
| R-04 数据库恢复 | 同一失败签名事件重投只提交一次，持久积压随后排空 |
| R-05 Worker 崩溃 | 实际停止/启动测试进程；API 仍健康而 Worker 心跳过期 |
| R-06 过期租约 | 只恢复一次并增加一次尝试；脚本显式构造合成过期租约，不宣称被停止进程曾持有该任务 |
| R-07 核对流程 | 组件恢复保留故障；显式核对可关闭合成记录，不执行导入 |
| R-08 WAHA 中断 | 停止真实本地容器；网络修复后 API/Worker/监控保持独立可达 |
| R-09 权限/诊断 | 伪造签名不写诊断，签名拒绝正文回滚，故障列表按账号隔离 |
| R-10 顺序/上限 | 旧健康采样不倒退，反复崩溃达到上限，行锁超时返回失败 |

测试正文均为合成数据。SQLite 只证明兼容性；行锁/并发以 PostgreSQL 为证据。自动测试通过不是 E 独立评审通过。实际检查和真实中断结果记录于[进度](progress.md)。

## 剩余边界

### 修复后真实文字变更验证通过 — 2026-10-06

UTC 07:07 再次复测：账号/连接限定的只读数据库元数据确认，UTC 06:48:01 有一条 ACK（接收计数 34 到 35，不创建正文任务），随后 UTC 07:07:12/31/41 为同一条新消息的新建/编辑/撤回（计数 35 到 38）。持久修订 1/2/3，内部及完整供应商标识一致，最新映射为修订 3 且已撤回。三个任务均尝试一次后完成，处理耗时 9/8/10 毫秒、完成延迟 114/321/266 毫秒。7 项安全 HTTP 检查再次通过，当前 pipeline_ready=true，无积压/失败。拒绝计数 88，最后 SOURCE_MESSAGE_UNRESOLVED 时间 UTC 06:48:08 早于这轮文字变更，期间未增长；聚合计数不能确认被拒绝事件类型。11 条核对记录未确认。无运行代码修改或 commit/push。

通过按账号/连接限定的 PostgreSQL 只读元数据查询，确认 10 月 6 日新增四条正文事件。UTC 06:02:32 一条独立新消息保存修订 1；另一条消息在 UTC 06:37:17 新建、06:37:23 编辑、06:37:34 撤回，依次保存修订 1/2/3。后三条使用同一内部消息标识和完整供应商标识，最新映射为修订 3，持久版本已标记撤回；未导出真实标识或正文。接收计数由 30 到 34，四个任务全部完成，用户状态样本中无待处理/处理中/失败任务。处理耗时为 12/8/11/9 毫秒，接收到完成延迟为 539/242/75/205 毫秒；仅为四个本地样本，不是性能保证。LIVE_EXTRACTION_PENDING 与 SOURCE_SUPERSEDED 是本阶段预期终态代码，任务完成不代表完成模型抽取或对外执行。配置卷修复后的新文字变更检查已通过，下文待验收描述保留为 10 月 2 日历史。11 条故障仍需单独人工核对，未自动确认；遗漏消息恢复及 E 独立评审尚未证明。

后续已确认另一个独立接收故障：Windows 挂载的私有配置在 API 容器内返回 `ENODEV`，主机文件却有效。伪造签名探测返回 `503 CONNECTOR_CONFIG_INVALID`，暴露旧健康检查遗漏该依赖；重新挂载也因 Docker Desktop 的 D 盘共享不可用而失败。改用私有 Docker 配置卷后恢复接收检查，无需重启 Docker Desktop、WAHA 或会话。UTC 13:39 四项健康、pipeline_ready=true，7 项 HTTP 检查与独立故障测试 8 个检查点通过。包括修复期间中断在内，9 条核对记录仍未确认。真实新建/编辑/撤回尚待用户重新测试；此前 WAHA 短暂 connecting 的诱因仍未确定。

主机私有绑定现为 `local-data/waha-a02/bindings/ingress.json`；`migrate-binding` 保留旧绑定及暂停状态。`sync-container-config` 通过子进程标准输入将私有配置同步到本项目 Docker 卷 `waha-monitor-config` 和 `waha-ingress-bindings`，密钥不进入命令参数或输出，容器只读挂载。修改主机配置后须重新同步并重新创建相关服务；聊天授权仍需 `provision`，HMAC 轮换仍需通过 `configure-live` 更新供应商。配置卷含凭据，不得发布或导出。保留真实会话卷，不要对真实项目执行 `down -v`。独立故障测试使用自己的绑定卷，仅清理自己的资源。

API `/health` 现在检查数据库，以及启用 WAHA 时私有绑定的可读性、有效性和持久归属映射；绑定不可用返回 503。无 WAHA 绑定的 Replay 保持支持。健康检查仍不能代替真实回调验证。

UTC 13:24–13:25 的用户手动复测：连接新鲜但 connecting，API/Worker/监控 healthy、WAHA unavailable，没有新增正文同步。13:27 实查 WAHA 已自行恢复 WORKING，主动诊断四项健康且 pipeline_ready=true，期间 agent 未重启或要求重新扫码。最近 WAHA 故障已有恢复时间，但六条核对记录尚未确认。入库元数据为 22 条连接通知，加上此前已验证的 6 条正文/ACK 事件，合计 28；本次新文字变更尚未入库。私有选择与数据库授权白名单一致（1 个聊天）。此前安全日志显示 10:48 的 SOURCE_MESSAGE_UNRESOLVED 对应 ACK，11:34 的 CONVERSATION_NOT_ALLOWED 对应 message.any，不能据此断定用户最新测试发生了什么。connecting 的具体诱因未确定。手动正文验收仍待完成，应等链路就绪后，在已选择且授权的聊天用新消息复测；未自动确认任何故障记录。

本地容器中断不等于路由器/Internet 故障或 WhatsApp 注销后扫码恢复测试。供应商重投有限，真实遗漏正文恢复未证明。持久存储不可用时诊断无法覆盖全部故障；状态仅是采样健康，不保证每次回调送达。未新增生产告警通道、前端展示页、历史导入、模型抽取、发送或对外执行。本批供 E 一次独立统一评审，未自动 commit/push。
