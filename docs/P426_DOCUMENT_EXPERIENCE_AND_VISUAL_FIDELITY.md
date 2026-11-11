# P4.26 — Document Experience & Visual Fidelity: Professional Layout, Native Rendering and Seamless File Delivery

**Started:** 2026-11-11  
**Branch:** `development/p426-document-experience-visual-fidelity-20261111`  
**Base:** P4.25 tested research line, SHA `d1a908ef134cf3c2c9e9528e8d20659498f636bc`

## Outcome

Turn native HWPX composition into a polished, accessible document experience:
consistent design tokens → editable HWPX content → explicit rendering
capability → working MCP file handoff. Retain the P4.25 feature set
but promote page geometry, typography and equation-fidelity diagnostics
to product-level functions.

## Research units (independent evidence)

1. **A — Layout:** reusable named design-token sets; compile into P4.23
   `style_profile` and P3.18 page setup, not another HWPX writer.
   Page body geometry, table fit and image width must be checkable before
   native composition.
2. **B — Native rendering:** capability discovery and render-plan tools
   built on P4.24's actual Windows Hancom PDF bridge or a clearly
   identified optional alternative. Never call XML geometry estimates a
   real image preview. Do not recreate previously deleted local files.
3. **C — Seamless delivery:** the existing P3.33 MCP ResourceLink +
   authenticated revision download must remain directly usable from a
   one-call author/edit tool. Test against actual MCP runtime rather
   than assuming a returned URL appears as a downloadable attachment.
4. **D — Academic quality:** equations remain editable OWPML/HWP
   Equation Editor scripts; provide equation-script diagnostics,
   numbered captions and stable source/reference identifiers.

## Competitor and first-party technology map (2026-11-11)

- Dayoooun/hwpx-mcp: atomic ZIP/XML updates, text `lineseg` reset after
  editing, nested table handling, expression insertion as HWP script.
  **Adopt workflow principles; do not copy unknown upstream code**.
- Topabaem05/hwpx-mcp: Windows COM HWP equation support versus
  cross-platform `python-hwpx` creation; gateway tool search.
- treesoop/hwp-mcp + edwardkim/rhwp: text-in-order Markdown and
  OWPML equation rendering AST (fraction, radicals, arrays, sums,
  relations); optional WASM/CLI SVG/PDF previews. A rendered result is
  renderer-specific, not proof of Hancom equivalence.
