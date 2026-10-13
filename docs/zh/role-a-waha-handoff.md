# WAHA 当前实现与团队交接总览

2026-10-10 第二批：已实现固定的原消息时间/时区输入、可点击来源片段和绑定版本/哈希的只读已核对交接资料；C 业务晋升和 B 真实处理器仍待接入，见[媒体协议](role-a-media-ingestion.md)。

2026-10-10 媒体扩展：[A 附件读取](role-a-media-ingestion.md)新增明确授权的原文件下载/预览、私有存储、持久处理/核对任务及来源核对。B 尚未接真实模型，OCR/ASR/解析/GenAI 仍是 B 的依赖，不是 A 已交付能力；没有新增发送或工单权限。

当前基线（2026-10-10）：PR #11、#13 和 D01 #15 已进入 main（1336c60）。Andy_WAHA_message_sync 包含该 main 和下述已验证 D01 兼容。PR #14 现以 main 为目标；保留 0008 迁移、受限时间线/历史/媒体观察及分页，不用 main 覆盖当前分支。下方较早的依赖目标描述是历史记录。

2026-10-10 D01 兼容：组合 PR #15 的原请求持久恢复、过期/授权版本校验、授权重新载入及回放工作台，与消息同步分支的会话分页、已载入搜索/类型筛选和 WahaMessages。恢复会话发现时保留原 offset/limit/version/key，将选项和 next_offset 返回页面，不自动提交新分页，也不重置未保存的勾选。connect/recover 原请求恢复仍与服务端 result_unknown 的明确核对分开。真实手机/群聊/媒体及独立验收边界不变。

评审修正（2026-10-09）：撤销授权不再依赖 provider 配置；新增/重新授权仍会检查配置。不同窗口及分页刷新会保留有效候选 ID，不延长到期时间。D 保存后应刷新选项，并明确处理真正过期或授权版本冲突。A 的消息同步分支在配置失效撤权时仍取消活动同步并记录禁止读取区间。见[接入规则](role-a-setup-api-acceptance.md)。基线修复已作为 99e73b1 推送至 PR #11，并包含于 Andy_WAHA_message_sync。新增消息同步 PR 在 PR #11 合并前以 Andy_WAHA_upgrade 为目标。

更新：2026-10-09。本页说明 GigMate 实际实现，不把 WAHA 自身全部能力当作项目功能。[英文对应](../en/role-a-waha-handoff.md)，[验证证据与故障历史](role-a-recovery-acceptance.md)，最新[消息同步批次](role-a-message-sync-acceptance.md)。

## 目前已经能做什么

2026-10-08：[统一适配交付](role-a-integration-acceptance.md)把 D 页面接到[接入后端](role-a-setup-api-acceptance.md)，提供归属隔离持久连接操作、临时二维码、不透明聊天选择、暂停/恢复和已恢复故障审阅。本地产品页面已实现；生产/多商户接入仍待做。

可选本地 WAHA 接入把可信事件送入现有模块化后端、PostgreSQL Inbox 和独立 Worker，Replay 保留。固定 WAHA Core 2026.9.1、WEBJS，镜像摘要见 [Compose](../../infra/waha.compose.yaml)；其他版本/引擎未验证。

