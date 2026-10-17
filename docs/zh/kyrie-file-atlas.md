# Kyrie 的文件地图：先读哪几个，其他以后查

当前交付文件（2026-10-16）：[OrderCreation](../../apps/web/src/OrderCreation.tsx) 画新建表单和客户原文选择；[OrderLifecycle](../../apps/web/src/OrderLifecycle.tsx) 说明状态操作影响；[CalendarWorkspace](../../apps/web/src/CalendarWorkspace.tsx) 画月历／待办和下载按钮；[ReviewWorkspace](../../apps/web/src/ReviewWorkspace.tsx) 摆出人工复核事项；[order-command-api](../../apps/web/src/order-command-api.ts) 保留原编号请求；[features](../../apps/web/src/features.ts) 解释未接通功能。[workspace_api.py](../../apps/backend/src/gigmate/workspace_api.py) 提供按账号读取的辅助接口；[calendar_export.py](../../apps/backend/src/gigmate/calendar_export.py) 写日历文件。main 已包含 #25，当前候选是 `codex/d-final-workspace`；下方完整表保留旧版路径／历史观察。

D-03 新文件：[ApprovalsWorkspace.tsx](../../apps/web/src/ApprovalsWorkspace.tsx) 画核对与历史页面；[approvals-api.ts](../../apps/web/src/approvals-api.ts) 请求后端，并记住断网前那笔原请求；[approval-view.ts](../../apps/web/src/approval-view.ts) 解释状态和为什么不能批准。它们在待评审的 D-03 分支，不是 main 的文件。

更新：2026-10-12。[English atlas](../en/kyrie-file-atlas.md) · [从零学习手册](kyrie-learning-guide.md)。

这不是“今天必须学完”的清单。先学 5 个位置：`App.tsx` 看登录／页面选择；`chat-choices.ts` 看怎么算一页；`ChatChoices.tsx` 看怎么画勾选；`WorkOrderWorkspace.tsx` 看业务核对；`workspace-api.ts` 看请求。长连接页和后端最后再查。

普通目录是 main `bbb0074`，新 D 代码在 `codex/d02-workspace` 的另一个目录。`git worktree list` 可查位置。原表保留完整参考和旧文件历史，版本列表示当时路径是否存在，不表示今天所有内容相同。新 D 定位链接使用已推送的 `4665692`，完整 D-02 分支现在准备提交 PR，尚未合入 main。新 App／入口测试列出仓库路径，可在完整 D 分支或对应 PR 中查看。

角色是分工参考：A 接通消息，B 整理和拟建议，C 工单规则，D 网页，E 独立检查；不是“谁打了每个字”。“两版／main 新增／历史退役”是旧 D `c702f0c` 与 main 的对照。测试通过不等于手机成功；生成文件不能手改。忽略的依赖、缓存、密钥和会话不逐一列出。

## 新 D 文件：现在优先读

| 文件 | 用人话说 |
| --- | --- |
| `apps/web/src/App.tsx` | 登录与退出，业务／连接两页切换；在本地 D 工作目录 |
| `apps/web/app.test.mjs` | 检查无演示绕过、空密码、空工单提示、真实接口路径与退出 |
| [apps/web/src/WorkOrderWorkspace.tsx](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/src/WorkOrderWorkspace.tsx) | 业务页：看原文、核对变更、明确确认排期、看日历和待办 |
| [apps/web/src/work-order-view.ts](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/src/work-order-view.ts) | 把工单状态／时间译成显示文字，查正确来源和冲突工单 |
| [apps/web/work-order-view.test.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/work-order-view.test.mjs) | 检查多会话来源、午夜日期、筛选、版本和冲突名称 |
| [apps/web/work-order-workspace.test.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/work-order-workspace.test.mjs) | 自动操作真实业务组件，检查核对、勾选、过期和冲突 |

下面是需要时再查的完整参考；遇到 API／版本／测试等词，可回学习手册第 9 节。先不用钻数据库迁移：它是给已保存资料的结构升级，不是普通网页编辑。

## Root configuration / 根配置

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [.dockerignore](../../.dockerignore) | Docker 构建排除私有/依赖/无关目录 | A | 两版 |
| [.env.example](../../.env.example) | 配置占位符样例；不能替换成真实凭据提交 | A/B/C/D | 两版 |
| [.gitattributes](../../.gitattributes) | 文本换行/Git 文件属性规则 | A/B/C/D | 两版 |
| [.gitignore](../../.gitignore) | 忽略 .env/session/local-data 等本地私有/生成物 | A/B/C/D | 两版 |
| [.node-version](../../.node-version) | 约定 Node.js 运行时版本 | D | 两版 |
| [.python-version](../../.python-version) | 约定 Python 运行时版本 | A/B/C | 两版 |
| [AGENTS.md](../../AGENTS.md) | 仓库工程约束、权限/契约/测试与双语要求 | A/B/C/D/E | 两版 |
| [README.md](../../README.md) | 项目英文总入口/范围与启动；按具体 dated 记录核对 | A/B/C/D/E | 两版 |
| [跟單_WhatsApp业务协作助手_新版方案v2.docx](../../%E8%B7%9F%E5%96%AE_WhatsApp%E4%B8%9A%E5%8A%A1%E5%8D%8F%E4%BD%9C%E5%8A%A9%E6%89%8B_%E6%96%B0%E7%89%88%E6%96%B9%E6%A1%88v2.docx) | 原始 v2 产品方案输入；本次未逐页重新核对，不是实现证据 | 产品/全队 / Product/team | 两版 |

