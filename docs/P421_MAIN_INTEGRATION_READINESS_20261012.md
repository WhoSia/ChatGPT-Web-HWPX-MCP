# P4.20 / P4.21 Main Integration Readiness — 2026-10-12

## Verified GitHub facts
- PR #15 P4.20: Draft, mergeable=true, head `950bff8d3ed16f1d6eda20e190b2b32cd8280733`, 392 changed files, 67 commits ahead of main, 0 behind. Exact-head GitHub Actions: 21 completed SUCCESS. No submitted reviews or unresolved review threads in read API.
- PR #16 P4.21: Draft stacked on P4.20 branch, CURRENT observed head `c6c9b00f64d89b816cd053cff637c2b8af6add84` (this readiness document's prior commit), 21 files changed, 32 ahead of P4.20, 0 behind. Its 2 exact-head PR workflows completed SUCCESS before this audit-document update. Its old head `64fba26f...` and 20/31 numbers were the immediately preceding snapshot, NOT current. CI must be re-observed on any subsequently changed head.
- Main base SHA observed from PR #15: `1b28199b21b72a392e791863b82cab850e750f69`. Neither branch is behind main in Git compare at audit time.
- PR #15 includes server entrypoints, Dockerfile, a package migration map, CI workflows, and native document code; this is a substantial operational refactor.
- These are CI/mergeability observations, NOT a release approval. Production database backup/PITR and Render preview verification were not revalidated in this audit.

## Ordered promotion gates
1. **P4.20 human technical review** of 392-file migration, imports/entrypoints, production Docker image and storage schema compatibility; preserve old main commit and artifacts as rollback targets.
2. **Production protection gate:** establish and independently confirm tested database recovery (snapshot / restore drill / applicable PITR), baseline service health, configuration invariants and reversible Render rollout. Do not regard past reports of backup status as current proof.
3. **P4.20 integration:** after explicit operator approval, merge PR #15 to main under verified checks and deployment controls. Record exact main SHA and deployment health/rollback success criteria.
4. **P4.21 rebase/retarget:** rebase or retarget stacked PR #16 onto the new main, confirm intended P4.21-only diff, then run whole-suite, native package, live endpoint contract, release image and deployment smoke in the new base context.
5. **P4.21 integration:** seek explicit operator approval, merge only after all gates and rollout/rollback plan. Capture new main SHA and deploy readback.
6. **Branch cleanup:** delete the obsolete P4.20 and P4.21 development branches only after merged commits are reachable from main, deployed version is healthy and rollback references are secured.

## Release BLOCKERS (not inferred as failures)
- No approvals submitted on PR #15.
- Preview/prod-like Render smoke and DB recovery verification unavailable in this audit.
- P4.21 existing remote live MCP is on a separate deployed release: GitHub PR CI PASS does not imply deployed API has the P4.21 quality additions.
- Manually-rendered single-paragraph HWPX success does not certify professional composite-document fidelity.

## Current decision
`PRE_MERGE_AUDIT_COMPLETE`; `MAIN_MERGE=HOLD_APPROVAL_AND_OPERATIONAL_GATES`; `BRANCH_DELETION=HOLD`.

No automatic promotion, merge, deployment, database mutation or deletion is authorized by this document.


## P4.20 actual Render–Neon release-admission readback — 2026-10-12

This is an **independent read-only connector inspection of connected Render and Neon state**, not an inferred GitHub YAML configuration. No secrets or private document records are copied into this report; no service or DB was modified. The previous `PRE_MERGE_AUDIT_COMPLETE` meant only a GitHub review of the PRs; this deeper infrastructure gate overrides any interpretation that release is ready.

### Verified actual deployed service and automatic deployment trap

