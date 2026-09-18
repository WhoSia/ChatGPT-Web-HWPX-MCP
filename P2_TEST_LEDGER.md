# P2 Test Ledger

Formal stage:

**ChatGPT Web HWPX MCP P2 — Structured Document Introspection, Stable Text/Object Addressing, Revision-Safe Edit Transactions & Semantic-Diff Validation**

## Canonical implementation

Server version: `0.3.0-p2`

P2 extends the closed P1.2 OAuth/custody boundary without replacing it:

```text
OAuth-authenticated opaque document_id
→ structured HWPX section/paragraph map
→ paragraph locator
→ exact revision precondition
→ candidate-package edit
→ package validation before commit
→ atomic replacement
→ revision increment
→ semantic/structure receipts
```

P2 does not yet claim structural editing, formatting, tables, images, equations, or native Hancom rendering fidelity.

## Address contract

Paragraph locators have the form `p_<hash>`.

- If a paragraph exposes an intrinsic HWPX `id`, the locator is derived from section identity plus that intrinsic id and is classified as `intrinsic-id`.
- If no intrinsic id is available, the locator falls back to section identity plus paragraph ordinal and is classified as `revision-bound-ordinal`.
- `intrinsic-id` locators are expected to survive text-only edits while the underlying intrinsic id survives.
- `revision-bound-ordinal` locators are not claimed to be globally stable; callers must reacquire a document map after structural edits in later phases.

The map also seals:

- whole-document semantic SHA-256 over paragraph text;
- structure SHA-256 over paragraph structural identity/order;
- per-paragraph text SHA-256;
- section/paragraph indices and locator metadata.

## Revision-safe transaction contract

`apply_edits` currently admits only `replace_paragraph_text` operations.

A transaction requires the exact current revision. A stale `expected_revision` is rejected before byte mutation.

For an admitted transaction:

1. resolve every locator against the same pre-edit map;
2. reject unsupported operations, unknown locators, duplicate targets, or invalid payloads before commit;
3. materialize a candidate HWPX in a sibling temporary file;
4. apply all requested text changes to the candidate;
5. rebuild the semantic/structure map from the candidate;
6. run the full HWPX package validator against the candidate;
7. only after candidate validation succeeds, atomically replace the original package;
8. increment the document revision and update package/semantic/structure receipts.

Therefore a stale revision, invalid operation set, unknown locator, or candidate-validator failure leaves the original document bytes unchanged.

## P2 MCP surface

P2 adds:

- `get_document_map(document_id)`
- `get_text(document_id, locator="")`
- `apply_edits(document_id, expected_revision, operations)`
- `compare_document(document_id, semantic_sha256="", structure_sha256="")`
- `p2_capabilities()`

Existing P1.2 tools remain available. New and ingested P2 documents begin at revision `1`; legacy ephemeral metadata is lazily promoted to revision `1` on first P2 access.

## Unit and OAuth-native CI receipt

Canonical confirmatory workflow:

- workflow: `P2 Structured HWPX edit lifecycle CI`
- run: `34753183796`
- commit under test: `aaabacb9f3f761904e70bbcd0714e2991ebc90ca`
- conclusion: **SUCCESS**

Confirmed boundaries:

| Boundary | Verdict |
|---|---|
| Python compilation | PASS |
| P1.2 ingress regression suite | PASS |
| durable OAuth regression suite | PASS |
| structured document-map generation | PASS |
| unique paragraph locator generation | PASS |
| semantic and structure digests | PASS |
| text-only locator continuity | PASS |
| text-only structure-digest invariance | PASS |
| stale-revision rejection | PASS |
| stale-revision byte non-mutation | PASS |
| invalid multi-operation full abort | PASS |
| candidate-validator failure rollback | PASS |
| OAuth-protected P2 server start | PASS |
| unauthenticated MCP rejection | PASS |
| P2 tool discovery | PASS |
| secret-free tool schemas | PASS |
| authenticated create at revision 1 | PASS |
| document-map retrieval | PASS |
| locator-targeted atomic edit | PASS |
| revision 1 → 2 transition | PASS |
| targeted post-edit text read | PASS |
| semantic digest change | PASS |
| structure digest preservation | PASS |
| compare-document semantic mismatch detection | PASS |
| compare-document structure-match detection | PASS |
| edited artifact signed export/download SHA receipt | PASS |
| edited artifact re-ingress and validation | PASS |
| cleanup/delete | PASS |

