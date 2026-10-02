# ChatGPT Web HWPX MCP P4.14 — Distributed Native Capture Agent, Signed Evidence Ingestion, Hancom Build-Matrix Certification, Release-Triggered Visual Drift Adjudication, Automated Rollback Authority & Per-Document Public Trust Receipts

Product: `0.39.0-p4.14`

Immutable parent: P4.13 `0.38.0-p4.13`, exact head `adeb06e6f55fbc0b7116e998ebbfe3ed18811754`, Render deploy `dep-davkg0vavr4c73cd4j30`.

## Frozen invariants

- `P414_CAPTURE_AGENT_NEVER_GLOBAL_KILL`: an agent may close or terminate only Hwp.exe PIDs it created for its own job; it never enumerates-and-kills the machine's Hwp processes.
- `P414_CAPTURE_AGENT_OUTBOUND_ONLY_BY_DEFAULT`: the worker processes only an explicit envelope and has no listener, daemon, directory watcher, or inbound control port.
- `P414_CAPTURE_AGENT_SOURCE_BYTES_IMMUTABLE`: each declared source byte string is hashed before and after capture; output paths cannot overlap the source root.
- `P414_NATIVE_RECEIPT_SIGNATURE_REQUIRED`: only Ed25519-signed canonical payloads from active registered public keys can enter accepted native evidence.
- `P414_RECEIPT_REPLAY_PROTECTED`: one agent/job and agent/nonce can be accepted once; exact retries are idempotent, altered or separately replayed receipts are rejected and audited.
- `P414_EXACT_HEAD_SOURCE_PDF_HANCOM_BUILD_BOUND`: accepted evidence binds product, exact head, source manifest, fixture identity, PDF digest, capture-agent protocol/version, and Hancom build.
- `P414_BUILD_MATRIX_VERSION_INDEXED`: certification is a cell for an exact Hancom build and fixture/family/release tuple; it never transfers to another build.
- `P414_VISUAL_DRIFT_CAN_BLOCK_RELEASE`: PDF byte drift alone is diagnostic; semantic disappearance, vector escape, clipping, overlap, bar/KPI visibility regression, or a novel defect blocks.
- `P414_ROLLBACK_REQUIRES_SIGNED_EVIDENCE_AND_RELEASE_IDENTITY`: CI failure alone cannot authorize rollback. Dry-run and explicitly approved execution are distinct.
- `P414_DOCUMENT_TRUST_RECEIPT_DISTINGUISHES_RELEASE_BASELINE_FROM_PER_DOCUMENT_CAPTURE`: a P4.12/P4.13 baseline does not certify an individual document.
- `P414_NO_NATIVE_PASS_WITHOUT_REAL_HANCOM_EVIDENCE`: synthetic fixtures and unit tests can validate rules, never native rendering.

## Authority and rollout

P4.13 remains immutable history and the parent release identity. P4.12's five-case native baseline remains inherited evidence, not P4.14 agent capture. The new agent protocol itself requires fresh capture before its build cell can be promoted. Machine CI, Docker, OAuth, or deployment readiness cannot turn `NATIVE_VERIFICATION_PENDING` into native PASS. A P4.14 production deployment is gated on exact-head CI/Docker and a nonblocking capture obligation; if the protocol-change obligation remains blocking, retain P4.13 production and stop for the Windows capture handoff.

Only public verification keys may be registered server-side. Private signing keys are created and held on the capture machine, never stored in the repository or server database. Evidence attempts are append-only; receipt identity and canonical digests are deterministic.
