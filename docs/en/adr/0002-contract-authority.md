# ADR 0002 Documentation and contract authority

- Status: Accepted; domain/OpenAPI/type generation implemented in v0.2
- Date: 2026-10-01
- Owner: Repository maintainer

## Decision

Root README and `docs/en/` provide English navigation. `docs/zh/` provides internal checks and working requirements; root README must not reference it. Internal-facing files are still accessible in a public repository.

ADRs govern architecture, schemas govern fields/enums, and the API agreement governs endpoints. Bilingual documentation expresses the same rules. Contradictions block the affected change until reconciled. The original plan is context; the kickoff proposal is historical planning.

## Schema authority transition

Baseline v0.1 used handwritten domain schemas. In v0.2, apps/backend/src/gigmate/contracts.py is canonical; scripts/export_contracts.py generates contracts/domain/models.schema.json and contracts/openapi.json. Frontend generate:api creates src/generated/api.d.ts. Backend --check and frontend check:api detect drift; original positive/negative fixtures remain compatible. Event/AI schemas remain independently versioned. OpenAPI describes implemented routes only; model definitions do not establish implemented action services.

Update affected documents and samples in the same PR. Negative fixtures are intentionally invalid and marked in the manifest. Scenario expectations describe intended behavior, not executed test results.