## Render/public deployment receipt

Canonical P2 deployment:

- service: `chatgpt-web-hwpx-mcp-p0`
- public base: `https://chatgpt-web-hwpx-mcp-p0.onrender.com`
- deploy: `dep-daj8470ae00c738uql5g`
- commit: `a64ae33a6f3815fdf36093415afac8fcf0c2873b`
- status: **live**
- finished: `2026-09-13T11:00:22.127659Z`

The first P2 public-boundary workflow run (`34753222221`) failed before receiving an HTTP response: GitHub-hosted curl reported `Failure when receiving data from the peer` throughout its polling window. Render application logs independently showed the old and new instances continuously serving `/health` with HTTP 200, the new P2 instance starting normally, no application crash/restart loop, and the deployment reaching `live`.

The verification transport was then hardened with HTTP/1.1, retry-all-errors, and explicit timeouts. No server semantics were changed.

Canonical public-boundary retry:

- workflow: `P2 Render public boundary verification`
- run: `34753533084`
- commit: `8dc7e2a026e634a507fb46c149ed9c84708842f4`
- conclusion: **SUCCESS**

Confirmed public boundaries:

| Public boundary | Verdict |
|---|---|
| public P2 health/version `0.3.0-p2` | PASS |
| durable OAuth store reachable | PASS |
| OAuth protected-resource metadata | PASS |
| authorization-server metadata | PASS |
| `offline_access` advertised | PASS |
| unauthenticated `/mcp` blocked before tool execution | PASS — HTTP 401 |

The initial public failure is therefore classified as a transient GitHub-runner ↔ Render edge transport failure, not a P2 application failure.

## P2.1–P2.3 extension receipt

Current extended server version: `0.3.3-p2.3`.

P2.1 added paragraph insertion/deletion/same-container reordering with locator rebinding. P2.2 added paragraph/run formatting introspection, formatting-only atomic transactions, resolved property summaries, and `formatting_sha256`. P2.3 adds direct-text range addressing and the following admitted operations:

- `set_range_format` — `[start,end)` selection over paragraph `direct_text`, splitting only plain/split-safe runs;
- `copy_run_format` — exact same-document `charPrIDRef` reuse to a run set or character range;
- `copy_paragraph_format` — exact same-document `paraPrIDRef` reuse, with optional named `styleIDRef` reuse;
- nested paragraph-property mutation by minting/reusing a `paraPr` from the target's current property and rebinding the addressed paragraph;
- `normalize_formatting` — merge adjacent split-safe runs with identical run attributes after other formatting mutations.

Range splitting is fail-closed for field/control/mixed-inline runs. Every formatting transaction still requires exact revision, validates the candidate package before commit, and rejects the candidate if semantic or paragraph-structure digests change.

### Canonical P2.3 lifecycle receipt

- workflow: `P2.3 Rich-text HWPX lifecycle CI`
- run: `35305810290`
- commit: `4d03ac80b522f1fe2fd9e1ff39bcf550ac85b9ab`
- conclusion: **SUCCESS**

Confirmed P2.3 boundaries include Python compilation, legacy ingress/auth regressions, range-run splitting, exact style-ref reuse, nested paragraph formatting, normalization, OAuth-native map → text edit → range formatting → targeted read → compare → export → re-ingest lifecycle, and cleanup.

