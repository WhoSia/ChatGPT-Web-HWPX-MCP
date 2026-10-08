# P4.18-P3 — Trusted Execution Productization Gate

## Scope and exact architecture
P3 adds a host-only consent verifier and single-execution coordinator on top of P2's durable admission ledger. The host must independently authenticate the end user, show the scope of mutation, and sign a short-lived consent envelope using a secret never accessible to MCP clients or language-model prompts.

1. Authenticated owner stages an immutable draft and verified document identity/revision snapshot.
2. The independent host presents exact effects for explicit human confirmation.
3. The host signs a scoped consent assertion. Only the server validates it and CAS-promotes STAGED→APPROVED.
4. The trusted host obtains an opaque approval key; P3 coordinator CAS-claims the exact draft, preview, binding, scope and stable execution id after live ownership/revision revalidation.
5. The *trusted* execution adapter performs exactly the approved mutation and reads an independently verifiable committed document revision, SHA and durable receipt.
6. On success, ledger COMMITTED is durable and further invocations return stored receipt for exact revision delivery only; on ambiguous failure, UNCERTAIN blocks retries until separate forensic verification.

## Current boundary
The host signature verifier, PostgreSQL approval call, execution-coordination function and cross-restart test scaffolding are implemented. However **the real independent user-confirmation host, its secret custody, semantic task-authorization adapter and underlying HWPX commit-receipt verifier are NOT production-wired**. An injected callback alone is not an authorization mechanism. The old P1 mutation tool still has its own legacy execution route.

## Required product release gates
- Fully integrate authentication, human-facing consent capture and server-only one-time approval.
- Persist or independently authenticate the complete normalized task/effect, not just a user-supplied hash. Bind it to the exact executed action.
- Verify actual owner, immutable source revision, output bytes/sha and commit receipt; separately prove CREATE, EDIT_INTENT, TEMPLATE_FILL side effects.
- Test crash after document commit but before ledger commit, double-submit across multiple workers, and stale/denied/revoked consent.
- Pass product-kernel, PostgreSQL, exact-head Docker, Windows, full lifecycle, production boundary, public MCP smoke, latency/error/compatibility SLO and rollback. Each gate must refer to the **same commit**.
- Confirm no github-actions[bot]-authored commits; preserve unrelated archive branches until full Git bundle backup; squash merge only on green.

**Verdict:** P4.18-P3 HOST EXECUTION CANDIDATE; NOT PUBLICLY RELEASED; RELEASE HOLD.
