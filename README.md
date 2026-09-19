# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for authenticated HWPX document creation, custody, validation, structured introspection, revision-safe editing, and signed artifact delivery from ChatGPT Web.

## Current phase

**P0 / P1 / P1.1 / P1.2 are closed / PASS.** The project has established native ChatGPT MCP discovery and actions, opaque document custody, signed HWPX delivery, OAuth-native secret-free invocation, durable restart-safe OAuth authority, and bounded existing-HWPX ingress. See the corresponding test ledgers.

**P2 rich-object, P3.0 durable custody, and P3.1 durable concurrency are CLOSED / PASS. P3.2 is active.** P3.2 governs long-lived revision lineage: pinned restore anchors, lease-safe snapshot compaction, append-only commit receipts, restore-reachability checks, and a tamper-evident SHA-256 audit chain.

```text
ChatGPT Web
→ durable OAuth 2.1 authority
→ caller-owned opaque document_id
→ structured section/paragraph map
→ stable-or-revision-bound paragraph locator
→ exact expected_revision
→ candidate-package validation
→ atomic HWPX replacement
→ semantic / structure / formatting receipts
→ signed export
```

## MCP tools

| Tool | Side effect | Purpose |
|---|---:|---|
| `probe_read` | No | Authenticated connectivity probe |
| `probe_capabilities` | No | Base auth/custody capability boundary |
| `p2_capabilities` | No | P2 addressing/edit capability receipt |
| `create_document` | Yes | Materialize a small HWPX at revision 1 |
| `ingest_document` | Yes | Admit one bounded existing HWPX at revision 1 |
| `inspect_document` | No | Validate and inspect one caller-owned document |
| `get_document_versions` | No | List retained durable revision snapshots |
| `get_document_commit_receipt` | No | Return a deterministic commit receipt plus audit-chain hashes |
| `acquire_document_lease` | Yes | Acquire a short durable coordination lease for one revision |
| `release_document_lease` | Yes | Release a durable lease by opaque token |
| `restore_document_revision` | Yes | Promote one retained historical snapshot as a new monotonic revision |
| `set_document_retention` | Yes | Update document TTL under revision CAS |
| `pin_document_revision` | Yes | Protect a historical revision as a restore anchor |
| `unpin_document_revision` | Yes | Remove a restore-anchor pin |
| `compact_document_history` | Yes | Prune unpinned old byte snapshots while preserving the commit ledger |
| `verify_document_lineage` | No | Verify audit-chain integrity plus current/pinned restore reachability |
| `get_document_map` | No | Return sections, paragraph locators, and semantic/structure/formatting receipts |
| `get_text` | No | Return whole-document or locator-targeted paragraph text |
| `get_formatting` | No | Resolve paragraph/run formatting refs and property summaries |
| `get_inline_map` | No | Return direct inline text spans, special atoms, field/control boundaries, and inline-structure receipts |
| `apply_edits` | Yes | Apply one revision-guarded atomic text/paragraph-structure transaction |
| `apply_formatting` | Yes | Apply one revision-guarded formatting-only transaction |
| `apply_inline_edits` | Yes | Apply one control-aware cross-run inline text transaction |
| `apply_control_edits` | Yes | Mutate hyperlink/field semantics or insert/delete special inline atoms |
| `get_table_map` | No | Return table/cell semantic addresses, merge geometry, and table receipts |
| `apply_table_edits` | Yes | Apply one revision-guarded table structure/geometry/cell-format transaction |
| `get_object_map` | No | Return picture objects, package-owned media items, geometry and custody receipts |
| `apply_object_edits` | Yes | Apply one revision-guarded picture/media/geometry transaction |
| `get_equation_map` | No | Return equation identities, EqEdit scripts, geometry and custody receipts |
| `apply_equation_edits` | Yes | Apply one revision-guarded verified-equation lifecycle/geometry transaction |
| `compare_document` | No | Compare semantic/structure/formatting/inline/table receipts with the current revision |
| `export_document` | No* | Return a short-lived signed download URL |
| `delete_document` | Yes | Delete the caller-owned HWPX and metadata |

There are no password, passphrase, API-key, or access-token fields in MCP tool schemas. Authentication happens at the HTTP/MCP transport layer.

## P3.3 large-document navigation and replay-safe creation

P3.3 reduces agent cost and lost-response fragility without changing the HWPX editing authority model.