### Canonical P2.3 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-dambik61egvs738rucjg`
- commit: `4d03ac80b522f1fe2fd9e1ff39bcf550ac85b9ab`
- deploy status: **live**
- public workflow: `P2.3 Render public boundary verification`
- run: `35305810231`
- conclusion: **SUCCESS**

The public receipt confirms P2.3 health/version availability, durable OAuth metadata, `offline_access`, and unauthenticated MCP rejection.

## P2.4 control-aware inline extension receipt

Current extended server version: `0.3.4-p2.4`.

P2.4 adds a direct inline atom map and a new revision-guarded `apply_inline_edits` lane. The admitted mutation is `replace_inline_text` over `[start,end)` offsets in paragraph `inline_text`.

The inline map distinguishes:

- ordinary text spans with run, field-stack, and mixed-markup context;
- visible one-character special atoms: tab, lineBreak, nbSpace, fwSpace, soft hyphen;
- zero-width field begin/end, markup, control, bookmark/object boundaries;
- field spans such as HYPERLINK and DATE;
- `inline_text_sha256` and an offset-insensitive `inline_structure_sha256` over the preserved control/field/markup/special-atom skeleton.

P2.4 permits cross-run ordinary-text replacement when all selected spans share one field/markup context. Hyperlink display text and DATE/PATH cached text can therefore be edited without rewriting their wrappers. Requests that cross a field/control/markup boundary or consume a special atom fail before candidate commit. Candidate validation, paragraph-structure invariance, and inline-structure invariance are hard commit gates.

### Canonical P2.4 lifecycle receipt

- workflow: `P2.4 Control-aware inline HWPX lifecycle CI`
- run: `35306521565`
- commit: `663a0b0e0801f4e2caebbab635a5c3e2da3fdd18`
- conclusion: **SUCCESS**

Confirmed P2.4 boundaries include:

- plain cross-run replacement while preserving run topology;
- HYPERLINK display-text mutation with field wrapper preserved;
- single-run DATE cached-text mutation with field wrapper preserved;
- atomic rejection of selection crossing a field boundary;
- preservation of mixed `hp:t` markup;
- rejection of surgery through lineBreak/special atoms;
- OAuth-native `get_inline_map → apply_inline_edits → get_inline_map → compare_document` lifecycle;
- inline-structure match after cross-run text mutation;
- signed export, re-ingest, validation, and cleanup.

### Canonical P2.4 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-dambnq8u01pc73f31sn0`
- commit: `663a0b0e0801f4e2caebbab635a5c3e2da3fdd18`
- deploy status: **live**
- public workflow: `P2.4 Render public boundary verification`
- run: `35306521538`
- conclusion: **SUCCESS**

The public receipt confirms P2.4 health/version availability, durable OAuth metadata, `offline_access`, and unauthenticated MCP rejection.

## P2.5 field/control semantic mutation extension receipt

Current extended server version: `0.3.5-p2.5`.

P2.5 separates intentional control-structure mutation from P2.4's structure-preserving inline text lane. The new authenticated MCP tool is `apply_control_edits`.

Admitted operations:

- `create_hyperlink` — wrap complete contiguous plain-text spans with canonical HYPERLINK fieldBegin/fieldEnd runs while retaining the display-text runs;
- `retarget_hyperlink` — replace only HYPERLINK `fieldBegin/@name`;
- `remove_hyperlink` — remove canonical control-only wrapper runs while preserving display text;
- `set_field_name` — mutate a field's `name` while preserving field type and wrapper identity;
- `insert_special_atom` / `delete_special_atom` — tab, lineBreak, nbSpace, fwSpace, and soft hyphen.

`get_inline_map` now exposes per-paragraph `field_index` values. Field indexes are revision-scoped and are resolved against the same pre-edit state used for the transaction.

Special-atom authoring follows the observed HWPX conventions: lineBreak/nbSpace/fwSpace/soft-hyphen are nested under `hp:t`, while tab is authored as a run-level sibling atom.

