# P4.18-P2 — Release Admission and Handoff

**Status:** PRODUCT CLOSURE HOLD. The durable orchestration primitives are implementation candidates, not publicly activated user-approved mutations.

## Built, testable scope
- Non-executing workflow draft compilation, input binding, preview and correction.
- Server-owned staging revalidates document ownership/revision and persists intent.
- PostgreSQL admission state and user-confirmation verifier interface; only a trusted, independent host can call approve().
- Single CLAIMED transition with row-level locking and fail-closed ambiguous-outcome handling.
- Crash recovery, explicit pre-claim cancellation and independently verified commit reconciliation; never rerun a mutation solely because a process restarted.
- Tests: product kernel, real PostgreSQL service, Docker exact head. Every gate must be GREEN at the **same exact PR head**.

## Do not claim
- A self-hashed draft is **not** server-authenticated approval.
- Approval callback interface does not mean trusted confirmation transport is deployed.
- Durable ledger logic does not mean the execution adapter and document commit receipt have been integrated atomically.
- A COMMITTED ledger row does not override actual immutable document custody and delivery authorization.
- P1 production release authority does not extend automatically to new P2 behavior.
- Never mark phase CLOSED or promote a version while a workflow is queued, cancelled or failing.

## Blocking work for launch
1. Implement authenticated user confirmation channel with one-use host-origin verification, expiry and explicit scoped consent. An MCP client must not be able to fabricate this event.
2. Bind admission to execution: re-check current owner/revision, claim transaction, invoke exactly the authorized effect, verify underlying document revision/sha/receipt, persist resolution. Handle crash after underlying commit.
3. Prove concurrent double-submit, restart and uncertain reconciliation on real PostgreSQL and native HWPX targets; separately test recovery with source and destination documents.
4. Include Windows, complete lifecycle, production-boundary deployment and public user smoke on an exact head.
5. Publish release notes, maintain rollback instructions, observe error and latency regressions; verify default-branch author provenance before release.

## Branch policy
Keep one development PR branch at a time; merge by verified squash into main, preserve WhoSia author identity, then request deleting the merged feature branch. Never rewrite unarchived history. Archive branches with no common ancestor of main need full Git bundle custody and SHA/fixity checks before deletion.
