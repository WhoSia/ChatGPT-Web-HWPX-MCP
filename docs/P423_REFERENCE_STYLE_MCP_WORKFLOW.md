# P4.23 — Reference-style reuse as a real ChatGPT MCP workflow

## Why this exists

In previous versions, role-aware style extraction (P3.35) produced useful
reports but did not let a ChatGPT user **apply** the resulting appearance.
The P4.23 workflow connects that existing extractor to the ordinary HWPX
composer, without creating another renderer or making the user handle
paragraph-level style IDs.

This is influenced by:

- [kordoc agency packs](https://github.com/chrisryugj/kordoc/blob/main/docs/agency-pack.md):
  learn a bounded candidate style from a user's specimen document, surface
  unsupported details, keep the user's original document private.
- [HwpForge style templates](https://github.com/ai-screams/HwpForge/blob/main/docs/guide/style-templates.md):
  separate document content from style roles and compose inherited overrides.
- [python-hwpx-automation skill-first workflows](https://github.com/airmang/python-hwpx-automation/blob/main/docs/skill-first-workflows.md):
  keep a small high-level workflow over a verified atomic edit engine.

## Step 1 — Ingest/choose a document the user owns

Use the existing `ingest_document` tool, or a previously created owned
`document_id`. Do not upload somebody else's private document.

## Step 2 — Preview candidate typography

`get_p423_reference_style_candidate(document_id, profile_name, expected_revision)`

This **read-only** tool verifies server-side ownership and source revision
and returns:
- `candidate.style_profile`, a supported subset of role-based typography;
- `candidate.warnings`, including unportable native styles;
- `candidate.style_profile_sha256`, a reproducible exact-content digest;
- `approval_required: true`, `stored_preference: false`.

It does not mutate the reference or save a cross-session personal profile.

## Step 3 — User review and approval

The assistant should show the proposed title/body typography and warnings,
and let the user correct the profile or explicitly approve it. Approval
MUST NOT be inferred from the mere fact of document upload.

For a user-corrected custom profile, call the ordinary
`create_document_from_plan` with an explicit `plan.style_profile`.
For an unchanged candidate, the user may use the next tool.

## Step 4 — Compose one approved document

```text
create_p423_document_with_approved_reference_style(
    reference_document_id="...",
    expected_reference_revision=3,
    accepted_profile_sha256="<from the preview>",
    plan={"preset":"school-report","blocks":[...]},
    profile_name="reference-style",
    filename="my-report.hwpx",
    request_id="optional-stable-request-id"
)
```

The server checks the reference owner and revision, re-extracts the style
candidate, compares the approved fingerprint and delegates to the existing
atomic, idempotent `create_document_from_plan`. A mismatch stops before
document creation. It does not silently overwrite a plan's existing
`style_profile` field.

`expected_reference_revision` protects against source edits; this is not
a durable signed approval ledger or persistent user-profile storage.
The caller/host is responsible for obtaining actual user approval.

## Native template preservation

When `template_document_id` is passed to `create_document_from_plan`,
its page geometry now outranks the generic report preset by default:

```json
{"preset":"school-report",
 "preserve_template_setup":true,
 "blocks":[{"id":"p","type":"paragraph","text":"추가 내용"}]}
```

Explicit `style_profile.page` or `plan.setup` changes still apply.
Use `preserve_template_setup:false` to deliberately reapply the generic
preset. This avoids changing school/agency margins just because a generic
report style was chosen for new paragraphs. It does **not** establish
pixel-perfect preservation of paragraph geometry, captions, native layout
or Hancom pagination — those require visual inspection.

## Unfinished release gates

- Verify all tests on the **exact latest commit**; prior PR CI success is
  insufficient if the branch has advanced.
- Render the reference and the personalized output with actual Hancom,
  comparing pages, heading roles, font fallback and inline equation baselines.
- Confirm the connected production MCP has the new tool declarations;
  draft GitHub code is not deployed behavior.
- Persistent private profile storage, user deletion, longitudinal style
  learning and multi-exemplar institutional consensus are **not shipped**.
