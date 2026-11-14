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

## R10 — Renderer-derived native HWPX TOC cache repair, independently re-rendered (2026-11-11)

The 28-row synthetic report was structurally valid and rendered in 5 pages
without clipped table cells, yet its native TOC entry for **결론 및 한계**
still cached page **1** even though the actual heading appeared on page **5**.

**Actual implemented repair, not a guessed page number:**

1. Generate the complete real `rhwp v0.8.7` SVG-page manifest.
2. Parse SVG text positions to match the numbered heading text against
   actual pages, explicitly rejecting missing/ambiguous observations.
3. Use `hwpx_mcp/render/p426_toc_cache_refresh.py` to change **only**
   cached page numbers in native HWPX TOC entries whose hyperlinks
   target `HWPHYPERLINK_TARGET_OUTLINE`; preserve the original HWPX
   bytes, ZIP members, XML namespaces, hyperlinks and other objects.
4. Persist a new HWPX at
   `P426_합성_전기회로_목차갱신.hwpx`; never silently mutate the
   source. Save original/new SHA-256 and an exact change list.
5. Independently render the **new** HWPX again with the same real
   `rhwp` CLI and audit the refreshed SVG output. Require matching
   heading pages, stable total page count and zero clipped table lines.

This is **rendered-evidence-informed cached TOC updating**. It does
not promise native HWP's internal pagination-field refresh semantics,
nor does it imply visual equivalence between `rhwp` and Windows
Hancom. The re-render audit is the acceptance authority here.

**Measured results:** initial TOC pages
`[1,1,1,1]` versus actual heading pages `[1,1,1,5]`.
One cached entry changed. Refreshed TOC pages
`[1,1,1,5]`, all four entries match actual SVG heading locations.
The document remains **5 pages**, with **0 rhwp cell overflow lines**.
Source SHA-256:
`b348f634b40b8294ca740396d4f1373e0ad46e3765174a400a5f717b731ff63e`.
Refreshed HWPX SHA-256:
`79f093f8fef277c2855bf5af086e52a751e667e41e13c58f49e92938be16be06`.

**Verified test execution:**

