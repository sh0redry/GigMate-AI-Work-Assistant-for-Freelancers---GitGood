# 附件读取与 A/B 对接批次

2026-10-10 · Andy_WAHA_media_ingestion，基于消息同步 56e482e。用户已授权原文件读取，并明确 **B 尚未接入真实模型，先完成 A 和对接协议**。[英文](../en/role-a-media-ingestion.md)、[ADR 0006](../en/adr/0006-owned-media-handoff.md)。仅对明确同意的请求替代 ADR 0005 暂缓读取的边界。

## A 实现什么

白名单媒体观察 → 对单附件明确同意下载 → 持久读取任务 → 私有文件及哈希 → 受保护预览/下载 → 可选调用 B 处理器 → 独立记录商户来源核对。收到 webhook 不自动下载、不自动调用模型、不确认工单、不发送消息。真实文件只能保存到私有本地目录/数据卷，不进入跟踪文件。

支持声明类型：PNG/JPEG/WebP、Ogg/MP3/WAV/M4A 音频、PDF、UTF-8 TXT。规范 audio/ogg; codecs=opus 等 MIME 参数，未知/不匹配类型明确拒绝。文件最大 20 MiB，TXT 最大 1 MiB。签名/UTF-8 检查是有限格式门槛，**不是完整解码、病毒扫描、PDF 解析或音频时长验证**；B 在模型调用前负责解析/页数/时长/token 限制。SVG/HTML/压缩包/Office/视频不属于本批。

