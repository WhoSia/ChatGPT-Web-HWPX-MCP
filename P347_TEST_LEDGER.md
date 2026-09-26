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


## Trust-root and bearer-certificate adversarial repair

The pre-closure audit found two residual trust failures that source hashing alone could not justify.

1. A caller could change only \`builder.id\` and make two caller-supplied attestations appear to come from independent rebuilders.
2. Differential host observations were syntactically checked and hash-bound, but the caller could manufacture the observation rows.
3. A hash-sealed PASS certificate was an integrity receipt, not an authenticated bearer credential; accepting it directly at install time would let a caller fabricate an internally consistent certificate.

Repair:
- every authoritative build attestation now carries an Ed25519 signature verified against an owner-scoped, preconfigured builder root;
- reproducibility authority requires two distinct trusted builder identities, key IDs and public-key fingerprints;
- every authoritative host observation is Ed25519-signed and bound to a preconfigured \`(host_id, host_contract_sha256, key_id)\` root;
- raw reproducibility and host-conformance comparison APIs remain available only as descriptive diagnostics and do not confer trust authority;
- the document owner configures a trust policy before package admission, and that policy becomes immutable once any package is admitted;
- install no longer accepts a caller-supplied certificate. It reruns package normalization, signed provenance verification, signed host verification, sandbox/determinism negative controls, certificate construction and Rust certificate sealing against the document trust policy;
- a generation CAS is checked both before and after recertification, closing trust-policy/package TOCTOU;
- stored certificates are therefore server-derived rollout receipts, not user-supplied credentials.

This mirrors the verifier-root principle in current SLSA provenance verification without claiming a SLSA build level or Sigstore transparency-log inclusion.

Additional closure authority:
\`OWNER_SCOPED_TRUST_ROOT_POLICY_PASS / SIGNED_BUILD_PROVENANCE_PASS / INDEPENDENT_TRUSTED_REBUILD_PASS / SIGNED_HOST_EVIDENCE_PASS / FORGED_BUILDER_REJECTION_PASS / FORGED_HOST_RECEIPT_REJECTION_PASS / INSTALL_TIME_RECERTIFICATION_PASS / BEARER_CERTIFICATE_FORGERY_PATH_CLOSED / TRUST_POLICY_TOCTOU_GUARD_PASS\`.
