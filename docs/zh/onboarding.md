# 新成员入门与首个 PR

适用版本：v0.2 回放骨架。每位成员，包括仓库创建者，都按同一流程参与。本文是操作清单，完成与否由实际证据决定；作者或自动化复查不能替代另一位队友独立实测。

## 1. 准备自己的环境

- Git、自己的 GitHub 账号；提交使用自己的身份，不共享登录、Token 或 SSH 私钥。
- Docker Engine / Docker Desktop，支持 Linux 容器和 `docker compose`。先打开引擎再运行命令。
- 只运行回放可以全部使用容器；本地代码开发另需 Python 3.12.10、Node 24.15.0、npm 11.12.1。依赖必须按锁文件安装。
- 可以访问 GitHub、容器镜像与依赖下载服务。端口默认是 web 18080、API 18000、数据库 54329，不能与其他服务冲突。
- GitHub 权限尚未配置时可以克隆公开仓库；提交同仓库分支需要成员权限，也可通过 fork 提交 PR。

在终端确认 `git --version`、`docker version`、`docker compose version`。`docker version` 必须同时能看到客户端和服务端；只有客户端版本不代表引擎就绪。

## 2. 从全新克隆开始

在自己选择的父目录运行，不复制他人的 `.venv`、`node_modules` 或数据库：

```text
git clone https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood.git
cd GigMate-AI-Work-Assistant-for-Freelancers---GitGood
git status -sb
git rev-parse HEAD
```

记录实际提交 SHA。`v0.2.0` 是固定实现参考，开发任务从最新 main 创建分支，不在标签的 detached HEAD 上开发。仓库未来迁入组织后，以实际新地址为准。

按以下顺序阅读：本文 → [平等协作规则](team-governance.md) → [范围](scope.md) → [工程标准](engineering-standards.md) → [业务流程](domain-workflows.md) → [架构与 ADR](../en/architecture.md) → [契约](../../contracts/README.md)。开始具体任务再读[协作检查表](collaboration-checklist.md)。

## 3. 启动并确认各服务

在仓库根目录运行：

```text
docker compose --env-file .env.example -f infra/compose.yaml up --build -d --wait
docker compose --env-file .env.example -f infra/compose.yaml ps -a
```

预期：数据库和 API 健康，web、worker 运行；migrate 完成并以状态码 0 退出，这是正常的一次性迁移服务。

打开 http://127.0.0.1:18080，API 文档位于 http://127.0.0.1:18000/docs。开发账号 `merchant`，密码 `demo-only-change-me`；`other` 使用相同示例密码，用于查看账号隔离。当前仅处理虚构数据，没有真实 WhatsApp、通用模型或发送功能。

每位队友需要自己的初始数据库状态。新克隆不保证数据库全新：Compose 使用固定项目名 `gigmate-replay`，同一电脑的旧克隆可能共享已有命名卷。已有数据时记录这一情况，不为了复现初始版本而删除数据库。

## 4. 手动运行回放验收

| ID | 操作 | 预期结果 |
| --- | --- | --- |
| ONB-01 | 完成克隆、启动和登录 | 能独立进入工作台，服务状态正常 |
| ONB-02 | 点击 15:00 冲突回放，等待 worker 处理 | 看见原文来源与提议；冲突不能确认，正式工单不变 |
| ONB-03 | 点击 16:30 可用回放，确认前检查工单 | 新提议可核对，但正式安排仍未改变 |
| ONB-04 | 手动确认可用提议 | 工单版本推进、日历更新、旧自动待办取消、新待办生成；地址保持缺失 |
| ONB-05 | 再次点击同一回放 | 去重，不重复创建同一变更或待办 |
| ONB-06 | 重启数据库/API/worker 后刷新并重新登录 | 已确认安排、版本和相关任务保留 |
| ONB-07 | 退出，再用 other 登录 | 看不到 merchant 的工单及原文 |
| ONB-08 | 完成一个小 PR、CI 与同伴评审 | 有真实 Issue、PR、检查链接和评审记录 |

首次默认数据中工单从版本 3 变为 4，16:30–17:30 按 Asia/Hong_Kong 展示。已有回放状态时检查实际版本与记录；不能把“检查已有结果”写成“首次确认经过验证”。这些 ONB 编号是入门验收，与产品 AC 场景分开。

重启与停止命令：

```text
docker compose --env-file .env.example -f infra/compose.yaml restart api worker db
docker compose --env-file .env.example -f infra/compose.yaml down
```

`down` 保留数据库卷，不加 `-v`。重启后需要等待健康检查恢复。

## 5. 运行检查

本地脚本需要 Python 环境。按[英文开发入口](../en/getting-started.md)建立 `.venv` 并安装后端锁文件后，从根目录执行：

```text
.venv/Scripts/python.exe scripts/check_baseline.py
.venv/Scripts/python.exe scripts/smoke_replay.py
```

