# WAHA 本地产品接入后端：交付与统一验收

2026-10-08 扩展：[统一适配](role-a-integration-acceptance.md)已接入 D 页面，新增故障审阅、0006 provider 采样和旧操作记录承接。inspect/discover 不推进 control_version。下方初期范围和证据按日期保留，前端页面已不再待做。

日期：2026-10-07；Andy_WAHA_upgrade，基于 main 0cd7e3f。[英文对应](../en/role-a-setup-api-acceptance.md)。范围为一个私有配置的本地 Core/WEBJS session 的后端接入，不做页面、生产身份、任意多商户/session 注册、AI、历史导入、发送或 Cloud API。

## 已实现的结构

操作者仍先用 team init/up（或旧安装流程）准备自己的环境。浏览器登录确定本地应用账号，服务端私有配置及数据库映射确定其唯一连接；浏览器不能提交服务端密钥、供应商地址、session 或账号归属。所有控制写操作校验 session/CSRF、来源、control_version 和归属，事务提交后才响应成功。只读鉴权不再持有账号写锁，取私有二维码时不会在整个供应商请求期间占用消息接收的账号锁。

迁移 0005_waha_controls 保留旧数据，增加 control_version、持久 WahaControl 操作/租约及有期限的 WahaCandidate 元数据。操作由独立 Worker 执行，与正文队列共用进程但不是 AI/业务任务。API 保存意图并返回 202，不在请求中执行供应商写操作。同连接请求键唯一，同键同内容返回同一操作，不再次调用供应商。每个连接只允许一个活动控制操作；待执行两分钟后过期，执行租约两分钟过期进入 result_unknown，不自动重试写操作。租约 token 阻止过期 Worker 覆盖后续核对结果；PostgreSQL 控制锁/语句上限 3/5 秒。

## D 可直接使用的接口

统一前缀 `/api/v1/connectors/{connection_id}`，应用 UUID 来自已登录 GET /api/v1/connectors。使用 api.d.ts 生成类型，不把供应商凭据给前端、不直接调用 WAHA。

| 方法/路径 | 输入与结果 |
| --- | --- |
| GET /setup | control_version、启用、配置可用、采样供应商状态/时间/过期、活动/最近操作 UUID |
| POST /operations | WahaControlCommand + Idempotency-Key，connect/recover/inspect/discover，返回 202 WahaControlResult |
| GET /operations/{operation_id} | 按归属查询，只返回安全状态/错误码 |
| POST /operations/{operation_id}/reconcile | WahaVersionCommand，显式对 result_unknown 做只读供应商核对，不重发 |
| GET /qr | 有归属、启用且等待扫码时返回 PNG，no-store/nosniff，不写文件或日志，配对材料仅短暂展示 |
| GET /chats | 已选聊天应用 UUID、未过期发现 UUID/标签，不返回 provider ID |
| PUT /chats | expected_version、selected_ids、consent=true，替换授权集合，不自动恢复暂停 |
| POST /pause、/resume | expected_version，暂停持久拒绝接入、恢复须显式；不删 session、不清缺口核对 |
| POST /recovery-issues/review | WahaIssueReviewCommand，明确无需导入后，原子核对自己连接的已恢复故障并保留历史 |

写请求示例：

```json
{"action":"connect","expected_version":1}
```

```json
{"expected_version":2,"selected_ids":[],"consent":true}
```

版本仅为示例，新意图先 GET setup。相同 POST 意图重试保留同一个请求键和原请求体，丢响应后不能另造键；新意图才使用新键与当前版本。操作结果返回原提交快照版本，当前版本读 setup。恢复/选择采用版本比较，旧请求重试会返回 WAHA_SETUP_VERSION_CONFLICT，应重新读取，不能盲写旧选择。

### 页面调用顺序

登录 → GET connectors/setup → 暂停时显式 resume → POST connect → 轮询操作。新 session 直接配置签名业务回调；已有正确 session 只核对，不覆盖回调，probe/其他回调不匹配时由操作者核对配置。操作 succeeded 不代表 WhatsApp 已就绪。SCAN_QR_CODE 时短暂显示 PNG，用完释放 object URL，配对材料不进入埋点、截图或公共样例；STARTING 用 inspect/状态轮询，FAILED/STOPPED 用显式 recover。过期样本不当当前连接状态，端到端就绪看 ConnectorStatus.pipeline_ready。

WORKING 后：POST discover → 轮询 → GET chats → 明确同意和选择 → PUT chats。只发现最多 100 个近期聊天，不是完整目录；选择项十分钟过期，限定账号/连接，过期/外部/重复标识拒绝且不改授权。保存的是有限私有联系人元数据，不是聊天正文；每小时维护删除过期候选。已选项使用持久应用 UUID 和通用标签，供应商标识留服务端。

PUT 后刷新 setup/chats，使用持久已选 UUID，不长期保留过期发现标识。已选项有匹配的未过期发现记录时显示名称，否则显示通用标签；重新 discover 更新名称。标签按不可信普通文字显示，不作为 HTML。取二维码后再次校验授权/版本，取图期间暂停或配置变化不返回图；WAHA_NOT_WAITING_FOR_QR 返回 409，页面应刷新状态，不当作图片加载故障。

移除授权推进会话上下文，再授权也不能使旧提议重新有效；正文任务仍检查当前同意/版本。CLI provision/pause 也推进 control_version，provision 推进变化的会话上下文。浏览器选择以数据库为准，不回写主机配置；之后 CLI provision 会按主机 allowlisted_chats 明确替换，不要随意混用两套授权来源。up/重启保留数据库授权与暂停状态。