| 能力 | 实际行为与边界 |
| --- | --- |
| 本地扫码连接 | 私有初始化及持久后端控制；已登录页面临时显示二维码和状态，复用已有会话卷。尚无生产接入。 |
| 聊天选择 | 页面发现不透明聊天选项，明确保存数据库权威授权；CLI 配置选择/provision 保留为操作者替代路径，混用可能覆盖选择。 |
| 历史/同步 | 旧 CLI 仍只计数；产品页面明确授权导入有范围的私有快照，支持进度/取消/重试及已记录的权限排除区间，complete_history=false，不自动处理业务或保证完整历史。 |
| 群聊/媒体及文件 | 参与者/引用出处、说明文字、附件元数据及支持的 ACK/编辑/撤回；明确原文件下载/预览和 A/B 任务/核对接口可选启用，真实 OCR/ASR/解析/GenAI 由 B 负责，真实格式仍待验收。 |
| 文字事件 | 规范化收发文字的新建、编辑和撤回；保守解析完整/短供应商标识，校验方向并拒绝歧义目标。恢复后两轮真实测试确认同一消息修订 1/2/3。 |
| ACK 与会话事件 | ACK 更新送达元数据，不改变正文/上下文、不创建抽取任务；会话通知更新状态采样并处理顺序冲突。accepted 包含这些事件，不是文字条数。 |
| 来源与授权 | 原始请求体 HMAC、大小/类型校验、服务端可信账号/session、同意与聊天白名单先于业务持久化。密钥不进入前端/模型。浏览器仍为开发账号/session/CSRF，尚非生产鉴权。 |
| 持久接收 | Inbox/消息修订/上下文/Job 原子提交，提交后才响应成功；稳定事件标识、去重、身份冲突拒绝、上下文变化与旧提议失效。不保证供应商重投完整或外部 exactly-once。 |
| 独立 Worker | PG 行锁/租约、权限版本、有界重试/崩溃恢复及旧持有者保护；真实文字经 B 证据接口以 EXTRACTION_NEEDS_REVIEW 或 SOURCE_SUPERSEDED 处理。独立只读同步有页进度/退避，不生成业务 Job。 |
| 健康与状态 | 持久连接/新鲜度、最后正文同步、接收/去重/旧事件计数与任务数；分别显示 API/WAHA/Worker/监控健康、pipeline_ready、review_required 和安全指标。健康检查验证私有绑定及归属。 |
| 故障核对 | 持久故障/来源问题、有范围的明确补查/来源查询及独立人工审阅；找到快照不代表重建修订或清除故障。DB 不可用时不能实时记录全部问题。 |
| 本地运维 | diagnose/reconcile、暂停、授权注册同步、回调配置、绑定迁移/私有配置卷同步，以及显式 30 天内容清理。没有任意发消息命令。配置使用 Docker 私有卷，会话卷保留。 |
| 验证 | 最新 PG 配置全套 385 通过，媒体 SQLite 模块 35 通过/1 项 PG 专用跳过，前端 48 通过，15 个隔离 HTTP/worker/评估检查点。之前真实文字/授权/暂停证据单独保留；真实媒体/历史、B 真实适配器及 E 独立验收仍待完成。 |

## 接口、工具与阅读顺序

新组员按[自己账号的本地联调流程](role-a-team-local-development.md)执行：独立团队数据库、启动/诊断/测试起点/验证工具，以及下游具体接入位置。已有旧安装不自动认领或迁移。

- 前端使用已登录且账号隔离的 `GET /api/v1/connectors`、`GET /api/v1/connectors/{connection_id}/recovery-issues`。
- 供应商使用独立签名接口 `POST /api/v1/connectors/waha/{connection_id}/events`；前端不得直接管理 WAHA 或读取密钥。
- `scripts/waha_local.py`：init/probe/create/status/qr/restart/observations/select-chats/history/sync-container-config；probe 的 observations 是易失能力观察，不是持久业务 Inbox。
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
| B | 已授权可信事件、来源修订与上下文、合成样例及持久业务存储；provider 接口与默认 deterministic 实现；离线评测；持久 `proposals` + `model_call_traces` 证据 | 真实内容的真实模型接入。deterministic provider 对未知 live 内容返回 `EXTRACTION_NEEDS_REVIEW`；放开这道闸是后续单独授权的真实模型批次。 |
| C | 持久归属、Inbox/Job、来源/上下文失效、行锁和有上限恢复 | 业务确认/审批规则，以及外部批准动作、outbox、发送前校验和未知结果核对。Replay 内部确认不等于 WAHA 外部执行。 |
| D | 已实现本地扫码/选择/同意/健康/核对及消息同步页面，生成类型及账号隔离接口 | 完善独立真机 UX；连接/就绪/审阅/同步完成分开。展示 ID 不直接作为 SourceRef，需实际 source_message_id/revision。 |
| E | 阶段证据、安全 HTTP 检查、独立故障脚本与真实文字证据 | 独立验收/评审；Internet/路由器/注销后扫码恢复和遗漏正文恢复未证明。 |

## 尚未实现或尚未证明

- 完整历史覆盖、未经再次同意的自动补查、缺失修订重建或完整性/顺序保证；有界快照导入及明确补查已经实现。
- 真实媒体转写/OCR/解析/GenAI、完整镜像、群管理与跨引擎；明确原文件下载/预览及 A/B 接口已可选实现，B 处理器与真实格式仍待验收。
- 真实通用 AI 抽取、自动确认工单/正式日程；AI 仍只能输出提议/草稿。外部发送适配器、审批/outbox、发送回声、未知发送结果核对均未实现。
- 生产鉴权、多商户自助接入、生产密钥管理、公网加固及告警推送；本地连接页面已实现。
- E 独立签字或没有漏消息的保证；历史未处理数量是运行时数据，应查当前 status，不沿用早期固定计数。

## 剩余批次计划

Cloud API 继续不纳入计划。接下来用自己的账号统一验收媒体/历史，B 接真实处理器，E 独立复核。用户已授权 A 的原文件链路，真实模型/业务提取仍交 B。后续多 session/部署及批准发送须明确范围，C 的批准/outbox/核对先于发送适配。继续整批开发、统一验收；本总览不授权额外发送。
