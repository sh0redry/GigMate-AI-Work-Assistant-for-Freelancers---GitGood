# ADR 0002 Documentation and contract authority

- Status: Accepted baseline; schema generation pending
- Date: 2026-10-01
- Owner: Repository maintainer

## Decision

Root README and `docs/en/` provide English navigation. `docs/zh/` provides internal checks and working requirements; root README must not reference it. Internal-facing files are still accessible in a public repository.

ADRs govern architecture, schemas govern fields/enums, and the API agreement governs endpoints. Bilingual documentation expresses the same rules. Contradictions block the affected change until reconciled. The original plan is context; the kickoff proposal is historical planning.

## Schema authority transition

Baseline v0.1 uses handwritten schemas and API agreements because no backend exists. The skeleton must implement matching Pydantic models, demonstrate fixture compatibility, then switch domain/API schema generation to those models in one reviewed change. Add generated OpenAPI/frontend types, generated-file labels and CI drift checks. Keep independently versioned event and AI schemas explicit. Remove competing handwritten copies.

Update affected documents and samples in the same PR. Negative fixtures are intentionally invalid and marked in the manifest. Scenario expectations describe intended behavior, not executed test results.
