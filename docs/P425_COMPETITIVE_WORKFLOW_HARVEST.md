# P4.25 — Peer HWPX MCP product workflow harvest (2026-11-10)

## Why this cycle changed

The hosted ChatGPT MCP already has a large internal P2/P3 document
engine, but its `server.py` previously exposed almost none of the
document editing operations: only create, ingest, inspect, export, delete,
and diagnostic/PDF utilities. That is a product API deficit, not a need
for another signing layer. The P4.25 change reuses the real existing
P3.37 atomic HWPX inline editing implementation and P3.0 durable revision
store, then exposes its functionality to an authenticated MCP caller.

## Public source research and design provenance

- [Dayoooun/hwpx-mcp](https://github.com/Dayoooun/hwpx-mcp),
  MIT: `batch_replace`, `search_text`, table-cell search,
  user-oriented document operations, atomic package replacement.
  Its docs distinguish HWPX XML editing from native Hancom PDF export.
- [treesoop/hwp-mcp](https://github.com/treesoop/hwp-mcp),
  MIT: template filling, agent-friendly one-call workflows and rhwp
  fallback engine; one-line setup.
- [deoksangcho/hwpx-mcp-server](https://github.com/deoksangcho/hwpx-mcp-server),
  MIT: stateless per-document actions, `plan_edit`, `preview_edit`,
  `apply_edit`, structured read/outline and batched replacements.
- [Topabaem05/hwpx-mcp](https://github.com/Topabaem05/hwpx-mcp):
  advertised discoverable tools through a search/describe gateway.
  License not yet confirmed here; only the interface idea is noted.
- [gridi-ai/hancom-mcp](https://github.com/gridi-ai/hancom-mcp),
  MIT: familiar open/edit/replace/save work process and styles.

**Source policy:** Interface and workflow ideas are adopted, but this
cycle did not copy upstream source text. The implementation calls the
repository's pre-existing `p337_product_workflow` functions. If code is
copied in a later phase, retain the upstream copyright, license and
NOTICE obligations and track the exact upstream commit.

## Added on P4.25 development branch

MCP tools registered on the real `server.py`, backed by owned immutable
revision bytes (no raw file path parameters):

1. `create_and_deliver_document(text, title, filename, request_id)`
   uses the existing generated HWPX and P3.33 attachment service in one
   request. Returns an MCP ResourceLink as well as structured metadata,
   rather than just a JSON URL. Repeating an identical request_id can
   reuse an earlier creation.
2. `read_document_structure(document_id, offset, limit, include_text)`
   returns ordered body/nested paragraphs with stable locators, section and
   container coordinates. Paragraph offsets are not native page numbers.
3. `find_document_text(document_id, query, max_matches, case_sensitive)`
   returns body/table text matches, locators, bounded context.
4. `preview_template_fill(document_id, values, require_each, require_unique)`
   returns exact-match counts, current revision and plan hash, no mutation.
5. `fill_template_and_deliver(document_id, values, expected_revision, ...)`
   reuses P3.37 ZIP/XML atomic inline edit and source validation, then
   commits a single new owner-scoped durable revision using optimistic
   concurrency and returns the existing P3.33 MCP ResourceLink attachment
   plus structured metadata.
6. `replace_text_and_deliver(document_id, replacements, expected_revision)`
   performs multiple literal replacements in the same durable commit
   through that same editor rather than reimplementing XML manipulation.

All seven are registered at server import. `probe_capabilities` now
advertises them. The new test module exercises the tool registration,
preview without writes, CAS errors, owned-document boundary, output link,
structured read and body/table search with synthetic byte fixtures.

## Important scope

This is a *genuine MCP API integration* in the development branch, but
not a deployed public endpoint until the branch is merged and the server
deployed. The tests for this new commit must run and the real HWPX
editor must be exercised with controlled test fixtures. Native PDF
generation/remote Windows transport is not claimed.

Next harvest: a richer `create_and_deliver_document` entrypoint,
table creation/style catalog exposed as MCP tools, robust HWPX→Markdown
export, and client-visible file transfer. Prefer existing P3.38/P3.44
engines over reimplementing ZIP/XML operations.

User instruction: Do not recreate `C:\p424-validation` or the deleted
survival-rate HWPX. There is no need for that local test to develop P4.25.

## 2026-11-10 additional product integration

The actual one-call `create_and_deliver_document` now returns a
`CallToolResult` containing an MCP `resource_link`, human-readable
attachment message and the structured delivery receipt. Template fill
and batch replacement use this same attachment handoff, not a bare JSON
URL. The private HWPX payload is still delivered through existing
revision-scoped URL semantics; ChatGPT host attachment rendering still
requires a live host test. Tests assert structured receipts and link
handoff using fake P3.0 revision state and synthetic files.

## 2026-11-10 rich document authoring now exposed

`create_rich_document_and_deliver(rich_plan, filename)` is now a
registered MCP tool that compiles a P3.38 multi-section plan (headings,
tables, equations, images, page setup), executes the existing P3.21
native composer, validates the generated HWPX, commits the owned
revision and returns the existing P3.33 `resource_link` attachment.
It does **not** claim a native PDF, and it does not touch the removed
`C:\\p424-validation` folder. A synthetic mock-composer integration
test covers server tool registration and delivery handoff; actual
multi-section rendering on Windows still requires separate evidence.

## 2026-11-10 — Native HWPX tables moved into production-facing MCP surface

Two further first-class tools now reuse the existing P2.7 table engine:

- `list_document_tables(document_id, offset=0, limit=10)` extracts
  table grids, cells including merged anchors, captions, dimensions and
  precise table/cell locators from the authenticated retained HWPX bytes.
- `edit_table_and_deliver(document_id, expected_revision, operations)`
  applies existing native table-cell text edits, merge/split, shading,
  borders and structural operations through `apply_table_edits_atomic`,
  checks the requested revision, commits one P3.0 durable CAS revision
  and emits a real MCP `resource_link` HWPX attachment. The operation
  JSON is the existing P2.7 locator schema (table/cell locators obtained
  by `list_document_tables`), not a separately invented API.

This makes **nine** directly usable new P4.25 MCP tools in this cycle,
all registered on server import (rather than being isolated internal
research helpers). Synthetic contract tests also cover cell grid read
and editing one durable revision. The genuine HWPX test with complex
merged tables remains to be executed on controlled fixtures; the
removed `C:\\p424-validation` and deleted survival-rate file will
not be recreated or used.