- `search_document_text` returns compact paragraph hits, revision-bound locators, match offsets, and bounded context.
- `get_document_slice` returns at most 200 paragraphs per call with `next_start_paragraph`, so large documents can be read incrementally.
- Both surfaces expose the current revision and semantic SHA-256, making a navigation result explicitly stale after later edits.
- `create_document(request_id=...)` is replay-safe: the same owner + request id + payload resolves to the same durable document after a lost response. Reusing the key with a different payload is rejected.
- The existing full `get_document_map` remains available when complete structural materialization is actually needed.

## P3.2 durable revision-lineage contract

P3.2 separates **commit authority** from **historical byte retention**.

```text
append-only commit receipt ledger
  └─ SHA-256 previous_audit_hash → audit_hash chain

revision byte snapshots
  ├─ current revision: always protected
  ├─ explicitly pinned restore anchors: DB-level protected
  ├─ recent K revisions: retention policy
  └─ older unpinned snapshots: eligible for compaction
```

`compact_document_history` is revision-CAS guarded and refuses to run while an unexpired document lease exists. A compaction transaction may delete only historical `hwpx_document_revisions` rows; it does not delete `hwpx_document_commits`. After compaction the server immediately re-verifies the audit chain, the current revision snapshot, and every pinned restore anchor.

The commit audit hash covers `document_id`, `revision`, `expected_revision`, document SHA-256, deterministic `receipt_id`, and the previous audit hash. P3.1 rows with no audit fields are migration-backfilled once; existing non-NULL audit values are never auto-healed, so later tampering remains observable across process restart.

Pinned revisions are protected by a database foreign-key constraint in addition to application-level candidate filtering. Restore semantics stay monotonic: an old retained snapshot is never made current by pointer rewind; it is promoted as a fresh `current_revision + 1` commit.
## P2 address contract

Paragraph locators use the form `p_<hash>`.

- `intrinsic-id`: when HWPX exposes a paragraph id, the locator derives from section identity plus that id and is expected to survive text-only edits while the id survives.
- `revision-bound-ordinal`: when no intrinsic id is available, the locator falls back to section plus paragraph ordinal. This is deliberately not claimed to survive later structural edits.

`get_document_map` also returns whole-document `semantic_sha256`, `structure_sha256`, `formatting_sha256`, per-paragraph text digests, section identity, paragraph/container indexes, and locator stability classification.

## P2/P2.1 text and structural transaction contract

`apply_edits` admits:

- `replace_paragraph_text`
- `insert_paragraph_before`
- `insert_paragraph_after`
- `delete_paragraph`
- `move_paragraph_before`
- `move_paragraph_after` (same container in P2.1)

Inserted paragraphs inherit the anchor paragraph's paragraph/run formatting shell, receive a fresh paragraph intrinsic id, and deliberately do not duplicate rich inline controls. Structural transactions return structure-diff and locator-rebinding receipts.

```text
expected_revision == current_revision
→ resolve every locator against one pre-edit map
→ reject invalid/duplicate/unknown operations
→ write sibling candidate HWPX
→ rebuild semantic/structure map
→ validate candidate HWPX package
→ atomic os.replace commit
→ revision + 1
→ update package/semantic/structure receipts
```

Stale revisions, invalid operation sets, unknown locators, and candidate-validator failures leave the original document bytes unchanged. Cross-container paragraph moves and table/image/equation mutation remain outside the P2.1 boundary.

## P2.2 formatting layer

`get_formatting` resolves the formatting surface independently from text and structure. P2.3 additionally exposes `direct_text`, `direct_text_length`, and each run's `[start,end)` offsets plus `range_safe` classification:

- paragraph `paraPrIDRef`, `styleIDRef`, page/column break attrs;
- direct run indexes and `charPrIDRef`;
- resolved run summaries such as size, text color, bold/italic/underline/strike, font refs, script and outline;
- resolved paragraph summaries such as alignment, margin, line spacing, break settings and heading refs;
- document-level `formatting_sha256`.

`apply_formatting` supports two operation families:

```text
set_run_format
  → bold / italic / underline / color / font / size / highlight / strike
  → underline/strike shapes, ratio, letter spacing, shadow, superscript/subscript,
    outline, emboss, engrave

set_paragraph_format
  → alignment / line spacing / indents / before-after spacing
  → outline level / keep rules / page or column break
  → bottom border / tab stops
```

