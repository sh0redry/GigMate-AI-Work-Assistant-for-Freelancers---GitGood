# ADR 0004 Equal collaboration

- Status: Accepted policy; platform permissions/protection pending
- Date: 2026-10-01
- Decision requested by: Project initiator; applies equally to all members

## Decision

All actual members have the same repository permission target and can propose, review and merge. Module contacts rotate and coordinate interfaces, not authority. Any qualified independent peer may approve; there is no creator-only or mandatory code-owner gate. Once two contributors are active, PRs require one independent approval and applicable checks. Solo self-review remains an explicitly recorded temporary mode.

The permission target is identical repository Admin access through a team in a GitHub organization. The current personal repository cannot assign owner-equivalent management permissions to multiple collaborators. Organization Owner privileges are a separate scope that needs an explicit decision. Migration and invitations await real usernames, organization and permission scope.

main should require PRs, stale-review dismissal, resolved discussions, up-to-date passing checks and protection applying to administrators without a per-member bypass. Any member can merge a compliant PR. All-admin access allows rule changes, so shared administration conventions remain necessary. See [governance and platform sources](../team-governance.md).

## Consequences and evidence

Equal access does not remove business approval, ownership/provenance checks or CI requirements. Admin rights are not contingent on passing onboarding. Independent onboarding records setup friction and the first real peer-reviewed PR; a maintainer or automated substitute cannot prove it.

Documentation, report and issue/PR templates are prepared. Actual teammate verification, permission assignments and branch protection are not implemented by this ADR. Changing permission scope or merge policy requires a recorded amendment and matching English/internal documents.