P2.5 deliberately permits `inline_structure_sha256` to change. The retained hard gates are exact revision, paragraph-structure invariance, full HWPX candidate validation, and atomic replacement. Field `type` mutation remains unsupported.

### Canonical P2.5 lifecycle receipt

- workflow: `P2.5 Control-semantic HWPX lifecycle CI`
- run: `35307519782`
- commit: `50f9413fc9b1cbf8feed5e31d68415e6ad7de586`
- conclusion: **SUCCESS**

Confirmed P2.5 boundaries include:

- hyperlink create → retarget → remove while preserving display text;
- DATE field-name mutation with field type preserved;
- lineBreak insertion/deletion round trip;
- legacy P2.1–P2.4 regressions;
- OAuth-native `apply_control_edits` special-atom transaction;
- signed export, re-ingest, validation, and cleanup.

Two early P2.5 CI attempts failed at Python compilation because generated source contained literal control bytes in the URL-validation tuple. The validation was rewritten to use numeric character codes; no HWPX transaction semantics were changed.

### Canonical P2.5 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-dambv3e7bikc73b27p60`
- commit: `50f9413fc9b1cbf8feed5e31d68415e6ad7de586`
- deploy status: **live**
- public workflow: `P2.5 Render public boundary verification`
- run: `35307519673`
- conclusion: **SUCCESS**

The public receipt confirms P2.5 health/version availability, durable OAuth metadata, `offline_access`, and unauthenticated MCP rejection.

## P2.6 partial-span hyperlink, typed-field, bookmark/reference and rebinding receipt

Current extended server version: `0.3.6-p2.6`.

P2.6 extends the P2.5 control transaction without weakening its exact-revision, candidate-validation, paragraph-structure-invariance, and atomic-replace gates.

Confirmed surfaces:

- partial-span `create_hyperlink` with safe run splitting around the selected ordinary-text range;
- typed DATE/PATH/MAILMERGE property mutation restricted to confirmed semantic lanes rather than arbitrary XML attributes;
- bookmark create/rename/remove lifecycle;
- internal bookmark-reference create/retarget lifecycle;
- control identity rebinding receipts after mutation, using intrinsic field identity where available and revision-scoped bookmark rebinding otherwise.

### Canonical P2.6 lifecycle receipt

- workflow: `P2.6 Bookmark and typed-control HWPX lifecycle CI`
- run: `35308426183`
- commit: `0e70871a8a22b7f5d0378cead7ef23e58d4672d9`
- conclusion: **SUCCESS**

An earlier focused regression run failed during development; the subsequent OAuth-native partial-hyperlink roundtrip and final full lifecycle both passed on the canonical implementation.

### Canonical P2.6 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-damc5q2d0e5s73esgq10`
- commit: `0e70871a8a22b7f5d0378cead7ef23e58d4672d9`
- deploy status: **live**
- public workflow: `P2.6 Render public boundary verification`
- run: `35308425996`
- conclusion: **SUCCESS**

The public receipt confirms the final P2.6 head is live behind the existing OAuth/public boundary.

## P2.7 table semantic, grid-addressing and geometry transaction receipt

Current extended server version: `0.3.7-p2.7`.

P2.7 promotes tables to a first-class MCP structure instead of treating them only as nested paragraph content.

The semantic map exposes table identity/context, merge-aware cell anchors, row/column dimensions, cell text and style references, plus independent `table_structure_sha256` and `table_format_sha256` receipts.

Addressing contract:

- tables use intrinsic `hp:tbl/@id` or `instid` when present, with revision-bound ordinal fallback;
- cells use the current table locator plus logical merge-anchor `(row,col)`;
- because HWPX does not guarantee a durable independent cell id, every mutation returns explicit table/cell rebinding receipts instead of overstating cell-address permanence.

Admitted P2.7 mutation lanes:

