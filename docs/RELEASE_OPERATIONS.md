# Production release operations

This is an **operator runbook**, not evidence that a new release has been deployed.

## Exact source and production identity

1. Record the full GitHub `main` SHA, exact-head CI results, all required failures/waivers, `WhoSia` commit author and committer identity, and source tree.
2. Confirm Render workspace/service, linked repository, branch `main`, Dockerfile, health-check route, current LIVE deployment and the prior known-good deployment.
3. Render may have `autoDeploy=yes` but actual GitHub-to-Render triggers can fail silently. **Do not infer a release from git push.** Read the Render deployment ID and commit SHA independently. If no new deploy appears, the service owner can select **Deploy → Deploy latest commit** in the Render dashboard. Avoid concurrent or duplicated deploys.
4. Wait for build completion, deploy LIVE state, repeated HTTP 200 responses from `/health`, and authenticated MCP metadata readback. Require the deployed SHA to equal the intended source SHA; package version strings alone are insufficient.
5. On a dedicated short-lived test document, test create, validation, inspection, CAS/revision-safe edit, reread, export/handoff and independent file acquisition/openability if available. Verify quality metadata separately from true Windows/Hancom native visual rendering. Clean up only the test document and verify its deletion.
6. Check recent Render logs for startup errors, auth/DB timeouts, five-second health-check failures, throttling and 5xxs. If production behavior regresses, stop promotion and use the Render dashboard's rollback facility to restore a known-good deploy while verifying database compatibility.
7. Preserve the prior main Git ref and recoverable Neon data state **before** rollout. Neon copy-on-write branches are not equivalent to a tested point-in-time snapshot restoration, and restoring a DB branch can change OAuth state. Validate current backups, LSN and schema/readback; do not publish connection strings.
8. Publish a GitHub Release only after all required release checks and required native/Hancom/consumer claims are actually supported. Attach an exact source SHA and provenance-checked artifacts, plus a dependency/SBOM and third-party notices.

## CI and evidence classification

- **SOURCE_CI_PASS**: exact source runs completed successfully.
- **DEPLOYED_SHA_PASS**: Render deploy LIVE and SHA equal expected SHA.
- **API_SMOKE_PASS**: authenticated real-service create/edit/delivery transactions verified.
- **CONSUMER_OPEN_PASS**: independently acquired final bytes open correctly in a consumer.
- **NATIVE_VISUAL_PASS**: independent Hancom renderer evidence and human/qualified assessment available.

A pass in one lane cannot silently certify another. P4.21 preregistered native-render cases are not evidence of completed captures or human reviews.

## Release blockers and safety

- Docker registry `HTTP 429` is an infrastructure/materialization failure, not an application-code PASS. Retry within bounded limits or change documented image-mirror strategy after verifying provenance; never suppress failed gates.
- A stale Render SHA fails production release admission even when the endpoint returns HTTP 200.
- Never include OAuth tokens, DB URLs, private documents, fixtures without redistribution rights or secrets in logs, commits, artifacts, containers or public releases.
- On any stop condition: preserve source refs, preserve the old LIVE deployment, record failure and do not delete recovery/development branches automatically.

## Sole-maintainer attribution and branch retirement

Commit authorship and committer identity must both be `WhoSia`; Actions may test and build but never author commits. Prefer compare-and-swap fast-forward main updates over merge commits with `web-flow`/bot committer identity. Archive release results in PR discussion and canonical product authority. **Development and safety branches are removed only by the repository owner, manually, after successful production verification.**

## P4.29 · Production Release Assurance & Consumer Acceptance

Exact-Build Deployment, ChatGPT Attachment Verification & Rollback Readiness

Run `python scripts/p429_check_live_build.py <health-url> <full-commit-sha>`
to compare the healthy runtime with the intended source. A match establishes
runtime identity only. Cross-check Render's LIVE deployment ID and commit
before recording deployment evidence. For the ChatGPT acceptance run, retain
the committed revision number and SHA-256, acquire the attachment through the
ChatGPT interface, and hash the downloaded bytes. Use the previous LIVE
deployment ID as the rollback reference and verify database compatibility
before treating it as recoverable.

After saving the attachment, use
`python scripts/p429_check_attachment.py downloaded.hwpx receipt.json`.
The receipt can contain just the committed `revision` and `sha256`. Keep
the browser acquisition observation with the result. The command verifies
bytes against the receipt and does not establish where the file was obtained.

For deployment or rollback readback, pass `--render-deployment record.json`
with the Render deployment record. The combined check requires the Render
deployment to be LIVE and both commit SHAs to match the expected commit.
A rollback readback uses the commit reserved before rollout. This verifies
identity and health. Database compatibility and the rollback operation
require their own evidence.

The source comparison of deployed `f7517b33` and candidate `2a1eb31`
found no changes in the existing document-store or OAuth-store files,
Dockerfile, or Render manifest. The added native-PDF store is initialized
on first use when PDF delivery is enabled. Its table and index are additive,
and the foreign key cascades from document revisions. A staging rollback
check should exercise attachment retrieval and revision deletion on an
isolated database under both builds. Until that exercise is recorded, this
source review does not certify database rollback.
