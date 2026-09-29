# P4.2 Compatibility Repair & Upgrade Promotion Ledger

## Release
**ChatGPT Web HWPX MCP P4.2 — Upstream Compatibility Repair, Semantic Migration Adapters, Real-Document Regression Matrix, Controlled Dependency Canary, Performance Budgeting, Diagnostic Provenance & Zero-Surprise Upgrade Promotion**

## Product objective
Repair the concrete python-hwpx 6.6.0 incompatibilities observed at P4.1 without weakening P3.18/P3.19/P3.38 semantics, then promote the dependency only after version-parallel product evidence closes.

## Compatibility repairs
- Page geometry: separate raw OWPML storage geometry from drawn page geometry. Current Hancom semantics (`NARROWLY` landscape / `WIDELY` portrait) and P3.18 legacy 6.5 swapped-`WIDELY` documents map to one stable product contract.
- Numbered lists: migrate the historical default pattern `^1.` to semantic `DIGIT`; preserve the label pattern through the upstream numbering definition instead of abusing `numFormat` as free text.
- Rich-builder: inherits the P3.18 semantic page map; no special P3.38 fork.

## Real-document canary
Three HWPX attachments from one official Ministry of Education work with KOGL Type 1 attribution are fetched ephemerally in CI. No bytes are committed or redistributed. Both source pin and candidate parse the exact same URLs.

## Promotion sequence
1. keep production pin 6.5.0;
2. run 6.5 and 6.6 targeted regressions;
3. run same real-document matrix under both versions;
4. enforce frozen P4.1 performance budget;
5. build candidate Docker with 6.6;
6. rehearse exact rollback to 6.5;
7. only then create a separate pin-promotion commit;
8. require full lifecycle + exact-head Render + public boundary before production closure.

## Closure target
`P42_SEMANTIC_PAGE_ADAPTER_PASS / P42_LIST_FORMAT_MIGRATION_PASS / P42_SOURCE_PIN_REGRESSION_PASS / P42_CANDIDATE_REGRESSION_PASS / P42_REAL_DOCUMENT_MATRIX_PASS / P42_PERFORMANCE_BUDGET_PASS / P42_CANDIDATE_DOCKER_PASS / P42_ROLLBACK_REHEARSAL_PASS / P42_DEPENDENCY_PROMOTED / P349_AUTHORITY_PRESERVED / FULL_LIFECYCLE_PASS / EXACT_HEAD_RENDER_DEPLOY_PASS / PRODUCTION_BOUNDARY_PASS`