- row structure: `insert_row_by_clone`, `delete_row`;
- column structure: `delete_column`, `set_column_widths`, `autofit_columns`;
- merge geometry: `merge_cells`, `split_merged_cell`;
- cell content/style: `set_cell_text`, `set_cell_shading`, `set_cell_borders`;
- table normalization: `equalize_columns`, `equalize_rows`.

Row/column structural operations delegate to the validated `python-hwpx.table_patch.apply_table_ops` grid/fail-closed implementation. Merge/split and cell-format operations delegate to `HwpxOxmlTable` rather than maintaining a second independent table-geometry model.

Arbitrary column insertion is intentionally not admitted in P2.7 because the current upstream verified primitive set does not provide an evidence-backed insert-column operation.

### Canonical P2.7 lifecycle receipt

- workflow: `P2.7 Table-semantic HWPX lifecycle CI`
- run: `35309669171`
- commit: `2345e9de0a47fb13c9ee5f38dc57967b1fa456b7`
- conclusion: **SUCCESS**

Confirmed boundaries include table/cell locator maps, row insert/delete, column deletion, merge→split geometry, cell text/shading/border mutation, legacy regression coverage, and OAuth-native table ingest → map → cell edit → map lifecycle.

An earlier regression run failed because the P2.7 test module omitted its new engine import; the implementation itself was unchanged, and the corrected canonical run passed.

### Canonical P2.7 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-damceugu01pc739nq2ng`
- commit: `2345e9de0a47fb13c9ee5f38dc57967b1fa456b7`
- deploy status: **live**
- public workflow: `P2.7 Render public boundary verification`
- run: `35309669195`
- conclusion: **SUCCESS**

The public receipt confirms the final P2.7 version is live behind the existing OAuth/public boundary.

## P2.8 table creation/deletion, advanced cell semantics and evidence-gated column insertion receipt

Current extended server version: `0.3.8-p2.8`.

P2.8 closes the basic table-object lifecycle while preserving the evidence boundary established in P2.7.

New positive mutation lanes:

- `create_table` — document-attached table creation through `HwpxDocument.add_table`, with bounded rows/columns, optional width/height and optional initial cell matrix;
- `delete_table` — fail-closed deletion through `table_patch.apply_table_ops`;
- `set_cell_properties` — schema-backed `header`, `protect`, `editable`, and cell `name`;
- `set_cell_margin` — left/right/top/bottom `cellMargin` plus `hasMargin=1`;
- `set_cell_size` — explicit cell width/height;
- `set_cell_border_fill` — bind an existing borderFill reference;
- `set_cell_gradient` — evidence-backed gradient fill through the existing style machinery.

The table map now adds cell name/margin state and a `table_object_sha256` receipt. `compare_document` also accepts table structure/format/object receipts.

### Evidence-gated column insertion

The current installed `python-hwpx` surface has render-verified row clone/delete and column delete/width operations but no render-verified arbitrary column-insert primitive. P2.8 therefore does not invent one.

`insert_column_by_clone` is a deterministic negative gate:

- request is refused before candidate mutation;
- the error states that the evidence gate remains closed;
- regression coverage asserts source bytes are unchanged on refusal.

This is recorded as **CLOSED_NEGATIVE**, not as an implementation PASS for column insertion.

### Canonical P2.8 lifecycle receipt

- workflow: `P2.8 Table-object lifecycle HWPX CI`
- run: `35310685005`
- commit: `a19e4f762d06c9ed304af089c0a9b4f38c16cc0b`
- conclusion: **SUCCESS**

Confirmed boundaries include legacy P2.1–P2.7 regressions, table create → map → delete through OAuth-native MCP, advanced header/protect/editable/name/margin/size mutation, table-object digest changes, and byte-identical refusal for unsupported column insertion.

### Canonical P2.8 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-damcma67bikc73b4tuug`
- commit: `a19e4f762d06c9ed304af089c0a9b4f38c16cc0b`
- deploy status: **live**
- public workflow: `P2.8 Render public boundary verification`
- run: `35310685042`
- conclusion: **SUCCESS**

