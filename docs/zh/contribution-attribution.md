# 提交归属说明：署名为 `Zhao, Dingcheng <shredry1@gmail.com>` 的提交

## 为什么写这份文件

做角色 B 工作的那台机器，仓库级 git 身份是 `Zhao, Dingcheng <shredry1@gmail.com>`（`git config user.name` 与 `git config user.email`，且没有配置全局身份）。因此这台机器上产生的每一个提交都会带上这个作者名，包括 **WillW27（`willw7@connect.hku.hk`）** 在 2026-10-08 至 2026-10-17 期间借助 AI 完成的工作。仅凭 git 元数据无法区分两者，所以用本文件明确记录归属，供评审、验收与评分使用。

本文采用的判定规则：提交信息或分支名包含 `Role B`、`role-b`、`will`、`WillW27` 的，归 WillW27；其余保持原作者不变。

## 已经修正（PR #35 分支上的 9 条）

2026-10-17 已把分支 `WillW27/role-b-live-gates-and-order-evidence` 的 author 与 committer 全部重写为 `WillW27 <willw7@connect.hku.hk>`，并用 `--force-with-lease` 推送；[PR #35](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/35) 现在 9 条提交全部显示 WillW27。重写前的历史保留在本地备份分支 `backup/role-b-before-author-fix`。

| 新 sha | 旧 sha | 日期 | 提交信息 |
| --- | --- | --- | --- |
| `2872af8` | `cea901b` | 2026-10-17 | feat: real-model extraction gates and work-order media evidence |
| `a95d21a` | `72ae7f6` | 2026-10-17 | docs: record live DeepSeek smoke evidence and image-capability probe |
| `41a4f0f` | `9b78a86` | 2026-10-17 | merge: integrate main into media-authorization and work-order-evidence batch |
| `e92b599` | `b5b9dc1` | 2026-10-17 | feat: live vendor quality, real media seam and bounded agent drafts |
| `f64f2f2` | `a0f8c57` | 2026-10-17 | feat: file-based model credentials, recorded vendor decision and a real PDF run |
| `381fc02` | `b9b27fa` | 2026-10-17 | fix: keep evidence promotion in one request transaction and bound PostgreSQL waits |
| `d8f5cd1` | `5ed8722` | 2026-10-17 | fix: renumber the migration revisions and seed the event PostgreSQL requires |
| `ff541b2` | `6419ee8` | 2026-10-17 | merge: integrate main (#34) and close the remaining PostgreSQL self-deadlocks |
| `2241e12` | `c4e788d` | 2026-10-17 | test(pdf): declare Linux-only PDF isolation cases |

## 归 WillW27，但**故意不重写**的 19 条（已并入 `main`）

这些提交已通过 PR #18、#20、#31、#33 合并进 `main`。要改它们就必须 force push `main`，那会让所有队友的本地仓库失效、并改变所有已合并 PR 的 sha；团队决定不这么做，改以本文件作为归属凭证。

| sha | 日期 | 提交信息 |
| --- | --- | --- |
| `485762c` | 2026-10-09 | Role B: llm provider skeleton for the real-model batch |
| `d29eb71` | 2026-10-10 | Merge remote-tracking branch 'origin/main' into william/role-b-deepseek-integration |
| `df7c82b` | 2026-10-10 | Role B: wire LLM provider to real DeepSeek call (mock-based tests) |
| `202ab17` | 2026-10-10 | Role B: anchor manifest path resolution to repo root |
| `72b1dc6` | 2026-10-10 | Role B: address P2 review findings on PR head e44d8ec |
| `4a9c4cd` | 2026-10-10 | Role B: address PR #18 review findings on the llm skeleton |
| `85711eb` | 2026-10-10 | feat(media): real-model processor seam (Role B) |
| `cc2ac8e` | 2026-10-10 | Merge pull request #18 from sh0redry/WillW27/role-b-llm-skeleton |
| `1dc716f` | 2026-10-10 | Merge remote-tracking branch 'origin/main' into role-b-deepseek-integration-merge |
| `bbb0074` | 2026-10-10 | Merge pull request #20 from sh0redry/WillW27/role-b-deepseek-integration |
| `81e0fa1` | 2026-10-12 | feat(media): real PDF parser with two-layer extraction (Role B) |
| `e2c8755` | 2026-10-16 | Role B: implement the real-text pre-activation acceptance gates |
| `f4bd7df` | 2026-10-16 | docs: correct Role B gate evidence counts and branch name |
| `a4e6b8a` | 2026-10-16 | Role B: land pre-activation batch 2 (cost boundary, startup audit, injection regression) |
| `3a0a23f` | 2026-10-16 | Role B: land pre-activation batch 3 part 1 (new-work-order contract, evaluation classification, unknown-outcome pinning) |
| `382f1c4` | 2026-10-16 | Role B: land pre-activation batch 4 (media-attachment injection regression) |
| `ce2aaf9` | 2026-10-17 | Role B: fix PR #31 review findings P2-1..P2-5 in extraction LLM gates |
| `914df74` | 2026-10-17 | Role B: re-fix PR #31 review findings P2-1..P2-5 (round 2) in extraction gates |
| `d9e1fe7` | 2026-10-17 | Role B: close PR #31 review round 2 findings (P2-1, P2-2, P2-6, P2-7) |

## 暂未认领、待 WillW27 确认的 8 条

属于同批角色 B 工作，但提交信息里没有 `Role B` / `will` 关键字，因此本文**不**主张归属：

| sha | 日期 | 提交信息 |
| --- | --- | --- |
| `534c2b3` | 2026-10-10 | fix(extraction): anchor manifest path to repo root |
| `e44d8ec` | 2026-10-10 | docs: note manifest path resolution now anchored to repo root |
| `b5d7e84` | 2026-10-10 | fix(docs): add blank line between PR #21 review correction and B media section |
| `0d91ad1` | 2026-10-12 | test(media): pin the new pre-client PDF refusal code |
| `9d6db85` | 2026-10-17 | docs(freeze): record AI-detected new work orders as follow-up |
| `cc0c5ec` | 2026-10-17 | docs(freeze): narrow the record to proposal-based creation |
| `c96ec7f` | 2026-10-17 | Merge remote-tracking branch 'origin/main' into docs/freeze-2026-10-16-workorder-creation |
| `038ae3b` | 2026-10-17 | Merge main e912977 into PR #31 branch (resolve worker.py, progress docs, generated types) |

## 明确不认领

- 所有 `sh0redry <sh0redry@connect.hku.hk>` 的提交（44 条）—— 同一项目的另一个身份。
- `0630e8a`（2026-09-29）Initial commit，以及 PR #4、#5、#15、#16、#24、#25、#30 的合并提交 —— 没有 `Role B` / `will` 标记。
- `Kyriehe`、`Kyrie`、`kyrieslhe`、`Lena`、`Lena070112` 的全部提交。
- `Andy_WAHA*`、`Kyrie_Frontend`、`lena/*`、`codex/*` 分支上的提交。

## 如何核验

```bash
# main 上仍带旧身份的角色 B / WillW27 提交
git log origin/main --author='shredry1@gmail.com' --format='%h | %ad | %s' --date=short | grep -Ei 'role.?b|will'

# 已修正的 PR #35 分支
git log origin/main..origin/WillW27/role-b-live-gates-and-order-evidence --format='%h | %an <%ae> | %s'

# 所有分支的作者分布
git log --all --format='%an <%ae>' | sort | uniq -c | sort -rn
```

## 防止再次发生

每个克隆执行一次（助手不得修改 git 配置）：

```bash
git config user.name "WillW27"
git config user.email "willw7@connect.hku.hk"
```

在此之前，助手每次提交都会显式带上 `--author="WillW27 <willw7@connect.hku.hk>"`。相关记录见 [progress.md](progress.md)。
