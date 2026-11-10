# P4.25 — Competitive Capability Convergence: Native HWPX Authoring, Editing & Agentic Workflow Integration

**Korean name:** 경쟁 기능 통합 — HWPX 네이티브 문서 작성·편집 및 에이전트 작업 흐름 고도화  
**Version:** P4.25  
**Start date:** 2026-11-10  
**Development branch:** `development/p425-competitive-capability-convergence-20261110`  
**Base:** P4.24 branch at `df66571eaf23477dd09b05f03bc207660c205b69`

## Objective

Make the public ChatGPT Web MCP work like a useful HWPX editor, not an
audit/debugging interface. Adapt proven user-facing workflows from publicly
documented HWPX MCP projects, reuse our substantial P2/P3 editing engines,
and put directly usable actions on the **real MCP tool surface**. One
ordinary request should lead to an editable native HWPX and an actual
client-consumable HWPX attachment with as few intermediary calls as possible.

### Product acceptance scenarios

1. **One-call authoring:** Given plain text or a rich block plan, create
   a native HWPX revision and return its MCP `resource_link`.
2. **Find, preview, replace:** Read text and paragraph/table locators,
   preview substitution counts, apply edits, and return revised HWPX.
3. **Native tables:** Inspect real cell grids, then update cells,
   merge/split or add/remove rows via existing P2.7 editor.
4. **Native formatting:** Expose paragraph/run styles and document
   templates as approachable, discoverable MCP calls.
5. **Document interchange:** Read HWPX into structured text/Markdown
   without asserting layout equivalence; produce native HWPX from a
   structured authoring plan.
6. **Tool discoverability:** Avoid forcing the client to inspect the
   entire low-level tool catalogue. Provide a small user-facing tool
   overview / action suggestions.
7. **File experience:** Return `CallToolResult` with `ResourceLink`
   and structured receipt, and verify real ChatGPT attachment behavior
   separately from server-generated URLs.

## Existing P4.25 implementation inherited at branch creation

Nine real tool registrations were already committed to P4.24's development
branch and inherited here:

- `create_and_deliver_document`
- `create_rich_document_and_deliver`
- `read_document_structure`
- `find_document_text`
- `preview_template_fill`
- `fill_template_and_deliver`
- `replace_text_and_deliver`
- `list_document_tables`
- `edit_table_and_deliver`

These use P3.21/P3.37/P3.38/P2.7 engines and P3.0 durable revision commits.
Inheritance of code does not mean those new tools have passed the real
host/WSL integration test or been deployed.

## Peer references (design patterns, not unlicensed code copies)

- https://github.com/Dayoooun/hwpx-mcp — bulk replace, table operations,
  text search, discoverable document actions (MIT).
- https://github.com/treesoop/hwp-mcp — templates and compact one-call
  document workflows (MIT).
- https://github.com/deoksangcho/hwpx-mcp-server — preview/apply workflow,
  structured reading and stateless per-document tools (MIT).
- https://github.com/gridi-ai/hancom-mcp — familiar open/edit/save UX (MIT).
- https://github.com/Topabaem05/hwpx-mcp — tool discovery gateway concept;
  license must be verified before direct code reuse.

Never equate copied functionality with copying source. If actual upstream
source is incorporated later, preserve required copyright/license notices.

## Explicit non-goals

- Recreating or testing the user's deleted `C:\\p424-validation` folder,
  or retrieving the deleted survival-rate HWPX document.
- Adding unrelated signing or certificate systems to make routine
  document editing harder.
- Equating the presence of a new tool with successful production delivery.
- Replacing the functioning native HWPX engine before finding a concrete
  compatibility or correctness advantage.

## Release checkpoints

- **P425-A:** Version branch and canonical scope; tools are genuinely
  registered and user-facing workflows documented.
- **P425-B:** Rich HWPX read/search/edit/table/formatting API integrated
  with existing corpus fixtures, and routine workflows tested.
- **P425-C:** Compact tool discovery/description interface and practical
  Markdown/structured export.
- **P425-D:** Real authenticated MCP end-to-end HWPX ResourceLink handling,
  concurrency/revision edit and native compatibility demonstrations.

This is a development program, not a production-ready release declaration.
Keep P4.24's native PDF transport work as a separate technical lane.

## First P4.25-native implementation — tool discovery gateway

`discover_hwpx_workflows(task, limit=5)` is a newly registered MCP tool
that recommends actual existing document operations using Korean/English
keyword matching. It surfaces only tool names, purposes and required
inputs; it does not silently modify or read private document content.
It is a practical miniature implementation of the agent-facing discovery
pattern found in peer MCP servers. Discovery itself is not evidence
that a host successfully invoked a suggested tool.

