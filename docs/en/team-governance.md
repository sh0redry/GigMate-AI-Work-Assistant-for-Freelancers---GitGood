# Equal collaboration and onboarding

All actual project members should have the same repository permissions and ability to propose, review and merge changes. The repository creator follows the same workflow. Module contacts coordinate work and can rotate; they do not have exclusive approval rights. Any member may change any module, with informed peer review for shared contracts, migrations and approval behavior.

See [ADR 0004](adr/0004-equal-collaboration.md) for this policy decision.

## Platform status and permission target

On 2026-10-01 the public repository is owned by the personal account sh0redry. Personal repositories have one owner and collaborators; collaborators cannot receive the owner's complete management permissions. Equal administrative repository access is not configured.

The target is a team-agreed GitHub organization with the repository assigned to one team granting every project member Admin. Audit other individual/team grants for differences. Organization policy can still restrict deletion or transfer. Repository Admin is distinct from organization Owner; organization membership administration and billing require a separately agreed scope. Actual usernames, organization and scope are needed before migration/invitations. Use individual accounts, not shared credentials. No migration or invitations were performed by this documentation change.

Sources: [personal repository permissions](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository), [organization repository roles](https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization).

## Shared merge and administration process

- Start with a scoped issue, branch and PR. Any qualified peer can review; no creator-only or mandatory code-owner gate.
- Once a second contributor participates, require at least one independent approval for PRs, applicable checks and resolved discussions. Authors cannot approve their own PR; any member can merge when conditions are met.
- Until then, record solo self-review. Do not fabricate peer approval or treat onboarding as a permission-promotion examination.
- Resolve disagreements using evidence and recorded decisions. Architectural changes use ADRs.
- Management operations affecting deletion, transfer, visibility, permissions or protection settings need a recorded impact and another member's review. This is a common operating agreement, not a lesser platform role for some members.

## Main branch protection — applied 2026-10-06

At the user's explicit request, main protection was configured and read back through GitHub API: PR with one approval, stale approvals dismissed, conversations resolved, strict up-to-date status checks `documentation-and-contracts`, `backend`, `frontend` restricted to GitHub Actions app 15368; administrators included; force pushes/deletion disabled; no review bypass list or CODEOWNERS gate. PR #3 has passing checks and zero approving reviews and is blocked pending independent approval. Settings impact: direct/unreviewed main changes are blocked, personal feature branches remain available. Independent teammate review of the administration change is still pending; no attempted force push/delete or merge was used as a verification test. The former target below now describes the applied policy.

Protect main through PRs; require one independent approval after a second member is active; dismiss stale approvals, resolve conversations and require up-to-date branches. Require the existing GitHub Actions checks documentation-and-contracts, backend and frontend. Apply rules to administrators with no creator/member bypass list. Disable force pushes and deletion of main; do not restrict merging to a named person or require CODEOWNERS approval.

Verify existing branch rules/rulesets before changing settings. Record actual configuration, permissions, a verification PR and date in both progress records. All-admin access means members can change protection settings; enforced merge rules do not make the rules immutable. See [protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## Independent teammate onboarding gate

The executable setup/check commands remain in [Getting started](getting-started.md). A teammate must use a fresh clone and their own environment, record the commit SHA/tool versions and any reused database volume, and follow these checks:

| Case | Required observation |
| --- | --- |
| ONB-01 | Clone, start services and sign in independently |
| ONB-02 | Conflicting 15:00 replay cannot be confirmed; formal order stays unchanged |
| ONB-03 | Available 16:30 replay remains a proposal before confirmation |
| ONB-04 | Explicit confirmation updates order/calendar/generated tasks; unknown address stays missing |
| ONB-05 | Repeated replay is deduplicated |
| ONB-06 | Confirmed state survives database/API/worker restart |
| ONB-07 | Other account cannot see merchant's orders/messages |
| ONB-08 | Real small PR, passing CI and an independent peer review |

Fresh seed moves the example order from version 3 to 4. Existing volumes may already contain confirmed state: record that limitation rather than claiming a first confirmation. Compose uses a fixed project name, so another clone on the same machine can reuse its volume. Do manual replay before the HTTP smoke, which confirms synthetic changes on its first run. Do not delete existing volumes for onboarding.

Record participant, date, OS/tool versions, repository/commit, help received, each case's pass/fail/not-run result, actual commands, sanitized error, fix PR, CI/reviewer links and retest. Fix one reproducible setup/documentation issue in a small first PR, updating corresponding English/internal documentation. If no issue is found, select a meaningful existing starter task.

Maintainer or automated fresh-clone checks are supplementary; they cannot replace another person's independent onboarding and approval. The checklist/report materials are prepared; no teammate report or first peer-approved PR has yet been completed. Logs, credentials, real conversations, QR codes and session files must not be published.
