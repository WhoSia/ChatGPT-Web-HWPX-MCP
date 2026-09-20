# P3.12 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.12 — Hancom-Native Render Harness Intake, Font-Environment Sealing, Pagination/Line-Box Capture, Fixture-Level Raster World Contact & Exact-vs-Calibrated Fidelity Adjudication**

## Current verdict

`IMPLEMENTATION_PASS / RENDER_RECEIPT_SCHEMA_PASS / FONT_ENVIRONMENT_SEAL_PASS / PAGINATION_LINE_BOX_CAPTURE_PASS / FIXTURE_LEVEL_ADJUDICATION_PASS / EXACT_PIXEL_CLAIM_CROSSCHECK_PASS / SERVER_SURFACE_BOUND / CI_CONFIRMATION_PENDING / REAL_HANCOM_FIXTURE_WORLD_CONTACT_HOLD / PIXEL_RENDER_FIDELITY_HOLD`

## What P3.12 adds

P3.12 promotes P3.11 from a generic render adjudicator to a sealed fixture-level world-contact intake.

Canonical module: `p312_render_harness.py`.

The receipt schema is:

`chatgpt-web-hwpx-mcp/render-receipt/p3.12/v1`

Each fixture receipt binds:

- fixture id
- source and target document SHA-256
- renderer name/version
- explicit Hancom-native declaration
- renderer executable SHA-256
- OS and DPI
- PDF backend
- rasterizer and rasterizer version
- source and target font inventories
- source and target page captures
- per-page raster SHA-256
- per-line geometry boxes and baselines
- calibrated raster/layout metrics

## Font environment sealing

Font inventories are canonicalized and sorted before hashing.

Each font may carry:

- family
- style
- PostScript name
- version
- font-file SHA-256

The source and target inventories receive independent deterministic hashes.
A pixel-fidelity promotion remains blocked when the hashes differ.

## Pagination and line-box capture

Each capture must contain a non-empty contiguous page sequence starting at page zero.

Per page:

- width / height in pixels
- raster SHA-256
- ordered line boxes
- line x/y/width/height
- baseline
- optional text SHA-256
- optional paragraph locator

Line boxes must fit inside page bounds and remain vertically ordered.

P3.12 derives pagination equality and line-box topology equality from the captures.
A caller-supplied `pagination_equal` or `line_break_equal` value that contradicts the captured evidence is rejected.

## Exact-pixel claim crosscheck

`exact_pixel_match=true` is not trusted by itself.

Exact pixel promotion additionally requires source and target page raster-hash lists to be present and identical.
A contradictory exact-pixel claim is rejected before authority is issued.

## World-contact seal

A fixture is considered sealed world contact only when:

- renderer is marked Hancom-native,
- P3.11 name-consistency check recognizes the renderer as Hancom/Hangul,
- renderer executable SHA-256 is present,
- DPI is positive,
- every source and target page has a raster hash,
- font-environment receipts are available.

This is evidence-integrity sealing, not remote attestation of the executable identity.
P3.12 therefore does not claim that an arbitrary caller-provided packet proves genuine Hancom execution without custody of the capture environment.

## Fixture-set authority

Multiple fixture receipts can be adjudicated as one set.

Set-level exact-pixel authority is issued only when every fixture independently earns `PIXEL_RENDER_FIDELITY_PASS`.

One failing or incomplete fixture leaves the set at calibrated/HOLD authority.

## Server tools

P3.12 exposes:

- `get_layout_fidelity_receipt(document_id)`
- `adjudicate_render_world_contact(document_id, render_receipt)`

The first returns renderer-independent HWPX evidence.
The second validates one external render packet against the owned HWPX document and applies the P3.11 promotion gate.

Server version is advanced to:

`0.9.0-p3.12`

## Regression tests

`test_p312_render_harness.py` covers:

1. deterministic font sealing,
2. exact sealed fixture promotion,
3. missing executable-seal downgrade,
4. source/target font mismatch HOLD,
5. captured-pagination contradiction rejection,
6. false exact-pixel claim rejection,
7. fixture-set exact authority,
8. deterministic receipt hashing.

P3.12 CI also repairs the prior P3.11 workflow gap where `test_p311_layout_fidelity.py` was compiled but omitted from the actual unittest command.

## Repository receipts

- render harness implementation: `96c2586002fbe94788fc0a37623d0e6b65f5a893`
- P3.12 unit tests: `57a392ccff755fb109e72d0cf2d09ac214f6531d`
- MCP surface + server version: `d44ea6e1750eb0cdb47f09d87d5fb69cd0d55bf5`
- production image packaging: `0d1503c5fe0673ac3d4ac7d16ee43778225c91e5`
- lifecycle CI binding: `28d7db2589291cd0a5fb1fd491d497ab6755c18f`
- public-boundary version binding: `87bf303966aac99b39968b02e68937b230e8033f`

At ledger creation time GitHub combined status for the current head had not yet published check results.

Render production was still on the sealed P3.9 deployment `dep-dancnnbbc2fs73dvebi0`; no P3.12 production authority is claimed by this ledger.

## Authority boundary

P3.12 establishes the intake and adjudication machinery.

It does **not** itself supply genuine Hancom-native fixture captures.

Canonical remaining holds:

`REAL_HANCOM_FIXTURE_WORLD_CONTACT_HOLD / PIXEL_RENDER_FIDELITY_HOLD`

## Successor

**ChatGPT Web HWPX MCP P3.13 — Trusted Windows/Hancom Capture Runner, Artifact-Custody Chain, Near-Wrap Positive-Sensitivity Corpus, Cross-Version Hancom Replay & Pixel-Fidelity Promotion Trial**