## GitHub collaboration and CI / GitHub 协作与持续集成

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [.github/ISSUE_TEMPLATE/bug.md](../../.github/ISSUE_TEMPLATE/bug.md) | Issue 模板：缺陷复现/预期实际 | A/B/C/D/E | 两版 |
| [.github/ISSUE_TEMPLATE/onboarding.md](../../.github/ISSUE_TEMPLATE/onboarding.md) | Issue 模板：独立成员入门证据 | A/B/C/D/E | 两版 |
| [.github/ISSUE_TEMPLATE/task.md](../../.github/ISSUE_TEMPLATE/task.md) | Issue 模板：任务与验收 | A/B/C/D/E | 两版 |
| [.github/pull_request_template.md](../../.github/pull_request_template.md) | PR 描述/范围/证据/限制模板 | A/B/C/D/E | 两版 |
| [.github/workflows/baseline.yml](../../.github/workflows/baseline.yml) | GitHub Actions 文档/schema/baseline 工作流 | A/E | 两版 |
| [.github/workflows/skeleton.yml](../../.github/workflows/skeleton.yml) | GitHub Actions 后端/前端构建和测试；main 增评测/模型冒烟脚本的静态检查 | A/B/D/E | 两版 |

## Backend configuration / 后端配置

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [apps/backend/alembic.ini](../../apps/backend/alembic.ini) | 数据库迁移工具 Alembic 的配置入口 | A/C | 两版 |
| [apps/backend/pyproject.toml](../../apps/backend/pyproject.toml) | Python 包/依赖范围、Ruff/pytest 配置 | A/B/C | 两版 |
| [apps/backend/requirements.lock](../../apps/backend/requirements.lock) | 后端精确依赖锁；使用项目 .venv 安装 | A/B/C | 两版 |

## Migrations / 数据库迁移

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [apps/backend/migrations/env.py](../../apps/backend/migrations/env.py) | 迁移连接/模型元数据加载；非环境变量密钥文件 | A/C | 两版 |
| [apps/backend/migrations/versions/0001_replay_foundation.py](../../apps/backend/migrations/versions/0001_replay_foundation.py) | 增量迁移：回放基础表/身份/消息/工单/计划/工作；禁止改共享历史 | A/C | 两版 |
| [apps/backend/migrations/versions/0002_waha_ingress.py](../../apps/backend/migrations/versions/0002_waha_ingress.py) | 增量迁移：WAHA 重启后仍保存的接入、外部服务 身份与审查状态；禁止改共享历史 | A/C | 两版 |
| [apps/backend/migrations/versions/0003_waha_stanza_identity.py](../../apps/backend/migrations/versions/0003_waha_stanza_identity.py) | 增量迁移：统一 外部服务 stanza 消息身份与旧数据处理；禁止改共享历史 | A/C | 两版 |
| [apps/backend/migrations/versions/0004_waha_recovery.py](../../apps/backend/migrations/versions/0004_waha_recovery.py) | 增量迁移：健康/故障/恢复审查状态；禁止改共享历史 | A/C | 两版 |
| [apps/backend/migrations/versions/0005_extraction_evidence.py](../../apps/backend/migrations/versions/0005_extraction_evidence.py) | 增量迁移：B 外部服务 抽取请求/结果/证据表；禁止改共享历史 | B | main 新增 |
| [apps/backend/migrations/versions/0005_waha_controls.py](../../apps/backend/migrations/versions/0005_waha_controls.py) | 增量迁移：A 连接控制/发现/同一请求不重复执行的保护状态；与 B 并行分支；禁止改共享历史 | A/C | main 新增 |
| [apps/backend/migrations/versions/0006_waha_provider_sample.py](../../apps/backend/migrations/versions/0006_waha_provider_sample.py) | 增量迁移：外部服务 状态样本/有界观测字段；禁止改共享历史 | A/C | main 新增 |
| [apps/backend/migrations/versions/0007_merge_waha_extraction.py](../../apps/backend/migrations/versions/0007_merge_waha_extraction.py) | 增量迁移：合并 A/B 两条迁移历史；不是删除重复编号；禁止改共享历史 | A/C | main 新增 |
| [apps/backend/migrations/versions/0008_waha_message_sync.py](../../apps/backend/migrations/versions/0008_waha_message_sync.py) | 增量迁移：有限历史同步/媒体元数据等增量结构；禁止改共享历史 | A/C | main 新增 |