以上为 Windows 命令，macOS/Linux 使用 `.venv/bin/python`。首次冒烟会确认虚构改期，之后检查已有结果。因此先完成手动验收，再运行冒烟。保存输出，不提交原始日志、数据库或真实会话。只安装 Docker 的队友可先完成浏览器验收，在 PR 中明确本地脚本未运行，再由 CI 执行代码/文档检查；不把它写成本地检查已通过。当前 API 镜像不包含仓库 scripts/docs，不能直接在 api 容器内运行这些脚本。

本地开发与完整检查按[英文开发入口](../en/getting-started.md)执行，不能只运行一个文档检查就宣称所有测试通过。纯文档改动运行基线与链接检查；后端改动检查 Ruff、生成契约、迁移和 PostgreSQL 测试；前端改动检查生成类型、格式和构建。CI 的三个检查为 `documentation-and-contracts`、`backend`、`frontend`。

## 6. 提交首个小 PR

推荐任务：修正本次入门发现的一个具体文档问题，并同步对应英文说明。范围限定到一个可复现问题，不顺带更换框架、依赖或业务规则。没有发现问题时领取一个已有的边界明确的小任务，不制造无意义改动。

1. 用 Engineering task 模板创建 Issue，写明复现步骤、预期行为、范围和 ONB 编号。
2. 从最新 main 建立自己的分支：

```text
git switch main
git pull --ff-only
git switch -c docs/onboarding-first-pr
```

3. 修改相关文档，执行适用检查，记录实际结果。
4. 明确列出要提交的文件，检查差异后提交：

```text
git diff --check
git diff
git add docs/zh/onboarding.md docs/en/getting-started.md
git commit -m "docs(onboarding): clarify the verified setup issue"
git push -u origin docs/onboarding-first-pr
```

上面的文件和分支是示例，应替换为任务的实际范围；已有同名远端分支时换一个名字，不强制覆盖。fork 用户将分支推到自己的 fork，再向上游 main 发 PR。

5. 在 GitHub 创建 PR，base 为 main，关联 Issue，填写现有 PR 模板；附检查结果、限制和[入门报告](onboarding-report-template.md)。
6. 请求任意另一位有权限且能评审该改动的队友审查。作者不能批准自己的 PR；不指定仓库创建者为唯一审核人。
7. 全部必需 CI 通过、意见解决、至少一位独立队友批准后，任何同等权限成员都可以合并。作者可以在满足这些条件后执行合并。

当前仍只有一人时记录 solo self-review，不能虚构独立批准或把本次文档交付当成 ONB-08 已通过。主分支保护是否生效见完成记录，流程约定与平台设置分别核对。

## 7. 反馈问题并修正文档

复制[报告模板](onboarding-report-template.md)到 Onboarding verification Issue 或 PR 描述，逐项标明通过、失败、未执行。另一位队友应先按文档尝试；需要口头帮助时记录帮助点，而不是隐藏障碍。

每个问题记录：系统及工具版本、提交 SHA、所在步骤、预期/实际结果、去敏后的错误、处理办法、对应修复 PR。修复后由遇到问题的成员重试，再更新[完成记录](progress.md)与英文记录。

不得上传真实聊天、二维码、Cookie、Token、密钥、session 文件；英文和中文文档都保持事实一致。

## 常见故障

| 现象 | 首先检查 | 处理 |
| --- | --- | --- |
| Docker pipe/daemon 连接失败 | 引擎是否启动，是否使用 Linux 容器 | 启动 Docker Desktop，确认 docker version 的服务端，再重试；不算应用测试通过 |
| 端口占用 | 18080、18000、54329 的已有服务 | 不终止无关服务；复制 .env.example 为忽略的 .env，调整 web/API 端口及 TRUSTED_ORIGINS 后用 --env-file .env 启动；数据库端口目前写在 Compose 中，需另作明确配置变更 |
| 下载镜像或依赖失败 | 网络和实际下载错误 | 保存去敏错误，恢复下载后重试；使用锁文件，不随意升级依赖 |
| 登录失败 | 实际 seed 密码与账号 | 使用首次 seed 的密码；后来改 DEMO_PASSWORD 不会重置已有账号 |
| CSRF/Origin 拒绝 | 浏览器地址与 TRUSTED_ORIGINS | 使用文档中的地址，配置对应 origin，不关闭保护绕过 |
| 回放没有提议 | worker、任务错误和输入 | 查日志；桩只支持固定回放；STUB_UNSUPPORTED_INPUT 不是通用 AI 失败 |
| 初始版本不是 3 | 本机已有项目卷或之前确认记录 | 记录已有状态，按持久结果复查，不删除共享数据 |

排查命令：`docker compose --env-file .env.example -f infra/compose.yaml logs --tail 50 api worker migrate`。先去敏再提供片段。新增故障项必须来自实际问题或明确的配置限制，注明未实测的环境。
