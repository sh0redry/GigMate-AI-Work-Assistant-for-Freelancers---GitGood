# D-01：前端扫码连接与会话选择

负责人 Kyrie。2026-10-06 在 `Kyrie_Frontend` 准备，基础是 `main` 合并提交 `0cd7e3f`。用户要求创建本地提交，message 为 `还没测试`；不推送。2026-10-07 已尝试真实 WhatsApp 扫码，但尚未成功，用户验收仍待完成；验证证据记录如下。[英文对应](../en/role-d-stage1-acceptance.md)。

## 范围与当前结果

本批只修改 `apps/web` 内前端文件，以及这一对 D 专属验收文档。后端、WAHA 工具、迁移、基础设施、依赖、共享文档、契约及生成类型与 main 完全一致。之前未提交的 D-01 后端／共享改动已私下备份到 Git 忽略的 `local-data`，并移出当前改动范围。

PC 工作台提供扫码区域、连接与处理状态、会话勾选、明确保存、撤销及放弃更改，以及清楚标记的合成演示。会话读取授权不会开启自动回复；自动回复与消息发送属于后续独立里程碑。

真实模式使用 main 已有的鉴权连接查询与故障记录查询，分别显示连接状态、采样就绪度、状态新鲜度、接收权限及待核对问题。产品扫码和会话选择接口仍待实现。明确启用本机开发入口后，可以通过 Andy 未修改的服务端适配器在页面内显示真实扫码状态与二维码；默认开发和生产构建仍禁用扫码。真实模式的启动／重启和会话选择按钮保持禁用，浏览器不会直接调用 WAHA 管理接口。

演示仅保存在浏览器内存中，可以模拟扫码、连接／断线、状态过期、选择、保存及断线撤销。离开演示或刷新页面就会重置。二维码位置是占位展示，不能真正扫描。演示成功不能证明数据库写入、真实授权、扫码或送达。

**D-01 端到端验收仍需 Andy 的产品接口及真实账号测试。** 本批前端不实现这些接口。

## 需要和 Andy 对齐的接口

main 已实现且真实模式使用：

| 查询 | 前端用途 |
| --- | --- |
| `GET /api/v1/connectors` | 账号隔离、分页的 `ConnectorStatus`；使用 main 的生成类型 |
| `GET /api/v1/connectors/{id}/recovery-issues` | 账号隔离、分页的 `RecoveryIssue`；使用 main 的生成类型 |

下列产品接口及字段只是**前端建议**，请 Andy 确认或调整。它们没有写入共享契约，也不代表产品后端已经实现。下文的本机开发入口不能代替这些接口。

| 建议接口 | 所需行为 |
| --- | --- |
| `GET /api/v1/connectors/{id}/pairing` | 当前扫码状态、`connected`、`qr_available`；只允许登录的归属账号查询 |
| `POST /api/v1/connectors/{id}/pairing/start` | 启动／重连自己的会话；结果未知时不能盲目重试 |
| `GET /api/v1/connectors/{id}/qr` | 等待扫码时返回私有、不缓存的 PNG；不暴露密钥及 provider session 文件 |
| `GET /api/v1/connectors/{id}/chats` | 分页发现会话元数据，供可视化勾选；不返回消息正文 |
| `GET /api/v1/connectors/{id}/selection` | 权威版本及已选会话；断线时仍可读取 |
| `POST /api/v1/connectors/{id}/selection` | 根据预期版本及服务端签发的会话选项原子替换；空列表表示撤销全部 |

`src/connection-api.ts` 中的 `Pairing`、`Choice`、`Selection`、`Discovery` 只是演示用的前端暂定类型，不是权威领域模型。建议授权返回 `{version, selected}`；选项为 `{choice_id, token, name, kind, selected, conversation_id}`；发现列表为 `{items, next_offset}`。ID／token 归属必须由服务端验证。对齐后由 Andy 负责后端模型、迁移、API 及契约生成；D 在后续接入生成类型并开启真实适配器。

开启写入前需对齐返回包装、分页、过期／错误码、同源会话鉴权、CSRF 与幂等约定。保存／撤销应在刷新后保持，核对版本并更新权威白名单；获得授权前不能存业务正文或调用模型。写入结果未知时需核对。前端不能持有 WAHA 密钥、webhook 密钥或 provider session 文件。这里授予读取／处理权限，不是自动回复权限。

## Windows／Mac 预览与已有接口

在 `apps/web`，安装仓库固定版本的 Node／npm 依赖后：

```bash
npm run dev
```

打开 http://127.0.0.1:5173，点击 **D-01 演示预览**。预览无需 Docker 或登录。查看真实状态时，按 main 原有说明启动后端，登录后进入 **WhatsApp 连接**。没有已配置连接的账号会显示空状态。后端环境仍由对应负责人维护，参见[现有启动说明](../en/getting-started.md)与 [Andy 本地开发指南](role-a-team-local-development.md)。

Vite 默认代理仍为 `http://127.0.0.1:18000`。如要查看自己已经配置的 ingress 后端，只设置前端进程环境：

```bash
GIGMATE_API_URL=http://127.0.0.1:18702 npm run dev
```

