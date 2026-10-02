# A-03 可靠接入、连接监控与统一验收

## 真实发送、编辑、撤回验证通过

2026-10-02 UTC 09:18，用户依次操作后接收计数 **6 → 7 → 8**，last_sync_at 每次更新，待处理/处理中/失败任务均为 0。只读元数据确认新增创建、编辑修订 2、撤回修订 3，三者使用同一内部消息标识及完整 provider 标识，最新版本已标记撤回。累计事件为：2 条连接状态、3 条创建、1 条 ACK、1 条编辑、1 条撤回。数据库等待锁数仍为 0，六项 HTTP smoke 通过，未输出真实正文或 provider 标识。本地固定 WEBJS 版本的文字变更链路验证通过；E 独立评审、断网恢复及既有其他边界仍待完成。下文此前“待验证”的记录描述本次成功测试之前的证据。本次未 commit/push。

## 后续 API 卡住问题修复

用户明确确认已经依次发送、编辑、撤回，不能把未入库归因于用户没有操作。检查发现接入 API unhealthy，健康检查和 HTTP smoke 超时，数据库有一个持锁但事务空闲的连接、两个等待锁的连接。异步回调接口在事件循环内执行同步数据库接收；并发请求等待行锁时阻塞事件循环，使先前请求的事务退出无法得到调度。

已改为通过 `run_in_threadpool` 执行接收，保留函数作用域事务在成功响应前提交。新增回归测试在同一个 ASGI 事件循环中阻塞接收，同时检查健康请求仍可响应。PostgreSQL 全套 **204 通过**；SQLite 接入子集 **33 通过、1 跳过**；Ruff/格式和 export 检查通过。重新构建启动后，API 健康、六项 HTTP smoke 通过，数据库等待锁数为 0，监控恢复刷新。已持久接收 5 条，任务无积压/失败。本次修复不改 schema 或前端行为，此前相应验证作为历史证据保留。真实编辑/撤回仍需新消息复测；中断或未提交的回调不能视为已入库，也不能承诺自动恢复。

## 后续真实事件证据

用户随后查询接收计数达到 5。只读元数据检查确认：2 条连接状态、2 条新消息、1 条 ACK；两条消息均为修订 1，未撤回。新增文字和独立 ACK 已持久接收，队列无积压和失败，尚无编辑/撤回入库证据。近期回调诊断未见新增编辑/撤回失败；较早的目标未匹配错误属于 UTC 08:33 的 ACK。诊断输出不包含正文、provider 标识或凭据。

## 真实目标 ID 格式修复补充

