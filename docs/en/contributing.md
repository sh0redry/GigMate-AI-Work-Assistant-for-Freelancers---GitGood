# Contribution rules

## Tasks and branches

Use the task template with scenario, module, dependencies, case IDs and exclusions. Prefer changes reviewable within a day. Use `feat/<name>`, `fix/<name>`, `docs/<name>` or `chore/<name>`. Keep main coherent and reviewable. Commit format: `type(scope): summary`.

## Review

Use the PR template to describe behavior, contracts, validation and limits. Link the issue and acceptance cases. Label documentation-only future behavior accurately.

With one maintainer, record self-review against the checklist before merging. Once another contributor is active, require an independent reviewer for code changes. Shared schemas, migrations and approval rules require affected module-owner review. Solo work still requires validation and migration notes. Host branch protection must be configured separately; templates do not enforce it.

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

Before backend implementation, handwritten schemas and API agreements are canonical. Execute the schema-source transition in [ADR 0002](adr/0002-contract-authority.md) as one reviewed change; do not keep manual and generated competing definitions. Never edit a shared migration to hide a schema change.

Record architectural decisions in ADRs. Use issues for current work and blockers; when contributors join, assign module owners and check the main flow daily.
