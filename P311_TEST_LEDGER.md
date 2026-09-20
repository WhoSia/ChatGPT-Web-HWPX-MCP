# P3.11 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.11 — Font-Metric & Glyph-Advance Attribution, Inline-Object Baseline Geometry, Border/Paint Raster Semantics, Cross-Renderer Residual Decomposition & Pixel-Fidelity Promotion Gate**

## Current verdict

`IMPLEMENTATION_PASS / PAGE_SECTION_RECEIPT_PASS / EXPLICIT_BREAK_RECEIPT_PASS / FONT_INVENTORY_RECEIPT_PASS / FAIL_CLOSED_RENDER_ADJUDICATOR_PASS / PRODUCTION_PACKAGING_BOUND_PASS / CI_CONFIRMATION_PENDING / HANCOM_NATIVE_RENDER_WORLD_CONTACT_HOLD / PIXEL_RENDER_FIDELITY_HOLD`

## Implementation

P3.11 adds `p311_layout_fidelity.py`.

The module separates renderer-independent document evidence from renderer-dependent evidence.

Renderer-independent receipt:
- page width / height
- page margins
- header / footer / gutter
- text-frame width / height
- section count
- explicit page / column breaks
- hard line breaks
- HWPX font inventory hash

Renderer-dependent evidence is never inferred from document XML. It must be supplied by an external render receipt.

## External render receipt

The adjudicator expects:
- renderer name/version and explicit Hancom-native declaration
- source/target font inventory hashes
- font-environment control receipt
- pagination equality
- line-break equality
- exact-pixel equality
- pixel diff ratio
- MAE
- edge disagreement
- rendered bounding-box displacement
- glyph-advance delta
- inline-object baseline delta
- border/paint raster difference

Missing measurements remain HOLD rather than being imputed.

## Promotion rule

`PIXEL_RENDER_FIDELITY_PASS` requires all of:
- structural page/section receipt exists
- renderer is explicitly Hancom-native and name-consistent
- font environment is controlled
- source/target font inventories match
- pagination exact
- line-break exact
- glyph advance within calibration
- inline baseline within calibration
- border/paint residual within calibration
- calibrated raster metrics pass
- exact_pixel_match == true

A calibrated nonzero raster residual may earn:

`RENDERER_NORMALIZED_FIDELITY_PASS / PIXEL_RENDER_FIDELITY_HOLD`

but never exact-pixel authority.

## Residual attribution

The adjudicator distinguishes:
- `HANCOM_NATIVE_RENDER_WORLD_CONTACT_HOLD`
- `FONT_ENVIRONMENT_UNCONTROLLED`
- `RENDER_METRICS_INCOMPLETE`
- `PAGINATION_LAYOUT_DIVERGENCE`
- `LINE_BREAK_DIVERGENCE`
- `FONT_METRIC_GLYPH_ADVANCE_DIVERGENCE`
- `INLINE_OBJECT_BASELINE_DIVERGENCE`
- `RENDERED_GEOMETRY_DISPLACEMENT`
- `BORDER_PAINT_RASTER_RESIDUE`
- `RASTERIZER_ONLY_RESIDUE_CANDIDATE`

## Tests

`test_p311_layout_fidelity.py` covers:
1. page/section geometry and hard-break extraction,
2. prohibition on non-Hancom pixel promotion,
3. exact Hancom evidence promotion,
4. attribution of glyph-advance and border/paint residuals without overpromotion.

## Repository receipts

- implementation module: `6690d285f3732f903e36b904074cc4dc1104a032`
- unit tests: `73ddba37fbfeae206ef14f242dcaff119c561d07`
- Docker packaging: `988b44e5fccd6ef9aa082465b2b3bda5a727d0f9`
- CI binding: `0c126052c0a24551d91fb55781b28e89169b3d23`

At ledger creation time GitHub combined-status had not yet published a check result for the CI-binding head, so CI success is intentionally not claimed.

## Authority boundary

P3.11 does not manufacture or simulate Hancom render observations.

Until a real Hancom-native render-control receipt is ingested and passes the promotion gate:

`HANCOM_NATIVE_RENDER_WORLD_CONTACT_HOLD / PIXEL_RENDER_FIDELITY_HOLD`

remains canonical.

## Successor

**ChatGPT Web HWPX MCP P3.12 — Hancom-Native Render Harness Intake, Font-Environment Sealing, Pagination/Line-Box Capture, Fixture-Level Raster World Contact & Exact-vs-Calibrated Fidelity Adjudication**
