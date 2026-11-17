# P4.27 — Lossless Structured Editing & Native Preservation
**Nested Tables, Merged-Cell Semantics, Formatting Stability & Transactional HWPX Editing**

**Opened:** 2026-11-11
**Parent:** P4.26 — Document Experience & Visual Fidelity: Professional Layout, Native Rendering and Seamless File Delivery
**Exact parent commit:** `c478bdf0c6a9832b4b21bc536900c094237a8040`
**Base branch:** `development/p426-document-experience-visual-fidelity-20261111`
**Development branch:** `development/p427-lossless-structured-editing-20261111`
**Integration PR:** [#26](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/26) targets the retained P4.25 branch, **including** inherited P4.26 commits; the Git history remains based on the exact P4.26 verified SHA. P4.26 [PR #25](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/25) was closed without merge as superseded by the integrated successor.
**Status:** Research and implementation active; not deployed, not merged.

## Intent and lineage

P4.26 established a scientific-report authoring path: real native editable equations,
tables and images, renderer-informed caption spacing and TOC refresh, portable equation
diagnostics and a byte-exact signed ResourceLink delivery test. It also repaired
data integrity and native table input typing. P4.26 ends as a *verified development
research stage*, **not** as a production release or Windows Hancom parity
certification. Its tested parent commit has 61 inherited P4.25 + 98 P4.26
native regressions PASS, the pinned independent rhwp renderer PASS and
product/Docker CI PASS.

P4.27 directly inherits those bytes and gates. **No rewrite and no fake clean-room
restart.** The next question is whether an AI agent can safely edit an already
formatted HWPX, including merged cells and nested tables, while proving unrelated
content and formatting unchanged.

## R1 — Nested/merged editing acceptance contract

- Use authentic self-contained synthetic HWPX documents; do not access the
  owner's deleted validation directory or old private documents.
- Preserve existing table/paragraph/equation/picture writer and reader engines.
  Prefer a fail-closed contract around their native operations over a parallel
  XML editor or an invented renderer.
- Fixture variations: ordinary table; a merged anchor with covered grid slots;
  an inner table embedded in a cell when the installed native library supports
  one; adjacent unrelated table with distinctive formatting and paragraph text.
- Initial admitted edits: update one **known anchor** cell text,
  repeat-header/row metadata; preserve target merged geometry and
  unrelated table formatting, text, captions and section layout.
- Guard non-anchor covered coordinates, missing/ambiguous locators, stale
  revisions, edit batches with conflicting target identities and changes outside
  the declared edit footprint. Prefer explicit unsupported status for unsafe
  nested-table actions rather than a false success.
- After every edit reopen the generated native HWPX; compare pre/post
  table structure, per-cell spans/formatting, paragraph text and artifact hash.
  Invalid operations must not change the source file's SHA-256.
- Independent SVG/Windows Hancom rendering are separate evidence classes;
  no claim of pixel parity follows from OWPML reopening.

## R1 acceptance gates

1. P4.26 inherited 159 native tests still pass.
2. New native saved-file merged/complex editing regression passes, including
   exact unrelated-object invariants and failure injection.
3. Actual rhwp synthetic render still succeeds; no duplicated caption or
   clipped table text in the baseline showcase.
4. Docker and product integration pass at the **exact latest code commit**.
5. PR/Notion/GitHub records preserve the P4.26→P4.27 parent SHA and
   clearly distinguish green code CI from live connected MCP (last probed P4.18).
6. No automated bot commit authors or deployment/merge without release gate.

## Future R2–R4 research backlog

- R2: nested-table traversal and deeply scoped cell locator identity;
  test whether the library can round-trip genuine nested containers.
- R3: edited-object semantic delta with unaffected object proofs and stable
  cross-reference/bookmark handling.
- R4: realistic multi-page external-document benchmark: edit success,
  preservation failures, visual drift and host-side downloadable artifact.

No code development claim is made for R2–R4 until corresponding artifacts and
CI evidence exist.


## R1 implementation and evolving acceptance evidence

- Replaced P3.23's `document.tables.all` indexing with the same
  `_collect_document_tables(document)` traversal used by the underlying
  P2.7/P2.8 table map. This aligns table locators and mutation targets
  when table nesting changes the traversal order; it does not yet establish
  actual nested-in-cell end-to-end compatibility.
- Added `tests/test_p427_merged_table_preservation.py`: generate a real
  HWPX containing a merged anchor and an unrelated second table; change
  a first-table header, reopen, compare merged spans/content and all
  unrelated table-cell data/geometry/format flags; fail-closed test
  fabricated cell identity and stale revisions with source bytes identical.
- Found and repaired stale `hp:tc@header` flags when a repeat-header
  designation moves from one row to another. The change now clears
  non-designated row header flags and a new test verifies 0→1→disabled
  transitions through saved-file reopening.
- Added `.github/workflows/p427-ci.yml`, with exact-head source checks,
  inherited P4.25/P4.26 test suites, P4.27 regression tests and synthetic
  inherited report creation.
- First successful new P4.27 workflow on commit `56656f86`,
  [run #42974374273](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42974374273):
  **61 inherited P4.25 + 98 P4.26 + 3 P4.27 = 162 passing tests**.
  New header-switching test and corresponding code were added afterward
  on `6a3a28f`; consult exact-head CI before claiming they passed.

**Source-of-truth boundary:** The PR's integration target (P4.25)
is different from its direct source ancestry (verified P4.26). This
is intentional: the P4.26 PR is archived without merge; the successor
carries both P4.26 and P4.27 implementation for a future controlled
merge/release instead of silently dropping predecessor functionality.


## R2 — Genuine nested-table-in-cell editing acceptance (2026-11-11)

Unlike the R1 fixture with two adjacent tables, R2 builds a **genuine native
nested container**. It first generates an ordinary HWPX with two tables by
`python-hwpx`, then moves the existing child `hp:tbl` element into an
outer `hp:tc/hp:subList/hp:p/hp:run` inside the same section package,
without synthesizing new binary resources. XML ancestry is inspected
directly: exactly one `hp:tbl` must have an `hp:tc` ancestor.
This structural assertion prevents a misleading pass on adjacent tables.

New acceptance fixture: `tests/test_p427_nested_table_in_cell.py`.

### Tested editing matrix

| Edit | Expected admission | Postcondition |
| --- | --- | --- |
| Read outer and inner table locators | Admit | Two distinct table indices; exactly one nested child |
| Change inner table page-break metadata | Admit | Child has new saved property; parent content and nesting preserved |
| Edit a text cell inside the nested child | Admit | Target child value updated; all other child and parent values unchanged |
| Edit a **non-host** peer cell in the parent | Admit | Peer value updated; all child cell values/geometry remain identical |
| Replace whole parent **host cell** text | Refuse | `NESTED_TABLE_HOST_CELL_TEXT_EDIT_DEFERRED`; original HWPX SHA-256 unchanged |

The guard is implemented in the established P2.7 native `set_cell_text`
path rather than through a redundant XML writer. It specifically checks
whether the target native cell contains a descendant `hp:tbl`. A host-cell
replacement could destroy that child; until a lossless region-preserving
algorithm is validated, it is *not* admitted. Normal neighboring cell edits
remain available. No automatic flattening of nested structures is authorized.

### Executed evidence

- [R2 initial native CI #42975392819](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42975392819) **SUCCESS**, 61 inherited P4.25 + 98 P4.26 + 6 P4.27 = **165/165 tests** (genuine nested lookup and inner metadata edit).
- [R2 updated native CI #42975783376](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42975783376) **SUCCESS**, 61 + 98 + 8 = **167/167 tests** (adds nested child text edit and host-cell fail-closed SHA-256 protection).
- [R2 peer-cell native CI #42976028908](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42976028908) **SUCCESS**, 61 + 98 + 9 = **168/168 tests** (adds parent peer edit while preserving all child cell data/geometry). Tested code commit: `17b7a52e81b1ac10a56e380ee23929a4ed64d125`.
- Existing independent real [rhwp render #42976028824](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42976028824) **SUCCESS** and [P4.26 native CI #42976028894](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42976028894) **SUCCESS** on this code commit.

**Evidence boundary:** R2 verifies a synthetic HWPX package, native
library reopening and semantic/geometry preservation for the specified
edit scope. It does **not** prove arbitrary third-party nested-table import,
all edit operations, strict unchanged ZIP bytes for successful edits,
native Hancom pixel parity or production MCP deployment. The product/Docker
pipeline is independently evaluated; see exact commit results before release.


## R3 — Two-layer native edit preservation with unrelated paragraph guard (2026-11-11)

P3.42 already exposes a bounded package-part mutation footprint certificate.
P4.27 **reuses** it and adds a stricter *within-part* semantic comparison
before the original HWPX can be replaced. A package-part certificate by itself
cannot detect accidental edits to a neighboring table or paragraph in the
same `Contents/section*.xml` file.

The new `hwpx_mcp/custody/p427_structured_edit_preservation.py` implements
`apply_bounded_table_edit_with_preservation_atomic`. It stages a temporary
native HWPX, delegates to the existing P3.23 table editor, then:

1. Computes the **intended** target table/cell delta before executing
   the edit. R3 admits a single `set_cell_text` or `set_table_page_break`
   operation only; edits with no observed effect are refused.
2. Reopens the native document, compares the complete exposed table
   maps for all tables, and rejects unapproved table and cell changes.
3. Compares unrelated section-body paragraphs **not containing table
   controls**, including their text, paragraph attributes and direct-run
   styling identifiers. Table-host paragraphs are excluded because a
   valid nested-cell edit can change their descendant text.
4. Invokes P3.42's `build_mutation_footprint` using exact, independently
   determined expected package parts (the source section and header) and
   requires `TARGETED_PARTS_ONLY`.
5. Atomically replaces the original only after all gates pass. Failure
   leaves source bytes unchanged and deletes the candidate. A validator
   hook permits controlled post-edit fault injection in tests.

Regression: `tests/test_p427_structured_edit_preservation.py`.
Injected failures include undeclared changes to another table, an extra
ZIP member, unrelated body-paragraph corruption, no-op edits and rejected
stale/unsupported operations. Positive cases edit a genuine nested child
cell or its native `pageBreak` property.

### Exact executed evidence

On code SHA `a05589d5f52b75c8a9f7aa17344e1a9a6af55d93`:

- [P4.27 native acceptance #42992174297](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42992174297):
  **SUCCESS**, 61 inherited P4.25 + 98 P4.26 + 16 P4.27 = **175/175 tests**.
- [P4.26 native regression #42992174256](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42992174256):
  **SUCCESS**.
- [Independent real rhwp renderer #42992174225](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42992174225):
  **SUCCESS**.
- [Product/Docker integration #42992174252](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42992174252):
  **SUCCESS**.

**Boundary:** This is a separate opt-in R3 preservation transaction, not
yet the default exposed ChatGPT MCP tool path. It compares the native
table API's exposed semantic properties and ordinary body paragraphs,
not every possible internal OWPML attribute, hidden style reference,
or rendered page pixel. Table-anchor paragraphs are excluded from
the paragraph gate and remain partly protected by table semantics.
Native Windows Hancom fidelity and live server deployment are separate
release gates. Do not describe this as arbitrary-document losslessness.


## R4 — Owner-gated MCP preservation transaction (2026-11-11)

P4.27 R3 was a callable Python preservation transaction, not yet an MCP
tool. R4 exposes **`apply_preserved_table_edit(document_id,
expected_revision, operation, lease_token="")`** as a new MCP tool in
`server_p2.py`; the existing `apply_advanced_table_edits` contract
remains unchanged. This is a **bounded alternative**, not an unsafe
global replacement or a production release.

The tool's implementation reuses `_owned_document` and the existing
OAuth principal/owner gate, revision readback and durable-store metadata
commit path, as well as `core.validate_hwpx_package` on the staged file.
R3 now retains the package validator's receipt, allowing the final MCP
response to carry validation, package-part footprint, table/cell semantic
preservation, unrelated-body-paragraph checks and the committed SHA-256.
Only one `set_cell_text` or `set_table_page_break` is admitted. Lease
tokens are handled through the existing revision store compatibility
mechanism; this does **not** establish multi-client serializability
independently of the durable revision/CAS store.

### CI lessons and corrective actions

1. First R4 test attempt [native CI #42993631155](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42993631155)
   failed importing `server_p2` because ordinary native CI has no
   `P12_AUTH_DATABASE_URL`. Do not interpret this as a successful server
   acceptance or turn off authentication to avoid the failure.
2. Splitting native and PostgreSQL tests exposed another authentic
   dependency: the host imports P3.45's **compiled TypeScript runtime**,
   which the Python-only runner had not built. The PostgreSQL R4 job
   initially failed for this reason. This was resolved by running the
   authenticated suite in the **exact production Docker image** with
   compiled TS/Rust components and a CI-only PostgreSQL service, instead
   of inventing a stub runtime.
3. The owner test now exercises the existing `_require_owner` check
   with a foreign caller identity, not just a mocked function exception.
   Other tests cover successful owner-scoped edit + metadata revision
   bump, stale revision, invalid operation, and package validation
   failure with the original file unchanged.

### Verified acceptance

At code SHA `4491c8b2f1e64a88d101e5cdc5e3b1cb5d7e69ee`:

- [P4.27 dual-mode acceptance #42994792940](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42994792940)
  **SUCCESS**. Native: inherited P4.25 61 + P4.26 98 +
  P4.27 21 discovered with **5 server-only skips** (16 executed
  native P4.27 tests). Production-image authenticated job:
  **5/5 real in-process server tests PASS**, with live PostgreSQL
  dependency, the actual compiled product runtime and validated HWPX.
  Explicitly do not count the native skips as passes.
- [P4.26 native #42994793020](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42994793020)
  **SUCCESS**.
- [Real rhwp #42994792898](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42994792898)
  **SUCCESS**.
- [Product / Docker #42994792977](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/42994792977)
  **SUCCESS**.

Test module: `tests/test_p427_server_preserved_edit.py`; exact
production runtime check: `.github/workflows/p427-ci.yml`. The
existing MCP client tool inventory in `tests/test_client.py` now
requires `apply_preserved_table_edit` but an actual network OAuth
client round trip has **not** been certified.

**Release boundaries:** No merge to main or deployment of P4.27,
and no claim of Windows Hancom-native visual fidelity. The exact
preservation assertion covers declared table data, unrelated ordinary
body paragraphs and package parts, **not** arbitrary hidden content,
global semantic invariants or visual page equivalence. The new
server entrypoint follows the existing durable commit design; full
cross-resource crash atomicity is a separate failure-injection gate.

## Table-anchor paragraph preservation

The preservation transaction now compares top-level section paragraphs that
contain a table control as well. The comparison retains surrounding text, run
and paragraph attributes, other inline markup, and each table's position in
the paragraph. The native table map still checks the table contents. This
allows a nested-cell edit inside a mixed-content paragraph while rejecting
changes to text or run formatting beside its containing table.

The MCP preservation receipt includes `table_anchor_paragraphs_verified`.
An unexpected anchor change raises `R3_UNDECLARED_TABLE_ANCHOR_PARAGRAPH_DRIFT`
before the staged file replaces the original. The regression suite injects
both text and run-style changes and checks the original bytes and temporary
file cleanup.

### Body controls, nested anchors and page-break scope

- The transaction compares normalized XML for ordinary body paragraphs,
  including inline controls such as line breaks. The nested anchor check also
  compares the markup around tables hosted in cell paragraphs. A successful
  receipt reports `nested_table_anchor_paragraphs_verified`.
- The earlier page-break scope admitted only its target section. At that stage
  the cell-text operation still allowed changes to `Contents/header.xml`.
- Saved-file regressions cover malformed operation names, unexpected line
  breaks, nested anchor run style changes and shared header drift. A positive
  test replaces Korean text in a merged cell and checks its geometry and the
  adjacent table after reopening the file.


### Target section, unedited cells, and receipt binding

Both admitted operations now limit package payload changes to the target
section. The native text writer updates the target cell and marks its section
dirty. The regressions exercise Korean input and reject a shared-header rewrite
for either operation.

The transaction compares normalized XML for unedited native grid anchors,
including character style references and inline controls omitted by the table
map. Each containing cell retains the position of any nested table control.
Inner cells are checked independently through the native table traversal.
The receipt reports the count in `unrelated_cells_verified`.

When package validation supplies a SHA-256, it must match the staged bytes
identified by the footprint before replacement. The receipt uses that same
digest for `committed_sha256`. An injected mismatch leaves the source intact.
The edited cell still uses the native text writer's formatting behavior.

### Formatting and inline objects in the edited cell

A preserved cell-text edit compares the ordered native inline objects in the
target cell, including their run attributes. The native equation regression
replaces Korean explanatory text next to an equation and reads the original
EqEdit script back from the saved HWPX. Changes to the script or its run style
cause rollback. The MCP receipt reports `target_cell_inline_objects_verified`.

The original cell geometry, sublist attributes, first paragraph attributes,
and first run attributes are checked. The writer can invalidate layout caches
and set the dirty flag. Nonempty text in a squeezed cell may trigger the
native transition from SQUEEZE to BREAK. Text spacing controls such as tabs
remain part of the replacement text. When replacing the entire cell value,
formatting in discarded text-only runs is outside this comparison.

### Phrase corrections within a styled cell

Use `apply_preserved_table_edit` with one operation of this form:

```json
{
  "op": "replace_cell_phrase",
  "table": "<table locator>",
  "cell": "<cell locator>",
  "paragraph_index": 0,
  "old_text": "교정 전",
  "new_text": "교정 완료"
}
```

The paragraph index is zero-based within the cell. The nonempty old phrase
must occur exactly once in that paragraph and fit within a single plain text
node. An empty replacement deletes that phrase. The edit keeps each run and
inline object and invalidates only the selected paragraph's layout cache.
The transaction compares the full expected target cell XML with the reopened
candidate before replacing the source. Multiple matches, phrases spanning
nodes and mixed text controls in the selected paragraph are refused.
Cells within a nested table and cells that host a child table support scoped
phrase correction. For a host cell, phrase matching looks only at the
selected paragraph's own plain text nodes. The transaction compares the
whole candidate cell, including all embedded table XML, against the planned
signature. The enclosing paragraph position is checked as well. Whole-cell
replacement via `set_cell_text` remains blocked on host cells.

### Durable preserved edit and exact revision delivery

`apply_preserved_table_edit` reads the owner-checked active revision from
PostgreSQL, runs the preservation checks on a private candidate, and builds
metadata from that candidate. It commits the same bytes through the existing
revision CAS and lease checks. The candidate SHA-256 must match both the
package validation and preservation receipts before the commit.

`edit_preserved_table_and_deliver` accepts the same single operation and
returns the MCP ResourceLink for the revision it just committed, even if a
newer revision has already become current. If link preparation fails after
commit, the response contains the committed revision and
`RETRY_DELIVERY_ONLY`. Use `deliver_document(document_id, revision)` to renew
the download without applying the change again.

The Docker/PostgreSQL test exercises the MCP registration and invocation,
candidate conflicts at the same revision, lease checks, and the signed HTTP
download handler. Browser attachment display and Hancom open/resave are
separate acceptance checks.

### Preserved table batch delivery

`edit_preserved_table_batch_and_deliver(document_id, expected_revision,
operations, lease_token="", link_ttl_seconds=900)` accepts one to eight of
the existing `set_cell_text`, `replace_cell_phrase`, and `set_table_page_break`
operations. Supply the same table and cell locators as for a single edit.
Each cell and each table's page-break field can be a target once. This makes
the intent unambiguous if different operation types address the same cell.

Operations run in order on one private working copy. Each operation passes
the existing cell and section preservation checks against the preceding
private state. The final package validator sees the complete batch. The
aggregate footprint compares that candidate to the original revision and
restricts changed contents to the union of addressed sections. An operation
failure reports its zero-based index in `P427_BATCH_OPERATION_FAILED`;
the source stays intact and PostgreSQL receives no new revision.

A successful batch creates one revision and one revision-bound ResourceLink.
The response includes the aggregate footprint and each operation's
preservation receipt under `preserved_edit`. If link preparation fails,
request a new link for the committed revision via `deliver_document`.
Search `discover_hwpx_workflows` for “표 셀 여러 일괄 보존 다운로드” to
find the batch endpoint.

### Read-only preview and optional plan check

1. Call `preview_preserved_table_batch(document_id, expected_revision,
   operations)`. It executes the checked editor on temporary bytes and
   returns each target's before/after value, affected sections, the
   preservation grade, and a `plan_sha256`. Cell values in this result
   are capped at 240 characters and marked when truncated.
2. To apply the same plan, pass that digest as `expected_plan_sha256` to
   `edit_preserved_table_batch_and_deliver` with the same document,
   revision, and ordered operations. Changed input is rejected before editing.
   A new revision makes the preview stale. Existing callers may omit the
   digest and submit an edit directly.
3. The preview digest identifies the inputs, including the source HWPX digest,
   and is separate from the SHA-256 of the downloaded output. The apply call
   reruns validation and commits using the existing database CAS.

The preview is a structural before/after inspection. It creates no
document revision or download link. Page rendering is a separate workflow.

## Functional comparison against the last P4.26 commit

The baseline is [P4.26 R15, c478bdf](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/commit/c478bdf0c6a9832b4b21bc536900c094237a8040).
P4.26 already verified strict table input types, native report composition
and editable equations, table pagination, figure and caption layout, an
independent SVG renderer, and signed HWPX delivery. P4.27 builds on those paths.

| Area | Addition on the P4.27 branch |
| --- | --- |
| Native table corrections | Match table locators to nested table traversal, clear stale repeat-header flags when moving the header row, and reject whole-cell replacement on a host cell containing a nested table. |
| Targeted edit | Edit a cell, change table page-break mode, or replace a unique phrase within one plain text node, including in a cell hosting a nested table. |
| Preservation | Validate body paragraphs, table anchors, neighboring cells, target geometry, inline objects and run styles as applicable. Limit changed package bytes to addressed sections and keep shared header definitions intact. |
| Durable edit | Commit the exact validated private candidate using owner and revision checks, with the existing lease support. |
| Batch and delivery | Validate one to eight operations as one revision and return its signed ResourceLink. Recover a failed download by reissuing the link for the committed revision. |
| Preview | Compute before/after changes on a temporary copy and optionally bind apply to the ordered previewed plan. |

P4.27 CI exercises reproducible native HWPX edits, retained PostgreSQL
revisions and MCP tool invocation. Browser attachment behavior, deployed
staging service, and Windows Hancom opening and resave have their own checks.

## Preserve unbraced LaTeX script arguments

`python-hwpx` 6.6 groups adjacent letters and numerals as lexer tokens.
For LaTeX `p_iS_i(t)` that consumed `iS` as the first subscript and saved the
wrong equation. The shared converter makes the single-token argument explicit
before calling the native compiler. `p_iS_i(t)` and `p_{i}S_{i}(t)` now produce
the same EqEdit script. Explicit groups such as `x_{ij}`, named commands,
and quoted text retain their boundaries. A missing script argument is rejected.

Capability inspection, script preview, document composition, inline equation
lines, piecewise conditions and revision-bound equation edits use this path.
The regression reopens saved HWPX bytes after composition and replacement.
It also verifies byte-exact rollback when a later operation has a missing
script argument. Existing document bytes are changed only through requested
edits. The compiler still applies its supported-command and size limits to
the normalized source.

The Korean cases test verifies quoted EqEdit text. The WSL bridge test
verifies the engine and length fields in the mock receipt. These checks cover
script representation and receipt handling. Hancom glyph shaping and page
rendering require a fresh Windows capture.