Run formatting can target one direct run by `run_index` or all text-bearing runs in the paragraph. Unspecified run properties inherit from the current `charPr` through `python-hwpx`'s style-table machinery instead of reconstructing styles from scratch.

Paragraph-property mutation is intentionally narrower in P2.2: it is accepted only for direct section-body paragraphs. Nested table-cell or shape-internal paragraphs are fully introspectable, but paragraph-property writes fail closed until their container-specific semantics are promoted.

The transaction boundary is formatting-only:

```text
expected_revision == current_revision
→ resolve formatting against the pre-edit locator map
→ write a sibling candidate
→ create/reuse HWPX charPr / paraPr definitions
→ apply refs
→ require semantic_sha256 unchanged
→ require structure_sha256 unchanged
→ validate candidate package
→ atomic os.replace
→ revision + 1
→ formatting diff receipt
```

If a formatting request changes document text or paragraph structure, the candidate is rejected before commit.

## P2.3 rich-text range and normalization layer

P2.3 extends `apply_formatting` without changing the MCP tool name:

```text
set_range_format
  target + start + end + format
  → offsets are [start,end) over target.direct_text
  → only boundary/intersected plain runs are split

copy_run_format
  source (+ source_run_index) → target
  → exact existing charPrIDRef reuse
  → target can be run_index, all text runs, or [start,end)

copy_paragraph_format
  source → target
  → exact existing paraPrIDRef reuse
  → copy_named_style=true optionally reuses styleIDRef too

normalize_formatting
  target paragraph or whole document
  → coalesce adjacent split-safe runs with identical run attributes
```

Range mutation is intentionally fail-closed for runs containing fields, shapes, mixed inline markup, tabs/controls, or other structures that cannot be split without guessing. Whole-run formatting remains available for those cases when the run itself can be addressed safely.

Paragraph-property mutation now works for both section-body and nested paragraphs. The engine mints or reuses a `paraPr` from the target's current `paraPrIDRef`, saves the header definition, then binds that reference back to the addressed nested paragraph. This avoids positional body-only APIs while preserving the same property-table semantics.

Normalization always runs after other formatting mutations in the same transaction, regardless of operation-array order. It is an inline run-coalescing layer; it does not garbage-collect unrelated historical `charPr`/`paraPr` definitions.

## P2.4 control-aware inline surgery

`get_inline_map` exposes a second, control-aware coordinate surface for each paragraph:

- `inline_text`: direct visible inline text only; nested table/shape text is not folded into its host paragraph;
- text spans with `[start,end)`, run index, active field stack, and mixed-markup context;
- visible one-character atoms for tab, line break, no-break space, full-width space, and soft hyphen;
- zero-width boundaries for field begin/end, bookmarks/other controls, mixed markup, and inline objects;
- resolved field spans such as HYPERLINK/DATE/PATH;
- document-level `inline_text_sha256` and `inline_structure_sha256`.

The inline-structure digest deliberately hashes the ordered control/field/markup/special-atom skeleton rather than ordinary text lengths or plain-run fragmentation. Text can therefore change without falsely reporting that a hyperlink or field wrapper was structurally rewritten.

`apply_inline_edits` currently admits:

```text
replace_inline_text
  target + [start,end) + text
  + optional expected_text
```

The selection may cross ordinary run boundaries, including different character styles. Replacement text is stored in the start span/run, while untouched suffix text remains in its original runs.

Safety rules are fail-closed:

- every selected visible atom must be ordinary text; tab/lineBreak/nbSpace/fwSpace/soft-hyphen must be split around rather than deleted implicitly;
- all selected text spans must share the same active field and mixed-markup context;
- field begin/end, bookmark/control, object, or markup boundaries may not occur strictly inside the selected range;
- HYPERLINK display text and DATE/PATH cached text are editable when the selection stays inside the field wrapper;
- selections that cross into/out of a field are rejected before byte mutation;
- replacement text may not introduce new special atoms in P2.4.

The transaction contract is:

```text
expected_revision == current_revision
→ resolve offsets against one pre-edit inline map
→ reject overlap / context crossing / special-atom surgery
→ edit text storage slots across one or more runs
→ require paragraph structure digest unchanged
→ require inline_structure_sha256 unchanged
→ validate candidate HWPX
→ atomic replace
→ revision + 1
→ inline text/structure diff receipt
```

This layer is intended to preserve fields and controls, not to rewrite their semantics. Hyperlink targets, field commands, bookmarks, shapes, and special inline atoms remain separate future mutation surfaces.