## 未知结果与限制

result_unknown 阻止新活动供应商操作。显式 reconcile 仅调度 GET 核对；connect/recover 必须匹配本连接签名回调，recover 仍 FAILED/STOPPED 就继续待核对。不确定 discover 可转 failed/WAHA_DISCOVERY_REISSUE_REQUIRED 后明确发起新读取。策略保守，有些未发生写入的模糊错误也可能需操作者核对。没有任意放弃/重发接口，不自动认领不匹配回调。最后数据库写失败保留 running，租约过期后进入 unknown。暂停不能撤销已经发起的远程操作，但业务接收仍拒绝。操作核对与 recovery-issues 历史缺口不同，不自动确认历史故障。

安全错误包含 CONTROL_DISABLED/CONFIG_INVALID、CONNECTOR_PAUSED、版本冲突、幂等键错误、选择过期/无效、OPERATION_NEEDS_RECONCILIATION 及供应商固定错误码。控制接口仅用于开发，生产限流、密钥轮换和多实例调度仍待做；未知操作可占用本地 session 控制队列，但正文任务继续处理。

## 部署与检查

先将数据库升级 head，再重建 API/Worker。Compose 将 WAHA_CONTROL_CONFIG、WAHA_CONNECTOR_CONFIG 通过只读私有卷同时给两者，内部供应商目标固定。主机开发可指定私有文件路径，不设置 WAHA_CONTROL_INTERNAL；凭据不进入浏览器。team up 自动迁移/重建，已配对 session 不需要另造账号或二维码。

```powershell
.venv\Scripts\python.exe scripts/check_waha_setup.py --run --suite
```

脚本拒绝已有 gigmate-waha-setup-check 资源，在 16432 启动一次性 PostgreSQL 17.9、18802 实际 API/Worker、18800 合成供应商，不创建真实 WhatsApp 连接/二维码/消息；假配对字节仅验证 HTTP。检查持久连接/幂等、二维码权限/缓存、发现/选择/版本、暂停/恢复、Worker 重启和跨账号拒绝，可接着跑全套 PG 测试。finally 仅停止子进程并删除独立测试项目，不当作真实账号独立验收。

独立人工步骤：自己的获授权测试账号上检查 setup/inspect、需要时扫码、发现/选择正确聊天、新建/编辑/撤回、移除授权、暂停/恢复和重启。只记录应用不透明 ID，真实聊天/密钥/二维码不入仓库。E 复核事务/并发/未知结果，D 按接口做页面，B/C 保留真实处理/审批职责。本机证据和受阻真实账号验证见 progress.md。

### 本机已准备好的人工环境 — 2026-10-07

已提交快照 cf14815，未 push。保留原数据库/会话卷，通过忽略的 `local-data/waha-a02/database-port-override.yaml` 将原数据库映射到 16433，避开 Windows 保留的 54329。已升级 0005、Alembic check 通过，重建 18702 的 API/Worker/监控，容器数据库地址改用内部 16433；原账号恢复 WORKING，业务回调匹配。主机 DATABASE_URL 使用原 gigmate_waha_a03 的 16433 地址；后续重新创建 Compose 要保留数据库覆盖文件及 WAHA_DATABASE_URL 内部 16433。新团队安装默认未改。

已代跑 273 项 PostgreSQL 及独立 HTTP/Worker 六个流程检查点与清理。真实本机账号的七项 HTTP、setup/配置可用、inspect、discover（87 个私有选项）、重复键一致、CSRF 拒绝及跨账号拒绝通过。connect 对已连接 session 核对成功，没有覆盖回调。真实自动检查未发送消息、未取二维码、未改白名单、未实际暂停或确认故障。

仅此机器已准备忽略的 `local-data/waha-a02/manual_setup_cf14815.py` 本地测试客户端，按已提交 HTTP 协议调用，不直接管理 WAHA；不属于仓库/队友安装文件。Windows 前缀为 `.venv\Scripts\python.exe`，数据库工具先设本机 localhost:16433/gigmate_waha_a03。

1. 客户端 `discover` 仅在本地看名称/不透明 ID。测试聊天已经 selected=true 就保留；否则 `select --choice <UUID>` 并输入 YES，其他已选聊天不变。不要分享联系人列表。
2. `waha_team.py checkpoint` 后，手机新发一条文字、编辑一次、为所有人删除；每次 `waha_ingress.py status`，最后 `waha_team.py verify` 应为 mutation_sequence_verified=true。这些手机操作需本人完成。
3. 客户端 `pause` 后新发测试文字，确认 enabled=false/pipeline_ready=false，该文字不推进 last_sync_at，拒绝应为 CONSENT_REVOKED。保持暂停等待已配置的有限回调重试结束，再 `resume`，发一条全新文字验证恢复；不保证暂停期间消息自动导入。
4. 测移除授权先客户端 `status` 刷新，取当前 selected 的持久 UUID，`remove --choice ...` 输入 YES，发测试文字应 CONVERSATION_NOT_ALLOWED 且不推进正文同步；重新 discover/select 恢复。候选 ID 会过期/更换，不在 API 验收中运行 CLI provision，避免按主机旧白名单覆盖。
5. 账号已 WORKING 不强制注销来取二维码。仅自然出现 SCAN_QR_CODE 时客户端 connect、qr，打开打印的私有路径扫码，再 inspect。不向聊天上传二维码/凭据/截图。POST 超时保留了原键/请求体，使用 retry，不换新键；result_unknown 停下来显式核对。