首条真实文字已持久接收，worker 已完成任务且未执行提取。随后编辑/撤回回调返回 SOURCE_MESSAGE_UNRESOLVED：适配器将短目标 ID 与数据库保存的完整消息 ID 直接比较，无法匹配。[WAHA 官方事件说明](https://github.com/devlikeapro/waha-docs/blob/main/content/docs/how-to/events/index.md)明确 editedMessageId/revokedMessageId 不含聊天 ID。

新增版本迁移 `0003_waha_stanza_identity`，保存短 ID 索引并回填符合格式的既有映射，不改此前迁移。匹配限定在已授权聊天、账号、内部会话及原消息方向；多个候选返回 SOURCE_MESSAGE_AMBIGUOUS。各修订仍保留完整 provider ID 与原内部消息 UUID。本地已有原消息映射已回填，文档不记录真实标识或正文。

修复后的 API/worker/monitor 已重新构建运行。PostgreSQL 全套 **203 通过**；SQLite **201 通过、2 跳过**。新增测试覆盖短目标编辑/撤回、旧事件重试去重、方向不符与群聊目标歧义；六项 HTTP smoke 通过。真实状态保持连接且未过期，接收计数为 3，待处理/处理中/失败任务均为 0；尚不能据此宣称真实编辑/撤回验收完成。请在授权聊天新发一条测试文字，再编辑、撤回，每一步检查 status。此前被拒绝的回调未入库，不承诺自动恢复。

日期：2026-10-02。基线：第二阶段提交 `016a679`，分支 Andy_WAHA。用户已明确授权修改共享模块。本批实现持久 WAHA 接收和核心监控，保留独立 worker。[英文对应记录](../en/role-a-stage3-acceptance.md)。

## 已完成开发

- 新增版本迁移 `0002_waha_ingress`，不改 `0001`：三张表保存账号所属 session、白名单聊天/内部会话映射、原消息/修订映射；Inbox 新增可空连接外键及索引。表内不保存连接器密钥。
- [接入服务](../../apps/backend/src/gigmate/waha_ingress.py)与 `POST /api/v1/connectors/waha/{connection_id}/events`：原始字节 SHA-512 HMAC、严格有界 JSON、私有服务端绑定、账号/连接启用与会话白名单检查，全部在保存正文前执行。Inbox、消息版本、上下文、任务和映射一起提交；函数作用域依赖保证事务退出完成后才响应成功。数据库失败返回安全 503，不声称可靠接收成功。
- 事件身份包含 instance/账号/session/provider event ID，重试接收时间变化不改变语义摘要。重复事件和创建别名不新增版本/任务；同一身份改变标准化含义拒绝。新版本之后重试旧事件仍能去重。
- 编辑/撤回通过持久原消息映射关联，串行分配本地已接收修订版本。更早/相同时间戳的变更、原消息未知、撤回后再修改和身份冲突必须拒绝或核对。不能推断缺失的远端版本，不声称完整历史还原。
- ACK 独立保存，单调更新回执等级，不推进正文/上下文，不创建提取任务。错误或不支持的 ACK 要求核对；ACK 不等于客户确认或已批准发送。
- 持久连接状态，忽略旧通知，同时间戳状态冲突要求核对。[状态契约](../../apps/backend/src/gigmate/contracts.py)和登录保护的 `GET /api/v1/connectors` 提供状态/新鲜度、最近正文接收时间、接收/重复/旧通知计数与待处理/处理中/失败任务数，按账号隔离，不返回密钥和 provider 聊天标识。原 Replay 状态与回放接口兼容保留。
- [本地操作工具](../../scripts/waha_ingress.py)支持同步用户已选聊天、暂停接入、核对状态、配置业务回调和过期内容清理。注册时创建独立会话，不猜测关联工单；再次 provision 会撤销被移除聊天的数据库白名单，不重置已有消息。
- [Compose 扩展](../../infra/waha-ingress.compose.yaml)新增本机 `18702` API、worker 和每 30 秒核对一次的监控。使用本地 PostgreSQL 的独立 `gigmate_waha_a03` 数据库，保留 provider 会话并隔离旧 Replay 数据。监控失败不捏造状态，超过 120 秒的观察显示 stale，不报 live_connected；这是保守配置窗口，不是可用性保证。
- Worker 重检账号/连接/会话授权，回收过期租约，禁止过期持有者完成任务。真实消息不经过虚构提取桩，以 LIVE_EXTRACTION_PENDING 结束，不生成提议或正式写入；没有新增 AI、发送或 outbox。
- Worker 启动及每小时维护、手动 purge 清理超过 30 天的 Inbox/任务，清空旧修订正文，保留身份/版本/来源元数据。超出窗口的事件拒绝，避免重试重新引入旧正文；暂停连接也清理。完整账号删除及备份删除尚不在本批范围。

领域 schema/OpenAPI/前端类型从源模型重新生成，事件 wire 仍为 0.1.0，没有手工改事件 schema。消息接口显示已保存最新修订，账号所属 WAHA 会话详情返回真实 provider 聊天标识。

## 本机使用

当前机器已注册并配置业务回调，不必重新创建或扫码。全新环境需先完成第二阶段私有配置/聊天选择，准备本地 PostgreSQL 和独立数据库，再执行：

```powershell
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'
# 数据库须已存在；开发账号初始化可重复执行：
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv\Scripts\python.exe -m gigmate.seed
.venv\Scripts\python.exe scripts/waha_ingress.py provision
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml up --build -d --wait ingress ingress-worker ingress-monitor
# 更新 provider 回调，可能重启其会话：
.venv\Scripts\python.exe scripts/waha_ingress.py configure-live
.venv\Scripts\python.exe scripts/waha_ingress.py reconcile
.venv\Scripts\python.exe scripts/waha_ingress.py status
.venv\Scripts\python.exe scripts/smoke_waha_ingress.py
```

`local-data/waha-a02/ingress.json` 是 Git 忽略的私有服务端绑定。API 只读挂载并通过 WAHA_CONNECTOR_CONFIG 加载；没有配置时接入关闭。密钥、二维码和 profile 保留在私有本地位置。开发账号/密码与 PostgreSQL 凭据仅用于本机测试，不代表生产鉴权；instance/账号/session 映射须对应真实 provider，不把实际 profile 放进夹具，不启用无关账号连接。

后续改变聊天选择，要执行 select-chats，然后在此数据库上执行 `waha_ingress.py provision`；仅重启旧 probe 不会改变持久授权。立即停止接入使用 `waha_ingress.py pause`；串行化后续请求/任务会拒绝或取消。只编辑本地 consent 标志不能代替暂停权威数据库连接。更换挂载的绑定/密钥后，需重启 ingress/monitor 并同步 provider HMAC 配置。

真实验收时，在同意测试的白名单聊天里，**业务回调配置完成后新发一条合成文字**，再编辑/撤回同一条。查询 `waha_ingress.py status`，accepted 和 last_sync_at 应更新，任务积压应清空且不产生提议。旧手机历史没有导入，修改旧的未接收消息会返回 SOURCE_MESSAGE_UNRESOLVED。原 observations 属于内存能力 probe，目前已不接收业务订阅通知。

configure-live 等 provider 写请求结果不确定时不自动重试，先查 provider/数据库状态。来源/顺序失败需人工核对，不伪造原消息或盲目导入历史。provider 回调重试次数有限，长时间故障可能丢通知；历史条数不保证可补齐。此次更新连接配置后恢复 WORKING，无需重新扫码；更完整的断网/注销恢复仍待独立真实验收。

## 实际检查与剩余边界

最终自动检查及重启证据见共享[进度记录](progress.md)。测试覆盖签名、归属/白名单、去重/冲突、新消息/编辑/撤回顺序、独立 ACK、回滚/提交后响应丢失、提交失败、过期租约、worker 授权、状态过期/核对竞态、保留期、注册撤销、PostgreSQL 并发接收和一次性 SQLite 迁移保留/降级。PostgreSQL 和 SQLite 均运行，只有前者证明行锁行为。

运行证据：独立数据库迁移/初始化/注册完成，可信 provider 查询确认 WORKING；配置回调后 STARTING 与 WORKING 通过真实 HMAC HTTP 持久入库，两条状态通知不创建任务。本地 API 健康/鉴权/伪造签名/状态/退出冒烟不读取实际正文。API/worker/monitor 重启保留事件、映射和状态；前端类型/格式/build 通过，完整真实连接 UI 留给 D 后续配合。

本批准备交由 E 一次统一评审，不能声称 E 已独立验收。仍需真实验证：新文字/编辑/撤回持久接入、独立 ACK、完整 provider 目标兼容、断网恢复。生产鉴权/密钥管理、通用抽取、工单归类页面、审批外发/outbox/核对、完整历史恢复、媒体和完整删除仍待开发。本批没有自动 commit 或 push。