代理只接受本机 HTTP 地址。这只选择已有后端，不会初始化 WhatsApp 或补产品接口。后端原有的 origin／鉴权要求仍适用。

要在页面显示真实二维码，需使用自己已初始化、绑定当前工作目录的 Andy 团队环境，保持服务及会话运行，然后在 `apps/web` 启动前端：

```bash
GIGMATE_API_URL=http://127.0.0.1:18702 GIGMATE_LOCAL_PAIRING=1 npm run dev
```

Windows PowerShell 对应命令，同样在 `apps/web` 运行：

```powershell
$env:GIGMATE_API_URL = "http://127.0.0.1:18702"
$env:GIGMATE_LOCAL_PAIRING = "1"
npm run dev
```

网页使用标准浏览器 API。本机入口在 Windows 选择 `.venv/Scripts/python.exe`，在 Mac 选择 `.venv/bin/python`，通过路径解析和无 shell 的调用执行，并隐藏 Windows 子进程控制台。每台机器均需自行初始化 Andy 原有团队环境，安装仓库固定版本 Node／npm／Python 依赖并保持 Docker 服务运行。Mac 已验证；Windows 已核对代码兼容性，仍需队友实际运行验收。Apple 芯片 Mac 仍需下文记录的兼容 WAHA 镜像／平台配置，本前端不修改 Andy 的 Compose 文件。

登录本地工作台并进入 **WhatsApp 连接**。provider 为 `SCAN_QR_CODE` 时，页面自动把最新 PNG 载入浏览器内存，可见时每 20 秒更新，也可以手动刷新。图片获取 30 秒后若尚未替换就隐藏；provider 可能更早轮换二维码。不再需要在「预览」打开 PNG。本入口不会读取或重写原来被忽略的 `qr.png`。退出登录、状态／二维码读取失败、provider 不再等待扫码，以及离开工作台都会清除图片并释放对象 URL。显示成功不能证明手机关联成功。

`apps/web/local-pairing.mjs` 是 Vite 开发中间件，需明确启用，生产服务／构建不包含此入口。只读路径为 `GET /__gigmate_local_pairing/{connection_id}/status` 和 `/qr`。请求需通过本机 socket／Host、同源、自定义请求头及工作台登录校验。获取前后通过 main 原有连接接口确认归属和接收开关；Python 进程还核对工作目录 profile 与私有连接 binding。浏览器只收到安全状态字段或私有、不缓存的 PNG，密钥留在原有 Python 服务端适配器中。不会变更会话、查询聊天、写白名单或发送消息。这不是可部署的产品登录接口；后续鉴权产品接口与共享契约仍由 Andy 负责。

## 验收证据

2026-10-06 的验证证据记录在这里，不修改共享进度文档：

- 范围核对：相对 main 只有 5 个前端文件（`main.tsx`、`vite.config.ts`、`ConnectionWorkspace.tsx`、`connection-api.ts`、`connection.css`）和这两份 D 文档不同。提交前没有暂存改动，分支 HEAD 等于 `0cd7e3f`。后端／WAHA、共享契约／生成类型、依赖锁及共享文档与 main 字节一致。
- 前端 `check:api`、`format:check`、TypeScript 及生产构建通过。使用固定版本 Node 24.15.0／npm CLI 11.12.1。
- 未修改的 main：契约导出检查、基线检查（52 个 Markdown／253 个本地链接）、Ruff 检查／格式及 pytest 通过：**248 通过，5 跳过**。PostgreSQL 专属用例跳过，不声称验证了 PostgreSQL 锁行为。
- 使用 main 原有迁移创建新的、被 Git 忽略的 SQLite 开发库，填入虚构账号，Alembic check 通过。已替换此前 D-01 后端进程，从 main 源码重新启动。真实本地 API 登录、连接空状态及原有工单回放读取通过。
- 纯浏览器演示：没有业务 API 请求；选择／保存／放弃、刷新状态保留未保存勾选、断线撤销、状态过期及离开演示重置均通过。
- 拦截生成的合成样例匹配 main 状态／故障接口：连接分页、多连接、当前连接移除、分别显示连接／就绪／核对状态、网络失败／恢复及 401 清除数据均通过。扫码／会话／保存／撤销按钮保持禁用，没有请求未实现的连接接口或执行 HTTP 写入。
- 桌面及 320／375 像素的演示／真实模式样例布局通过，无横向溢出或页面错误。已目视检查桌面／移动截图。合成截图与浏览器检查脚本只保留为被忽略的本地文件。

前端必跑命令：`npm run check:api`、`npm run format:check`、`npm run build`。契约及基线检查使用未修改的 main 源码。浏览器验收需区分真实 main API 响应与拦截生成的合成状态样例。

外部验证待完成：真实 WAHA 手机扫码、真实会话发现、持久化保存／撤销及独立队友评审。后续 PostgreSQL 证据记录在下文；合成预览及 SQLite 开发登录均不能证明真实接入。

## 2026-10-07 电脑控制验收