## P2.5 field/control semantic mutation layer

P2.5 adds a separate `apply_control_edits` transaction rather than weakening P2.4's inline-structure-invariance contract.

Admitted operations:

```text
create_hyperlink
  target + [start,end) + url
  → wraps complete contiguous plain-text spans
  → preserves existing display-text runs and character formatting

retarget_hyperlink
  target + field_index + url
  → mutates HYPERLINK fieldBegin/@name only

remove_hyperlink
  target + field_index
  → removes canonical fieldBegin/fieldEnd wrapper runs
  → keeps display text unchanged

set_field_name
  target + field_index + name
  → mutates fieldBegin/@name while preserving field type

insert_special_atom / delete_special_atom
  → tab, lineBreak, nbSpace, fwSpace, soft hyphen
```

`get_inline_map` now assigns a stable pre-revision `field_index` inside each paragraph. Field-index operations are resolved against the same pre-edit revision and processed from higher indexes downward.

Special-atom creation follows observed HWPX authoring conventions rather than treating every atom identically:

- `lineBreak`, `nbSpace`, `fwSpace`, and soft hyphen are nested inside `hp:t` mixed content;
- `tab` is emitted as a run-level sibling atom.

Hyperlink creation is intentionally conservative in P2.5: the selected range must align to complete contiguous plain text spans with no existing field/markup/control boundary. Partial-range wrapping can be promoted later without weakening the current contract.

Unlike P2.4, P2.5 **expects** `inline_structure_sha256` to change. The hard transaction invariant is instead:

```text
expected_revision == current_revision
→ resolve field/range/atom target against one pre-edit inline map
→ write candidate package
→ require paragraph structure_sha256 unchanged
→ validate HWPX package
→ atomic replace
→ revision + 1
→ return before/after inline_text + inline_structure receipts
```

Field `type` mutation remains fail-closed; P2.5 does not reinterpret a DATE field as HYPERLINK or vice versa. Bookmark/shape/object semantic creation and deletion are also outside this layer.

## P2.6 partial-span, typed-field, and bookmark/reference layer

P2.6 keeps the same `apply_control_edits` MCP tool and extends its admitted operations.

### Partial-span hyperlink wrapping

`create_hyperlink` no longer requires whole text spans. A selection may begin/end inside plain `hp:t` runs:

```text
[start,end) over inline_text
→ require ordinary text only
→ reject existing field/markup/control crossings
→ split only boundary runs
→ preserve each selected fragment's original run attributes
→ insert canonical HYPERLINK fieldBegin/fieldEnd wrapper runs
```

`create_bookmark_reference` uses the same range mechanism with an existing bookmark target. `retarget_bookmark_reference` validates the destination bookmark before replacing the hyperlink target.

### Typed field mutation

The inline map now exposes each field's intrinsic id/fieldid, begin attributes, and typed parameter snapshot.

P2.6 admits only field-property combinations backed by the current upstream HWPX contract:

- DATE: `DateFormat="YYYY년 M월 D일"`, `DateNation="KOR"`, matching observed Command value, plus optional cached text;
- PATH: observed `filename` lane (`Command="$F"`, `Format="$F"`) plus optional cached text;
- MAILMERGE: rename `Command` and `FieldValue`, preserving `FieldType="USER_DEFINE"`; the default `{{old_name}}` cached placeholder is synchronized when requested.

Unsupported DATE/PATH formats remain typed rejections rather than guessed format-language translations.

### Bookmark/reference lifecycle

```text
create_bookmark
rename_bookmark
remove_bookmark
create_bookmark_reference
retarget_bookmark_reference
```

Bookmark names are document-unique in this layer. Renaming a bookmark updates matching internal HYPERLINK targets (`#name`) by default. Removing a bookmark is rejected while internal references still point to it; callers must retarget/remove those references first.

### Control identity rebinding

Every P2.6 control transaction returns `control_rebinding`.

- fields are rebound primarily by their intrinsic HWPX field id, so ordinary property/target edits retain a stable identity;
- bookmarks have no equivalent intrinsic id in the observed structure, so bookmark identity is explicitly revision-scoped and rebound by paragraph/offset position when possible;
- created/deleted/unresolved controls are reported separately rather than silently treated as stable.

The hard transaction boundary remains exact revision, paragraph-structure invariance, candidate HWPX validation, and atomic replacement. Inline/control structure is allowed to change when the requested operation requires it.