## Backend modules / 后端模块

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [apps/backend/src/gigmate/__init__.py](../../apps/backend/src/gigmate/__init__.py) | Python 包标识/导出；通常很少业务逻辑 | A/B | 两版 |
| [apps/backend/src/gigmate/api.py](../../apps/backend/src/gigmate/api.py) | 后端入口：接网页请求，检查后调用相应业务方法 | A/C | 两版 |
| [apps/backend/src/gigmate/config.py](../../apps/backend/src/gigmate/config.py) | 环境配置与启动参数；不是存放真实密钥的地方 | A/B | 两版 |
| [apps/backend/src/gigmate/contracts.py](../../apps/backend/src/gigmate/contracts.py) | 工单等数据的正式格式和检查规则；前端说明从这里生成 | A/B/C/D | 两版 |
| [apps/backend/src/gigmate/db.py](../../apps/backend/src/gigmate/db.py) | 定义数据库怎样保存记录；不是网页临时状态 | A/B/C | 两版 |
| [apps/backend/src/gigmate/errors.py](../../apps/backend/src/gigmate/errors.py) | 统一业务异常/code；供 API 映射为可解释错误 | A/C/D | 两版 |
| [apps/backend/src/gigmate/extraction/__init__.py](../../apps/backend/src/gigmate/extraction/__init__.py) | Python 包标识/导出；通常很少业务逻辑 | A/B | main 新增 |
| [apps/backend/src/gigmate/extraction/deterministic.py](../../apps/backend/src/gigmate/extraction/deterministic.py) | 固定输入的可重复抽取，供回放与离线评测 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/disabled.py](../../apps/backend/src/gigmate/extraction/disabled.py) | 明确禁用 外部服务；未配置不能假装成功 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/evaluator.py](../../apps/backend/src/gigmate/extraction/evaluator.py) | 按场景检查 外部服务 输出/缺失值/来源与预期 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/legacy.py](../../apps/backend/src/gigmate/extraction/legacy.py) | 把早期理解接到 外部服务 接口的兼容层 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/llm.py](../../apps/backend/src/gigmate/extraction/llm.py) | LLM/DeepSeek HTTP 与解析 可替换的调用位置；硬开关保持关闭 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/persistence.py](../../apps/backend/src/gigmate/extraction/persistence.py) | 记录抽取请求、结果、来源证据与状态 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt](../../apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt) | 独立版本抽取提示词；不是允许自动确认的指令 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/registry.py](../../apps/backend/src/gigmate/extraction/registry.py) | 外部服务 注册/配置选择，拒绝未知配置 | B | main 新增 |
| [apps/backend/src/gigmate/extraction/types.py](../../apps/backend/src/gigmate/extraction/types.py) | 外部服务 输入/输出/证据接口类型 | B | main 新增 |
| [apps/backend/src/gigmate/identity.py](../../apps/backend/src/gigmate/identity.py) | 检查你是谁、能读哪个账号的数据 | A | 两版 |
| [apps/backend/src/gigmate/messaging.py](../../apps/backend/src/gigmate/messaging.py) | 消息规范化接收、同一请求不重复执行的保护与修订/context 更新 | A | 两版 |
| [apps/backend/src/gigmate/planning.py](../../apps/backend/src/gigmate/planning.py) | 计算是否撞期，以及该有的日历和准备待办 | C | 两版 |
| [apps/backend/src/gigmate/seed.py](../../apps/backend/src/gigmate/seed.py) | 虚构 demo 账号/工单/日历与任务初始化 | A/C | 两版 |
| [apps/backend/src/gigmate/understanding.py](../../apps/backend/src/gigmate/understanding.py) | 早期固定样例理解；不是通用模型抽取 | B | 两版 |
| [apps/backend/src/gigmate/waha_adapter.py](../../apps/backend/src/gigmate/waha_adapter.py) | 将 WAHA 外部服务 事件规范化为消息事件 | A | 两版 |
| [apps/backend/src/gigmate/waha_client.py](../../apps/backend/src/gigmate/waha_client.py) | 服务端 WAHA HTTP 客户端；凭据留服务器 | A | 两版 |
| [apps/backend/src/gigmate/waha_controls.py](../../apps/backend/src/gigmate/waha_controls.py) | 正式 setup/QR/发现/白名单/暂停/撤权/核对控制 | A/D | main 新增 |
| [apps/backend/src/gigmate/waha_ingress.py](../../apps/backend/src/gigmate/waha_ingress.py) | 签名/连接白名单验证与重启后仍保存的接入 HTTP 服务 | A | 两版 |
| [apps/backend/src/gigmate/waha_probe.py](../../apps/backend/src/gigmate/waha_probe.py) | 探测 外部服务/pipeline 健康，生成状态/故障事实 | A | 两版 |
| [apps/backend/src/gigmate/waha_recovery.py](../../apps/backend/src/gigmate/waha_recovery.py) | 恢复/故障人工核对与受控状态转换 | A | 两版 |
| [apps/backend/src/gigmate/waha_replay.py](../../apps/backend/src/gigmate/waha_replay.py) | 离线重放 WAHA 合成创建/编辑/撤回事件 | A/E | 两版 |
| [apps/backend/src/gigmate/waha_sync.py](../../apps/backend/src/gigmate/waha_sync.py) | 有界历史读取、合并实时事件、规范修订/媒体元数据 | A/D | main 新增 |
| [apps/backend/src/gigmate/worker.py](../../apps/backend/src/gigmate/worker.py) | 处理已保存的排队工作，不阻塞每个网页请求 | A/B | 两版 |
| [apps/backend/src/gigmate/workorders.py](../../apps/backend/src/gigmate/workorders.py) | 检查工单修改的依据、版本、冲突，执行正式内部确认 | C | 两版 |

## Backend tests / 后端测试

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [apps/backend/tests/conftest.py](../../apps/backend/tests/conftest.py) | pytest 共享 DB/账号/测试隔离夹具 | A/B/C/E | 两版 |
| [apps/backend/tests/fixtures/waha_a01.json](../../apps/backend/tests/fixtures/waha_a01.json) | 虚构 外部服务 原始事件样例，用于 请求转换层/replay | A/E | 两版 |
| [apps/backend/tests/test_contracts.py](../../apps/backend/tests/test_contracts.py) | 领域形状/状态约束与契约有效性回归 | A/B/C/E | 两版 |
| [apps/backend/tests/test_extraction.py](../../apps/backend/tests/test_extraction.py) | 外部服务、来源证据/评测及 LLM 可替换的调用位置 的受控测试 | B/E | main 新增 |
| [apps/backend/tests/test_waha_adapter.py](../../apps/backend/tests/test_waha_adapter.py) | 外部服务 事件身份/归一化与无效输入测试 | A/E | 两版 |
| [apps/backend/tests/test_waha_controls.py](../../apps/backend/tests/test_waha_controls.py) | setup/授权/同一请求不重复执行的保护/归属/未知结果控制测试 | A/D/E | main 新增 |
| [apps/backend/tests/test_waha_ingress.py](../../apps/backend/tests/test_waha_ingress.py) | 签名/白名单/重复/修订/重启后仍保存的工作接入测试 | A/E | 两版 |
| [apps/backend/tests/test_waha_local.py](../../apps/backend/tests/test_waha_local.py) | 本地 helper 边界/配置/安全输出测试 | A/E | 两版 |
| [apps/backend/tests/test_waha_migration.py](../../apps/backend/tests/test_waha_migration.py) | WAHA 迁移/数据兼容与表约束检查 | A/E | 两版 |
| [apps/backend/tests/test_waha_recovery.py](../../apps/backend/tests/test_waha_recovery.py) | 健康/恢复/故障复核与失败路径测试 | A/E | 两版 |
| [apps/backend/tests/test_waha_sync.py](../../apps/backend/tests/test_waha_sync.py) | 有限同步、归属、重复、群聊、编辑撤回历史冲突测试 | A/E | main 新增 |
| [apps/backend/tests/test_waha_team.py](../../apps/backend/tests/test_waha_team.py) | 团队工作区/资源/私有绑定保护与验收 helper 测试 | A/E | 两版 |
| [apps/backend/tests/test_workflow.py](../../apps/backend/tests/test_workflow.py) | 完整合成回放/权限/版本/冲突/确认事务测试 | A/B/C/E | 两版 |

