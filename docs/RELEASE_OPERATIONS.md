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
