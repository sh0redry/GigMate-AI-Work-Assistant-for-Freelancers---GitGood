# 已完成工作与验证记录

记录日期：2026年10月1日。当前里程碑：v0.2 回放工程骨架。维护人：当前仓库维护者。后续实现必须持续更新本记录及英文 implementation-status，注明实际完成、测试证据和未完成范围。

## 已完成内容

| 任务 | 当前结果 | 代码与配置位置 |
| --- | --- | --- |
| SKEL-01 环境及锁定 | Python 3.12.10、Node 24.15.0、PostgreSQL 17.9，依赖锁与 Compose 完成 | apps、infra、.env.example |
| SKEL-02 数据与权限 | 13张业务/运行表、初始迁移、两套隔离开发账号、登录会话与 CSRF | backend/migrations、identity.py、api.py |
| SKEL-03 消息与后台 | 白名单校验、去重、编辑/撤回版本、持久任务、领取租约、有限重试、断库恢复 | messaging.py、worker.py |
| SKEL-04 工作台与确认 | 原文、待确认变更、冲突提示、显式确认、日历/待办及重启持久化 | web、workorders.py、planning.py |
| SKEL-05 契约与 CI | Pydantic 生成 domain schema/OpenAPI，生成前端类型及漂移检查，新增代码 CI | contracts、scripts、.github/workflows |

已完成的是回放骨架，不是完整 P0。固定桩只识别“冲突改期”和“可用时段”两段虚构文字，不调用模型服务。数据库、前端和 worker 使用真实实现；没有连接 WhatsApp，也没有任何外发执行。

正式改期必须由商户显式确认。后端检查账号、白名单、工单/会话版本及来源消息，再检查时间重叠，最后在一个事务内更新工单、日历、相关自动待办和审计。取消仅影响系统生成的待办，无关人工待办保留。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| Windows 开发环境及 Linux 容器构建 | 通过；运行时与依赖均锁定 |
| Compose 全套启动与健康检查 | 通过；迁移正常退出，API/数据库健康，worker/web 运行 |
| Alembic 初始迁移与模型漂移检查 | 通过，无额外迁移差异 |
| PostgreSQL 测试 | 26项通过：18项行为与8项旧契约样例兼容检查，含并发领取、失败三次终止、数据库短断恢复 |
| 原契约正反样例及生成漂移检查 | 通过 |
| Ruff、前端格式、类型及生产构建 | 通过 |
| 实际浏览器操作 | 冲突不能确认；16:30可确认，版本3升4，日历更新、旧自动待办取消、新待办生成，地址仍缺失 |
| 实际 HTTP 冒烟 | 登录、回放、确认/已有结果、日历待办、重复输入及退出检查通过 |
| 服务重启 | 数据库/API/worker 重启后已确认安排与任务仍保留，重复冒烟通过 |

测试使用虚构数据和隔离的临时 PostgreSQL schema，不清空工作台数据库。测试工具有一个 Starlette/httpx 上游弃用提示，未造成失败；未进行真实新成员计时测试。

恢复工作时 Docker Desktop 未运行；启动引擎并执行 Compose up --wait 后，服务恢复，已有确认结果的 HTTP 冒烟再次通过。文档基线和生成契约同步检查也再次通过。

## COLLAB-01：团队共享基线冻结（2026年10月1日）

- 已发布骨架提交：[3231810](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/commit/3231810b7e17f7f3dd052eb8084fdd7b87d3c827)。开始整理冻结记录时，本地与 origin/main 一致，工作区干净，无需重复提交骨架。
- [文档与契约基线 CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/runs/36853663964)通过。
- [回放骨架 CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/runs/36853664016)通过：后端 PostgreSQL 测试、迁移、契约与代码检查，以及前端依赖安装、类型生成检查、格式与生产构建。
- 整理基线期间，本地再次通过 Ruff、格式、契约同步、文档/正反样例及前端检查。
- 本次额外的本地 PostgreSQL/迁移与 HTTP 复测未完成：Compose 启动后 Docker 引擎不可用，已中断等待中的原生迁移检查。冻结时最新 PostgreSQL 证据采用上述云端后端运行结果，之前的本地通过记录仍为历史证据。
- 单人自审：本次追加提交仅修改文档，未改运行时契约或共享迁移，中英文记录一致、文档检查通过、未加入私人数据。
- 基线标签为 v0.2.0，注释标明经过测试的实现提交；后续冻结记录只修改文档，不扩大运行时范围。团队不得移动已发布标签，修复用新提交和后续版本标识。
- 冻结范围仅为虚构回放工程骨架，不代表生产发布、真实 WhatsApp 连通或通用 AI 准确率。