- Hancom Developer portal (https://developer.hancom.com/docsmenu):
  HWP Automation (COM/OLE), web editor, document viewer/conversion
  solutions, OWPML/open-source resources.
- Hancom Automation manual:
  https://developer.hancom.com/hwpautomation — lists
  `HwpAutomation.pdf`, `ActionTable.pdf`, `ParameterSetTable.pdf`
  and event-handler guide. **Important license**: personal
  non-commercial Automation use is described as freely available;
  commercial products may require a separate Hancom license.
  Do not imply general commercial rights.

These notes use public claims in the official docs and peer READMEs;
no upstream source code was imported. A competitor's claims of
'perfect compatibility' are not our independent conformance result.

## Acceptance targets

- A single declared design token set controls native page margins,
  typography and heading hierarchy; its digest survives the P3.38
  compile path, not merely the outer request JSON.
- Bad page geometry, wide tables, or oversized images are identified
  before file creation; no automatic destructive edit.
- The native equation's source `latex`, generated EqEdit script and
  retained script digest are distinguishable; supported complex
  expression cases have readable acceptance tests.
- Actual native-generated HWPX reopens with table, picture and
  equation objects; screenshot/PDF behavior only claimed when
  independently rendered.
- MCP tool returns actual Pydantic `CallToolResult` with usable
  `ResourceLink` and retained revision identity.
- Keep exact P4.25 parity; no new signing system or fake PDF created.

**Non-goals**: use/deletion/recreation of the owner's removed
`C:\\p424-validation` directory or deleted survival-rate HWPX,
production deployment without an explicit release decision, or
inflating commit counts with cosmetic/no-op changes.

## R4 — Portable equation spacing, figure fit, and actual file-delivery regression (2026-11-11)

P4.26 adds a bounded, opt-in portable equation dialect, rather than
pretending all LaTeX commands are supported by the installed HWPX
EqEdit compiler. `hwpx_mcp/equations/p426_latex_compatibility.py`
exports `normalize_equation_latex(latex, policy="strict"|"portable")`.
Strict is the default and preserves the input exactly; portable only
replaces known spacing control sequences (`\\,`, `\\;`, `\\:`,
`\\!`, `\\quad`, `\\qquad`) with spaces. Structural LaTeX
commands (fraction, root, integral, summation, matrix, etc.) are not
modified by this adapter. It explicitly returns the removed macros,
original/normalized digests and `visual_spacing_preserved` flag.

Both `preview_native_equation_script(..., policy)` **and** actual
ordered science-report equation blocks
`{"type":"equation","latex":"...","policy":"portable"}`
use this shared translator, so visual diagnostics and HWPX composition
do not silently diverge. A real native HWPX equation roundtrip test
covers an integral previously rejected due to `\\,`. Portable mode
necessarily changes spacing, not mathematical structure, and must not
be described as glyph/pixel-perfect preservation.

P4.26 improves real one-call HWPX user experience: report creation
now derives the default downloadable filename from the supplied report
title, e.g. `전기 회로 특성 분석.hwpx`, rather than the generic
`report.hwpx`, while explicit `filename` wins. Fixed native
rich-document metadata to preserve the title from `rich_plan.document.title`
instead of discarding it.

For professional layout, `fit_figures_to_page=true` opt-in limits
oversized picture widths to A4 text body width less a small inset,
scaling native HWPUNIT width and height proportionally while leaving
embedded PNG/JPEG bytes and captions untouched. No re-encoding,
rasterization or cropping. It never resizes tables or equations
implicitly. The default is false, preserving source layout.

**File delivery testing:** The P3.33 end-to-end test imported the full
OAuth server and required `P12_AUTH_DATABASE_URL`. A CI attempt
therefore failed during import despite 60 passing P4.25 and 44
passing P4.26 tests. P4.26 now has
`tests/test_p426_delivery_roundtrip.py`: a real synthetic native
HWPX built through P3.21 is handed off as an MCP
`CallToolResult(ResourceLink)`, its actual signed revision URL is
opened through the P3.33 Starlette HTTP handler, and the returned
HWPX bytes, MIME, Unicode attachment filename and SHA-256 are
compared. No fake application PostgreSQL or external OAuth server is
required. It preserves `host_attachment_status=NOT_OBSERVED`:
working HTTP is **not** proof of ChatGPT UI attachment presentation.

This section represents implemented code and committed tests. Latest
CI must be consulted independently before claiming a pass for
post-creation commits. No deleted local validation directory, private
source HWPX or fake PDF is used.

### Exact CI evidence for this product slice

At code HEAD `0c2682325ee5d9c908a48cb5cd5dc010c99f0533`,
[P4.26 Actions #42940964099](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42940964099)
completed **SUCCESS**: **61 P4.25 regression tests + 49 P4.26
tests = 110 passing tests**, zero failures/errors. Specific passed
integration cases include:

- The P3.21 native HWPX writer saves a picture after opt-in
  `fit_figures_to_page` and P2.9 reads back exact fitted
  width/height.
- Actual HWPX bytes created by P3.21 pass through P3.33 MCP
  `ResourceLink`, a genuine signed HTTP response handler, and
  roundtrip byte-for-byte as a Unicode-named attachment.
- Portable `\\,` spacing adaptation allows the installed native
  EqEdit compiler to save an editable integral formula, while strict
  mode explicitly rejects the unsupported input.
- The Korean task-discovery gateway now advertises P4.26 equation,
  renderer, and native reference tools.

A previous CI run did fail when the legacy P3.33 server-level test
imported PostgreSQL OAuth configuration and later because a new test
used `ResourceLink.mimeType` rather than its Python property
`mime_type`. Both were diagnosed via actual Actions logs and the
integration suite was repaired; this pass is the corrected head.

The GitHub workflow uses synthetic temporary HWPX files and does not
perform an actual ChatGPT client-side attachment click, live `rhwp`
process rendering, or Windows Hancom native PDF comparison. These
remain separate release acceptance items.

## R7 — Long-table authoring, native pagination policy, and inspection (2026-11-11)

A further P4.26 research unit addresses lengthy academic tables without
introducing another HWPX XML writer. The report frontend
`_as_native_table` now validates and forwards:

- `width`: optional positive integer in native HWP units.
- `first_row_header`: semantic header indicator.
- `table_format.page_break`: `CELL`, `TABLE`, or `NONE`.
- `table_format.repeat_header`: boolean; combined with a marked
  first header row to set native `repeatHeader` and `hp:tc@header`.
- `table_format.border_color`: `#RRGGBB` or `RRGGBB`.

These fields are passed to the pre-existing P3.21 table finisher and
P3.23 advanced table operations, not a simulated HTML table renderer.

**Synthetic real-file test:** an 80-row × 3-column table is composed
into a real native HWPX and reopened through
`build_advanced_table_map`. The test checks 80 retained rows,
240 cell payloads, `pageBreak=CELL`, `repeatHeader=true` and
header flags on the first row.

**New MCP tool:** `inspect_document_table_layout(document_id, offset,
limit)` reads an authenticated retained revision and returns native
HWPX table locators, row/column counts, per-row geometry, repeated-header
flags and page-break policy. Added to real `server.py`
registration, `probe_capabilities` and Korean workflow discovery.

**Preflight warnings:** `assess_native_layout` now identifies
`LONG_TABLE_WITHOUT_CELL_SPLIT` or
`LONG_TABLE_WITHOUT_REPEATED_HEADER` for tables of at least 40 rows
under potentially problematic policies. These are conservative
**static review hints**: the tool cannot prove whether a specific row
will cross a page boundary before a native renderer paginates it.

Test modules: `tests/test_p426_long_table_layout.py`,
`tests/test_p426_table_layout_inspection.py`, and extended
`tests/test_p426_layout_preflight.py`.

**Connected-deployment discovery:** calling the currently installed
ChatGPT Web HWPX MCP's live `probe_capabilities` on 2026-11-11
reported version **`0.43.0-p4.18`**, with only the seven old
document tools in its capability list. That deployed service is **not**
the P4.26 branch. Therefore a passing GitHub PR CI cannot be
represented as a successful live P4.26 ChatGPT host acceptance test.
A separate controlled deployment/update is required, followed by a
fresh capability probe and real host-side file link observation.

No prior deleted validation directory or private sample HWPX was used.

## R8–R9 — Actual HWPX artifacts and renderer-directed page repair (2026-11-11)

This research unit went beyond synthetic mock tests: P3.21 generated a
real, downloadable P4.26 scientific report HWPX (title, semantic
paragraphs, editable EqEdit formulas, a programmatically drawn PNG
figure, a long table, native footnote, bookmark, cross-reference, TOC
and page numbers). The file is generated by
`scripts/p426_generate_native_showcase.py` and validated by
reopening **that exact saved ZIP** through P2/P3 native readers.
The generator outputs `P426_생성검증_manifest.json`, HWPX SHA-256
and an explicit list of claims *not* established by its structural
checks. GitHub Actions uploads the real HWPX bytes for manual review
rather than declaring success based only on a mocked `ResourceLink`.

A second actual CI workflow
`.github/workflows/p426-real-svg-render-ci.yml` downloads the
external `rhwp v0.8.7` Linux CLI from its GitHub release, verifying
**SHA-256 `f1e541a25cfe76b6bc1daf18bf9c1f9a5ac5e03e2c01b188daaf54107214f631`**
before running the executable. It executes the real
`rhwp export-svg ... --json -p N` on the synthetic report, observes
rendered pages and `overflowCellLines`, and exports actual SVG and
PNG artifacts. Korean glyph fallback is installed in the **runner**
through `fonts-noto-cjk`; **font files are not distributed** in
user artifacts. SVG→PNG rasterization uses `librsvg2-bin`.

**Genuine visual defect discovered:** the first unsegmented 80-row
table passed all native HWPX ZIP/XML validation, but actual rhwp
reported **67 clipped table cell lines on page 3** of 4 rendered pages.
This proves structural acceptance alone was insufficient.

**Implemented native fix, opt-in:** `hwpx_mcp/orchestration/
p426_table_pagination.py` splits oversized logical tables into
small native tables, repeating the original header row and inserting
explicit native page breaks before each segment. Every source data
row is preserved in order; the logical table caption number remains
consistent across continuation segments. The existing continuous
table mode remains available. API:
`segment_long_tables=true`, `table_segment_rows=20` (conservative
general-purpose default). Both report preview and document creation
support these arguments.

On 2026-11-11, real external render CI
[run #42947146854](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42947146854)
**succeeded** on the five-segment native report, showing **7 pages
and 0 clipped cell lines**. The associated native CI
[run #42947146901](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42947146901)
passed **125 tests** (61 P4.25 + 64 P4.26), including segmentation
byte/row preservation, continuation captions and real HWPX readback.

The benchmark [run #42947977558](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42947977558)
rendered the same synthetic table with three budgets:

| Maximum rows per native segment | Actual rhwp pages | Clipped cell lines |
|---:|---:|---:|
| 20 | 7 | 0 |
| 28 | 5 | 0 |
| 36 | 5 | 0 |

We selected **28 rows for the short-cell synthetic demonstration**
to reduce page count without adopting the larger 36-row budget.
The public library default remains **20 rows**, because long or
wrapped table cells may have very different geometry. A new CI run
on the 28-row default showcase is required to validate its specific
downloadable artifact. Never generalize the 28-row result to all
documents or to native Windows Hancom print output.

**Further visual limitations observed:** the initial SVG rasterizer
lacked Korean glyph fonts, displaying Hangul as tofu boxes; installing
an open Korean font fallback on the test runner corrected the preview.
The native TOC currently caches page numbers too early: the SVG
shows TOC entries as page 1 even when the conclusion actually appears
later. Correct TOC page numbers require genuine repagination and field
refresh, not merely asserting that the TOC object exists. The final
Windows Hancom PDF comparison and live ChatGPT host attachment-card
acceptance are still unverified.

The generated showcase intentionally uses only artificial V-I
data and an original synthetic PNG chart; it is **not an empirical
experiment** or a copy of the user's private experiment.
