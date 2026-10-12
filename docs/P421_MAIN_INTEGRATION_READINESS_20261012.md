# P4.20 / P4.21 Main Integration Readiness — 2026-10-12

## Verified GitHub facts
- PR #15 P4.20: Draft, mergeable=true, head `950bff8d3ed16f1d6eda20e190b2b32cd8280733`, 392 changed files, 67 commits ahead of main, 0 behind. Exact-head GitHub Actions: 21 completed SUCCESS. No submitted reviews or unresolved review threads in read API.
- PR #16 P4.21: Draft stacked on P4.20 branch, head `64fba26f897a058e30a433bb064f1611e5eec814`, 20 files changed against PR #15, 31 commits ahead of P4.20. Exact-head P4.21 and P4.18–P4.19 CI: 2 completed SUCCESS.
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
