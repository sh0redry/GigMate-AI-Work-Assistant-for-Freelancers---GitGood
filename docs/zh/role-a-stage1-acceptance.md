# A-01 第一阶段开发与统一验收

日期：2026-10-02。基线：v0.2 回放骨架；交付范围：独立、离线的事件适配与异常验证。对应[开发演进](role-a-development-roadmap.md)的 A-01；[英文记录](../en/role-a-stage1-acceptance.md)同步维护。

本轮按用户协作限制，只新增实现/测试/样例/演示/验收文件，并修改本轮此前新建的 A 职责与演进文档。未修改已有共享接收服务、API、Worker、契约、迁移、依赖、CI、根 README、全局进度或状态记录。本文件承担本轮完成记录，避免修改未经允许的共享文件。未提交或推送。

## 1. 已交付内容

| 文件 | 作用 |
| --- | --- |
| [waha_adapter.py](../../apps/backend/src/gigmate/waha_adapter.py) | 无网络/数据库副作用的事件转换、可信映射检查、现有 schema 校验和语义摘要 |
| [waha_replay.py](../../apps/backend/src/gigmate/waha_replay.py) | 合成样例展开与内存验收账本，展示重复、身份冲突和来源版本规则 |
| [waha_a01.json](../../apps/backend/tests/fixtures/waha_a01.json) | 自带版本/分类的合成语料清单，6 个合法例与 17 个异常例 |
| [test_waha_adapter.py](../../apps/backend/tests/test_waha_adapter.py) | 87 项自动测试：转换、非法输入、隔离、版本、重复/冲突、错误安全和命令行 |
| [replay_waha.py](../../scripts/replay_waha.py) | 本地运行全部样例、单例和七步状态演示，不需要服务器或真实账号 |

语料 profile 为 `synthetic_waha_a01_v1`，清单版本为 `1.0.0`；输出沿用现有事件 wire `0.1.0`，没有新建或改写共享 schema。样例放在模块测试 fixtures 中，拥有自己的清单，不加入共享 contracts/examples，也不修改其 manifest。

## 2. 支持矩阵与边界

| 通知 | 本轮离线适配 | 现有服务接收 WAHA / 真实验证 |
| --- | --- | --- |
| message / message.any | 转换为 message.created；支持文字及显式 API 发出来源 | 未接入 / 未实测 |
| message.edited | 解析 editedMessageId，通过可信映射关联原消息 | 未接入 / 未实测 |
| message.revoked | 解析 revokedMessageId；before 为空也可处理；正文不复制 | 未接入 / 未实测 |
| message.ack | 保持独立事件身份，不推进消息内容版本 | 未接入 / 未实测 |
| session.status | 将已列出的供应商状态转换为四类项目状态，丢弃 QR/认证材料 | 未接入 / 未实测 |
| 媒体、反应、其他未知通知 | 明确拒绝，不误当文字 | 不支持 |

当前 `messaging.ingest` 仍只接收 Replay。不能将输出的 connector 从 waha 改成 replay 绕过边界；本轮也没有新增 Webhook、扫码、模型调用或发送接口。WORKING 转 connected 仅是通知转换，不证明连接状态新鲜或已实测。

## 3. 输入与可信映射约定

