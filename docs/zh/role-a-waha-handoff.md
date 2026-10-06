# WAHA 当前实现与团队交接总览

更新：2026-10-06。本页说明 GigMate 实际实现，不把 WAHA 自身全部能力当作项目功能。[英文对应](../en/role-a-waha-handoff.md)，[验证证据与故障历史](role-a-recovery-acceptance.md)。

## 目前已经能做什么

可选本地 WAHA 接入把可信事件送入现有模块化后端、PostgreSQL Inbox 和独立 Worker，Replay 保留。固定 WAHA Core 2026.9.1、WEBJS，镜像摘要见 [Compose](../../infra/waha.compose.yaml)；其他版本/引擎未验证。

| 能力 | 实际行为与边界 |
| --- | --- |
| 本地扫码连接 | 私有配置初始化、会话启动/状态查询、二维码保存在本地供操作者扫码；服务重启复用 Linux 会话卷。尚无产品扫码页面。 |
| 聊天选择 | CLI 列出近期聊天供本地选择，追加到忽略的配置；`provision` 同步数据库权威白名单和账号/session 映射。只做本地选择不能更新数据库授权。 |
| 历史能力探测 | 仅统计白名单聊天中可用记录，返回 complete_history=false，不导入历史正文、不证明历史完整。 |
| 文字事件 | 规范化收发文字的新建、编辑和撤回；保守解析完整/短供应商标识，校验方向并拒绝歧义目标。恢复后两轮真实测试确认同一消息修订 1/2/3。 |
| ACK 与会话事件 | ACK 更新送达元数据，不改变正文/上下文、不创建抽取任务；会话通知更新状态采样并处理顺序冲突。accepted 包含这些事件，不是文字条数。 |
| 来源与授权 | 原始请求体 HMAC、大小/类型校验、服务端可信账号/session、同意与聊天白名单先于业务持久化。密钥不进入前端/模型。浏览器仍为开发账号/session/CSRF，尚非生产鉴权。 |
| 持久接收 | Inbox/消息修订/上下文/Job 原子提交，提交后才响应成功；稳定事件标识、去重、身份冲突拒绝、上下文变化与旧提议失效。不保证供应商重投完整或外部 exactly-once。 |
| 独立 Worker | PostgreSQL 认领/行锁、租约、版本/同意校验、含崩溃恢复的三次尝试上限、旧租约持有者保护、耗时记录及数据库等待上限。真实内容以 LIVE_EXTRACTION_PENDING 或 SOURCE_SUPERSEDED 完成，不执行虚构抽取。 |
| 健康与状态 | 持久连接/新鲜度、最后正文同步、接收/去重/旧事件计数与任务数；分别显示 API/WAHA/Worker/监控健康、pipeline_ready、review_required 和安全指标。健康检查验证私有绑定及归属。 |
| 故障核对 | 持久保存供应商/API/监控/Worker 中断与来源问题；恢复时间不自动清除核对。`issues` 与显式 `ack-issue` 支持人工处理，不导入历史。数据库不可用时不能保证实时记录所有故障。 |
| 本地运维 | diagnose/reconcile、暂停、授权注册同步、回调配置、绑定迁移/私有配置卷同步，以及显式 30 天内容清理。没有任意发消息命令。配置使用 Docker 私有卷，会话卷保留。 |
| 验证 | PostgreSQL 241 项；SQLite 236 通过/5 项需 PostgreSQL 跳过；真实独立数据库/API/Worker 故障测试 8 个检查点、本地 WAHA 中断、7 项 HTTP 检查，以及重复真实新建/编辑/撤回验证。E 独立验收另行完成。 |

## 接口、工具与阅读顺序

- 前端使用已登录且账号隔离的 `GET /api/v1/connectors`、`GET /api/v1/connectors/{connection_id}/recovery-issues`。
- 供应商使用独立签名接口 `POST /api/v1/connectors/waha/{connection_id}/events`；前端不得直接管理 WAHA 或读取密钥。
- `scripts/waha_local.py`：init/probe/start/status/qr/observations/select-chats/history/sync-container-config；probe 的 observations 是易失能力观察，不是持久业务 Inbox。
- `scripts/waha_ingress.py`：provision/status/diagnose/reconcile/watch/pause/purge/configure-live/issues/ack-issue/migrate-binding/sync-container-config。核对不导入历史；purge 会删除过期内容，不是常规验收步骤。
- 先读本总览，再读[职责](role-a-responsibilities.md)、[恢复操作与 E 用例](role-a-recovery-acceptance.md)、[API 约定](../../contracts/api-v1.md)、[完成记录](progress.md)。旧阶段保留开发历史，实际结果以最新日期为准。

新开主机 PowerShell 后，先启动 Docker Desktop 和已有数据库/WAHA 服务，并明确设置本地数据库：

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'
.venv\Scripts\python.exe scripts/waha_ingress.py diagnose
.venv\Scripts\python.exe scripts/smoke_waha_ingress.py
```

安装/迁移/Compose/私有卷同步按恢复文档执行，不要为已有安装重新 provision。密钥、二维码、真实聊天与会话文件不进入仓库；不要删除真实项目卷来解决连接报错。

## 其他组员可以接什么

| 角色 | A 已提供 | 仍需完成 |
| --- | --- | --- |
| B | 已授权可信事件、来源修订与上下文、合成样例及持久业务存储 | 真实内容的通用抽取、提示词/评估和接入；当前 live Job 完成不产生 AI 提议。 |
| C | 持久归属、Inbox/Job、来源/上下文失效、行锁和有上限恢复 | 业务确认/审批规则，以及外部批准动作、outbox、发送前校验和未知结果核对。Replay 内部确认不等于 WAHA 外部执行。 |
| D | 已生成 ConnectorStatus/RecoveryIssue 类型和账号隔离接口 | 产品扫码/选择/同意流程、健康与核对页面、安全错误展示；connected 不足以表示链路就绪，pipeline_ready 与 review_required 分别展示。 |
| E | 阶段证据、安全 HTTP 检查、独立故障脚本与真实文字证据 | 独立验收/评审；Internet/路由器/注销后扫码恢复和遗漏正文恢复未证明。 |

## 尚未实现或尚未证明

- 完整历史导入、自动补回断线遗漏、缺失修订自动恢复，以及中断后完整性/顺序保证。
- 通用媒体接入/转写、完整聊天镜像、群聊/媒体覆盖与跨引擎行为；供应商有某能力不等于产品已适配并验证。
- 真实通用 AI 抽取、自动确认工单/正式日程；AI 仍只能输出提议/草稿。外部发送适配器、审批/outbox、发送回声、未知发送结果核对均未实现。
- 生产鉴权、多商户自助接入、生产密钥管理、公网部署加固、告警推送及完整前端连接页面。
- E 独立签字或没有漏消息的保证；最新检查时本地仍有 11 条历史核对记录未确认。

## 剩余批次计划

按用户要求，官方 Cloud API 暂停，不纳入当前计划。下一步是与 E 做 A-03 统一评审，并由人工明确核对已记录缺口。后续 WAHA 工作须获授权且依赖齐备：D 的连接页面、B 的真实内容处理，之后 C 完成批准执行链路，才进入 A-04 发送适配器。继续整批开发、统一验收；本总览不授权额外实施或外部部署。
