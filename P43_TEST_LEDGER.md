# P4.3 Continuous Product Health Ledger

## Release
**ChatGPT Web HWPX MCP P4.3 — Representative Document Compatibility Service, Persistent Cross-Release Benchmarking, SLO-Calibrated Performance Budgets, Reproducible Failure Bundles, Regression Localization & Continuous Product Health Gates**

## Product objective
Turn P4.2's one-release compatibility evidence into a continuously deployable product-health service.

## External ecosystem use
- **python-hwpx 6.6.0** — production authoring/read-write engine.
- **raw ZIP + OWPML** — lowest-level package/XML structural oracle.
- **hwpxkit 0.2.1 / hwp-rs** — independent Rust parser oracle, CI-only.
- **python-hwpx-automation** — architecture/corpus/release-method donor only; not a runtime dependency because overlapping application/MCP authority remains locally owned.

External oracles never become mutation authority.

## Representative lanes
Generated feature families:
1. DOCUMENT_SETUP — P3.18 regression corpus
2. STRUCTURED_PUBLISHING — P3.19 regression corpus
3. ADVANCED_TABLES — P3.23 regression corpus
4. DRAWING_LAYER — P3.25 regression corpus

Public real-document family:
5. PUBLIC_OFFICIAL_DOCUMENT — three official Ministry of Education HWPX artifacts, ephemeral CI acquisition.

The gate therefore starts with >=5 feature families and >=27 documents/fixtures. This is a representative product-health seed, **not** a claim of population-wide HWPX representativeness.

## Multi-oracle rule
A document is consensus-PASS only when:
- raw HWPX package/OWPML oracle passes;
- python-hwpx parses it;
- hwpxkit parses it;
- section-count semantics agree across all available passing oracles.

Oracle disagreement is retained and localized; it is never silently majority-voted away.

## Cross-release benchmarking
History is review-append-only at `benchmarks/p43_release_history.json`.
- P4.1 and P4.2 are frozen seeds.
- fewer than 5 exact-head release observations => **PROVISIONAL_HARD_BUDGET**
- 5+ release observations => robust median/MAD-calibrated budget can become active.

Shared-runner timing is product-health evidence, not native-render or user-perceived SLO authority.

## Failure bundles
Failure bundles include source identity, SHA-256, feature family, oracle/version, bounded error class/message, localization and reproduction route. They exclude source bytes and raw stack traces by default.

## Release-health gate
PASS requires:
- >=5 feature families;
- >=3 public real documents;
- >=18 generated regression fixtures;
- multi-oracle consensus;
- performance budget PASS;
- deterministic diagnostic negative control;
- exact Docker PASS;
- rollback-ready release lineage;
- zero critical failures.

## Closure target
`P43_REPRESENTATIVE_MATRIX_PASS / P43_MULTI_ORACLE_CONSENSUS_PASS / P43_CROSS_RELEASE_HISTORY_PASS / P43_PROVISIONAL_BUDGET_PASS / P43_FAILURE_BUNDLE_PASS / P43_REGRESSION_LOCALIZATION_PASS / P43_HEALTH_GATE_PASS / P42_AUTHORITY_PRESERVED / FULL_LIFECYCLE_PASS / EXACT_DOCKER_PASS / EXACT_HEAD_RENDER_DEPLOY_PASS / PRODUCTION_BOUNDARY_PASS`
