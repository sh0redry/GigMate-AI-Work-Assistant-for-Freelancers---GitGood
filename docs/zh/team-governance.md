# 平等协作与仓库权限

团队目标：所有实际成员具有相同的仓库权限、提案权、评审权与合并权。仓库创建者遵守同样的工程流程。模块联系人负责沟通和交接，可以轮换，不拥有独占审批权；任何成员可以修改任何模块，跨模块变更需邀请熟悉相关内容的队友复核。

决策记录见 [ADR 0004](../en/adr/0004-equal-collaboration.md)。

## 权限目标与当前状态

截至2026年10月1日，仓库仍由个人账号 sh0redry 持有。GitHub 个人仓库只有 owner 与 collaborator 两级，不能让多位协作者拥有与 owner 相同的管理权限。当前没有完成成员统一授权；成员名单和目标组织待明确。

实现相同仓库管理权限的目标方案是：由团队确认目标 GitHub Organization，迁入仓库后通过一个团队给所有项目成员统一 Admin，并检查个人或其他团队授权没有造成额外差异。Admin 涵盖仓库设置和成员权限；组织策略仍可能限制删除、转移等操作。仓库 Admin 不等同组织 Owner；若“全部权限”也包含组织成员管理、计费等，需另外明确组织 Owner 范围，不能用仓库角色冒充组织权限。

具体迁移、成员邀请与授权必须先有实际用户名、目标组织及权限范围。每人使用自己的账号，接受邀请后分别验证权限。本文没有执行组织迁移或发出邀请。

依据：[GitHub 个人仓库权限](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)、[组织仓库角色](https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization)。

## 共同开发流程

- 所有人先创建有范围与验收条件的 Issue，再在分支中修改，通过 PR 合并。
- 至少一位独立队友评审，评审者可以轮换；不要求固定某个人批准，也不要求必需 CODEOWNERS 审核。
- 满足同伴批准、适用检查通过和意见解决后，任何成员均可合并；作者不能自我批准。
- 技术意见针对证据和规则，不能因成员资历不同采用不同验收要求。意见未解决时记录具体分歧，共同讨论；规则变化留下 ADR 或文档 PR。
- 当前单人阶段保留有记录的自审；第二位成员开始参与后采用同伴评审，不把新成员入门当成权限晋级考试。
- 删除、转移仓库、变更可见性、权限和保护规则等管理动作先留下影响说明并由另一成员复核；这是所有人共同遵守的操作约定，不是降低任何人的平台权限。

## 主分支保护配置清单（待平台落地）

| 项目 | 团队目标 |
| --- | --- |
| 目标分支 | main |
| 合并入口 | Require a pull request before merging |
| 独立批准 | 至少 1 人；有第二位实际成员后启用，单人期间不虚构评审 |
| 审批时效 | 新提交使旧批准失效，合并前解决讨论 |
| 必需检查 | documentation-and-contracts、backend、frontend，选择真实运行的 GitHub Actions 检查 |
| 检查最新代码 | Require branches to be up to date before merging |
| 适用对象 | 包括管理员；不为创建者或特定成员设置绕过名单 |
| 推送与删除 | 不允许强制推送、删除 main，不仅允许某个固定成员合并 |
| 固定代码所有者审核 | 不启用；邀请适合的同伴即可 |

若使用规则集，检查同样的目标与绕过设置；不盲目叠加互相冲突的规则。现有记录仍为“未配置”，文件不能替代 GitHub 设置。配置时记录实际规则、成员可见权限、检查名、验证 PR 与日期，并同步中英文完成记录。

全员 Admin 可以修改保护规则，因此“规则适用于所有人”不代表“管理员永远无法修改规则”。一致权限通过统一授权实现，一致流程通过平台检查与共同遵守实现。依据：[受保护分支](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。
