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
