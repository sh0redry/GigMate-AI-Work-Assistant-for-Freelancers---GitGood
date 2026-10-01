# Contribution rules

## Tasks and branches

Use the task template with scenario, module, dependencies, case IDs and exclusions. Prefer changes reviewable within a day. Use `feat/<name>`, `fix/<name>`, `docs/<name>` or `chore/<name>`. Keep main coherent and reviewable. Commit format: `type(scope): summary`.

## Review

Use the PR template to describe behavior, contracts, validation and limits. Link the issue and acceptance cases. Label documentation-only future behavior accurately.

With one contributor, record self-review against the checklist before merging. Once another contributor is active, require at least one independent peer approval for PRs, including onboarding documentation. Any member can merge after checks and review requirements are met; the creator is not a mandatory approver. Shared schemas, migrations and approval rules require an informed reviewer from the affected areas, not an exclusive module-owner gate. Solo work still requires validation and migration notes. Host branch protection must be configured separately; templates do not enforce it. See [equal collaboration and onboarding](team-governance.md) for permissions, platform limits and the pending setup.

## Definition of done

- Scope and acceptance cases are met; status is accurate.
- Schemas, fixtures, endpoint behavior and bilingual rules agree.
- Ownership, provenance, versions and errors follow the baseline.
- Applicable checks pass, with command output in the PR.
- New behavior has meaningful normal/failure tests; documents use baseline checks.
- No credentials, real chat, session files or private screenshots are included.
- Setup and migrations are reproducible when applicable.

## Shared changes

Wire fields use snake_case and canonical enums. Required-field additions, removals, renames, enum changes and reinterpreted states are breaking: bump the major schema/API version and describe migration. Compatible optional additions may bump minor versions, but strict clients still require coordination.

The transition in [ADR 0002](adr/0002-contract-authority.md) is implemented. Update Pydantic models, run scripts/export_contracts.py and frontend generate:api, then verify drift and fixture compatibility. Event/AI schemas remain independently maintained. Never edit generated files or shared migrations to hide a change. Update both implementation-status records with actual evidence.

Record architectural decisions in ADRs. Use issues for current work and blockers; when contributors join, agree rotating module contacts for coordination and check the main flow regularly. Contacts have no additional permissions or exclusive approval rights.