- [Actual SVG render/re-render run #42949858056](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42949858056): **SUCCESS** and
  `TOC visual pass: CONSISTENT_IN_THIS_RENDERER pages: 5`.
- [Native P4.26 CI #42949858050](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42949858050): **SUCCESS**, 61 inherited P4.25 tests plus 68 P4.26 tests = **129 tests**.
- Re-opened the actual uploaded artifact ZIP; manifest's before/after
  heading-page comparisons have `mismatch_count` **1 → 0**, with
  `unresolved_heading_count=0` both times.
- Native package test ensures the refreshed package preserves all
  archive members and alters only `Contents/section0.xml`.

**Artifacts:** run #42949858056 retains the refreshed HWPX, 5 actual
refreshed SVG/PNG pages, and JSON acceptance evidence in a GitHub
Actions downloadable artifact. It is also available as a direct
chat sandbox HWPX in the task conversation.

**Known limitations:** current integration still uses the four explicitly
declared headings of the synthetic demonstration for the external
renderer audit; arbitrary user-document heading discovery is follow-up
work. A native Windows Hancom repagination and a real ChatGPT MCP-host
delivery test remain separate prerequisites for production sign-off.

### R10.1 — Native TOC heading auto-discovery

The first TOC refresh pipeline required four explicitly supplied synthetic
headings. This has now been generalized *conservatively*:
`discover_native_toc_headings(source)` reads actual native TOC
`HWPHYPERLINK_TARGET_OUTLINE` entries from the source HWPX, verifies
sequential first-level numbering and unique titles, and obtains the
headings without needing caller-written title lists.
`scripts/p426_refresh_toc_from_render.py` defaults to that discovery.
Complex hierarchical/unrecognized numbering is intentionally rejected
instead of silently mapping to a guessed page.

**Verified on the actual external renderer** at
[run #42950411792](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42950411792):
`TOC visual pass: CONSISTENT_IN_THIS_RENDERER pages: 5`.
The resulting HWPX is still a new revision with all four cached page
numbers matching actual SVG heading locations. This extends the code
path beyond hardcoded demonstration headings while retaining the
rhwp-versus-Windows Hancom fidelity distinction.

## R11 — Actual figure-caption-to-body visual clearance (2026-11-11)

The previously accepted synthetic report still had a visibly tight
figure-caption and following-body spacing on page 2. Direct extraction
from its actual `rhwp` SVG placed caption text at baseline
`y=508.57` and the next paragraph at approximately `y=515.14`,
a gap of **6.57 SVG coordinate units**. XML validity and table/TOC
checks did not identify this typography problem.

**Actual code improvements:**

- `p425_report_presets._as_ordered_block` supports explicit,
  bounded native `paragraph_format` for body paragraphs:
  `spacing_before_pt`, `spacing_after_pt`, `keep_with_next`,
  and `keep_lines`. Values are validated and handed through P3.38
  into the pre-existing P3.21/P2.3 native formatting system.
- A report-level, opt-in `caption_clearance_pt` argument (0–36pt,
  default 0) applies a minimum native `spacing_before_pt` to a
  body paragraph directly after a captioned figure. It never
  modifies the image or overrides an explicitly larger user
  spacing setting. Both report preview and actual report creation
  receive the option; the synthetic science report chooses 14pt.
- `scripts/p426_visual_spacing_audit.py` reads actual SVG text glyph
  baseline coordinates and matches the full caption and next paragraph
  text; ambiguous/missing text cannot yield a false success. A CI
  visual acceptance step requires at least 16 SVG units between
  the two baselines. It explicitly identifies the authority as
  `ACTUAL_RHWP_SVG_BASELINES_NOT_NATIVE_HANCOM`.

**Actual rendered results:** latest pinned `rhwp v0.8.7`
renderer reports caption baseline **508.57**, body baseline
**533.81**, gap **25.24** SVG coordinate units. It meets the
16-unit threshold and improves the original measured ~6.57-unit gap.
A real PNG page rendering independently shows visible text clearance
and readable Hangul font fallback.

**Executed CI evidence:**
- [P4.26 real renderer #42960263196](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42960263196): **SUCCESS**, actual SVG
  `P4.26 caption clearance measured: 25.24`, 5-page native
  TOC re-rendering remains successful, zero clipped table lines.
- [P4.26 native regression #42960263395](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42960263395):
  **SUCCESS**, 61 inherited P4.25 tests plus 77 P4.26 tests =
  **138/138 tests passing**.
- [Artifact](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42960263196)
  contains the actual updated native HWPX,
  5-page SVG/PNG renderings, JSON TOC verification
  and `p426_visual_spacing_acceptance.json`.
  User-accessible direct HWPX and ZIP copies were materialized in
  the chat container.

**Scope:** SVG baseline gap is not a glyph-outline collision model or
a Windows Hancom page metric. This was tested on the synthetic
science report and is now available as a general, opt-in API argument.
No production deployment or live P4.26 client attachment claim.

## R12 — Native editable equations with visibly rendered captions (2026-11-11)

A direct inspection of the actual synthetic report's 5-page
`rhwp` SVG/PNG showed that the *equation objects rendered* (e.g.
`V=IR` and a fraction), but native equation-object captions
`식 1. 옴의 법칙` and `식 2. 저항의 정의` did **not appear in
the rendered page**. Previously, P3.21 attached these native captions
via `equation.set_caption`; the saved HWPX package was structurally
valid, but this renderer omitted them.

**Implemented a controlled, opt-in fallback:** the report DSL now
accepts `equation_caption_mode="native"|"visible-paragraph"`,
with `native` retained as the backward-compatible default.
Under `visible-paragraph`, caption numbering still occurs once
per equation; the equation stays a real editable native HWPX math
object, while its numbered caption is emitted as a separate ordinary
native paragraph immediately after the equation. The equation's
native caption field is removed *in this mode*, preventing duplicate
caption rendering in native Hancom. Caption paragraphs receive
bounded spacing and `keep_lines`.

**A real integration failure was caught and repaired:** initially,
styling a captionless native equation's empty anchor with regular
paragraph/run formatting caused the P2.3 formatting engine to reject
it (`Target paragraph has no text run to format`). P3.21's
`_preset_format_operations` now skips text-run styling for native
equation anchors without a caption; the equation's intrinsic script
and base unit are preserved, while the visible caption paragraph
is formatted separately. A synthetic real HWPX roundtrip confirms
two editable equation objects and two visible caption paragraphs.

**Visual acceptance:** `scripts/p426_visual_equation_caption_audit.py`
inspects real SVG text lines; the CI requires the two numbered
caption labels to be uniquely present in the rendered pages. The
actual pinned `rhwp v0.8.7` renderer run
[#42961200976](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42961200976)
completed **SUCCESS**, reporting both `식 1. 옴의 법칙` and
`식 2. 저항의 정의` exactly once on page 1. It also retains the
existing five-page TOC cache refresh and caption-to-body clearance
requirements.

**Native regression:** run
[#42961201010](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42961201010)
completed **SUCCESS** with **61 inherited P4.25 + 84 P4.26 =
145 passing tests**, zero errors/failures.

**Actual generated artifacts:** download from the real renderer
GitHub Actions run, including `P426_합성_전기회로_목차갱신.hwpx`,
5 real SVG/PNG pages, `p426_equation_caption_visibility.json`,
TOC and caption-spacing acceptance JSON. The refreshed HWPX was
materialized in the conversation as
`P426_수식캡션_목차_최신보고서.hwpx` (18,881 bytes;
SHA-256 `3a69610c1db1b8269903bb5b2ce785e4e85d98047fa07af36d01a284960823d5`).
A generated first-page PNG was visually inspected and confirmed to
show readable Hangul equation captions beside the editable formulas.

**Compatibility boundary:** this proves visual caption presence in
the independent rhwp SVG renderer, not the native Windows Hancom
placement or identical typography. The default native-caption mode
is still available. A browser-hosted P4.26 MCP attachment download
has not been verified against the currently deployed P4.18 service.


## R13 — Numeric integrity and column-legibility preflight (2026-11-11)

This incremental change targets avoidable defects in *real input* before native
composition, rather than counting tool registrations as user-visible progress.

- The report table adapter now rejects IEEE-754 NaN and positive/negative
  infinities using `math.isfinite`. Formerly these silently became literal
  strings `nan`, `inf`, `-inf` in the native HWPX table. Finite measurements
  and negative scientific notation retain their previous serialization.
  Regression: `tests/test_p426_numeric_integrity.py`.
- The existing P4.26 static layout preflight now warns when the average
  width of an explicitly sized multi-column table is below **12 mm**
  (`NARROW_AVERAGE_TABLE_COLUMN`), including an approximate mm value.
  This catches a case in which the table's *total* width fits but individual
  columns would likely be illegible. It is explicitly a conservative heuristic:
  real column widths, merged cells, font metrics, and wrapping still require
  renderer checks. Regression: `tests/test_p426_layout_preflight.py`.
- No new MCP tool was added; existing authoring and preflight interfaces are
  improved. This patch does not prove superiority over competitor MCPs,
  native Hancom rendering, live deployment, or client-side attachment UX.
- Do not report CI as passed until the exact latest commit's workflow completes.
  Preserve the current P4.26 draft branch; do not merge or deploy as part of
  this defect-repair slice.

**Competitive context:** Dayoooun/hwpx-mcp publicly advertises atomic
updates, nested table editing and broad HWPX tools; treesoop/hwp-mcp
advertises WASM-powered HWP/HWPX reading, Markdown traversal and SVG rendering.
Their public feature lists are useful backlog inputs, not head-to-head
benchmark scores. Next independent acceptance targets are real-world edits
of pre-existing layouts, renderer-specific legibility gates, and live
ChatGPT-generated document delivery.


## R14 — Input PNG integrity preflight (2026-11-11)

Native science-report figure authoring previously checked only PNG/JPEG magic
bytes, so broken PNG chunk CRCs, truncation and trailing content could be
accepted as a document image payload. That is not an appropriate professional
document creation boundary.

The existing `_as_native_figure` path now checks PNG chunk framing,
boundaries, CRC32, a single initial IHDR with nonzero dimensions, at least
one IDAT, and a terminal empty IEND with no trailing bytes. JPEG now rejects
an absent end-of-image marker, while full JPEG decoding is outside this
small change. Input images are not re-encoded or modified.

Regression: `tests/test_p426_figure_container_integrity.py` contains
valid-byte preservation and four corrupted-container cases. This is an
**input container-integrity check**, not a rendered-visual fidelity oracle.
The complete latest CI and genuine Hancom acceptance remain separate gates.


### R14 CI failure and corrective action

The initial R14 code commit `fdfbef6` and test commit `cb08a37`
failed in **both** inherited P4.25 native-report regression and the
authentic synthetic-showcase generation step. Logs showed a
`REPORT_FIGURE_SIGNATURE_MISMATCH` for valid PNGs: the newly added
PNG signature literal had accidentally been double-escaped in source,
so it matched printable backslash characters instead of actual PNG
header bytes. The regression was corrected in `d8dc00b` by using
the exact native PNG signature literal. This is an example of a new
validation gate breaking older working input; tests must include
both normal images and deliberately corrupt containers.

Do not treat the failed runs as passes. Latest full native and real
rhwp checks must be read from their completed workflows for the
corrected commit before promotion.


### Inherited test-fixture reconciliation

After repairing the PNG literal in `d8dc00b`, P4.25 inherited report
tests still failed: two historical fixtures were only a PNG signature
followed by fake strings (`fake-image`, `sample`), never valid images.
The parser was correct to reject them. Commit `d4249e0` replaces
those two stubs with a genuine small PNG fixture while retaining the
unchanged caption/order assertions and preserving intentionally invalid
image tests. The authentic native showcase PNG had already used proper
IHDR/IDAT/IEND chunk CRCs.

This distinction matters: legacy tests that accept intentionally malformed
data do not establish a production-grade compatibility contract. A failing
test can reveal an obsolete fixture rather than an incorrect validator.


## R15 — Strict native-table edit semantics and preservation (2026-11-11)

Existing P3.23 advanced table editing accepted loose Python truthiness for
`set_repeat_header.enabled` and `set_row_properties.header`, so an agent
sending the string `"false"` could silently **enable** a native table header.
Likewise `int(...)` coercion admitted booleans/numeric-looking strings for
native row indices and heights. This could create subtle unintended edits in
an existing HWPX even when the request appeared successful.

R15 adds strict, explicit type validation before creating a candidate
document. Boolean flags must be real JSON booleans, and row indices/heights
must be actual integer values with admitted bounds. Rejected edits leave the
original HWPX bytes unchanged, checked by SHA-256. Valid `true` and `false`
header transitions and valid row heights are reopened from native HWPX and
inspected.

Implementation: `hwpx_mcp/document/p323_advanced_tables.py`.
Regression: `tests/test_p426_table_input_integrity.py`.

This is a narrow but concrete competitive editing improvement, **not**
an independently measured nested-table editing benchmark. It does not
authorize merging into main or deploying P4.26. The tests and native
rendering workflow are separate acceptance gates; only completed runs
on the latest production-code commit establish green status.
