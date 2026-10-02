# ChatGPT Web HWPX MCP P4.15 — Self-Verifying Release Authority, Cross-Layer Evidence Graph, Native/Hosted Conformance Reconciliation, Provenance-Aware Rollback, Continuous Production Attestation & Autonomous Release Admission Control

Product: `0.40.0-p4.15`

Immutable parent release: P4.14 `0.39.0-p4.14`, canonical recovered lineage rooted at exact head `43039e416fcd32baf2f01827b5decc77d0c81439`.

## Purpose

P4.15 turns release authority from a collection of receipts into a machine-verifiable graph. Git ancestry, exact source identity, CI, lifecycle, Docker, release artifacts, Render deployment, public production boundary, native Hancom evidence, and rollback authority are represented as typed evidence with explicit truth layers.

## Frozen invariants

- `P415_RELEASE_AUTHORITY_IS_GRAPH_VERIFIABLE`: every admitted release claim is reducible to typed evidence nodes and explicit relations.
- `P415_OBSERVED_DERIVED_PENDING_SEPARATED`: observed evidence, derived claims, and missing/pending evidence are never collapsed.
- `P415_CANONICAL_PARENT_IMMUTABLE`: P4.14 canonical authority remains historical input and is never rewritten by P4.15.
- `P415_HOSTED_NEVER_IMPLIES_NATIVE`: CI, Docker, Render, PDF transport, or public boundary success cannot create a native Hancom PASS.
- `P415_NATIVE_CLAIM_HARD_GATE`: any release claim that includes native fidelity requires exact-head native evidence.
- `P415_PRODUCT_MACHINERY_MAY_CLOSE_WITH_NATIVE_PENDING`: the release-authority machinery itself may be admitted when all required machine gates pass while native authority remains explicitly pending and unclaimed.
- `P415_ROLLBACK_REQUIRES_CERTIFIED_ANCESTOR`: rollback targets must be certified authorized ancestors with matching artifact identity.
- `P415_PRODUCTION_DRIFT_HOLDS_AUTHORITY`: continuous attestation may place live authority on HOLD when product/head/boundary drift is observed; it never rewrites a sealed release.
- `P415_NO_SILENT_REQUIREMENT_DOWNGRADE`: missing evidence is HOLD, failed or contradictory required evidence is FAIL.
- `P415_READ_ONLY_ADMISSION_SURFACE`: admission and rollback certification tools return authority decisions; they do not mutate Git, deploy, or execute rollback.

## Evidence planes

1. **Source lineage** — canonical exact head and proven ancestry from P4.14.
2. **Build/test** — focused CI, full lifecycle, exact-head Docker.
3. **Artifact** — release artifact identity and digest.
4. **Hosted runtime** — Render deploy identity, public production boundary, continuous re-attestation.
5. **Native runtime** — signed Hancom capture and human visual adjudication inherited from the P4.14 evidence model.
6. **Rollback** — target release certification, ancestry reachability, and artifact identity.

## Admission semantics

The machine release requires:
`GIT_EXACT_HEAD`, `GIT_ANCESTRY`, `CI`, `FULL_LIFECYCLE`, `EXACT_HEAD_DOCKER`, `RELEASE_ARTIFACT`, `RENDER_DEPLOY`, `PRODUCTION_BOUNDARY`, and `PRODUCTION_ATTESTATION`.

If native fidelity is claimed, `NATIVE_HANCOM` becomes an additional hard gate. If native fidelity is not claimed and no exact-head native evidence exists, admission may PASS with `NATIVE_WORLD_CONTACT_PENDING` explicitly attached.

## Negative controls

P4.15 must reject or hold at least:
- forged or stale node digests,
- wrong exact head,
- broken P4.14 ancestry,
- stale release artifact identity,
- deployment head/product drift,
- missing native evidence when native fidelity is claimed,
- uncertified rollback target,
- rollback target that is not a proven ancestor,
- mismatched rollback artifact digest,
- dangling or tampered evidence-graph edges.

## Operational boundary

Render Free resource failures such as status 137 or cold-start timeout remain infrastructure observations. `/health` stays lightweight and no expensive aggregate query is reintroduced.

Repository-level PR-only protection remains `UNVERIFIED` unless GitHub exposes it successfully. Workflow-level repository permissions remain explicit and read-only. P4.15 does not authorize history rewrite or bot-authored release commits.