## Durable OAuth boundary

OAuth clients, pending approvals, authorization codes, access tokens, refresh tokens, and revocation state are persisted in encrypted Postgres state.

- lookup keys are SHA-256 fingerprints;
- payloads are authenticated-encrypted with AES-GCM;
- authorization-code and refresh-token consumption are transactional;
- refresh tokens rotate on use;
- revocation persists across server restarts;
- `offline_access` is advertised;
- native ChatGPT post-redeploy continuity has passed without resource-owner reauthorization.

Document bytes themselves are still intentionally ephemeral under `/tmp`; OAuth durability and document-custody durability are separate boundaries.

## Existing-HWPX admission gate

`ingest_document` accepts only small authenticated base64 HWPX packages. The gate enforces bounded package/expanded sizes, entry counts, compression-ratio limits, safe ZIP paths, duplicate/encrypted-entry rejection, CRC validation, required HWPX parts, mimetype placement/signature, XML/HPF parseability, and DTD/ENTITY rejection. Arbitrary remote URL fetching is not supported.

## HWPX validation

Generated, ingested, and P2 edited candidates are independently checked as ZIP/XML packages. Required parts include:

```text
mimetype
version.xml
META-INF/container.xml
Contents/content.hpf
Contents/header.xml
Contents/section0.xml
```

`mimetype` must be the first ZIP entry, stored without compression, and equal `application/hwp+zip`.

## Storage and ownership

Filesystem paths are never exposed to the model. Every document receives an opaque `doc_<random>` id and is bound to the authenticated OAuth subject. Current document custody is a bounded ephemeral filesystem store with a default 30-minute retention window.

## Local run

Install dependencies:

```bash
pip install -r requirements.txt
```

P2 uses the P1.2 durable OAuth environment plus the P2 wrapper:

```bash
P11_OAUTH_PASSPHRASE='local-oauth-passphrase' \
P1_DOWNLOAD_SECRET='local-download-secret' \
P12_AUTH_DATABASE_URL='postgresql://...' \
P12_STATE_SECRET='replace-with-at-least-32-random-characters' \
P1_PUBLIC_BASE_URL='http://127.0.0.1:8000' \
python server_p2.py
```

## Deployment

The canonical Render service intentionally retains its historical hostname:

```text
https://chatgpt-web-hwpx-mcp-p0.onrender.com
```

Server-side secrets remain deployment-only and are not stored in this repository.

## CI

P2 currently uses two confirmatory workflows:

- `P2.6 Bookmark and typed-control HWPX lifecycle CI` — legacy regressions plus partial-span hyperlink wrapping, typed field mutation, bookmark/reference propagation, control rebinding, and OAuth-native partial-link roundtrip.
- `P2.6 Render public boundary verification` — public P2.6 version/health, durable OAuth metadata, `offline_access`, and unauthenticated MCP rejection. The workflow uses HTTP/1.1 and retry-on-transport-error because one GitHub-runner↔Render edge reset was observed while Render itself remained healthy.

See [`P2_TEST_LEDGER.md`](./P2_TEST_LEDGER.md) for canonical run/deploy receipts and the initial transport-failure classification.

## Security boundary

P2.6 is still deliberately narrow. It does not mutate field types, infer unobserved DATE/PATH format languages, create/delete shape/object semantics, persist document bytes durably, move paragraphs across containers, mutate tables/images/equations, or claim native Hancom visual fidelity.

## Phase lineage

```text
P1     minimal valid HWPX + document_id + signed export
P1.1   OAuth-native secret-free lifecycle + authenticated ownership
P1.2   durable OAuth authority + bounded existing-HWPX ingress
P2     structured introspection + paragraph addressing + revision-safe text transactions
P2.1   paragraph insert/delete/reorder + locator rebinding
P2.2   paragraph/run formatting introspection + formatting mutation + formatting diff
P2.3   range selection + run splitting + nested formatting + style reuse + normalization
P2.4   control-aware inline map + field-safe cross-run text surgery + inline-structure diff
P2.5   hyperlink lifecycle + field-name semantics + special inline atom mutation
P2.6   partial-span hyperlink + typed fields + bookmark/reference lifecycle + control rebinding
P2.7   table semantic map + grid-addressed structure/merge/split/cell-format transactions
P2.x   richer cross-reference/control and container semantics
P3     tables / images / equations
P4     renderer oracle and Hancom fidelity validation
```