## Frontend / 前端

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [apps/web/chat-choices.test.mjs](../../apps/web/chat-choices.test.mjs) | 个人/群聊/未知、过滤与分页边界回归 | D/E | main 新增 |
| [apps/web/connection-state.test.mjs](../../apps/web/connection-state.test.mjs) | 新鲜/过期/故障等指导优先级回归 | D/E | 两版 |
| [apps/web/connection-workspace.test.mjs](../../apps/web/connection-workspace.test.mjs) | jsdom 挂载真组件，跨页 PUT/重读/撤权回归 | D/E | main 新增 |
| [apps/web/index.html](../../apps/web/index.html) | HTML 页面骨架与 React root；不是主要业务逻辑 | D | 两版 |
| [apps/web/local-operations.py](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/local-operations.py) | 旧桥 Python 本地运维 helper；最新 main 已退役 | D | 历史退役 |
| [apps/web/local-pairing.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/local-pairing.mjs) | 旧 Vite 本地扫码开发桥；最新 main 已退役 | D | 历史退役 |
| [apps/web/local-pairing.test.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/local-pairing.test.mjs) | 旧开发桥路由/QR/异常回归；不证明手机配对 | D/E | 历史退役 |
| [apps/web/package-lock.json](../../apps/web/package-lock.json) | 工具自动记录的精确安装版本，交给 npm 维护 | D | 两版 |
| [apps/web/package.json](../../apps/web/package.json) | 前端要安装什么工具，以及 npm run 后可用的命令 | D | 两版 |
| [apps/web/business-store.test.mjs](../../apps/web/business-store.test.mjs) | 回放订阅、异步竞态、登录/提议/确认状态回归 | D/E | 两版 |
| [apps/web/src/ChatChoices.tsx](../../apps/web/src/ChatChoices.tsx) | 把已载入聊天画成可勾选的行；翻页不丢勾选 | D | main 新增 |
| [apps/web/src/ConnectionWorkspace.tsx](../../apps/web/src/ConnectionWorkspace.tsx) | 连接页：看状态、显示真实扫码图、保存或撤销聊天授权 | D | 两版 |
| [apps/web/src/ReplayWorkspace.tsx](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/bbb0074/apps/web/src/ReplayWorkspace.tsx) | 旧工单页面；D-02 用 WorkOrderWorkspace 替代，点这里查 main 历史 | D | main 历史 |
| [apps/web/src/WahaMessages.tsx](../../apps/web/src/WahaMessages.tsx) | 显示已允许的消息时间线、导入进度和附件信息 | A/D | main 新增 |
| [apps/web/src/chat-choices.ts](../../apps/web/src/chat-choices.ts) | 计算搜索结果、聊天类型和每一页；不发送请求 | D | main 新增 |
| [apps/web/src/connection-api.ts](../../apps/web/src/connection-api.ts) | 约定连接页要用哪些方法和数据；不再含演示服务 | D | 两版 |
| [apps/web/src/connection-state.ts](../../apps/web/src/connection-state.ts) | 按当前状态选择提示文字；旧状态不能当作现在已连接 | D | 两版 |
| [apps/web/src/connection.css](../../apps/web/src/connection.css) | 连接页和聊天列表的布局与外观；旧演示样式已移除 | D | 两版 |
| [apps/web/src/generated/api.d.ts](../../apps/web/src/generated/api.d.ts) | 工具生成的数据说明；从后端说明生成，不手改 | A/B/C/D | 两版 |
| [apps/web/src/main.tsx](../../apps/web/src/main.tsx) | 启动网页；新整理版把登录和切换页面交给 App.tsx | D | 两版 |
| [apps/web/src/business-store.ts](../../apps/web/src/business-store.ts) | 记住工单页正在读／写什么；防止慢的旧答复覆盖新选择，现名 BusinessStore，已移除虚构输入操作 | D | 两版 |
| [apps/web/src/style.css](../../apps/web/src/style.css) | 网页整体的颜色、布局、文字换行和窄屏调整 | D | 两版 |
| [apps/web/src/waha-live-api.ts](../../apps/web/src/waha-live-api.ts) | 把连接和授权请求送给后端；答复丢失时核对原请求 | D | main 新增 |
| [apps/web/src/waha-sync-api.ts](../../apps/web/src/waha-sync-api.ts) | 向后端查询消息和有限历史导入的进度 | A/D | main 新增 |
| [apps/web/src/workspace-api.ts](../../apps/web/src/workspace-api.ts) | 读取工单／日历／待办，提交带版本的确认，解释请求失败 | D | 两版 |
| [apps/web/test_local_operations.py](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/test_local_operations.py) | 旧 Python helper 故障/运维回归 | D/E | 历史退役 |
| [apps/web/tsconfig.json](../../apps/web/tsconfig.json) | 规定 TypeScript 怎样检查我们的代码 | D | 两版 |
| [apps/web/vite.config.ts](../../apps/web/vite.config.ts) | 规定开发网页怎样启动、请求转给哪个后端 | D | 两版 |
| [apps/web/waha-live-api.test.mjs](../../apps/web/waha-live-api.test.mjs) | 正式控制 请求转换层 请求/key/错误/核对回归 | D/E | main 新增 |
| [apps/web/workspace-api.test.mjs](../../apps/web/workspace-api.test.mjs) | 回放 HTTP 错误、请求与认证回归 | D/E | 两版 |

