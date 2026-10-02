# ChatGPT Web HWPX MCP P4.4 Test Ledger

## Scope
P4.4 turns P4.3 release-health receipts into durable operational memory without transferring authoring or mutation authority away from `python-hwpx==6.6.0`.

## Durable health store
- Postgres-backed append-only release-health events.
- Postgres-backed append-only corpus-provenance events.
- Idempotency by stable payload hash; no update/delete API.
- Startup bootstrap imports P4.1/P4.2 plus P4.3 final closure head `a970def5bb92db5592b9e0e235baa98a8cd9ba1e`.
- P4.3's closed benchmark file is intentionally not rewritten.

## Federated provenance
Namespaces: `internal-generated`, `airmang/python-hwpx`, `Han-taz/hwpx-rust`, `kr-moe-live`.
Immutable upstream fixtures retain repository, exact commit, Git blob SHA, license, and feature-family identity. The Ministry of Education lane stays nonblocking freshness evidence when acquisition is unavailable.

## Automatic feature-family attribution
Raw ZIP/OWPML evidence produces ranked candidate families, confidence, evidence signals, and explicit abstention. No attribution result grants mutation authority.

## Drift detection
Categorical gate reversals can alert immediately. Performance stays `PROVISIONAL_HARD_BUDGET` before five historical baselines; only then may median/MAD thresholds activate. Engine changes are annotated rather than silently treated as like-for-like history.

## Native-render escalation
Native world-contact is reserved for high-value unresolved independent-oracle divergence, shared OWPML ambiguity, semantic-model divergence, and high-value attribution abstention. Package/container, primary-engine, and performance regressions stay engineering-reproduction lanes first.

## Operator dashboard and support bundle
Dashboard state derives from durable history. Support export excludes document bytes, raw stack traces, secrets, tokens, and passphrases.

## Closure target
`P44_DURABLE_STORE_PASS / P44_FEDERATED_PROVENANCE_PASS / P44_LONGITUDINAL_DRIFT_PASS / P44_ATTRIBUTION_WITH_ABSTENTION_PASS / P44_NATIVE_RENDER_ROUTER_PASS / P44_OPERATOR_DASHBOARD_PASS / P44_SUPPORT_BUNDLE_PASS / P43_AUTHORITY_PRESERVED / FULL_LIFECYCLE_PASS / EXACT_DOCKER_PASS / EXACT_HEAD_RENDER_DEPLOY_PASS / PRODUCTION_BOUNDARY_PASS`
