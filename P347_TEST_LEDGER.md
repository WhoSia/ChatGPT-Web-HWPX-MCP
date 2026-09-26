# P3.47 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.47 — Capability-Certified Extension Packages, Reproducible Build Attestation, Semantic Compatibility Solver, Differential Host Conformance, Migration/Rollback Governance, Supply-Chain Provenance & Self-Verifying Plugin Ecosystem**

## Explanandum lock

P3.47 does not create a public marketplace. It makes an extension package independently identifiable, attestable, certifiable, compatibility-classifiable, owner-scoped for rollout, and exactly rollbackable before any marketplace authority is considered.

## Authority split

- TypeScript: canonical package identity, provenance binding, dependency closure, reproducibility comparison, semantic compatibility classification, host-conformance comparison, certificate construction and rollout policy.
- Rust: independent certificate-seal, compatibility-class and rollout-transition guard.
- Python: cross-runtime bridge, immutable admitted-package catalog and owner-scoped rollout/rollback registry.
- P3.46 WASM sandbox/effect authority remains intact.
- P3.45 replay authority remains intact.

## Supply-chain model

The implementation borrows narrow structural ideas from OCI content-addressed identities, in-toto attestations, SLSA provenance and Sigstore-style self-contained verification material. It does **not** claim external SLSA level certification or Sigstore transparency-log inclusion.

Package identity binds:
- P3.46 validated extension manifest;
- exact WASM module digest;
- exact dependency package IDs;
- deterministic build-attestation digest.

Certification additionally binds:
- dependency-closure receipt;
- build-attestation receipt;
- differential host-conformance receipt;
- mandatory positive/negative test gates;
- canonical certificate SHA-256 independently rechecked by Rust.

## Rollout constitution

INSTALLED → CANDIDATE → SHADOW → CANARY → PROMOTED → RETIRED

Retirement is also permitted from pre-promotion states. Promotion atomically retires a previously promoted package for the same extension. Rollback is owner-scoped, generation-CAS guarded, certificate-reverified and restores only a package previously displaced by promotion.

## Initial closure targets

CONTENT_ADDRESSED_EXTENSION_PACKAGE_PASS / PROVENANCE_SUBJECT_BINDING_PASS / EXACT_DEPENDENCY_CLOSURE_PASS / REPRODUCIBLE_BUILD_ATTESTATION_PASS / SEMANTIC_COMPATIBILITY_SOLVER_PASS / EFFECT_ESCALATION_REJECTION_PASS / DIFFERENTIAL_HOST_CONFORMANCE_PASS / SELF_VERIFYING_CERTIFICATE_PASS / RUST_CERTIFICATE_SEAL_PASS / OWNER_SCOPED_ROLLOUT_PASS / SHADOW_CANARY_PROMOTION_PASS / ATOMIC_CERTIFIED_ROLLBACK_PASS / P346_SANDBOX_AUTHORITY_PRESERVED / P345_REPLAY_AUTHORITY_PRESERVED.

These remain targets until exact-head CI, lifecycle, Docker and production-boundary execution evidence is observed.