## Contracts and synthetic examples / 契约与虚构样例

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [contracts/README.md](../../contracts/README.md) | 契约权威/生成方式/独立 schema 与样例说明 | A/B/C/D | 两版 |
| [contracts/ai/change-proposal.schema.json](../../contracts/ai/change-proposal.schema.json) | 独立版本 AI 仅提议 JSON Schema | B/C | 两版 |
| [contracts/api-v1.md](../../contracts/api-v1.md) | 已实现 API 与目标/拟议接口分开记录；C #13 是目标 | A/B/C/D | 两版 |
| [contracts/domain/models.schema.json](../../contracts/domain/models.schema.json) | Pydantic 导出 domain schema；禁止手改 | A/B/C/D | 两版 |
| [contracts/evaluation/manifest.json](../../contracts/evaluation/manifest.json) | 离线 外部服务 评测场景/输入/期望；非真实聊天 | B/E | main 新增 |
| [contracts/events/message-event.schema.json](../../contracts/events/message-event.schema.json) | 独立版本消息事件 JSON Schema | A/B | 两版 |
| [contracts/examples/action-pending.json](../../contracts/examples/action-pending.json) | 待审批/待执行 Action 合同例子，不证明已可发送 | A/B/C/D/E | 两版 |
| [contracts/examples/action-unknown.json](../../contracts/examples/action-unknown.json) | 外部结果未知 Action 例子：须核对 | A/B/C/D/E | 两版 |
| [contracts/examples/approve-command.json](../../contracts/examples/approve-command.json) | 商户批准命令的版本/绑定示例 | A/B/C/D/E | 两版 |
| [contracts/examples/date-only.json](../../contracts/examples/date-only.json) | 只有日期，不能擅自补时间 | A/B/C/D/E | 两版 |
| [contracts/examples/invalid-ai-confirmed-field.json](../../contracts/examples/invalid-ai-confirmed-field.json) | 反例：AI 直接写 confirmed 字段应拒绝 | A/B/C/D/E | 两版 |
| [contracts/examples/invalid-ai-execution.json](../../contracts/examples/invalid-ai-execution.json) | 反例：AI 要求直接执行应拒绝 | A/B/C/D/E | 两版 |
| [contracts/examples/invalid-approval-no-merchant.json](../../contracts/examples/invalid-approval-no-merchant.json) | 反例：缺商户批准身份应拒绝 | A/B/C/D/E | 两版 |
| [contracts/examples/invalid-date.json](../../contracts/examples/invalid-date.json) | 反例：无效日期应拒绝 | A/B/C/D/E | 两版 |
| [contracts/examples/invalid-event-no-account.json](../../contracts/examples/invalid-event-no-account.json) | 反例：消息缺账号归属应拒绝 | A/B/C/D/E | 两版 |
| [contracts/examples/invalid-missing-value.json](../../contracts/examples/invalid-missing-value.json) | 反例：未知/缺失字段却填值应拒绝 | A/B/C/D/E | 两版 |
| [contracts/examples/manifest.json](../../contracts/examples/manifest.json) | 正反样例目录、schema 和预期结果 | A/B/C/D/E | 两版 |
| [contracts/examples/message-edited.json](../../contracts/examples/message-edited.json) | 虚构消息编辑与修订来源样例 | A/B/C/D/E | 两版 |
| [contracts/examples/message-original.json](../../contracts/examples/message-original.json) | 虚构原始预约消息事件 | A/B/C/D/E | 两版 |
| [contracts/examples/message-reschedule.json](../../contracts/examples/message-reschedule.json) | 虚构客户改期提议事件 | A/B/C/D/E | 两版 |
| [contracts/examples/message-revoked.json](../../contracts/examples/message-revoked.json) | 虚构撤回事件，使旧来源失效 | A/B/C/D/E | 两版 |
| [contracts/examples/proposal-reschedule.json](../../contracts/examples/proposal-reschedule.json) | AI 改期提议结构/来源；非确认写入 | A/B/C/D/E | 两版 |
| [contracts/examples/scenarios.json](../../contracts/examples/scenarios.json) | 业务/可靠性场景与验收预期 | A/B/C/D/E | 两版 |
| [contracts/examples/session-disconnected.json](../../contracts/examples/session-disconnected.json) | 连接断开事件结构例子 | A/B/C/D/E | 两版 |
| [contracts/examples/work-order.json](../../contracts/examples/work-order.json) | 工单字段/状态/版本/来源样例 | A/B/C/D/E | 两版 |
| [contracts/openapi.json](../../contracts/openapi.json) | FastAPI 实现 API 导出规范；禁止手改 | A/B/C/D | 两版 |

