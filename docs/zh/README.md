# 工程基线与团队内部检查入口

版本：v0.2 回放骨架。更新日期：2026年10月1日。当前只有一位成员；后续成员采用相同权限目标与同伴评审，模块联系人负责协调并可轮换。

工程标准和可运行回放骨架已建立，真实接入、通用 AI 与对外执行仍未实现。本入口供团队内部检查使用，根 README 不引用这里；公开仓库里的文件仍可访问。

| 文档 | 检查内容 |
| --- | --- |
| [新成员入门](onboarding.md) | 全新克隆、启动、回放与首个 PR 的操作清单 |
| [入门报告模板](onboarding-report-template.md) | 独立实测证据、问题与修复后复查 |
| [平等协作规则](team-governance.md) | 相同权限目标、同伴评审与主分支保护清单 |
| [范围](scope.md) | 首期闭环、优先级和不做事项 |
| [工程标准](engineering-standards.md) | 模块、命名、接口、数据、日志与契约 |
| [业务模型与流程](domain-workflows.md) | 状态转换、版本、审批与执行 |
| [协作检查表](collaboration-checklist.md) | 任务、提交、自查、评审与合并 |
| [验收要求](acceptance.md) | 当前文档验收与后续业务验收 |
| [阶段任务](roadmap.md) | 工作顺序、依赖与完成证据 |
| [A 的职责](role-a-responsibilities.md) | 消息接入、鉴权、可靠任务、监控和角色交接 |
| [WhatsApp 连接与消息获取](whatsapp-connection-flow.md) | 用户扫码、会话白名单、实时事件和历史同步 |
| [A 的技术开发演进](role-a-development-roadmap.md) | 完整批次开发、依赖、异常测试和统一验收 |
| [已完成工作](progress.md) | 实际实现、验证结果与未完成范围 |
| [英文架构决策](../en/adr/README.md) | 选型与决策依据 |
| [契约](../../contracts/README.md) | 字段、枚举、样例与接口约定 |

## 规则的唯一来源

架构以 ADR 为准；domain schema 与已实现 OpenAPI 从后端 Pydantic/路由生成，禁止手改；事件与 AI schema 独立维护。端点行为及未完成范围见 API 契约。中文检查和英文说明保持一致，同一 PR 同步源模型、生成文件、样例和文档。

仓库根目录原始 v2 方案是产品输入；[早期启动计划](../project-kickoff-plan.md)保留为历史提案，不覆盖本基线。原方案中的指标、接入能力和用户收益不能视为已经测试通过。

## 当前可以执行的验证

按[英文开发入口](../en/getting-started.md)安装校验依赖后运行：

```text
python scripts/check_baseline.py
```

该命令只校验文档与样例；应用启动、迁移、Ruff、类型与业务测试的真实命令已写入开发入口，实际结果见已完成工作记录。