后续依次完成：队友全新克隆独立启动、GitHub 主分支保护与必需检查、轮换模块联系人、首批边界明确的任务。当前尚未配置主分支保护，CI 通过与版本标签不等于合并门槛已经生效。

## COLLAB-02/03：入门材料与平等协作准备（2026年10月1日）

已准备[中文入门清单](onboarding.md)、[实测报告模板](onboarding-report-template.md)、[平等协作规则](team-governance.md)、对应英文说明和 ADR 0004。Issue 新增 Onboarding verification 模板，PR 模板新增入门证据与同伴评审要求；检查脚本要求这些入口存在。

清单覆盖全新克隆、固定环境、启动、ONB-01 至 ONB-08 回放/隔离/持久化/首个 PR、检查范围、故障反馈与文档修复。已核对 Compose 固定项目名可能复用数据库卷、API 镜像不包含 scripts/docs、示例密码不随环境变更重置等实际配置限制。

平等协作已作为文档规则落地：任何合适队友都可以评审，任何成员满足条件后都可以合并；模块联系人可轮换，无独占审批权；管理员同样遵守保护目标，不设置创建者绕过。当前个人仓库不能授予多个成员 owner 等价权限；目标为组织仓库中的全员相同 Admin，组织 Owner 权限另需明确。尚未迁移组织、邀请成员或配置保护。

本次变更仅为文档、模板及文档检查所需文件列表，未改业务实现或迁移。文档/链接/正反样例检查通过；单人自审核对了中英文规则、实际启动配置与未完成状态。没有代填任何成员报告、没有宣称队友独立实测或首个同伴批准 PR 已完成。COLLAB-02 实测及 COLLAB-03 平台设置继续待完成。

材料已发布在分支 docs/equal-team-onboarding，初始材料提交 6f84983；已建立[队友实测任务 #1](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/1)与[文档草稿 PR #2](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/2)，尚未合并 main。任务未指派，等待实际成员参与；这份材料 PR 不是队友的首个验收 PR。GitHub API 实际核对 main 的 protected=false，当前登录有仓库管理权限，但没有执行权限或保护变更。

## 启动与复查入口

详见[英文开发文档](../en/getting-started.md)，启动后访问 http://127.0.0.1:18080，开发账号 merchant / other，示例密码 demo-only-change-me。账号仅供本地回放；初次 seed 后修改环境密码不会自动重置已有账号。

关键验证命令：scripts/check_baseline.py、scripts/export_contracts.py --check、pytest apps/backend/tests、前端 check:api/format:check/build、scripts/smoke_replay.py。完整环境变量和命令在开发入口中，不能脱离环境直接宣称检查通过。

## 尚未完成

- LIVE-01：WAHA 真正连通、固定版本/引擎与双方消息、断线和回执实测。
- 通用 AI 抽取、真实样本标注与独立评测；当前桩不证明准确率。
- 多工单人工归类页面、其他需求字段、拒绝/编辑业务命令。
- 对外审批、outbox、代发、发送结果未知核对、API echo 和发送并发测试。
- 完整工作时间/缓冲规则、生产身份系统、资料删除与保留机制。
- 媒体、外部日历和其他增强模块。

下一阶段优先验证真实接入并实现对外审批执行闭环。所有新增工作按协作检查表提交，持续记录完成证据，不能把回放成功写成真实接入成功。
