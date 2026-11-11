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
