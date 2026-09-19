# P3.7 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.7 — HWP Run/Style Recovery, Header/Footer/Footnote/Endnote Controls, Nested Text-Box/Object Graph, Cross-Format Round-Trip Fidelity Oracle & Rich Promotion Expansion**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_CI_PASS / REAL_NESTED_FLOW_PASS / BODY_TEXT_EQUIVALENCE_PASS / RICH_FAMILY_REGRESSION_PASS / RUN_STYLE_RECOVERY_PASS / CROSS_FORMAT_STYLE_EXACT_HOLD / PRODUCTION_DEPLOY_PENDING_AT_SEAL`

## Server

- Version: `0.7.0-p3.7`
- Original HWP source remains read-only.
- P3.6 table/equation/picture promotion remains regression-protected.
- P3.7 adds paragraph/run style recovery, nested text-flow ownership and a cross-format oracle.

## Run/style recovery

Recovered from HWP 5.x:

- `PARA_HEADER` paragraph shape/style/control-mask/instance receipts
- `PARA_CHAR_SHAPE` source-WCHAR transition points
- DocInfo `CHAR_SHAPE` semantic attributes
- visible run spans when source-WCHAR→visible-text mapping closes
- control-free paragraphs use identity coordinates
- controlled paragraphs use the explicit control scanner mapping rather than raw string indexes
- UTF-16 surrogate pairs are combined into one Unicode scalar

Safe semantic run attributes include:

- bold
- italic
- underline
- font size
- text color
- superscript/subscript provenance

P3.7 does not claim complete cross-format style equality for arbitrary HWP/HWPX pairs.

## PARA_TEXT correction

Real-world differential testing exposed two parser defects that were fixed:

1. HWP extended control atoms must consume the documented 8-WCHAR structure rather than be treated as ordinary C0 characters.
2. UTF-16 surrogate pairs must map to one visible Unicode scalar without corrupting source→visible offsets.

Malformed/truncated synthetic control tails are handled fail-closed without consuming following visible text.

## Nested text-flow graph

Real OAuth-native fixture workflow: `35449499943` — SUCCESS.

Observed real fixtures:

- header: 1 nested paragraph
- footer: 1 footer paragraph plus 4 object-text paragraphs
- footnote: 9 footnote paragraphs
- endnote: 6 endnote paragraphs
- text-box fixture: 2 object-text paragraphs plus 2 footnote paragraphs

All nested families are exposed through explicit owner/control flow receipts.

Authority:

`RECOVERED_GRAPH / NATIVE_PROMOTION_DEFERRED`

Native HWPX header/footer/note/text-box synthesis is intentionally deferred rather than fabricated.

## Cross-format equivalence oracle

Real pair:

- HWP: `para-001.hwp`, 18,944 bytes
- HWPX: `para-001.hwpx`, 75,779 bytes

Final OAuth-native oracle result:

- authority: `CROSS_FORMAT_EQUIVALENCE_RECEIPT`
- source paragraphs: 21
- target paragraphs: 41
- strict paragraph exact: false
- source nonblank paragraphs: 11
- target nonblank paragraphs: 11
- semantic body-text exact: **true**
- mismatch count: 0
- table geometry exact: true
- equation script exact: true
- picture count exact: true
- recovered HWP run count: 40
- run-style comparable paragraphs: 11
- run-style exact paragraphs: 0

The body-text oracle canonicalization is explicit and narrow:

`drop whitespace-only paragraphs; preserve every nonblank code point exactly`

No nonblank text normalization, fuzzy matching or edit-distance tolerance is used.

## Style authority boundary

P3.7 earns:

- source HWP run segmentation
- source style references
- semantic CHAR_SHAPE decoding
- source→visible run-span mapping
- safe-subset HWPX style promotion

P3.7 does **not** earn:

- exact style equivalence for the external `para-001.hwp/.hwpx` pair
- universal font-face/theme/style-id identity
- native promotion of nested header/footer/note/text-box controls

This mismatch is retained as a real oracle signal, not suppressed.

## Regression evidence

Latest canonical head before production seal:

- native lifecycle: `35449499868` — SUCCESS
- P3.6 rich-family real-HWP regression: `35449499901` — SUCCESS
- P3.7 nested-flow + equivalence workflow: `35449499943` — SUCCESS

## Successor

**ChatGPT Web HWPX MCP P3.8 — Cross-Format Style Canonicalization, Font/FaceName Resolution, Paragraph-Style Semantics, Native Header/Footer/Note Promotion & Round-Trip Fidelity Expansion**