## Design, operations and acceptance documents / 设计、操作与验收文档

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [docs/en/README.md](../../docs/en/README.md) | 资料索引：选择下一篇；标题日期保留历史意义 | A/B/C/D/E | 两版 |
| [docs/en/adr/0001-foundation.md](../../docs/en/adr/0001-foundation.md) | 技术栈/单仓库模块化基础决策 | A/B/C/D/E | 两版 |
| [docs/en/adr/0002-contract-authority.md](../../docs/en/adr/0002-contract-authority.md) | Pydantic 生成权威与独立事件/AI 版本决策 | A/B/C/D/E | 两版 |
| [docs/en/adr/0003-approval-and-execution.md](../../docs/en/adr/0003-approval-and-execution.md) | 审批绑定、版本失效、结果未知与外发可靠性 | A/B/C/D/E | 两版 |
| [docs/en/adr/0004-equal-collaboration.md](../../docs/en/adr/0004-equal-collaboration.md) | 平等协作权限和独立评审决策 | A/B/C/D/E | 两版 |
| [docs/en/adr/0005-bounded-waha-observations.md](../../docs/en/adr/0005-bounded-waha-observations.md) | 有界历史/群聊/媒体元数据观测限制 | A/B/C/D/E | main 新增 |
| [docs/en/adr/README.md](../../docs/en/adr/README.md) | ADR 列表与读法；设计理由不等于阶段进度 | A/B/C/D/E | 两版 |
| [docs/en/architecture.md](../../docs/en/architecture.md) | 模块边界、状态流、归属与可靠性设计 | A/B/C/D/E | 两版 |
| [docs/en/contributing.md](../../docs/en/contributing.md) | Issue/分支/评审与完成规则 | A/B/C/D/E | 两版 |
| [docs/en/getting-started.md](../../docs/en/getting-started.md) | 已验证安装/运行/迁移/测试命令与 PG 配置 | A/B/C/D/E | 两版 |
| [docs/en/implementation-status.md](../../docs/en/implementation-status.md) | 英文实际完成与测试证据；每条看日期/版本 | A/B/C/D/E | 两版 |
| [docs/en/overview.md](../../docs/en/overview.md) | 产品目标、当前范围与排除项 | A/B/C/D/E | 两版 |
| [docs/en/role-a-development-roadmap.md](../../docs/en/role-a-development-roadmap.md) | A 按整批交付的计划/依赖；不是全部已完成 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-integration-acceptance.md](../../docs/en/role-a-integration-acceptance.md) | A 集成验收方法与当时结果 | A（D/E 阅读） / A (D/E readers) | main 新增 |
| [docs/en/role-a-message-sync-acceptance.md](../../docs/en/role-a-message-sync-acceptance.md) | A #14 有界消息同步的验收/限制 | A（D/E 阅读） / A (D/E readers) | main 新增 |
| [docs/en/role-a-recovery-acceptance.md](../../docs/en/role-a-recovery-acceptance.md) | 恢复/故障/人工核对验收与范围限制 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-responsibilities.md](../../docs/en/role-a-responsibilities.md) | A 职责边界与 B/C/D/E 交接 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-setup-api-acceptance.md](../../docs/en/role-a-setup-api-acceptance.md) | A #11 正式连接控制 API/迁移/同一请求不重复执行的保护验收 | A（D/E 阅读） / A (D/E readers) | main 新增 |
| [docs/en/role-a-stage1-acceptance.md](../../docs/en/role-a-stage1-acceptance.md) | 早期 WAHA 请求转换层/合成事件阶段验收 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-stage2-acceptance.md](../../docs/en/role-a-stage2-acceptance.md) | WAHA 重启后仍保存的 ingress 阶段验收 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-stage3-acceptance.md](../../docs/en/role-a-stage3-acceptance.md) | WAHA 状态/监控/联调阶段验收 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-team-local-development.md](../../docs/en/role-a-team-local-development.md) | 团队自己的测试账号/隔离环境/doctor/证据步骤 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-a-waha-handoff.md](../../docs/en/role-a-waha-handoff.md) | WAHA 当前能力矩阵、限制与角色入口 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/en/role-b-extraction.md](../../docs/en/role-b-extraction.md) | B 外部服务/证据/评测；main LLM 当前门禁与剩余工作 | B（D/E 阅读） / B (D/E readers) | main 新增 |
| [docs/en/role-d-frontend-user-guide.md](../../docs/en/role-d-frontend-user-guide.md) | D 用户操作/运行与模式区别；看当时版本 | D（全队参考） / D (team reference) | 两版 |
| [docs/en/role-d-stage1-acceptance.md](../../docs/en/role-d-stage1-acceptance.md) | D 连接/授权/分页的分阶段验收和历史记录 | D（全队参考） / D (team reference) | 两版 |
| [docs/en/team-governance.md](../../docs/en/team-governance.md) | 平等权限、main 保护与独立评审规则 | A/B/C/D/E | 两版 |
| [docs/en/whatsapp-connection-flow.md](../../docs/en/whatsapp-connection-flow.md) | 扫码→授权→事件→历史获取与边界 | A/B/C/D/E | 两版 |
| [docs/project-kickoff-plan.md](../../docs/project-kickoff-plan.md) | 早期启动规划历史，已被工程基线取代 | A/B/C/D/E | 两版 |
| [docs/zh/README.md](../../docs/zh/README.md) | 资料索引：选择下一篇；标题日期保留历史意义 | A/B/C/D/E | 两版 |
| [docs/zh/acceptance.md](../../docs/zh/acceptance.md) | E/团队验收准则；标准不等于完成结果 | A/B/C/D/E | 两版 |
| [docs/zh/collaboration-checklist.md](../../docs/zh/collaboration-checklist.md) | 任务、分支、提交、自查、评审清单 | A/B/C/D/E | 两版 |
| [docs/zh/domain-workflows.md](../../docs/zh/domain-workflows.md) | 业务实体、状态、批准与执行边界 | A/B/C/D/E | 两版 |
| [docs/zh/engineering-standards.md](../../docs/zh/engineering-standards.md) | 工程模块、命名、契约、数据和日志要求 | A/B/C/D/E | 两版 |
| [docs/zh/onboarding-report-template.md](../../docs/zh/onboarding-report-template.md) | 新成员独立启动/回放/PR 验收报告模板 | A/B/C/D/E | 两版 |
| [docs/zh/onboarding.md](../../docs/zh/onboarding.md) | 新成员克隆、环境、回放与首 PR 步骤 | A/B/C/D/E | 两版 |
| [docs/zh/progress.md](../../docs/zh/progress.md) | 中文实际完成与测试证据；每条看日期/版本 | A/B/C/D/E | 两版 |
| [docs/zh/roadmap.md](../../docs/zh/roadmap.md) | 阶段计划和依赖；与实际 progress 区分 | A/B/C/D/E | 两版 |
| [docs/zh/role-a-development-roadmap.md](../../docs/zh/role-a-development-roadmap.md) | A 按整批交付的计划/依赖；不是全部已完成 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-integration-acceptance.md](../../docs/zh/role-a-integration-acceptance.md) | A 集成验收方法与当时结果 | A（D/E 阅读） / A (D/E readers) | main 新增 |
| [docs/zh/role-a-message-sync-acceptance.md](../../docs/zh/role-a-message-sync-acceptance.md) | A #14 有界消息同步的验收/限制 | A（D/E 阅读） / A (D/E readers) | main 新增 |
| [docs/zh/role-a-recovery-acceptance.md](../../docs/zh/role-a-recovery-acceptance.md) | 恢复/故障/人工核对验收与范围限制 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-responsibilities.md](../../docs/zh/role-a-responsibilities.md) | A 职责边界与 B/C/D/E 交接 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-setup-api-acceptance.md](../../docs/zh/role-a-setup-api-acceptance.md) | A #11 正式连接控制 API/迁移/同一请求不重复执行的保护验收 | A（D/E 阅读） / A (D/E readers) | main 新增 |
| [docs/zh/role-a-stage1-acceptance.md](../../docs/zh/role-a-stage1-acceptance.md) | 早期 WAHA 请求转换层/合成事件阶段验收 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-stage2-acceptance.md](../../docs/zh/role-a-stage2-acceptance.md) | WAHA 重启后仍保存的 ingress 阶段验收 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-stage3-acceptance.md](../../docs/zh/role-a-stage3-acceptance.md) | WAHA 状态/监控/联调阶段验收 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-team-local-development.md](../../docs/zh/role-a-team-local-development.md) | 团队自己的测试账号/隔离环境/doctor/证据步骤 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-a-waha-handoff.md](../../docs/zh/role-a-waha-handoff.md) | WAHA 当前能力矩阵、限制与角色入口 | A（D/E 阅读） / A (D/E readers) | 两版 |
| [docs/zh/role-b-extraction.md](../../docs/zh/role-b-extraction.md) | B 外部服务/证据/评测；main LLM 当前门禁与剩余工作 | B（D/E 阅读） / B (D/E readers) | main 新增 |
| [docs/zh/role-d-frontend-user-guide.md](../../docs/zh/role-d-frontend-user-guide.md) | D 用户操作/运行与模式区别；看当时版本 | D（全队参考） / D (team reference) | 两版 |
| [docs/zh/role-d-stage1-acceptance.md](../../docs/zh/role-d-stage1-acceptance.md) | D 连接/授权/分页的分阶段验收和历史记录 | D（全队参考） / D (team reference) | 两版 |
| [docs/zh/scope.md](../../docs/zh/scope.md) | P0/P1 范围与排除项；不自行扩大 | A/B/C/D/E | 两版 |
| [docs/zh/team-governance.md](../../docs/zh/team-governance.md) | 平等权限、main 保护与独立评审规则 | A/B/C/D/E | 两版 |
| [docs/zh/whatsapp-connection-flow.md](../../docs/zh/whatsapp-connection-flow.md) | 扫码→授权→事件→历史获取与边界 | A/B/C/D/E | 两版 |

