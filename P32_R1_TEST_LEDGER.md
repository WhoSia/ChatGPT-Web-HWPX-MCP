# P3.2-R1 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.2-R1 — Render Deployment-Reconciliation Receipt, Public P3.2 Capability Materialization, Native Pin→Compact→Verify World-Contact & Full Closure**

## Verdict

`DEPLOYMENT_RECONCILED / PUBLIC_CAPABILITY_PASS / LOCAL_CONFIRMATORY_PASS / PRODUCTION_OAUTH_PASS / NATIVE_MCP_EDGE_TRANSPORT_HOLD`

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

Run `35415107429` originally stopped at the OAuth-secret preflight. The secret is now configured, and later authorized replays progressed through DCR 201 → authorize 302 → approval 303 → token 200 without exposing the secret value.

## Authority interpretation

Authentication authority is now confirmed. The surviving HOLD is the public Render edge → authenticated MCP upstream transport boundary, not P3.2 tool semantics or OAuth issuance.

P3.2 code, database migration, tamper persistence, compaction semantics, Render deployment, public version exposure, public OAuth metadata, and unauthenticated rejection are all confirmed.

The only unearned claim is **successful authenticated production MCP tool transport** after token issuance.

## Closure condition

P3.2-R1 may be promoted to `FULL CLOSURE` only after the production endpoint admits an authenticated MCP request and completes `tools/list → create/edit → pin → lease-block → compact → verify → cleanup`. OAuth, resource validation, and authorization must remain intact.


## Authorized replay update

- Repository secret `P11_OAUTH_PASSPHRASE`: configured; value never read or logged.
- SDK auto replay `35415391970`: OAuth entered, `server/discover` timed out.
- SDK modern-pinned replay `35415546295`: protocol `2026-07-28` established, first `tools/list` failed with server error response.
- SDK legacy replay `35415584381`: OAuth/token completed, `initialize` failed with server error response; rerun without a new push reproduced the failure.
- Raw-wire replay `35415773654` attempt 2: `oauth: DCR+PKCE+token PASS`, then authenticated `tools/list` returned a Render-branded HTML HTTP 502.
- The matching Render app logs contain no authenticated `/mcp` access entry, no app-level 502, and no error/warning event for that interval; `/health` remained 200 before and after.
- Therefore the surviving failure localizes to the production edge/upstream transport path before the MCP application receives the bearer request.

## Next boundary

**ChatGPT Web HWPX MCP P3.2-R2 — Production Authenticated-MCP Edge Transport Isolation, Bearer `/mcp` Reachability, Proxy/Protocol Compatibility Repair & Native Pin→Compact→Verify Final Closure**