The branch inherits nine real document workflows from P4.24 development
and adds discovery as the tenth first-class P4.25 MCP tool. Synthetic
regression tests were added for Korean table-edit lookup, rich report
lookup, and bounds. Run the tests against the current P4.25 branch;
none of these new tests has been executed on the owner's WSL yet.

## 2026-11-10 development cycle — Native formatting and Markdown interchange

New actual MCP registrations, in `hwpx_mcp/interfaces/p425_format_interchange.py`:

- `inspect_document_formatting(document_id, offset, limit, include_runs)`
  returns the P2.2-native paragraph/run formatting model with original
  paragraph locators, style properties and run-level font formatting.
- `preview_document_formatting(document_id, operations)` reuses the
  **same P2.2 native operation normalization** as the final commit path:
  checks target locator and permissible formatting fields without
  modifying the document. Returns current revision and target changes.
- `format_document_and_deliver(document_id, expected_revision, operations)`
  runs the existing P2.2 native formatting engine on owned revision bytes,
  preserves semantic text, commits one P3.0 CAS revision and returns the
  P3.33 MCP `resource_link` HWPX attachment.
- `export_document_markdown(document_id, include_table_cells,
  max_chars, include_tables)` reads native P2 paragraphs and optionally
  native P2.7 table grids; produces semantic Markdown directly in the
  MCP result. It escapes literal Markdown metacharacters, emits synthetic
  table column headings rather than inventing header rows, reports merged
  cell row/column spans that Markdown cannot preserve and marks tables
  as appended after paragraphs (not a layout-faithful reconstruction).
  It explicitly does not render pages, equations or embedded images.

The existing P4.25 agent discovery gateway now advertises the new
formatting/Markdown workflows and recognizes Korean keywords such as
`글꼴`, `서식`, `문단`, `마크다운`, `추출`.
The server's `probe_capabilities` listing and actual tool registration
are updated. The branch now exposes **14 P4.25 user workflow tools**
(9 inherited + 1 agent discover + 4 formatting/interchange).

Tests `tests/test_p425_format_interchange.py` exercise registered
tool contracts, run/paragraph inspection, formatting preview without
mutation, optimistic revision CAS, resource_link delivery, owner
isolation, Markdown escaping, table rows/columns, merged-cell caveats
and size bounds, using synthetic data only.

These new commits have been written to GitHub but **not executed in
the user's WSL environment or deployed to the hosted MCP**. They do
not require or recreate the user's deleted local Windows validation
folder. Next practical engineering work: real controlled HWPX fixture
test of P2.2 style operations, richer Markdown heading/list semantics,
and live ChatGPT attachment usability.

## 2026-11-10 — Markdown → native HWPX composition (P425-C)

A new first-class `create_from_markdown_and_deliver(markdown, filename)`
MCP workflow converts a deliberately bounded Markdown subset into
P3.38 `rich_plan` blocks and delegates the result to the **existing**
`create_rich_document_and_deliver` tool. It produces a genuinely
native HWPX using the P3.21 composer and current P3.33 attachment flow,
rather than a ZIP of Markdown text.

Supported input: `#`–`######` headings, paragraphs, bullet/numbered
list items and simple pipe tables with separator rows. Escaped pipe
characters inside cells remain literal text. Invalid table dimensions
are rejected before document creation. This is not a general CommonMark
implementation: inline emphasis, embedded media, HTML, code fences,
complex table spans and equation syntax are not interpreted as native
objects. Such content may remain literal paragraphs and should not be
described as losslessly converted.

The output-side Markdown exporter independently supports semantic
paragraphs plus appended HWPX table grids. Asymmetric features of the
two representations are declared rather than silently hidden.

The P4.25 development branch now contains **15 first-class workflows**
(nine inherited, discovery, four native formatting/Markdown reading
tools, and this new Markdown-to-HWPX authoring tool). Newly authored
synthetic tests verify Markdown blocks and table parser behavior;
new HEAD test execution in WSL remains outstanding.

## 2026-11-10 — Native report presets and one-call section authoring

New implementation `hwpx_mcp/interfaces/p425_report_presets.py` adds two
registered user-facing MCP tools:

- `list_report_presets()`: four grounded native P3.21 style presets
  with Korean labels and example report outlines. The display-oriented
  science-report alias maps to native `academic-report`, school-report
  maps to `school-report`, institutional-report to the native
  `institutional-report`, and polished-report to `polished-report`.
- `create_report_from_sections_and_deliver(title, sections, preset,
  subtitle, author, filename, page_numbers)`: takes plain section
  headings, paragraph arrays and nested `tables: [{caption, cells}]`
  and produces a native P3.38 rich plan. It delegates to the **same
  registered** P4.25 `create_rich_document_and_deliver` implementation
  and P3.21 HWPX composer, with no separate XML generation or renderer.
  The result is the pre-existing P3.33 resource_link attachment result.