官方字段依据[WAHA 事件说明](https://waha.devlike.pro/docs/how-to/events/)及[消息说明](https://waha.devlike.pro/docs/how-to/receive-messages/)查阅。具体引擎/运行版本尚未固定；本模块只验证明确的合成 profile，不承诺兼容全部实际引擎变体。

| 输入 | 本轮约定 |
| --- | --- |
| 顶层 id | 非空供应商事件身份；缺失返回 EVENT_ID_REQUIRED，不随机补 ID |
| 顶层 timestamp | 明确整数毫秒，转换成 UTC Z 时间；不猜秒/毫秒，不使用接收时间替代 |
| event / session | 事件在支持列表内；session 必须匹配服务端上下文 |
| message 的 payload.id | 新建/回执目标引用；供应商 ID 当不透明字符串，不自行解析电话号码 |
| editedMessageId / revokedMessageId | 修改/撤回的原消息目标引用；动作消息 ID 不能替代目标 |
| fromMe / from / to | 严格布尔方向与会话对应；最小 ACK profile 的发出消息可使用 from 中的会话标识 |
| hasMedia / body | 新建/修改必须明确 hasMedia=false 且有非空文字；不推测缺失类型 |
| account_id、metadata、原始 revision | 不授予权限，不用它们覆盖服务端归属/版本 |

调用方提供 `NormalizationContext`：账号 UUID、实例 ID、session、来源已验证与授权有效的事实。消息事件另需 `ResolvedMessage`：内部 conversation/message UUID、原消息 canonical provider ID、原始目标引用、会话标识、白名单、revision 和 app/api 来源。

这些 dataclass 是后端可信调用约定，**布尔字段不是实际身份认证**。合成语料声明 true 仅用于离线验证；未来公开请求不得直接构造这些对象。真实来源验证、session/账号查询、白名单以及持久消息映射应由接收服务完成后传入。当前没有实现 HMAC 或数据库 resolver。

revision 必须来自可信映射，本模块不自动分配。新建要求 1；修改/撤回至少 2；内存账本要求连续修订，乱序进入 VERSION_CONFLICT。缺少原消息或 revision 不明确时不猜测，需要未来持久核对/人工复核。

API 来源需要显式可信映射且方向为 outgoing；如原始 source 与映射冲突则拒绝。没有从“发出”直接推断“API 发出”。session.status 的 source=app 是该离线 profile 的约定。

## 4. 事件身份、摘要与回执语义

标准 event_id 使用固定 UUID namespace，加实例、账号、session 和供应商事件 ID 的 JSON 序列生成 UUIDv5。同一次事件重投保持 ID；跨实例/账号/session 隔离。供应商 ID 是否真的跨重投稳定，仍需真实验证。

`semantic_digest` 先校验标准事件，然后对除 received_at 外的字段排序、紧凑 UTF-8 JSON 做 SHA-256。因此接收时间变化不触发身份冲突；正文、目标、方向、版本、事件类型或发生时间改变仍冲突。摘要没有替换当前 Inbox 的全事件摘要；真实接入前要协调兼容策略。

`ReplayLedger` 演示：同事件重复不增加上下文；message/message.any 即便出现不同事件 ID，同消息同版本同内容也不重复推进；同版本不同内容拒绝；编辑和撤回逐次推进；ACK 不与文字记录折叠、不推进上下文；跨账号/会话复用内部消息 ID 拒绝。它只在内存中保存验收状态，进程结束即丢失，不是持久队列、数据库事务或 exactly-once 保证。

ACK 映射：PENDING(0)→unknown，SERVER(1)→sent，DEVICE(2)→delivered，READ(3)/PLAYED(4)→read。ERROR(-1) 返回 ACK_ERROR_NEEDS_RECONCILIATION，未知值和 ack/ackName 矛盾拒绝。本轮不把回执映射成客户确认，也不凭 PENDING 声称已提交；PLAYED 合并为 read 是现有 wire 枚举限制。

## 5. 本地运行

使用已安装锁定依赖的项目 `.venv`，从根目录运行，不需要数据库、WAHA 容器或公网服务器：

```powershell
# 全部 23 个合法/异常样例，预期拒绝也计作通过
.venv/Scripts/python.exe scripts/replay_waha.py
# 查看可运行案例
.venv/Scripts/python.exe scripts/replay_waha.py --list
# 查看修改事件的标准输出，文字仅来自合成样例
.venv/Scripts/python.exe scripts/replay_waha.py --case text-edited --show-events
# 重投、ACK、先到撤回被拒、补编辑后撤回成功
.venv/Scripts/python.exe scripts/replay_waha.py --sequence
# 独立模块测试
$env:PYTHONPATH = 'apps/backend/src'
.venv/Scripts/python.exe -m pytest apps/backend/tests/test_waha_adapter.py -q --basetemp=local-data/pytest-waha-a01
```

默认输出仅包含 case、pass、事件 ID/类型/摘要或稳定错误码，只有 --show-events 才打印合成标准消息。工具不接收真实账号、令牌或任意外部聊天文件。未知 case 非零退出；缺少依赖明确提示安装锁文件，不吐出原文或堆栈。测试临时目录只用于测试，其内容可被 pytest 替换。

七步演示预期：创建 context=1 → 重复仍为 1 → ACK 仍为 1 → 版本 3 的撤回先到被拒 → 版本 2 修改 context=2 → 撤回 context=3 → 撤回重投仍为 3。它验证失败后内存状态没有被污染，不验证数据库故障恢复。

## 6. 本轮实际证据

| 检查 | 实际结果 |
| --- | --- |
| Ruff check：apps/backend 和 export_contracts/smoke_replay/replay_waha | 通过 |
| Ruff format --check：同上 | 24 个 Python 文件符合格式 |
| export_contracts.py --check | domain 与已实现 OpenAPI 无漂移 |
| pytest apps/backend/tests，SQLite 回退 | 112 passed、1 skipped；其中新增适配测试 87 项；一个已知 Starlette/httpx 弃用警告 |
| replay_waha.py | 23 cases、0 failures（6 合法/17 预期拒绝） |
| replay_waha.py --sequence | 7 steps、0 failures |
| 单例 text-edited --show-events | 原消息 canonical ID、revision=2、UTC 时间和 schema 输出符合预期 |

文档 baseline 与最终差异检查的结果见本文件末尾的最终检查记录。pytest 没有设置 TEST_DATABASE_URL，跳过 PostgreSQL 并发领取测试；本轮不宣称验证行锁或数据库持久性。未改前端、迁移或部署，未执行前端构建、迁移或运行环境 HTTP smoke；真实 WAHA 与 E 人工验收未进行。

## 7. 与 E 的统一验收与下一步

E 可以一次运行语料、七步演示和测试，核对非法来源/归属/白名单、原消息引用、同身份冲突、连续版本、API 来源、回执含义以及安全错误，再记录缺陷和复测。自动测试通过不等于 E 已参与或真实接入完成。

本轮完成了 A-01 在“新增文件、独立验证”范围内的交付。完整 A-01 的共享接收事务、模型不调用断言、持久映射、数据库异常和旧提议失效集成仍沿用已有回放实现，并未新增 WAHA 证明。接入现有代码需要先取得用户同意并与 C 协调；后续 A-02 再做真实版本/引擎探测、鉴权、扫码和 adapter 挂接，A-03 验证持久恢复。不要直接用内存账本处理真实 Webhook。

## 8. 最终检查记录

- `.venv/Scripts/python.exe scripts/check_baseline.py`：40 个 Markdown 文件、152 个本地链接、3 个 schema、11 个合法/6 个拒绝共享样例及 12 个合成场景通过；模块的 23 个案例由 pytest/独立演示验证，不冒充 baseline 的样例数量。
- `git diff --check`：通过；变更范围检查确认已跟踪文件只修改本轮允许的 4 个 A 职责/演进文档，其他交付均为新增文件。
- 单人自查已核对现有 schema、来源与权限边界、双语记录、内存与持久化能力区分、合成分类及未包含私密数据。独立同伴评审、E 人工验收和真实接入未进行。