The public receipt confirms the final P2.8 version is live behind the existing OAuth/public boundary.

## P2.9 image/object semantics, media custody and geometry transaction receipt

Current extended server version: `0.3.9-p2.9`.

P2.9 promotes embedded pictures to first-class semantic objects and keeps their package media assets as a separate custody layer.

Confirmed positive lanes:

- `get_object_map` — picture identity, owning paragraph, inline/floating placement, BinData reference, geometry and package-media inventory;
- `insert_picture` — PNG/JPEG package custody plus inline or floating picture insertion;
- `replace_picture` — asset replacement while preserving the existing picture object/geometry, with optional orphan cleanup;
- `remove_picture` — picture-object removal with optional unreferenced-media garbage collection;
- `resize_picture` — coherent picture size update across `sz/orgSz/curSz`, rotation center, `imgRect`, `imgClip`, and `imgDim`;
- `set_picture_position` — offset mutation for existing floating pictures only.

Media custody is bounded to decoded PNG/JPEG payloads of at most 8 MiB. Signature mismatch, unsupported formats, stale revisions, invalid locators, and candidate-validation failures refuse before commit.

Independent receipts:

- `object_structure_sha256`;
- `object_geometry_sha256`;
- `media_custody_sha256`;
- picture create/delete/stable rebinding.

The upstream evidence basis is stronger than structural inference alone: `python-hwpx` documents `add_picture`, `add_image`, and `doc.media.replace_picture` as real-Hancom render-verified picture authoring/replacement lanes. P2.9 reuses those primitives rather than reconstructing the package media contract independently.

### Canonical P2.9 lifecycle receipt

- workflow: `P2.9 Image-object lifecycle HWPX CI`
- run: `35317728218`
- commit: `5ac0696c870b9eed70f7a0073a7e3c5da9e4b2cd`
- conclusion: **SUCCESS**

The same head passed focused picture lifecycle/geometry/custody regressions and the OAuth-native `insert_picture → get_object_map → remove_picture → get_object_map` round trip, while retaining legacy P2.1–P2.8 coverage.

### Canonical P2.9 Render/public receipt

- service: `chatgpt-web-hwpx-mcp-p0`
- deploy: `dep-dame5bad0e5s73f3l5m0`
- commit: `5ac0696c870b9eed70f7a0073a7e3c5da9e4b2cd`
- deploy status: **live**
- public workflow: `P2.9 Render public boundary verification`
- run: `35317728254`
- conclusion: **SUCCESS**

The public receipt confirms P2.9 is live behind the existing durable OAuth/public boundary.

## Current verdict

