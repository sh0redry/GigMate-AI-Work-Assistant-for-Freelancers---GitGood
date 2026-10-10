# 附件读取与 A/B 对接批次

## 第二批：原消息时间、来源核对与业务交接

在兼容 PR #16 的媒体分支上完成 A 的部分。真实 OCR/语音转写/PDF 解析/GenAI 仍依赖 B，外部发送不在本批范围。PR #18 尚未合并，也不是媒体处理器。

- 新增 **0010_waha_media_evidence**，接在未修改的 0009 后。`waha_snapshots.message_sent_at` 只从新观察到的原消息/历史消息 payload 中受限的数字 Unix 秒 `timestamp` 记录；编辑/撤回不覆盖原值，旧快照保留空值。缺失、格式错误、毫秒形态或非有限数保持未知，不用事件 occurred_at 或观察时间替代。收据摘要/来源指纹不变，时间字段不会破坏原有重复事件身份。[供应商事件示例](https://waha.devlike.pro/docs/how-to/events/)分别提供消息时间和修改引用；仍需用自己的账号验证引擎实际行为。
- `WahaMediaCommand.timezone` 可选填写合法 IANA 时区，由商户明确指定**本次请求**适用的时区，不冒充账号/客户时区；前端不根据电脑或号码默认选择。任务的 input_context 在排队时固定消息时间、时区及来源 merchant_choice/unknown、事件时间和观察时间，随受限 bytes 交给 B。旧任务不补造时间；改变时区不能复用原幂等键。显示结果保留生成它的时间依据，不继承后续任务的时区。原发送时间或适用时区不足时，解释相对日期前必须返回待确认问题。
- 建议中的来源可点击定位到文字片段。来源核对额外绑定确切结果任务、附件版本及 SHA；没有这些绑定的旧核对记录需明确重新核对才能交接，不要求重新下载或重新调用模型。
- 已实现只读 **GET /api/v1/connectors/{id}/media/attachments/{attachment_id}/evidence**，查询参数必须提供 expected_attachment_version、expected_context_version、expected_result_job_id。必须先核对当前结果；读取时重新检查归属、白名单、接收状态、来源、有效期与文件完整性，返回 no-store 的 WahaMediaEvidence 0.1.0。资料包括应用 UUID、来源指纹/哈希、固定时间依据、结果及片段/建议、核对与有效期，不包含供应商 URL/密钥/路径或执行权限。页面“查看业务交接资料（不写入工单）”只在核对后读取；暂停、权限/读取失败或刷新发现结果/上下文变化时清除展示。
- **C 的业务消费仍待接入**：在实际业务命令中重新读/校验证据；确定一个工单，歧义时交人工；保留附件/结果/哈希/片段出处，不能冒充规范文本 SourceRef；绑定目标工单和上下文版本。已复制资料不是持续授权。读取交接资料、核对来源不等于客户确认、商户业务批准或创建工单。本批不实现晋升/业务写入或外部执行批准。

### 一次性验收

1. 先恢复 Docker Desktop，保留原会话、私有配置和数据库，不 provision/seed。用原数据库 URL/PYTHONPATH 执行 Alembic upgrade head 和 check，再用原媒体 Compose 重建 API/worker。**此前记录的本机部署仍是 0009，本批没有部署 0010**；新代码需使用 0010。上方升级命令仍适用，不为升级重新初始化。
2. 在自己的已授权测试聊天发送图片、语音、PDF、TXT，说明文字使用虚构的相对日期。打开真实工作台，明确填写适用时区（如 Asia/Hong_Kong）或留未知，同意并读取，检查预览/刷新/任务恢复。对照手机核对原消息时间，不能与事件/观察时间混为一谈；编辑说明后原发送时间保持。旧记录没有依据就显示未知。
3. B 未配置时不期待 OCR、不开启模型同意，保留明确提示。B 提供 process/reconcile 后，核对其收到的时间/来源/哈希、页码/音频位置、覆盖范围和待确认问题。改变时区须新建明确任务，不复用不确定请求、不盲目重提。
4. 点击来源片段，对照原文件和结果，标记来源已核对后才读取交接资料。核对版本/哈希/结果 ID，确认没有新增工单/日历/发送。旧的未绑定核对需重新核对。
5. 暂停/取消授权/撤回或编辑原附件/改变会话上下文，交接及结果访问必须拒绝或消失。旧结果 ID、损坏文件用合成夹具测试。恢复操作必须明确进行，已复制/下载的内容无法收回。
6. Docker 可用后补跑隔离 PostgreSQL/HTTP、真实浏览器及 Windows/Apple Silicon 检查，由 E 独立评审。DOM 夹具和 SQLite 不证明真实供应商/模型或 PostgreSQL 锁。统一自动证据记录在进度文档。

2026-10-10 · Andy_WAHA_media_ingestion，基于消息同步 56e482e。用户已授权原文件读取，并明确 **B 尚未接入真实模型，先完成 A 和对接协议**。[英文](../en/role-a-media-ingestion.md)、[ADR 0006](../en/adr/0006-owned-media-handoff.md)。仅对明确同意的请求替代 ADR 0005 暂缓读取的边界。

## A 实现什么

白名单媒体观察 → 对单附件明确同意下载 → 持久读取任务 → 私有文件及哈希 → 受保护预览/下载 → 可选调用 B 处理器 → 独立记录商户来源核对。收到 webhook 不自动下载、不自动调用模型、不确认工单、不发送消息。真实文件只能保存到私有本地目录/数据卷，不进入跟踪文件。

支持声明类型：PNG/JPEG/WebP、Ogg/MP3/WAV/M4A 音频、PDF、UTF-8 TXT。规范 audio/ogg; codecs=opus 等 MIME 参数，未知/不匹配类型明确拒绝。文件最大 20 MiB，TXT 最大 1 MiB。签名/UTF-8 检查是有限格式门槛，**不是完整解码、病毒扫描、PDF 解析或音频时长验证**；B 在模型调用前负责解析/页数/时长/token 限制。SVG/HTML/压缩包/Office/视频不属于本批。

已读取固定 WAHA Core 2026.9.1/WEBJS 源码：单消息 GET 支持 downloadMedia=true 覆盖默认值。全局事件/API 自动下载仍关闭。后端依据已有快照解析当前账号/聊天/方向，检查返回的消息，再接受可信 provider 来源下的 /api/files 路径，把文件 GET 固定到配置好的 provider 客户端；拒绝跳转、目录穿越、query 密钥并限制读取大小。不获取 webhook 或浏览器提供的任意 URL。[WAHA 媒体文档](https://waha.devlike.pro/docs/how-to/receive-messages/#media-files)。真实 API/文件格式仍需单独验收。

文件使用随机服务端标识及 SHA-256 完整性检查，不向前端/模型暴露存储键、路径、provider URL 或凭据。同源重复读取复用文件。捕获来源或字节变化推进附件版本；下载/模型前后检查账号活动、接收开关、当前白名单、来源指纹、上下文、授权版本及租约。暂停/撤权禁止提交结果，预览每次 GET 都检查权限，页面在访问失败时清除预览。已经交付或下载的字节不能追回。

下载最多三次尝试/退避，180 秒租约可恢复。模型不自动重试：不确定提交/处理租约过期记为 result_unknown，阻止此附件重复提交；明确 reconcile 仅排 B 的原请求只读查询，不再 process。不确定任务不阻塞其他附件。B 未配置时明确失败，已下载文件仍可预览。

## B 接入协议

A 提供 `gigmate.media_processing.MediaInput` 和 `MediaProcessor`，B 提供服务端工厂，通过 `GIGMATE_MEDIA_PROCESSOR_FACTORY=your.module:factory` 配置。A 不交付真实 provider、OCR、ASR 或 PDF 解析器，也没有运行时合成降级；测试处理器仅注入隔离夹具。

- `process(input) -> WahaMediaResult`：输入含受限 bytes、规范 MIME、说明文字、origin=live、账号/会话/快照/附件 UUID、附件/上下文版本、指纹、SHA、已记录 source_occurred_at。不含凭据/URL/路径。message_sent_at/timezone 为第二批补齐的可空证据，**不能把观察时间或服务器时钟当作原发送时间处理相对日期**。原发送时间/账号时区应先联合补齐，否则返回待核对问题。
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

本机已升级 0009，媒体 API/worker/存储已启用，处理器未设置；没有自动读取真实文件。浏览器自动化助手两次都无法启动 Node runtime，故页面视觉/真实音频/PDF 行为留人工验证。自动音频/PDF HTTP 夹具仅验证传输/签名门槛，不证明有效解码/解析。第二批须先按上方说明升级到 0010 再重建 API/worker，不为验收重新 provision。

## 处理器工厂评审修复

服务端工厂返回的对象必须同时具备可调用的 `process` 和 `reconcile`。缺少方法或方法不可调用时，在提交前以 `ProcessingUnavailable` 拒绝。配置格式错误、模块无法导入、工厂名称缺失或不可调用属于配置错误。工厂构造函数抛出的异常由 `processor()` 原样透传，方便 B 排查实现缺陷；worker 仍保守记录意外处理异常，不会盲目重新提交。接口校验不会调用上述两个方法。