Example MCP tool arguments:

```json
{
  "title": "산화환원 반응 실험 보고서",
  "preset": "science-report",
  "author": "연구팀",
  "filename": "oxidation-report.hwpx",
  "sections": [
    {
      "heading": "실험 방법",
      "paragraphs": [
        "반응 조건을 일정하게 유지하고 흡광도를 기록하였다."
      ]
    },
    {
      "heading": "실험 결과",
      "paragraphs": ["조건에 따른 흡광도 변화를 비교하였다."],
      "tables": [
        {
          "caption": "조건별 흡광도",
          "cells": [
            ["조건", "흡광도"],
            ["A", "0.31"],
            ["B", "0.27"]
          ]
        }
      ]
    }
  ]
}
```

This is an **example using invented illustrative values**, not a
reproduction of a user's private chemistry experiment. Page numbers,
native A4 geometry, spacing and fonts are delegated to pre-existing
P3.21 presets. To keep API calls predictable, invalid headings,
excessively long paragraphs, ragged cell grids and more than 240
native blocks fail before creation. The template list is deep-copied so
callers cannot change global preset definitions.

The existing `discover_hwpx_workflows` gateway now recognizes Korean
report terms and exposes both new tools. The real `server.py` registers
both after the underlying rich authoring callback.

There are now **17 first-class user-facing P4.25 MCP workflows**
(9 inherited P4.24, 1 tool discovery, 4 native formatting/Markdown
interchange, 1 Markdown→HWPX authoring, 2 report preset tools).
`tests/test_p425_report_presets.py` provides synthetic plan,
table/section validation, native callback delegation and mutation
isolation tests; latest-HEAD execution is pending. No local Windows
validation directory or deleted private source is used.

### Native equation blocks in P4.25 science reports

The same `create_report_from_sections_and_deliver` tool now accepts
`sections[].equations`, each either a LaTeX string or
`{"latex": "V=IR", "caption": "옴의 법칙"}`. These become P3.21
`equation` blocks and are converted by the existing native
`latex_to_eqedit` authoring path, not raster images or copied
plaintext. The existing native engine governs EqEdit compatibility
and geometry; the P4.25 API refuses missing/empty LaTeX and malformed
captions before initiating document composition.

Example section:

```json
{
  "heading": "이론",
  "paragraphs": ["측정값에 옴의 법칙을 적용하였다."],
  "equations": [
    {"latex": "V=IR", "caption": "옴의 법칙"},
    "P=VI"
  ]
}
```

This adds a real scientific-report user workflow enhancement without
introducing another MCP tool or signing layer. Tests were committed,
but not observed passing at this latest HEAD.

## 2026-11-10 — Ordered scientific reports, preview, and native CI acceptance

A real end-user limitation was fixed: the original report frontend
grouped every section's paragraphs first, equations next, and tables last,
silently losing the user's intended narrative order. P4.25 now accepts
an optional **ordered** `sections[].content` array and emits blocks in
exact input order. Each item can be a native paragraph, heading, numbered
or bullet list item, equation, table, or page break. Mixing ordered
`content` with the older `paragraphs`, `equations` or `tables`
fields in the same section is rejected explicitly; the older simple
interface still works unchanged.

For example:

```json
{
  "title": "회로 특성 분석",
  "preset": "science-report",
  "table_of_contents": true,
  "page_numbers": true,
  "sections": [{
    "heading": "결과 및 논의",
    "content": [
      {"type": "paragraph", "text": "전압과 전류를 측정하였다."},
      {"type": "equation", "latex": "V=IR", "caption": "옴의 법칙"},
      {"type": "paragraph", "text": "이론과 측정값을 비교하였다."},
      {"type": "table", "caption": "측정 결과",
       "first_row_header": true,
       "cells": [["전압 (V)", "전류 (A)"], ["3.0", "0.15"]]},
      {"type": "paragraph", "text": "측정 오차를 해석하였다."}
    ]
  }]
}
```

The new `preview_report_plan` tool compiles this request using the real
P3.38 plan compiler and returns block counts, section setup count, plan
SHA and TOC/page-number flags, without creating a document. The
`create_report_from_sections_and_deliver` tool sends the exact
same native block plan to the shared P3.38/P3.21 composer. Explicit
`table_of_contents=true` uses the existing structured-publishing
native TOC operation; `first_row_header=true` uses the existing
native table header-finishing path. Neither is a fake printed heading.

A dedicated **P4.25 CI workflow** was added:
`.github/workflows/p425-ci.yml` installs the actual native HWPX/MCP
dependencies, compiles P4.25 modules and runs focused tests on PR #24.
The first run exposed real API incompatibilities: assignments to
`CallToolResult.structuredContent` after instantiation failed with
Pydantic, some synthetic delivery receipts omitted their required
`download_expires_at` value, and Markdown pipe escaping was doubled.
These were repaired in production code and test fixtures; MCP file
receipt metadata is now supplied to `handoff()` **at construction
time** and accessed in tests through the actual Python field
`structured_content` (wire alias: `structuredContent`).

