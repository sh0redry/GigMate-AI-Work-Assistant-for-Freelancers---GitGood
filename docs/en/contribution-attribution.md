# Contribution attribution: commits written as `Zhao, Dingcheng <shredry1@gmail.com>`

## Why this file exists

The repository-level git identity on the machine used for the role-B work was `Zhao, Dingcheng <shredry1@gmail.com>` (`git config user.name` and `git config user.email`; no global identity was configured). Every commit produced on that machine therefore carries that author, including the work done by **WillW27 (`willw7@connect.hku.hk`)** with AI assistance between 2026-10-08 and 2026-10-17. Git metadata alone cannot separate the two, so this file records the attribution explicitly for review, acceptance and grading.

Scope rule used here: a commit is claimed by WillW27 when its subject or branch name contains `Role B`, `role-b`, `will` or `WillW27`. Everything else stays with its git author.

## Already corrected (9 commits on the PR #35 branch)

On 2026-10-17 the branch `WillW27/role-b-live-gates-and-order-evidence` was rewritten so that both author and committer are `WillW27 <willw7@connect.hku.hk>`, then pushed with `--force-with-lease`. [PR #35](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/35) now lists all 9 commits under WillW27. The pre-rewrite history is kept locally on `backup/role-b-before-author-fix`.

| New sha | Old sha | Date | Subject |
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

## Attributed to WillW27, intentionally **not** rewritten (19 commits already in `main`)

These commits were merged into `main` through PRs #18, #20, #31 and #33. Rewriting them would require a force push to `main`, which invalidates every teammate's local clone and changes the sha of every merged PR; the team decided against it. This section is the attribution record instead.

| Sha | Date | Subject |
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

## Candidates left unclaimed (need WillW27's confirmation)

Same working sessions and the same role-B content, but the subject carries no `Role B` / `will` keyword, so they are **not** claimed here:

| Sha | Date | Subject |
| --- | --- | --- |
| `534c2b3` | 2026-10-10 | fix(extraction): anchor manifest path to repo root |
| `e44d8ec` | 2026-10-10 | docs: note manifest path resolution now anchored to repo root |
| `b5d7e84` | 2026-10-10 | fix(docs): add blank line between PR #21 review correction and B media section |
| `0d91ad1` | 2026-10-12 | test(media): pin the new pre-client PDF refusal code |
| `9d6db85` | 2026-10-17 | docs(freeze): record AI-detected new work orders as follow-up |
| `cc0c5ec` | 2026-10-17 | docs(freeze): narrow the record to proposal-based creation |
| `c96ec7f` | 2026-10-17 | Merge remote-tracking branch 'origin/main' into docs/freeze-2026-10-16-workorder-creation |
| `038ae3b` | 2026-10-17 | Merge main e912977 into PR #31 branch (resolve worker.py, progress docs, generated types) |

## Explicitly not claimed

- Every commit authored as `sh0redry <sh0redry@connect.hku.hk>` (44 commits) — a different identity on the same project.
- `0630e8a` (2026-09-29) Initial commit, and the merges of PRs #4, #5, #15, #16, #24, #25 and #30 — no `Role B` / `will` marker.
- All commits by `Kyriehe`, `Kyrie`, `kyrieslhe`, `Lena` and `Lena070112`.
- Commits on `Andy_WAHA*`, `Kyrie_Frontend`, `lena/*` and `codex/*` branches.

## How to verify

```bash
# role-B / WillW27 commits still carrying the old identity in main
git log origin/main --author='shredry1@gmail.com' --format='%h | %ad | %s' --date=short | grep -Ei 'role.?b|will'

# the corrected PR #35 branch
git log origin/main..origin/WillW27/role-b-live-gates-and-order-evidence --format='%h | %an <%ae> | %s'

# author distribution across all branches
git log --all --format='%an <%ae>' | sort | uniq -c | sort -rn
```

## Preventing a repeat

Run once per clone (the assistant must not change git configuration):

```bash
git config user.name "WillW27"
git config user.email "willw7@connect.hku.hk"
```

Until that is done, every commit made by the assistant passes `--author="WillW27 <willw7@connect.hku.hk>"` explicitly. Related records: [implementation-status.md](implementation-status.md).
