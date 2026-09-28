# P3.48 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.48 — Verifiable Public Extension Marketplace Constitution, Federated Namespace Ownership, Transparency-Logged Publication & Revocation, Capability-Aware Discovery, Split-View-Resistant Registry Replication, Adversarial Admission/Delisting & Offline-Verifiable Ecosystem Distribution**

## Explanandum lock

P3.48 does not weaken or replace P3.47 installation authority. It adds a public discovery/distribution constitution in front of P3.47 while preserving the rule that marketplace presence, ranking, publication signatures and registry checkpoints are never sufficient for installation.

## Authority split

- TypeScript: canonical marketplace event algebra, namespace/package state reduction, yank/revoke semantics and capability/effect-aware discovery.
- Python: Ed25519 publisher continuity, registry+witness checkpoint verification, Merkle snapshot binding, federation/split-view adjudication, offline bundle assembly and MCP integration.
- Rust: independent checkpoint quorum, event hash-chain/Merkle-root and offline-bundle guard.
- P3.47 remains the final install-time package recertification, rollout and exact rollback authority.
- P3.46 remains sandbox/effect authority.

## Identity and governance boundary

Initial namespace claim is self-signed and proves cryptographic continuity only. It does not claim legal identity, trademark ownership or real-world organizational verification. Subsequent publish/yank/revoke/key-rotation/ownership-transfer events must be signed by the current namespace key.

Registry checkpoints are signed by the registry and require an independently configured witness quorum. Mirrors distribute portable signed snapshots; they do not acquire install authority.

## Initial closure targets

\`VERIFIABLE_NAMESPACE_CONTINUITY_PASS / TRANSPARENCY_HASH_CHAIN_PASS / MERKLE_CHECKPOINT_PASS / REGISTRY_WITNESS_QUORUM_PASS / FEDERATED_PREFIX_CONSISTENCY_PASS / SPLIT_VIEW_EQUIVOCATION_DETECTION_PASS / CAPABILITY_AWARE_DISCOVERY_PASS / YANK_REVOKE_SEMANTIC_SEPARATION_PASS / REVOKED_PACKAGE_ADMISSION_BLOCK_PASS / REVOKED_PACKAGE_ROLLBACK_OR_RETIRE_PASS / OFFLINE_VERIFIABLE_BUNDLE_PASS / P347_INSTALL_TIME_RECERTIFICATION_PRESERVED / P346_SANDBOX_AUTHORITY_PRESERVED\`.

These remain targets until exact-head dedicated CI, full lifecycle, Docker and production-boundary evidence are observed.


## Dependency-drift adjudication

The first full-lifecycle P3.48 run exposed three legacy failures after PyPI resolution advanced from `python-hwpx 6.5.0` (the exact dependency observed on successful P3.47 lifecycle #1149) to `6.6.0`. The failures were outside the P3.48 surface: P3.18 orientation round-trip, P3.19 numbering-format interpretation, and P3.38 rich-builder orientation. P3.48 therefore freezes `python-hwpx==6.5.0` for the current production lineage rather than silently adapting historical semantics during marketplace work. Upstream 6.6+ migration is a separate explicit compatibility task, not an incidental dependency update.