按用户要求，在可见的本地浏览器直接操作已提交的 D-01 前端（`d0859f0`）。模拟扫码、载入会话、明确保存、刷新状态保留未保存勾选、放弃更改、断线撤销、过期／核对提示及离开演示重置均通过。真实本地开发登录、原有回放读取、退出登录及 API 停机／恢复状态通过。演示写入仅在浏览器内存中，不是真实会话授权。合成验收截图保留在被忽略的 `local-data`。

Docker Engine／Compose 已可用。使用 Andy 未修改的团队工具初始化新的本机私有环境，白名单为空，数据库为独立的 PostgreSQL 17.9。未修改的后端全套测试使用隔离的 PostgreSQL 测试 schema，结果为 **253 通过、没有跳过**（保留一项原有 Starlette／httpx 警告）。没有修改 main／共享源码或生成契约；本次只在 D 的两份文档记录证据。未新增提交或推送。

Mac 兼容问题：固定 WAHA 镜像没有 `linux/arm64/v8` manifest，因此原有团队启动在这台 Apple 芯片 Mac 上失败。通过标准输入传入临时 Compose 配置，仅为 WAHA 服务设置 `linux/amd64`，未修改已跟踪的 Compose 文件。Andy 需要决定团队工具如何支持／说明 Apple 芯片 Mac。兼容镜像随后下载成功，六项本地服务全部启动。doctor 确认 Docker／数据库／binding／API 健康。先确认 provider 会话不存在，创建一次后状态为 `SCAN_QR_CODE`。使用现有 CLI 生成私有 PNG，核对为 Git 忽略且权限为 0600，并在 Mac「预览」打开供用户扫码；没有把二维码内容写入已跟踪证据。前端仅通过进程环境 `GIGMATE_API_URL=http://127.0.0.1:18702` 重启，main 原有接口登录成功，并显示真实连接中状态、新鲜度及故障核对；缺失的产品接口仍禁用。接收白名单保持为空。用户报告手机提示 `Can't link new devices right now`；provider 仍为 `SCAN_QR_CODE`，没有到 `WORKING`。通过现有 CLI 更新一次二维码，确认图片已变化，并重新打开供及时重试；这不能证明手机错误的原因。真实扫码仍未验证通过。

重试后手机仍显示相同提示，用户决定结束真实扫码测试。用户怀疑账号原因，本次验证未能确定原因。没有继续扫码、重置会话或排查手机账号。最终真实页面显示会话未连接、处理链路尚未就绪；不含二维码的截图保留为被忽略的本地文件。本地服务暂保留供以后测试，不能据此认定 D-01 真实接入验收通过。

## 2026-10-07 页面内二维码修正

用户要求把二维码显示在浏览器页面，而非单独打开本地图片，并授权显示验证通过后创建本地提交。改动只涉及 D 的前端开发中间件／配置、前端适配器／工作台、测试及这两份文档。Andy／B／C 源码、基础设施、迁移、依赖、共享文档、生成类型及契约未改。后续跨平台核对请求已授权发布 `Kyrie_Frontend`，并向 `main` 发起 PR，由队友审核和合并。

电脑控制确认真实页面内图片成功解码为 **276×276**，使用内存 blob URL，手动刷新重新载入，可见时自动更新；退出登录后清除，重新登录后再次显示。provider 进入 `FAILED` 时，页面按预期隐藏二维码；确认失败状态后，仅使用一次 Andy 原有 CLI 重连，恢复 `SCAN_QR_CODE`，页面再次载入图片。合成演示仍使用虚构连接／会话数据，不含真实二维码。本次不重新尝试手机扫码，也不声称已到 `WORKING`。二维码下方控件的截图只保留在被忽略的 `local-data`，不含二维码像素。

在 `apps/web` 运行 `node --test local-pairing.test.mjs`，八项入口测试覆盖：鉴权图片／状态、拒绝无效登录／来源／Host／连接、暂停权限、获取期间登录过期、分页归属、无效 PNG／provider 错误、已连接时拒绝二维码、后端不可用及项目 Python 环境缺失。同时运行原有前端 API／格式／构建检查，以及 `prettier --check local-pairing.mjs local-pairing.test.mjs`。二维码和密钥不能进入已跟踪证据。

实际检查：**8 项入口测试通过**；前端 `check:api`、格式、TypeScript 及生产构建通过。即使设置本机入口环境变量，生产构建的客户端包也不包含本机扫码路径。未登录的本机二维码请求返回 401。直接通过 Vite 请求私有配置／二维码文件，只返回 SPA HTML 占位页，没有返回私有 JSON／PNG；前端文件服务明确拒绝 `local-data`。契约导出及基线检查通过。文档规定的 Ruff 范围（`apps/backend`、`scripts/export_contracts.py`、`scripts/smoke_replay.py`）通过。额外扩大到全部 `scripts` 的 Ruff 检查发现 main 原有 `scripts/check_baseline.py` 的 `sys` 未使用导入及格式问题，按用户的负责范围限制保留未改。未修改的后端 PostgreSQL 全套测试当天较早已通过 253 项，本次前端修正没有重复运行。最终显示验证后的浏览器警告／错误日志为空。
