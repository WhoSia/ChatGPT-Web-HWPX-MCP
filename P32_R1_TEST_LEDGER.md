# P3.2-R1 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.2-R1 — Render Deployment-Reconciliation Receipt, Public P3.2 Capability Materialization, Native Pin→Compact→Verify World-Contact & Full Closure**

## Verdict

`DEPLOYMENT_RECONCILED / PUBLIC_CAPABILITY_PASS / LOCAL_CONFIRMATORY_PASS / PUBLIC_OAUTH_WORLD_CONTACT_AUTH_HOLD`

## Render reconciliation receipt

- Render service: `chatgpt-web-hwpx-mcp-p0`
- Auto-deploy remained configured as `yes / commit`, but no P3.2 GitHub push created a Render deployment record.
- A one-time reconciliation redeploy was therefore triggered against current `main`.
- Deploy: `dep-damuvgegekts73f367sg`
- Deployed commit: `40400a02bafdfde392a230c763e90988fa3e992a`
- Final status: `live`

## Public materialization receipt

- Public boundary workflow: `35415107452` — SUCCESS.
- It verified the live server exposes `0.4.2-p3.2`, durable OAuth/document-store health, protected-resource metadata, authorization-server metadata, offline-access declaration, and pre-tool unauthenticated rejection.
- Local/confirmatory lifecycle on the same R1 trigger head: `35415107431` — SUCCESS.
- Client discovery expectations now explicitly include:
  - `pin_document_revision`
  - `unpin_document_revision`
  - `compact_document_history`
  - `verify_document_lineage`

## Public OAuth-native world-contact attempt

A dedicated workflow, `.github/workflows/p32-world-contact.yml`, was added to execute the full public OAuth-native lifecycle against:

`https://chatgpt-web-hwpx-mcp-p0.onrender.com/mcp`

The intended world-contact includes:

1. authenticated public MCP discovery,
2. create/edit lifecycle to revision 15,
3. `pin_document_revision(revision=1)`,
4. active-lease compaction rejection,
5. dry-run compaction,
6. actual compaction,
7. `verify_document_lineage`,
8. cleanup.

Run `35415107429` stopped before network mutation because the repository secret `P11_OAUTH_PASSPHRASE` is not configured. The workflow fails closed at a dedicated preflight step; no secret is printed, guessed, copied, or bypassed.

## Authority interpretation

This HOLD is an authentication-authority boundary, not an implementation or deployment failure.

P3.2 code, database migration, tamper persistence, compaction semantics, Render deployment, public version exposure, public OAuth metadata, and unauthenticated rejection are all confirmed.

The only unearned claim is **successful authenticated public native mutation** through the production OAuth approval gate.

## Closure condition

P3.2-R1 may be promoted to `FULL CLOSURE` only after one of these authorized paths succeeds:

- configure the GitHub Actions repository secret named `P11_OAUTH_PASSPHRASE` and retrigger the dedicated world-contact workflow, or
- invoke the already-connected ChatGPT Web HWPX MCP app in a session where its native tool namespace is available and execute the same pin→compact→verify sequence.

The passphrase must never be pasted into repository files, workflow YAML, logs, or chat.
