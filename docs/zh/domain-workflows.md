# 业务模型与执行流程

## 实体关系

| 实体 | 关键责任 |
| --- | --- |
| AccountConsent | 处理范围、白名单、有效期与撤销 |
| Conversation | 一个会话、当前上下文版本、可关联多个工单 |
| ConversationMessage | 方向、来源、消息 ID、发送时间、内容版本 |
| WorkOrder | 已确认需求、业务状态、version 与待决提议 |
| RequirementChange | 字段新旧值、提出者、顾客确认状态、来源 revision |
| Task / CalendarEvent | 截止/依赖与排期分别建模，来源指向已确认业务版本 |
| ApprovalAction | 不可变批准快照、行动 revision 与执行链 |
| AuditLog | 操作者、原因、关联对象、执行结果 |

联系人不能当工单 ID。会话和工单显式多对多；不明确时要求人工归类。同一消息可以关联多个受影响记录，但不能无证据地把所有开放工单一起更新。

## 状态及转换

状态值以[domain schema](../../contracts/domain/models.schema.json)为准。

| 状态链 | 状态 | 转换规则 |
| --- | --- | --- |
| 工单 | unclassified、pending_confirmation、confirmed、in_progress、waiting_customer、completed、cancelled | 归类由人确认；confirmed 需要关键需求及商户确认；开始执行、等待顾客、完成和取消由显式业务命令推动 |
| 字段 | missing、proposed、confirmed、needs_review | missing 不能补默认事实；proposed 需核对；来源改变转 needs_review；正式确认保留消息来源 |
| 顾客确认 | not_requested、pending、confirmed、ambiguous | 顾客回复只确认可明确对应的字段；含糊回复保持 ambiguous |
| 行动 | draft、pending_approval、approved、executing、succeeded、failed、result_unknown、cancelled、expired | 批准必须绑定快照；结果以执行证据为准 |

工单允许：unclassified → pending_confirmation；pending_confirmation → confirmed；confirmed → in_progress 或 waiting_customer；in_progress ↔ waiting_customer；in_progress → completed。活动状态可由商户取消。completed/cancelled 为终态，重新打开必须新建显式命令及审计，不由新消息自动恢复。

执行中工单收到新提议仍可保持 in_progress，同时存在 proposed 字段，不能把所有需求都退回未确认。

行动允许：draft → pending_approval → approved → executing；执行进入 succeeded、failed 或 result_unknown。尚未 dispatch 的草稿/审批/批准行动可取消或过期。failed 仅在确认未提交且重新校验通过后有限重试到 approved；内容变化应创建新 revision。result_unknown 核对后转 succeeded，或证实未提交后转 failed；无法核对则保留未知，禁止直接重发。拒绝审批记录为 cancelled 并保留原因。

## 三种版本

1. WorkOrder.version：已确认业务记录或影响审批的业务元数据变更时增加。
2. Conversation.context_version：每个去重后接受的新消息、编辑、撤回推进，不等待 AI 完成。ack 只更新送达状态，不作为新语义上下文。
3. ApprovalAction.revision：正文、收件人、变更内容、绑定版本或有效期变化时增加，旧批准不得继承。

修改动作在数据库锁/版本检查下校验 expected_*。旧值冲突返回409，不能最后写入覆盖。对未归单消息保守使该会话所有尚未执行的审批进入复核；后续可用来源依赖做更精确策略。

## 批准与发送

审批页展示正文/变更、新旧需求、收件人、来源、冲突及有效期。后端保存快照，snapshot_hash 由服务端对固定规范序列化的绑定内容计算，客户端返回仅用于确认看到的是同一快照，不能自己声明已批准。

send_text 快照字段和序列化算法统一定义在 [API 契约](../../contracts/api-v1.md)。正例中的 hash 已按该算法计算；执行状态、送达回执和审批人等过程字段不纳入内容快照。

发送前再次验证：账号授权、会话白名单、连接可用、工单未取消、快照匹配、未过期、最新 context_version、动作 revision 及未完成的幂等记录。用户手机主动发送也属于上下文更新，旧行动暂停。

自己经 API 发出的消息回流要关联 action_id/provider_message_id，更新上下文和结果，不再次自动生成回复或追溯取消已 dispatch 行动。尚未执行的其他行动仍按新上下文复核。

接受新事件与最终发送检查须序列化，避免本地已知道新消息但 worker 仍使用旧审批。连接器尚未传到系统的消息无法被该本地机制检测，应记录实测边界。

## 原文变化与改期事务

来源消息编辑/撤回只标记依赖字段、任务和审批待复核，不自动抹去已确认历史。正式改期审批通过后，将工单新值、正式日历、相关待办、旧提醒取消和审计共同提交；不删除无关安排。系统已有冲突时不能默认接受新时段；候选时段由计算结果提供。

模型输入中的指令是顾客内容，不是工具授权。schema 校验后还需核对来源存在、账号一致、消息 revision 有效、时间可解析和业务归属。金额、地址和数量等缺失不自动填充。
