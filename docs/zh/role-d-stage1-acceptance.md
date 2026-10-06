# D-01：前端扫码连接与会话选择

负责人 Kyrie。2026-10-06 在 `Kyrie_Frontend` 准备，基础是最新 `main` 合并提交 `0cd7e3f`。用户要求创建本地提交，message 为 `还没测试`；不推送。真实 WhatsApp 扫码及用户手动验收尚未测试，下文记录的自动检查已通过。[英文对应](../en/role-d-stage1-acceptance.md)。

## 范围与当前结果

本批只修改 `apps/web` 内前端文件，以及这一对 D 专属验收文档。后端、WAHA 工具、迁移、基础设施、依赖、共享文档、契约及生成类型与 main 完全一致。之前未提交的 D-01 后端／共享改动已私下备份到 Git 忽略的 `local-data`，并移出当前改动范围。

PC 工作台提供扫码区域、连接与处理状态、会话勾选、明确保存、撤销及放弃更改，以及清楚标记的合成演示。会话读取授权不会开启自动回复；自动回复与消息发送属于后续独立里程碑。

真实模式使用 main 已有的鉴权连接查询与故障记录查询，分别显示连接状态、采样就绪度、状态新鲜度、接收权限及待核对问题。扫码和会话选择功能显示「待接入」，对应按钮禁用。真实适配器不会请求尚未实现的接口或直接调用 WAHA 管理接口。

演示仅保存在浏览器内存中，可以模拟扫码、连接／断线、状态过期、选择、保存及断线撤销。离开演示或刷新页面就会重置。二维码位置是占位展示，不能真正扫描。演示成功不能证明数据库写入、真实授权、扫码或送达。

**D-01 端到端验收仍需 Andy 的产品接口及真实账号测试。** 本批前端不实现这些接口。

## 需要和 Andy 对齐的接口

main 已实现且真实模式使用：

| 查询 | 前端用途 |
| --- | --- |
| `GET /api/v1/connectors` | 账号隔离、分页的 `ConnectorStatus`；使用 main 的生成类型 |
| `GET /api/v1/connectors/{id}/recovery-issues` | 账号隔离、分页的 `RecoveryIssue`；使用 main 的生成类型 |

下列接口及字段只是**前端建议**，请 Andy 确认或调整。它们没有写入共享契约，也不代表后端已经实现。

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

## Mac 预览与已有接口

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

外部验证待完成：Docker／WAHA 手机扫码、真实会话发现、持久化保存／撤销、PostgreSQL 行为及独立队友评审。合成预览及 SQLite 开发登录均不能证明这些事项。