已读取固定 WAHA Core 2026.9.1/WEBJS 源码：单消息 GET 支持 downloadMedia=true 覆盖默认值。全局事件/API 自动下载仍关闭。后端依据已有快照解析当前账号/聊天/方向，检查返回的消息，再接受可信 provider 来源下的 /api/files 路径，把文件 GET 固定到配置好的 provider 客户端；拒绝跳转、目录穿越、query 密钥并限制读取大小。不获取 webhook 或浏览器提供的任意 URL。[WAHA 媒体文档](https://waha.devlike.pro/docs/how-to/receive-messages/#media-files)。真实 API/文件格式仍需单独验收。

文件使用随机服务端标识及 SHA-256 完整性检查，不向前端/模型暴露存储键、路径、provider URL 或凭据。同源重复读取复用文件。捕获来源或字节变化推进附件版本；下载/模型前后检查账号活动、接收开关、当前白名单、来源指纹、上下文、授权版本及租约。暂停/撤权禁止提交结果，预览每次 GET 都检查权限，页面在访问失败时清除预览。已经交付或下载的字节不能追回。

下载最多三次尝试/退避，180 秒租约可恢复。模型不自动重试：不确定提交/处理租约过期记为 result_unknown，阻止此附件重复提交；明确 reconcile 仅排 B 的原请求只读查询，不再 process。不确定任务不阻塞其他附件。B 未配置时明确失败，已下载文件仍可预览。

## B 接入协议

A 提供 `gigmate.media_processing.MediaInput` 和 `MediaProcessor`，B 提供服务端工厂，通过 `GIGMATE_MEDIA_PROCESSOR_FACTORY=your.module:factory` 配置。A 不交付真实 provider、OCR、ASR 或 PDF 解析器，也没有运行时合成降级；测试处理器仅注入隔离夹具。

- `process(input) -> WahaMediaResult`：输入含受限 bytes、规范 MIME、说明文字、origin=live、账号/会话/快照/附件 UUID、附件/上下文版本、指纹、SHA、已记录 source_occurred_at。不含凭据/URL/路径。message_sent_at/timezone 明确保留未知，**不能把观察时间或服务器时钟当作原发送时间处理相对日期**。原发送时间/账号时区应先联合补齐，否则返回待核对问题。
- B 负责 OCR、语音转写、PDF/文本解析及可选 GenAI 业务建议；按 request_id 持久幂等/核对并保存不可变的账号/来源/哈希关联。调用在租约提交后，数据库业务锁外执行。
- 输出含 provider/model/prompt 版本、coverage=complete/partial/unknown、带页码或音频区间的文字片段、摘要、引用零起始 source_indices 的建议及待确认问题。最多 200 片段/100000 提取字符，引用须存在。未知保持未知；禁止 confirmed 字段、工单写入、工具权限和发送；严格拒绝额外字段。
- `ProcessingUnavailable` 表示 B 保证未提交；`ProcessingUncertain` 表示可能提交，不重试；其他异常保守处理。输出/日志不得泄露服务响应或密钥。
- `reconcile(request_id) -> result | None` 只查原请求，None 表示仍未知；B 返回前核对原账号/附件/指纹/哈希关联，绝不借核对重发。
- 来源/上下文变化隐藏旧建议和核对记录。商户核对仅记录来源已看过及备注，不改原结果、不确认业务字段、不授权执行。关键字段晋升需 B/C 另定附件证据协议；快照 UUID 不等于 canonical 消息修订。

## 接口和迁移

账号归属前缀 `/api/v1/connectors/{id}/media`，浏览器登录/CSRF、服务端归属校验；凭据仅在私有服务端配置。

| 路径 | 行为 |
| --- | --- |
| GET /capabilities | 存储/处理器配置、类型及大小限制 |
| POST /jobs | WahaMediaCommand + Idempotency-Key；下载和模型分开明确同意、expected_version、已授权快照；提交后 202 |
| GET /jobs/{id} | 安全阶段/状态/尝试/错误，不含正文/provider ID |
| POST /jobs/{id}/cancel | WahaVersionCommand；无法追回已提交的模型调用 |
| POST /jobs/{id}/reconcile | 版本化明确只读核对 result_unknown |
| GET /attachments?snapshot_id=UUID | 来源范围内附件及 latest_job_id，刷新页面可恢复任务状态 |
| GET /attachments/{id} | 版本/哈希/当前结果/核对，不暴露存储路径 |
| GET /attachments/{id}/content | 鉴权字节；no-store/nosniff/sandbox/same-origin；download=true 强制下载 |
| POST /attachments/{id}/review | 明确核对、附件/上下文版本、expected_result_job_id 及备注，绝不确认工单 |

新增 **0009_waha_media_ingestion** 接在 0008，增加 waha_attachments/waha_media_jobs，不改共享迁移；契约/类型由源生成。未启用媒体时，原暂停流程不依赖新表；启用前必须升级 head。文件/结果/备注按捕获来源时间 30 天到期；worker 也清理旧无引用文件，保留无关文件。没有完整账号/备份删除。WAHA 自身媒体缓存另有保留问题，停止/关闭维护不会删除已有卷。

后端镜像把媒体挂载目录初始化为 appuser 所有、0700；API/worker 以非 root 用户共享卷，已有卷须验证可写。完整缓存的处理不依赖 WAHA 凭据；损坏/缺失缓存仅在明确请求及 provider 配置有效时重新获取。核对还检查原文件完整性及确切结果任务，防止新结果继承旧核对。

## 启动与一次性人工验收

保留原会话/绑定/数据库/授权，**不因升级重新 provision 或给 WAHA 库 seed 虚构工单**。新团队安装可设置 WAHA_MEDIA_ENABLED=true 后用 waha_team.py up，自动加[媒体 Compose](../../infra/waha-media.compose.yaml)。B 工厂和凭据另由操作者私下配置；B 未交付前保持工厂未设置。

本机旧安装（数据库已在 16433），根目录 PowerShell：

```powershell
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:16433/gigmate_waha_a03'
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini check
$env:WAHA_DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@host.docker.internal:16433/gigmate_waha_a03'
$env:WAHA_MEDIA_ENABLED = 'true'
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml -f infra/waha-media.compose.yaml -f local-data/waha-a02/restart-policy.override.yaml up --build -d --no-deps --wait ingress ingress-worker
```

最后的私有重启覆盖仅在本机存在；其他安装使用自己的数据库/私有设置和 unless-stopped 选择。原生 API/worker 共用绝对私有 WAHA_MEDIA_ROOT 并启用 WAHA_MEDIA_ENABLED=true，全局事件/API 自动下载仍关闭。

1. 自己账号工作台，在已授权且同意测试的聊天发送图片、语音、PDF、TXT，重载时间线。队友各用自己的账号/文件，不跟踪真实内容。
2. 打开 **附件读取与核对**，仅同意下载，读取后预览/下载；刷新重开应恢复任务/文件，不自动重读。核对 TXT UTF-8/大小，音频/PDF 原生解码为人工格式门槛。
3. B 未配置时模型选项不可用，无假 OCR/GenAI 成功。后端明确请求处理应返回任务错误 MEDIA_PROCESSOR_NOT_CONFIGURED，但保留文件。B 适配器为后续依赖。
4. 足够长下载中暂停/撤权/撤回或编辑媒体，结果须被抑制，缓存预览失效；明确恢复后再请求，不自动重授权或重试。
5. 下载中重启 worker，检查租约恢复及单文件发布。错账号/无 CSRF/大小/类型/恶意 URL 用自动夹具，不泄露真实凭据。
6. B 安装真实适配器后才明确授予模型同意：核对原文件、提取片段/范围、建议/待确认问题，再标记来源核对。旧来源/上下文不能核对；不确定结果只读查原请求，不盲目重发。这不是发送或工单创建。

自动合成检查验证 A 管道和注入的 B 结果结构，不证明真实 OCR/ASR/模型准确率。实际次数、运行证据及 B/真机门槛见[进度](progress.md)。

本机已升级 0009，媒体 API/worker/存储已启用，处理器未设置；没有自动读取真实文件。浏览器自动化助手两次都无法启动 Node runtime，故页面视觉/真实音频/PDF 行为留人工验证。自动音频/PDF HTTP 夹具仅验证传输/签名门槛，不证明有效解码/解析。本机直接从真实工作台开始人工步骤，不为验收重复迁移/provision。
