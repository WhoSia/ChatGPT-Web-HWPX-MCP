# P3.9 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.9 — Paragraph-Style Provenance Decomposition, HWPX Style/ParaPr Inheritance Graph, Native Text-Box Promotion, Rendered-Geometry Fidelity Oracle & Cross-Format Layout Expansion**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_CI_PASS / STYLE_PROVENANCE_GRAPH_PASS / NATIVE_RECTANGLE_TEXTBOX_PROMOTION_PASS / TABLE_CELL_GEOMETRY_EXACT_PASS / EQUATION_GEOMETRY_EXACT_PASS / PICTURE_GEOMETRY_EXACT_PASS / STRUCTURAL_HWPUNIT_LAYOUT_PASS / PIXEL_RENDER_FIDELITY_HOLD / PUBLIC_BOUNDARY_PASS / PRODUCTION_DEPLOYED`

## Canonical code evidence

Code head before documentation seal:

`d77d79c006c67d655810da061071ccf3f70b18ee`

Confirmatory runs:

- native lifecycle: `35459176414` — SUCCESS
- real HWP rich promotion: `35459176373` — SUCCESS
- nested-flow + HWP/HWPX equivalence: `35459176381` — SUCCESS

## Paragraph-style provenance decomposition

P3.9 adds a reference graph rather than treating a style value as provenance-free.

For HWP it records:

- direct ParaShape id
- paragraph Style id/name
- Style-referenced ParaShape id
- whether direct ParaShape equals the style-provided ParaShape

For HWPX it records:

- direct `paraPrIDRef`
- style id/name
- style-referenced paraPr id
- whether direct paraPr equals the style-provided paraPr

The retained `para-001.hwp/.hwpx` mismatch is therefore localized:

- source HWP direct ParaShape: 14
- source style: 0 / 바탕글
- source style ParaShape: 3
- source direct equals inherited style: false
- target HWPX direct paraPr: 13
- target style: 0 / 바탕글
- target style paraPr: 3
- target direct equals inherited style: false
- source left margin: 7.0556 mm
- target left margin: 3.5278 mm

Conclusion:

`DIRECT_OVERRIDE_DIVERGENCE / NOT_HIDDEN_STYLE_INHERITANCE`

P3.9 does not normalize this real difference away.

## Native rectangle textbox promotion

Real fixture: `footnote-tbox-01.hwp`.

Recovered mixed flow:

- body paragraphs: 3
- footnote paragraphs: 2
- object-text paragraphs: 2

Certified rectangle textbox:

- source controls: 1
- source object-text paragraphs: 2
- native promoted controls: 1
- deferred rectangle controls: 0
- status: `PROMOTED_NATIVE`

Verified structural receipt:

- width: 12,522 HWPUNIT
- height: 5,385 HWPUNIT
- horizontal offset: 9,291 HWPUNIT
- vertical offset: 12,485 HWPUNIT
- horizontal relation: PAGE
- vertical relation: PAPER
- treat-as-character: false
- paragraphs:
  - `여기에 각주가 들어있는`
  - `경우`

Post-materialization HWPX textbox map reproduced the same geometry and paragraph sequence.

Non-rectangle object-text families remain fail-closed rather than being synthesized as rectangles.

## HWP cell LIST_HEADER repair

Real HWP writer evidence required an extra 2-byte width-ref field between the 6-byte LIST_HEADER base and the 26-byte cell property structure.

P3.9 now parses:

`LIST_HEADER6 + width_ref2 + cell_property26`

and preserves:

- width-ref
- inner-margin flag
- row / column
- row span / column span
- width / height
- cell margins
- border-fill id

LIST_HEADER semantic bits are decoded from their observed upper-bit positions.

The previous 2-byte misalignment produced impossible dimensions such as hundreds of millions of HWPUNIT. After repair the real table fixture yields plausible, stable cell geometry.

## Table rich-promotion geometry

The first P3.9 oracle correctly exposed that `paragraph.add_table` initialized an even grid and therefore lost the HWP source's nonuniform cell geometry.

Promotion was repaired to:

1. create table topology,
2. materialize texts,
3. apply source merges,
4. reapply each surviving material anchor's certified source width/height **after** merges.

Real `table-001.hwp` result:

- source tables: 1
- target native HWPX tables: 1
- promoted tables: 1
- material cells: 131
- source cell-size receipts applied: true
- table topology geometry exact: true
- material-cell geometry exact: **true**
- source material cells: 131
- target material cells: 131

Authority:

`STRUCTURAL_HWPUNIT_CELL_GEOMETRY_EXACT`

## Equation geometry

Real `eq-01.hwp`:

- source equations: 3
- target equations: 3
- EqEdit script exact: true
- structural geometry exact: true

Widths/heights:

- 29,735 × 2,940
- 31,740 × 2,760
- 32,865 × 2,760

Authority:

`STRUCTURAL_HWPUNIT_EQUATION_GEOMETRY_EXACT`

## Picture geometry

Real `test-image.hwp`:

- source pictures: 5
- target pictures: 5
- picture count exact: true
- structural geometry exact: true

The oracle compares:

- width
- height
- horizontal offset
- vertical offset
- treat-as-character state

All five source/target geometry tuples match.

Authority:

`STRUCTURAL_HWPUNIT_PICTURE_GEOMETRY_EXACT`

## Geometry authority boundary

The current oracle proves document-structure geometry in HWPUNIT coordinates.

It does **not** yet prove:

- rasterized page identity
- line-breaking identity under a Hancom renderer
- glyph metric identity
- pagination identity
- pixel-level table border/background identity
- pixel-level equation or picture placement identity

Therefore the correct P3.9 verdict is:

`STRUCTURAL_HWPUNIT_LAYOUT_PASS / PIXEL_RENDER_FIDELITY_HOLD`

rather than claiming a rendered-pixel equivalence that was not measured.

## Regression protection

P3.9 preserves:

- P3.8 run-style exact real-pair result
- native header/footer promotion
- native dedicated footnote/endnote promotion
- P3.6 table/equation/picture family bindings
- durable revision/concurrency semantics

## Successor

**ChatGPT Web HWPX MCP P3.10 — Page/Section Geometry Constitution, Pagination & Line-Break Receipts, External Render-Control World Contact, Raster-Diff Fidelity Oracle & Layout-Authority Calibration**


## Final production closure

Runtime canonical code head:

`69477f547c9e4890e588ae6c457f4f3591200d79`

This head contains the P3.9 implementation plus the production-image fix that copies `p39_textbox.py` into the Docker image.

Production receipt:

- Render deploy: `dep-dancnnbbc2fs73dvebi0`
- status: `live`
- server version: `0.9.0-p3.9`
- native lifecycle: `35459385849` — SUCCESS
- public boundary: `35459385798`, attempt 2 — SUCCESS

The first production attempt exposed a deployment-only packaging defect: GitHub Actions could import `p39_textbox.py` from the repository, while the Dockerfile omitted that module from its explicit COPY list. The image contract was corrected; no textbox semantics were weakened.

The first public-boundary attempt after successful deployment reached the expected P3.9 version and OAuth metadata but hit a Render-branded 502 on the final unauthenticated MCP probe. Re-running the same code after the edge stabilized passed without application changes.

Therefore P3.9 production authority is closed for the implemented structural/document semantics. Pixel-render fidelity remains intentionally open.
