# 工程统一标准

## 架构与目录

采用单仓库、模块化单体后端、独立 worker，同一业务代码及数据库迁移。前端 React/TypeScript/Vite；后端 FastAPI/Pydantic；数据库 PostgreSQL；迁移 SQLAlchemy/Alembic；开发环境 Docker Compose。具体运行时和依赖版本在搭骨架时锁定，不把校验脚本运行机器的版本当作应用版本。

后续应用放 apps/web、apps/backend，基础部署放 infra，校验与工具放 scripts。当前阶段不创建无实现的应用空目录。模块职责见[英文架构](../en/architecture.md)：identity、messaging、understanding、workorders、planning、actions、audit。

跨模块通过应用服务调用；路由层和 adapter 不直接实现另一套状态机。AI 模块不拥有正式业务写入和发送权限。

## 命名与公共类型

- Python、数据库及 JSON 字段使用 snake_case；TypeScript 内部变量使用 camelCase，组件/类型使用 PascalCase，不擅自更改线上字段名。
- 公共实体 ID 使用 UUID；供应商消息 ID 使用不透明字符串，不能假定供应商使用 UUID。
- 状态值使用 schema 中的英文枚举；中文文案在展示层映射。禁止用一个 confirmed 混合顾客确认和商户审批。
- 布尔值必须有明确含义，不用 sent=true 代替完整执行状态。
- contracts 中的模型为第一版 wire contract，不是直接复制的数据库表设计；数据库约束、索引与迁移在实现时补齐。

## 时间与缺失值

明确时刻以 UTC RFC3339 Z 形式保存，另外保存 IANA 时区和来源；业务默认展示 Asia/Hong_Kong。全天截止用 YYYY-MM-DD，不补成一小时预约。相对日期依据消息发送时间和业务时区，不依据运行机器时间。时区数据库安装与测试在骨架阶段处理。

Task.due 使用 DeadlineValue 表示单个截止时刻或日期；CalendarEvent.schedule 使用 ScheduleValue 表示起止区间或全天事件，两者不能混用。

未知信息使用 null 或缺失状态，不猜地址、数量、币种及时间。“下午三点”但没有日期必须结合可靠上下文，否则进入待核对。模型输出任何时间都要经确定性日期校验。

## API 约定

业务前缀 /api/v1；请求/响应 application/json。登录采用服务端会话、HttpOnly Cookie，同站部署；写请求必须有 CSRF 保护。具体认证实现仍需骨架阶段完成，不允许以请求体 account_id 作为授权。连接器 Webhook 使用独立密钥/签名认证，不复用浏览器会话。

客户端读取含 request_id 的响应，列表使用 items、next_cursor 和 limit（默认20、最大100），详情使用 data。错误使用 error.code、error.message、error.details、request_id；details 不包含私密内容。具体端点及请求形状见[API 契约](../../contracts/api-v1.md)。

| HTTP | 统一错误 | 处理 |
| --- | --- | --- |
| 401 | UNAUTHENTICATED | 重新登录 |
| 403 | FORBIDDEN / CONSENT_REVOKED / CSRF_REJECTED | 拒绝执行，不重试绕过 |
| 404 | NOT_FOUND | 资源不存在或不属于当前账号，不泄露跨账号存在性 |
| 409 | VERSION_CONFLICT / APPROVAL_STALE / IDEMPOTENCY_CONFLICT | 刷新并重新核对 |
| 422 | VALIDATION_FAILED | 修正输入 |
| 429 | RATE_LIMITED | 按服务端提示等待 |
| 503 | CONNECTOR_UNAVAILABLE | 保留待处理状态，不能显示已发送 |

写操作携带 expected_version，批准还需 expected_context_version、expected_action_revision 和 snapshot_hash。POST 命令使用 Idempotency-Key；同键同内容返回原结果，不同内容返回冲突。幂等键按账号、命令和资源限定，保留至对应行动归档且不少于试点记录保留期。供应商能力未验证前不承诺外部恰好一次发送。

## 事件与处理

鉴权、白名单检查在业务内容落库前完成。允许事件与 context_version 的增加、处理任务建立在同一事务完成，然后才确认接收。event_id 是 adapter 对重投稳定的事件身份；provider_message_id 是消息身份；修改与撤回采用不同事件身份和消息 revision。供应商缺少 revision/稳定事件 ID 时，adapter 必须实测后确定持久映射策略，不用接收时间随机生成去重键。

同会话顺序处理；工单乐观版本检查；任务租约、防重复领取、失败分类、最大重试和人工核对入口统一实现。内部变更事务提交，对外通过 outbox。超时后不清楚是否已发送时进入 result_unknown。

## 权限、隐私与日志

所有读取、关联和修改都校验所属账号。来源消息的账号也必须一致。前端及模型不可拿到 WAHA 凭据。密钥和 session 文件不入库到普通业务字段、不进 Git、不打印日志。Webhook 管理端不公开暴露；按固定版本能力验证认证。

结构日志只保留 request_id、account_id、event_id、action_id、stage、duration_ms、error_code。原文在授权视图回看，不放进错误详情。测试数据使用虚构内容。原始聊天建议保留30天，这不是法定期限或已实现功能；真实试点前落实删除覆盖数据库、任务、附件、缓存和备份轮换。

## 契约演进

当前 schema 和 API 文档是唯一契约来源。实现 Pydantic 后按 ADR 0002 一次性转为生成流程，增加兼容性和漂移检查，不维护两套手写/生成定义。破坏性变化升级主版本并提供迁移说明；严格 schema 拒绝未知字段，所谓可选字段添加也要协调消费者升级。

提交依赖锁文件；迁移在 PR 中复核；已共享迁移用新迁移修正。应用格式化、lint、类型和测试具体工具/版本在骨架阶段锁定并提供真实命令。
