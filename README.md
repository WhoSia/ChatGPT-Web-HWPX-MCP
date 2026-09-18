# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for authenticated HWPX document creation, custody, validation, structured introspection, revision-safe editing, and signed artifact delivery from ChatGPT Web.

## Current phase

**P0 / P1 / P1.1 / P1.2 are closed / PASS.** The project has established native ChatGPT MCP discovery and actions, opaque document custody, signed HWPX delivery, OAuth-native secret-free invocation, durable restart-safe OAuth authority, and bounded existing-HWPX ingress. See the corresponding test ledgers.

**P2 is CLOSED / PASS. P2.1 and P2.2 are implemented. P2.3 is active.** P2.3 adds direct-text character ranges, safe run splitting, nested paragraph-property mutation, exact same-document style reuse, and run normalization on top of the existing formatting transaction layer.

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
| `get_document_map` | No | Return sections, paragraph locators, and semantic/structure/formatting receipts |
| `get_text` | No | Return whole-document or locator-targeted paragraph text |
| `get_formatting` | No | Resolve paragraph/run formatting refs and property summaries |
| `apply_edits` | Yes | Apply one revision-guarded atomic text/paragraph-structure transaction |
| `apply_formatting` | Yes | Apply one revision-guarded formatting-only transaction |
| `compare_document` | No | Compare semantic/structure/formatting receipts with the current revision |
| `export_document` | No* | Return a short-lived signed download URL |
| `delete_document` | Yes | Delete the caller-owned HWPX and metadata |

There are no password, passphrase, API-key, or access-token fields in MCP tool schemas. Authentication happens at the HTTP/MCP transport layer.

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

- `P2.3 Rich-text HWPX lifecycle CI` — ingress/auth regressions plus range splitting, style reuse, nested formatting, normalization, and OAuth-native map→edit→range-format→export→re-ingest lifecycle.
- `P2.3 Render public boundary verification` — public P2.3 version/health, durable OAuth metadata, `offline_access`, and unauthenticated MCP rejection. The workflow uses HTTP/1.1 and retry-on-transport-error because one GitHub-runner↔Render edge reset was observed while Render itself remained healthy.

See [`P2_TEST_LEDGER.md`](./P2_TEST_LEDGER.md) for canonical run/deploy receipts and the initial transport-failure classification.

## Security boundary

P2.3 is still deliberately narrow. It does not yet claim arbitrary range splitting through fields/controls/mixed inline markup, durable document bytes, cross-container structural moves, tables/images/equations, or native Hancom visual fidelity.

## Phase lineage

```text
P1     minimal valid HWPX + document_id + signed export
P1.1   OAuth-native secret-free lifecycle + authenticated ownership
P1.2   durable OAuth authority + bounded existing-HWPX ingress
P2     structured introspection + paragraph addressing + revision-safe text transactions
P2.1   paragraph insert/delete/reorder + locator rebinding
P2.2   paragraph/run formatting introspection + formatting mutation + formatting diff
P2.3   range selection + run splitting + nested formatting + style reuse + normalization
P2.x   richer control-aware inline and container-aware operations
P3     tables / images / equations
P4     renderer oracle and Hancom fidelity validation
```
