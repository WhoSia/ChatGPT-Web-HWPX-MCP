# ChatGPT Web HWPX MCP P4.28 — Visual Edit Assurance & End-to-End Delivery

Page-Scoped Layout Evidence, Revision-Bound Downloads & Native Hancom Acceptance

## R1 · Bind preview bytes to committed delivery

Base: P4.27 commit `75b7fc6b12cad8f739f6c503337b111d1532184a`.

1. Call `preview_preserved_table_batch` with the current revision and edit operations. For an optional rhwp comparison, request the affected page range.
2. Pass its `plan_sha256` and `candidate_sha256` as `expected_plan_sha256` and `expected_candidate_sha256` when committing. The plan binds the inputs. The candidate hash requires the saved bytes to match the preview before the revision is written.
3. Download the committed revision and compare its SHA-256 with the preview candidate. If link preparation fails after the write, call `deliver_document` with the returned revision to obtain a fresh link.

Existing clients may omit the candidate hash. rhwp provides page-level preview evidence. Windows Hancom reopen, layout checks, and the hosted ChatGPT download round trip require separate acceptance.

## R2 · Acceptance on the downloaded file

On WSL with Windows Hancom installed, use the existing native PDF acceptance command with the SHA-256 returned by the download receipt.

```sh
python scripts/p424_local_hancom_acceptance.py edited.hwpx \
  --output-dir /mnt/c/acceptance \
  --expected-source-sha256 "$download_sha256"
```

The command rejects a different file before invoking Hancom. Review the native PDF and check for a recovery prompt when opening the HWPX in Windows Hancom. Record the equation, merged cell, and adjacent table layout observations for the school-template case.

The production P4.18 connection was exercised separately with a synthetic HWPX. Authenticated creation and signed export returned revision 1, and the HTTPS download returned 7,625 bytes with the same SHA-256 as creation and export. This verifies the published download route for the deployed release. P4.28 requires its own deployment and ChatGPT attachment interaction before hosted acceptance.

## R3 · Review the school-template Hancom PDF

The supplied four-page A4 PDF identifies Hwp 2024 13.0.0.3622 and Hancom PDF 1.3.0.550 in its metadata. Its SHA-256 is `b148fcdf9367cf917f78a9ea4ee8ef56262fc19bbc0c5f5f45641cb55922ec4d`.

On the rendered first page, the equation `a+b` is visible beside the selection rationale, the merged-cell label `< 요건 >` fits on one line, and the next table remains on page 1 with its borders visible and no overlap with the preceding box. This is visual acceptance for the supplied post-edit PDF. The Windows reviewer also confirmed that reopening showed no recovery prompt. No pre-edit Hancom PDF was supplied for a same-renderer position comparison. Hosted P4.28 delivery remains a separate acceptance item.

## R4 · Check the download receipt against the commit

The delivery response verifies the document ID, revision and committed digest before returning the link. A mismatch keeps the edit committed and returns the existing delivery-only recovery response.

## R6 · Renew an expired link for the same bytes

Pass `revision` and `expected_sha256` from the committed delivery receipt to
`deliver_document`. The retained revision must match the requested revision
and digest before the service issues a new link. Recovery does not require a
new edit. The download exposes the revision in `X-HWPX-Revision` and the digest
in `ETag`.

The regression check expires an old link, advances the current revision,
then verifies that the reissued link still returns the pinned revision bytes.
The edit acceptance workflow follows `main` after branch consolidation.
