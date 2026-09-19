# P3.8 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.8 — Cross-Format Style Canonicalization, Font/FaceName Resolution, Paragraph-Style Semantics, Native Header/Footer/Note Promotion & Round-Trip Fidelity Expansion**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_CI_PASS / RUN_STYLE_EXACT_PASS / PARAGRAPH_STYLE_PARTIAL_EXACT / NATIVE_HEADER_FOOTER_NOTE_PROMOTION_PASS / TEXTBOX_PROMOTION_HOLD / RICH_FAMILY_REGRESSION_PASS / PUBLIC_BOUNDARY_PASS / PRODUCTION_DEPLOYED`

## Server

- Version: `0.8.0-p3.8`
- Runtime source head before final documentation seal: `dd774ac06109c5e26a57c3e86c55c8984c3df9bc`
- Render deploy: `dep-danbgpugekts738dp5b0`
- Deploy status: `live`

## Cross-format run-style canonicalization

The P3.7 exact-style HOLD was decomposed into semantic axes and resolved by canonicalizing document-local identifiers.

Canonical run axes:

- text
- bold
- italic
- underline
- strike
- size
- color
- font
- superscript/subscript state

Font semantics use resolved FaceName values instead of raw HWP face IDs or HWPX fontRef IDs.

Real pair:

- HWP: `para-001.hwp`, 18,944 bytes
- HWPX: `para-001.hwpx`, 75,779 bytes
- comparable paragraphs: 11
- segmentation-exact paragraphs: 11
- exact run-style paragraphs: **11/11**

Every canonical run-style axis matches **11/11**.

Authority:

`CROSS_FORMAT_RUN_STYLE_EXACT_PASS`

## Paragraph-style semantics

Compared axes:

- alignment
- left margin
- right margin
- first-line indent
- spacing before
- spacing after

Explicit zero and absent default-zero values are canonicalized to the same semantic zero.

Real-pair result:

- comparable paragraphs: 11
- exact paragraph styles: **10/11**
- alignment: 11/11
- first-line indent: 11/11
- left margin: 10/11
- right margin: 11/11
- spacing before: 11/11
- spacing after: 11/11

Retained mismatch:

- paragraph 0 source HWP left margin: **7.0556 mm**
- target HWPX left margin: **3.5278 mm**

The official HWP5 specification defines left margin and indent as distinct paragraph-shape fields, so this remaining difference is retained as a real cross-format signal rather than normalized away.

Authority:

`PARAGRAPH_STYLE_10_OF_11_EXACT / ONE_REAL_LEFT_MARGIN_MISMATCH`

## Native nested-flow promotion

Real nested-flow workflow: `35455036874` — SUCCESS.

Closed families:

### Header

- recovered: 1 paragraph/control family
- promoted native: 1
- status: `PROMOTED_NATIVE`

### Footer

- recovered footer paragraph: 1
- promoted native: 1
- associated object-text paragraphs remain separately deferred
- status: `PROMOTED_NATIVE`

### Footnote

Dedicated real fixture:

- source paragraphs: 9
- promoted controls: 9
- deferred: 0
- status: `PROMOTED_NATIVE`

### Endnote

- source paragraphs: 6
- promoted controls: 6
- deferred: 0
- status: `PROMOTED_NATIVE`

### Text-box / object-text

Dedicated mixed fixture:

- object-text paragraphs: 2
- note paragraphs: 2
- native text-box container/anchor fidelity: not certified
- object-text status: `DEFERRED`
- footnote promotion in the mixed fixture: 1 promoted / 1 deferred because one owner anchor is missing

No missing anchor is fabricated.

## Round-trip/equivalence evidence

Real HWP/HWPX equivalence workflow:

- body semantic text exact: **true**
- nonblank paragraph stream: 11 vs 11
- run-style exact: **true**
- paragraph-style exact: **false (10/11)**
- table geometry exact: true
- equation script exact: true
- picture count exact: true

The body-text normalization remains narrow:

`drop whitespace-only paragraphs; preserve every nonblank code point exactly`

## Regression and CI evidence

Canonical P3.8 code head `dd774ac06109c5e26a57c3e86c55c8984c3df9bc`:

- native lifecycle: `35455036889` — SUCCESS
- rich-family real-HWP regression: `35455036842` — SUCCESS
- nested-flow + equivalence: `35455036874` — SUCCESS
- public boundary: `35455036887` — SUCCESS

P3.6 table/equation/picture rich promotion remains regression-protected.

## Authority boundary

P3.8 earns:

- canonical FaceName/fontRef resolution
- exact real-pair run-style equivalence on the tested pair
- paragraph-style axis diagnostics and 10/11 exact result
- native header promotion
- native footer promotion
- native footnote promotion
- native endnote promotion
- family-graded partial note promotion
- fail-closed textbox/object-text deferral

P3.8 does **not** claim:

- universal paragraph-style equality across HWP/HWPX
- that the retained 7.0556 mm vs 3.5278 mm left-margin difference is parser noise
- native text-box/object-text promotion
- universal HWP→HWPX rendering identity

## Successor

**ChatGPT Web HWPX MCP P3.9 — Paragraph-Style Provenance Decomposition, HWPX Style/ParaPr Inheritance Graph, Native Text-Box Promotion, Rendered-Geometry Fidelity Oracle & Cross-Format Layout Expansion**