- Render workspace service `chatgpt-web-hwpx-mcp-p0`, ID `srv-daiimp8ae00c73em8tjg`, linked GitHub `WhoSia/ChatGPT-Web-HWPX-MCP`, deployed branch **`main`**, **actual service `autoDeploy=yes`, `autoDeployTrigger=commit`**. This is verified through the Render service API, not merely `render.yaml` (which independently says `branch: main` / `autoDeployTrigger: commit`). PR #15 merge into main may automatically trigger a production build and deployment **before a separate P4.20 operator deploy approval**. Treat this as **RELEASE BLOCKER / sequencing error** until actual Render automatic deployment is controllably suspended or an equivalently approved safe release window is actively in effect, AND the readback confirms the intended policy.
- Latest inspected Render live deployment: `dep-db4fkprncjis73crdqjg`, GitHub source commit **`1b28199b21b72a392e791863b82cab850e750f69`** (the present main base, not P4.20 PR #15 head `950bff8d...`), deploy marked live, successful 2026-10-09 14:33 UTC. A live deployment recorded as successful DOES NOT prove native Hancom/P4.21 quality acceptance.
- Recent real service events: 2026-10-12 **04:56:30 UTC** `server_failed` with **HTTP health check 5-second timeout**, and **04:57:32 UTC** `server_available` recovery. Also earlier 2026-10-09 failures/recoveries. Treat as a concrete baseline transient health/restart symptom; do not attribute it to P4.20 not yet deployed or assert permanent outage.
- Current service uses Render **free** instance, one instance, `/health` check, PR previews explicitly **off**. A green GitHub Docker image check is not production-like canary evidence. No preview or blue-green capability should be assumed without separately provisioning/approving it.

### Verified Neon recovery status; independent backup proof missing

- Connected Neon project `chatgpt-web-hwpx-mcp-auth`, project `patient-sea-81190049`, one observed branch `main` (ID `br-mute-hat-aybbvrgi`, primary, **not protected**). This connection has independent production relevance through `P12_AUTH_DATABASE_URL` and durable document store fallback, but **the environment-secret values were NOT read or compared**; do NOT assume exact configured URL equality without controlled operator verification.
- Neon list_snapshots returned **0 snapshots**, and get_snapshot_schedule(`main`) returned **[]** (no configured automatic snapshot schedule). The project metadata advertises **`history_retention_seconds=21600` (6 hours)**. These facts DO NOT prove that no off-platform backups or other recovery facilities exist; they DO prove this read-only inspection cannot attest to durable recoverability beyond the stated project history window.
- No branch restoration, PITR restore drill, snapshot creation or DB mutation was attempted. **Release requires an authorized, independently replayed recovery drill on a safe separate branch** with checksum/row-count/critical-table-equivalence and an exact restoration-point record. Keep auth leases, encrypted document revisions, audit chains and persisted P4.14 evidence in the acceptance criteria. Never publish access tokens, database URLs or patient/user records in PR comments.
- The package candidate `server.py` instantiates `DurableOAuthStore`, `DurableDocumentStore` and P4.14 evidence store at **module import**. `hwpx_mcp/storage/document_store.py` initialization includes `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and a migration-only `_backfill_audit_hashes()` that can UPDATE legacy rows. Not all statements are inherently unsafe, but **source rollback does not automatically revert any persisted schema/data changes**. Release requires a before/after schema and forward/backward compatibility matrix for the exact old/new container and same DB records.

### Health-check engineering review (hypothesis, not an established root cause)

- `hwpx_mcp/operations/durable_health.py` invokes one `SELECT 1` per distinct configured database URL with default `connect_timeout=3`, iterating serially across OAuth, document and evidence stores; `server.py` registers that probe on `/health`. Render's reported unsuccessful 5-second health check can be exceeded if **two independent DB endpoints both consume close to the 3-second timeout**. This is a bounded-code timing concern; actual current URL count, per-DB latency and causal role in the 2026-10-12 failure were not measured. Verify whether URLs deduplicate and perform controlled latency/failure injection under a 5-second external deadline. Green individual DB tests do NOT settle aggregate health timing.

### Corrected pre-merge operational decision order (no action yet authorized)

1. Freeze exact PR #15 HEAD and current Render deployed SHA and baseline service health metrics. Human reviewer signs off on the 392-file migration and package-root launcher/tool compatibility; AI-authored audit text must not impersonate independent human approval.
2. **BEFORE touching main**, operator explicitly controls actual Render `autoDeploy` policy or approves a staffed monitored release with deploy/rollback gates, then re-reads the real service settings; do not assume changing only `render.yaml` disables the already-running service policy.
3. Independently verify **real Neon backup/snapshot/PITR capability and a restore-to-isolated-branch drill**, exact timestamp, schema and encrypted-state invariants, and the availability of old image rollback. An old Git commit alone is not a complete data recovery procedure.
4. Test the actual PR #15 exact image and target environment in a **non-production, isolated, operator-approved** preview using non-production data or a properly sanitized backup. Demonstrate startup schema changes, health under cold DB and 5-second probe limit, OAuth/doc create/read/revision-edit/version/publish, full restart/recovery and old-image backward compatibility. No real user documents in an unauthorized preview.
5. Only after a **new explicit operator approval for the merge and deployment window**, reconcile PR #15 latest exact-head CI, review decision and non-production evidence. Because current `autoDeploy=yes`, merging cannot be treated as an inert administrative step unless that is changed and verified beforehand.
6. Observe the exact P4.20 new main SHA and Render deploy ID/live SHA as **two independent facts**. If rollback is needed, restore the verified old image and verify DB data invariants; do not assume revert preserves state without tests. Wait for stable health and real MCP contract checks before retargeting PR #16 to the new main.
7. Only afterward retarget PR #16; verify P4.21-only diff, rerun full target-base checks, obtain native Hancom/human evidence independently and seek separate merge/deploy approvals. Neither Draft PR may be auto-merged or cleaned up under present HOLD.

### Admission decision superseding the earlier summary

`P4.20 MAIN MERGE=HOLD` — **ACTUAL AUTO-DEPLOY ON MAIN** + **NO NEON SNAPSHOT/RESTORE DRILL EVIDENCE** + independent human review absent + no production-like canary. `P4.21 MAIN MERGE=HOLD`; `PRODUCTION ROLLOUT=HOLD`; `DELETE BRANCHES=HOLD`. No Render, Neon, main ref, or branch deletion mutations performed.