## Learning artifacts / 学习资料

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [docs/en/kyrie-file-atlas.md](../../docs/en/kyrie-file-atlas.md) | 本次逐文件职责/版本/阅读地图 | D（全队参考） / D (team reference) | 本次 |
| [docs/en/kyrie-learning-guide.md](../../docs/en/kyrie-learning-guide.md) | 本次学习主线：GitHub/架构/进度/D 代码/练习 | D（全队参考） / D (team reference) | 本次 |
| [docs/learning-assets/README.md](../../docs/learning-assets/README.md) | 截图来源、日期、公开范围与教学目的 | D/E | 本次 |
| [docs/learning-assets/github-actions.jpg](../../docs/learning-assets/github-actions.jpg) | 真实 GitHub Actions 页面截图；配合教程看 | D | 本次 |
| [docs/learning-assets/github-code.jpg](../../docs/learning-assets/github-code.jpg) | 真实 GitHub Code 页面截图；配合教程看 | D | 本次 |
| [docs/learning-assets/github-commit.jpg](../../docs/learning-assets/github-commit.jpg) | 真实 GitHub Commit dcd7527 页面截图；配合教程看 | D | 本次 |
| [docs/learning-assets/github-diff.jpg](../../docs/learning-assets/github-diff.jpg) | 真实 GitHub Files changed 页面截图；配合教程看 | D | 本次 |
| [docs/learning-assets/github-issue19.jpg](../../docs/learning-assets/github-issue19.jpg) | 真实 GitHub Issue #19 页面截图；配合教程看 | D | 本次 |
| [docs/learning-assets/github-pr16.jpg](../../docs/learning-assets/github-pr16.jpg) | 真实 GitHub Merged #16 页面截图；配合教程看 | D | 本次 |
| [docs/learning-assets/github-pulls.jpg](../../docs/learning-assets/github-pulls.jpg) | 真实 GitHub PR list 页面截图；配合教程看 | D | 本次 |
| [docs/zh/kyrie-file-atlas.md](../../docs/zh/kyrie-file-atlas.md) | 本次逐文件职责/版本/阅读地图 | D（全队参考） / D (team reference) | 本次 |
| [docs/zh/kyrie-learning-guide.md](../../docs/zh/kyrie-learning-guide.md) | 本次学习主线：GitHub/架构/进度/D 代码/练习 | D（全队参考） / D (team reference) | 本次 |