At GitHub HEAD `7d77b97dc4b36bd7fd55e734fffb64fcdc609ad1`,
a real **49-test P4.25 CI run passed**, including two synthetic
end-to-end tests that wrote actual native HWPX in temporary directories
and reopened them to inspect table and equation objects and native
TOC authoring. The subsequent P4.25 workflow discovery/capability changes were
then checked independently at GitHub commit
`265f1b5dc3e78dc8081ff27c63743b728390b383`: the dedicated
P4.25 Actions run `42789301612` completed **SUCCESS**, with
`Ran 50 tests ... OK`. This includes the additional tool-discovery
test as well as the native HWPX integration tests. Later
documentation-only commits did not require a new execution.
No deleted user HWPX or `C:\\p424-validation` path was used.

P4.25 currently exposes **18** user-facing MCP tools (nine inherited,
one discovery, four formatting and Markdown-read tools, one
Markdown-to-native-HWPX author, and three report-preset tools).

## 2026-11-10 — Native figures, source footnotes and caption numbering

This cycle implemented native scientific-report media and source annotation
rather than introducing an unrelated renderer or another security gate.

- `create_report_from_sections_and_deliver` accepts `sections[].content`
  `{"type":"figure","content_base64":"...","image_format":"png",
  "width":4000,"height":3000,"caption":"측정 그래프"}` or a legacy
  `sections[].figures` list. PNG/JPEG data, bounded byte size and
  native dimensions are checked before delegating to the existing
  P3.21 native HWPX picture composer. These are editable/movable native
  picture objects rather than embedded screenshots of a whole page.
  `figure`, `picture`, `image` resolve to the same P3.21 `picture`
  block.
- `list_document_figures(document_id, offset, limit)` now exposes
  existing P2.9 picture locators, section/paragraph position, image
  geometry, placement and media references for an owned revision,
  without returning raw binary media. Real `server.py` MCP registration
  and Korean/English `discover_hwpx_workflows` entries are updated.
- Ordered paragraphs accept `footnote` text, e.g.
  `{"type":"paragraph","text":"선행연구 결과","footnote":"출처 A"}`.
  A unique paragraph block ID becomes a P3.20 `add_footnote`
  native annotation with a `$block:` reference. No fake textual
  superscripts are used.
- `number_captions=true` in native report creation and preview
  numbers figure, table and equation captions in block order,
  independently per object kind. An existing explicit numbered caption
  is left unchanged. The default is false, preserving user text.

A complete ordered fragment:

```json
{
  "title": "전기 회로 실험",
  "preset": "science-report",
  "number_captions": true,
  "sections": [{
    "heading": "측정 및 분석",
    "content": [
      {"type": "paragraph", "text": "장치를 관찰하였다.",
       "footnote": "합성 실험 조건에 관한 설명"},
      {"type": "figure", "image_format": "png",
       "content_base64": "<base64 PNG bytes>",
       "width": 4000, "height": 3000, "caption": "실험 배치"},
      {"type": "equation", "latex": "V=IR", "caption": "옴의 법칙"},
      {"type": "table", "cells": [["전압 (V)", "전류 (A)"], ["3.0", "0.15"]],
       "caption": "측정값"}
    ]
  }]
}
```

The image Base64 string above is an API placeholder, not valid image
data. The API takes the actual encoded bytes, never a remote URL or
a path from a deleted local file.

### Evidence

- The first figure CI attempt exposed a malformed base64 synthetic
  fixture; it was corrected with a valid generated PNG.
- Native HWPX creation/reopening with a real P3.21 picture, equation,
  and table succeeded in dedicated P4.25 CI run `42790278322`
  (**53 tests passed**).
- A subsequent run `42790466731` completed successfully with
  **54 tests**, including the new figure-listing MCP tool.
- Native P3.20 footnote roundtrip was executed in CI run
  `42790786595`: **57 tests passed**.
- At tested commit `f459f4bb8b7e9ba1ee16676e7972172181b29b85`,
  P4.25 GitHub Actions run `42791151300` completed **SUCCESS**,
  with **59 tests, 0 errors/failures**, explicitly including real
  native figure roundtrip, native footnote roundtrip, and caption
  numbering tests.
- This proves ZIP/XML-native authoring and reload correctness with
  synthetic fixtures, **not Windows Hancom PDF layout parity** or a
  verified ChatGPT host download.

The development branch now has **19 first-class MCP user workflow
tools** (18 previously counted plus `list_document_figures`). No
main merge, public deployment, use of the removed local validation
folder, or retrieval of the deleted private survival-rate document.
