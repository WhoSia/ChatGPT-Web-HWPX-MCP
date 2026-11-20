# ChatGPT Web HWPX MCP P4.28 — Visual Edit Assurance & End-to-End Delivery

Page-Scoped Layout Evidence, Revision-Bound Downloads & Native Hancom Acceptance

## R1 · Bind preview bytes to committed delivery

Base: P4.27 commit `75b7fc6b12cad8f739f6c503337b111d1532184a`.

1. Call `preview_preserved_table_batch` with the current revision and edit operations. For an optional rhwp comparison, request the affected page range.
2. Pass its `plan_sha256` and `candidate_sha256` as `expected_plan_sha256` and `expected_candidate_sha256` when committing. The plan binds the inputs. The candidate hash requires the saved bytes to match the preview before the revision is written.
3. Download the committed revision and compare its SHA-256 with the preview candidate. If link preparation fails after the write, call `deliver_document` with the returned revision to obtain a fresh link.

Existing clients may omit the candidate hash. rhwp provides page-level preview evidence. Windows Hancom reopen, layout checks, and the hosted ChatGPT download round trip require separate acceptance.