## Runtime configuration / 运行配置

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [infra/backend.Dockerfile](../../infra/backend.Dockerfile) | 构建后端/worker 容器镜像 | A | 两版 |
| [infra/compose.yaml](../../infra/compose.yaml) | 开发 API/worker/web/PostgreSQL 服务与端口/volume | A | 两版 |
| [infra/nginx.conf](../../infra/nginx.conf) | Web 反向代理/static/API 路由配置 | A/D | 两版 |
| [infra/waha-arm64.compose.yaml](../../infra/waha-arm64.compose.yaml) | Apple Silicon/ARM64 WAHA 固定镜像/platform override | A | main 新增 |
| [infra/waha-ingress.compose.yaml](../../infra/waha-ingress.compose.yaml) | 重启后仍保存的 ingress 服务组合配置 | A | 两版 |
| [infra/waha-probe.Dockerfile](../../infra/waha-probe.Dockerfile) | 构建探测/接入相关辅助运行镜像 | A | 两版 |
| [infra/waha-recovery.compose.yaml](../../infra/waha-recovery.compose.yaml) | 健康监控/恢复联调服务配置 | A | 两版 |
| [infra/waha-setup-check.compose.yaml](../../infra/waha-setup-check.compose.yaml) | setup 诊断/验收服务组合 | A/E | main 新增 |
| [infra/waha-team.compose.yaml](../../infra/waha-team.compose.yaml) | 隔离团队 PostgreSQL/运行参数 override | A | 两版 |
| [infra/waha.compose.yaml](../../infra/waha.compose.yaml) | 可选 WAHA 服务基础 Compose | A | 两版 |
| [infra/web.Dockerfile](../../infra/web.Dockerfile) | 构建前端静态文件与 nginx 容器 | A/D | 两版 |

## Scripts / 脚本

| 文件 | 大概做什么 / 读它能学什么 | 协调角色 | 版本 |
| --- | --- | --- | --- |
| [scripts/check_baseline.py](../../scripts/check_baseline.py) | 校验 Markdown 链接、schema/样例/基线规则；非运行验收 | A/B/C/D/E | 两版 |
| [scripts/check_waha_recovery.py](../../scripts/check_waha_recovery.py) | 可重放故障/恢复/人工核对验收 runner | A/E | 两版 |
| [scripts/check_waha_setup.py](../../scripts/check_waha_setup.py) | 连接/setup 诊断 runner 和异常证据检查 | A/E | main 新增 |
| [scripts/check_web_contracts.mjs](../../scripts/check_web_contracts.mjs) | 对照 OpenAPI 重生成前端类型并检查漂移 | D | 两版 |
| [scripts/export_contracts.py](../../scripts/export_contracts.py) | 从 Pydantic/实现路由导出 domain/OpenAPI；--check 查漂移 | A/B/C/D | 两版 |
| [scripts/replay_waha.py](../../scripts/replay_waha.py) | 命令行重放虚构 WAHA JSON 事件 | A/E | 两版 |
| [scripts/requirements-baseline.txt](../../scripts/requirements-baseline.txt) | 文档/schema 校验器的固定依赖 | A/E | 两版 |
| [scripts/run_evaluation.py](../../scripts/run_evaluation.py) | 离线抽取场景评测 runner；不等于真实模型验收 | B/E | main 新增 |
| [scripts/smoke_deepseek.py](../../scripts/smoke_deepseek.py) | DeepSeek 受控调用冒烟脚本；主线仍有门禁 | B/E | main 新增 |
| [scripts/smoke_replay.py](../../scripts/smoke_replay.py) | HTTP 固定回放冒烟：输入到确认与计划变化 | A/C/D/E | 两版 |
| [scripts/smoke_waha_ingress.py](../../scripts/smoke_waha_ingress.py) | 受控 HTTP ingress 冒烟检查 | A/E | 两版 |
| [scripts/smoke_waha_local.py](../../scripts/smoke_waha_local.py) | 本地绑定/API 健康冒烟；不等于真实消息全验收 | A/E | 两版 |
| [scripts/waha_container_config.py](../../scripts/waha_container_config.py) | 生成安全 WAHA 容器配置与架构相关参数 | A | 两版 |
| [scripts/waha_ingress.py](../../scripts/waha_ingress.py) | CLI 启动重启后仍保存的接入 HTTP 服务 | A | 两版 |
| [scripts/waha_local.py](../../scripts/waha_local.py) | 本地连接配置/初始化/QR 与私有输出工具 | A | 两版 |
| [scripts/waha_team.py](../../scripts/waha_team.py) | 团队 init/up/doctor/run/checkpoint/verify 与隔离保护 | A/E | 两版 |

## 用文件定位进度

D 优先读 `main.tsx` → `ConnectionWorkspace.tsx` → adapters/state → `chat-choices.ts`/`ChatChoices.tsx` → tests。回放读 `ReplayWorkspace.tsx` → store/API → `workorders.py`/`planning.py`。

A #11 对应 controls/0005_waha_controls/0006、setup-api-acceptance；D #15 对应 live adapter/工作台。A #14 对应 sync/0008/WahaMessages/message-sync-acceptance；D #16 对应 chat choices/组件测试。B #9/#18/#20 对应 extraction/0005_extraction_evidence/评测；C #13 新建工单仍在 api-v1.md 目标段，不是已实现文件。A/B 0007 合并两条迁移头。

具体剩余问题和验收标准见学习手册第 3 章；不要把英文/中文同主题文档当作两份不同交付，也不要以文件数量评估个人贡献。


## 接通 C 之后新增的文件关系（2026-10-16）

`InspectOrderAttempt.tsx` 是“拿原小票查保存记录”的小面板；`order-command-api.ts` 留住原编号，只在核对到已保存记录后允许结束本地提醒。`workspace_api.py` 只查原有记录，不代替 C 修改工单。自动生成的接口类型现在包含 C 的建单／状态命令，以及只读查记录的填表约定。
