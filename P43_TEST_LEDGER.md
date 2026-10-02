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

Immutable external fixture families, pinned to exact upstream commits and Git blob identities:
5. FORMATTING
6. NOTES
7. FORM_FIELDS
8. NUMBERING
9. MERGED_TABLES
10. TEXTBOX_FIELDS
11. HYPERLINKS
12. LINE_SPACING

Sources are split across Apache-2.0 `airmang/python-hwpx` and MIT `Han-taz/hwpx-rust`. The blocking denominator therefore begins with **12 feature families / 32 generated-or-immutable fixtures**.

The three official Ministry of Education HWPX URLs remain a **live freshness lane**. Their availability/parser observations are recorded but do not block a release when the source site is transiently unavailable. This is a representative product-health seed, **not** a claim of population-wide HWPX representativeness.

## Multi-oracle rule
Product authority and independent observation are deliberately separated.

**Product-authority PASS** requires:
- raw HWPX package/OWPML oracle passes;
- python-hwpx parses it;
- raw/package and python-hwpx section semantics agree.

**Independent consensus** additionally asks hwpxkit 0.2.1 to parse and agree. A hwpxkit-only divergence is retained as a WARNING failure bundle and regression-localization signal; it does not silently become a product failure. The representative release gate still requires at least **80% independent-oracle coverage** across the full denominator.

No disagreement is majority-voted away, and raw/python product failures remain release-blocking.

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
- >=12 combined generated/external feature families;
- >=6 immutable external HWPX documents from >=2 upstream repositories;
- >=18 generated regression fixtures;
- multi-oracle consensus;
- performance budget PASS;
- deterministic diagnostic negative control;
- exact Docker PASS;
- rollback-ready release lineage;
- zero critical failures.

## Closure target
`P43_REPRESENTATIVE_MATRIX_PASS / P43_MULTI_ORACLE_CONSENSUS_PASS / P43_CROSS_RELEASE_HISTORY_PASS / P43_PROVISIONAL_BUDGET_PASS / P43_FAILURE_BUNDLE_PASS / P43_REGRESSION_LOCALIZATION_PASS / P43_HEALTH_GATE_PASS / P42_AUTHORITY_PRESERVED / FULL_LIFECYCLE_PASS / EXACT_DOCKER_PASS / EXACT_HEAD_RENDER_DEPLOY_PASS / PRODUCTION_BOUNDARY_PASS`

## First P4.3 release-health observation
- measured head: `c4a48b2ee45758a0f87d01bd5496bc7950c97321`
- generated matrix: **24/24 PASS**, 4 internal feature families
- immutable external matrix: **8/8 product-authority PASS**, **8/8 hwpxkit agreement**, 8 external feature families, 2 upstream repositories
- combined blocking denominator: **32 documents/fixtures / 12 feature families / 100% independent-oracle coverage**
- performance: create+validate p95 **125.54 ms**; existing validate p95 **1.13 ms**; `PROVISIONAL_HARD_BUDGET` PASS
- release-health: **PASS / failed_gates=[] / failure_bundles=0**
- live Ministry freshness lane: **UNAVAILABLE in this run**, preserved as nonblocking acquisition evidence (artifact `11014381855`)
- release-health artifact: `11014372061`
- immutable external artifact: `11014206214`
- performance artifact: `11014087185`
- generated matrix artifact: `11013687876`

P4.3 is the third exact-head benchmark observation. Calibrated SLO remains intentionally disabled until at least five release observations exist.