```text
P2_STRUCTURED_INTROSPECTION = CLOSED_PASS
P2_TEXT_TRANSACTION = CLOSED_PASS
P2_1_PARAGRAPH_STRUCTURAL_EDITING = PASS
P2_2_FORMATTING_INTROSPECTION_MUTATION_DIFF = PASS
P2_3_RANGE_RICH_TEXT_SELECTION = PASS
P2_3_RUN_SPLITTING_SAFE_LANE = PASS
P2_3_NESTED_PARAGRAPH_FORMATTING = PASS
P2_3_STYLE_COPY_REUSE = PASS
P2_3_FORMAT_NORMALIZATION = PASS
P2_4_INLINE_ATOM_MAP = PASS
P2_4_CROSS_RUN_CHARACTER_EDITING = PASS
P2_4_HYPERLINK_FIELD_SAFE_SELECTION = PASS
P2_4_DATE_FIELD_CACHED_TEXT_EDITING = PASS
P2_4_MIXED_MARKUP_BOUNDARY_PRESERVATION = PASS
P2_4_INLINE_STRUCTURE_DIFF = PASS
P2_5_HYPERLINK_CREATE_RETARGET_REMOVE = PASS
P2_5_FIELD_NAME_SEMANTIC_MUTATION = PASS
P2_5_SPECIAL_INLINE_ATOM_INSERT_DELETE = PASS
P2_5_CONTROL_STRUCTURE_TRANSACTION = PASS
P2_5_OAUTH_NATIVE_LIFECYCLE = PASS
P2_5_RENDER_DEPLOYMENT = PASS
P2_5_PUBLIC_BOUNDARY = PASS
P2_6_PARTIAL_SPAN_HYPERLINK_WRAPPING = PASS
P2_6_TYPED_FIELD_PROPERTY_MUTATION = PASS
P2_6_BOOKMARK_LIFECYCLE = PASS
P2_6_BOOKMARK_REFERENCE_LIFECYCLE = PASS
P2_6_CONTROL_IDENTITY_REBINDING = PASS
P2_6_OAUTH_NATIVE_LIFECYCLE = PASS
P2_6_RENDER_DEPLOYMENT = PASS
P2_6_PUBLIC_BOUNDARY = PASS
P2_7_TABLE_SEMANTIC_INTROSPECTION = PASS
P2_7_TABLE_CELL_ADDRESSING = PASS
P2_7_ROW_STRUCTURAL_MUTATION = PASS
P2_7_COLUMN_DELETE_WIDTH_MUTATION = PASS
P2_7_MERGE_SPLIT_GEOMETRY = PASS
P2_7_CELL_FORMATTING_TRANSACTION = PASS
P2_7_TABLE_REBINDING = PASS
P2_7_OAUTH_NATIVE_LIFECYCLE = PASS
P2_7_RENDER_DEPLOYMENT = PASS
P2_7_PUBLIC_BOUNDARY = PASS
P2_8_TABLE_CREATE_DELETE = PASS
P2_8_HEADER_CELL_SEMANTICS = PASS
P2_8_ADVANCED_CELL_PROPERTIES = PASS
P2_8_TABLE_OBJECT_DIGEST = PASS
P2_8_TABLE_OBJECT_LIFECYCLE = PASS
P2_8_COLUMN_INSERTION_EVIDENCE_GATE = CLOSED_NEGATIVE
P2_8_OAUTH_NATIVE_LIFECYCLE = PASS
P2_8_RENDER_DEPLOYMENT = PASS
P2_8_PUBLIC_BOUNDARY = PASS
P2_9_IMAGE_OBJECT_INTROSPECTION = PASS
P2_9_MEDIA_ITEM_CUSTODY = PASS
P2_9_INLINE_FLOATING_INSERTION = PASS
P2_9_PICTURE_REPLACEMENT_REMOVAL = PASS
P2_9_OBJECT_GEOMETRY_TRANSACTION = PASS
P2_9_OBJECT_REBINDING = PASS
P2_9_OAUTH_NATIVE_LIFECYCLE = PASS
P2_9_RENDER_DEPLOYMENT = PASS
P2_9_PUBLIC_BOUNDARY = PASS

COLUMN_INSERTION = EVIDENCE_GATE_CLOSED
ARBITRARY_FIELD_TYPE_MUTATION = HOLD
BOOKMARK_SHAPE_OBJECT_CROSS_SEMANTIC_MUTATION = HOLD
CROSS_CONTAINER_PARAGRAPH_MOVES = HOLD
PICTURE_EFFECT_CROP_GROUP_OPERATIONS = HOLD
EQUATION_OPERATIONS = HOLD
DURABLE_DOCUMENT_OBJECT_STORAGE = HOLD
HANCOM_RENDERER_FIDELITY_ORACLE = HOLD
```

P2.9 is **IMPLEMENTATION PASS / NATIVE-CI PASS / PUBLIC PASS**. Column insertion remains **CLOSED_NEGATIVE** pending an evidence-backed primitive. The remaining control gap is now beyond the confirmed hyperlink/typed-field/bookmark lanes: arbitrary field-type reinterpretation, richer object/shape reference semantics, cross-container editing, tables/images/equations, durable document-byte storage, and native Hancom fidelity.
