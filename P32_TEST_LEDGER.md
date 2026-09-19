# P3.2 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.2 — Durable Revision-Lineage Integrity, Retention/Compaction Semantics, Garbage-Collection Safety, Restore-Reachability Preservation & Tamper-Evident Audit Closure**

## Canonical verdict

`IMPLEMENTATION_PASS / CONFIRMATORY_CI_PASS / PUBLIC_RENDER_DEPLOYMENT_PENDING_AT_SEAL`

## Authority contract

- Commit authority and historical byte retention are separate layers.
- `hwpx_document_commits` is the append-only lineage ledger and is never removed by revision compaction.
- Commit rows carry `previous_audit_hash` and `audit_hash`; the SHA-256 chain covers document id, revision, expected revision, document SHA-256, deterministic receipt id, and previous audit hash.
- Pre-P3.2 rows are backfilled only when `audit_hash IS NULL`. Existing non-NULL audit values are never auto-healed, so tampering remains observable after process restart.
- Current revision is always retained.
- Explicit revision pins are DB-level restore anchors protected by a composite foreign key with `ON DELETE RESTRICT`.
- Recent K revisions are protected by compaction policy; older unpinned snapshots may be pruned.
- An active unexpired durable lease blocks compaction.
- Restore never rewinds the current pointer; retained historical bytes are promoted as a new monotonic revision.
- Whole-document expiry cleanup does not delete a document while an active lease exists.

## MCP surface added

- `pin_document_revision`
- `unpin_document_revision`
- `compact_document_history`
- `verify_document_lineage`

## Confirmatory attacks

- Five-revision history with revision 2 pinned; `keep_last=2` dry-run identifies revisions 1 and 3 only as prunable.
- Active lease blocks compaction.
- Actual compaction deletes only revisions 1 and 3 while retaining 2, 4, and 5.
- Commit ledger remains five rows after snapshot compaction.
- Pinned revision remains loadable and can be promoted as revision 6.
- Manual commit-row SHA tampering is detected by the audit chain.
- Fresh `DurableDocumentStore` construction after tampering does not heal the corrupted non-NULL audit state.
- OAuth-native lifecycle exercises pin → lease-blocked compaction → dry-run → commit compaction → lineage verification.

## Confirmatory receipt

- GitHub Actions final-head lifecycle run: `35414739938` — SUCCESS.
- Final documented head at initial seal: `4b7e5b181e6503c954cfba64f880caf7be50938b`.
- Earlier confirmatory heads `24ab8ee…`, `6bace21…`, `bcd34af…`, and `bbf7c71…` also passed lifecycle CI.

## Remaining boundary at this seal

- Render auto-deploy was still serving the P3.1 image during the initial P3.2 seal; the public workflow was waiting for `0.4.2-p3.2`.
- Native ChatGPT custom-app schema refresh/world-contact for the four new P3.2 tools is therefore not claimed by this ledger yet.
