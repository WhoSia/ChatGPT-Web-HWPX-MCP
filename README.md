# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for authenticated HWPX document creation, custody, validation, structured introspection, revision-safe editing, and signed artifact delivery from ChatGPT Web.

## Current phase

**P0 / P1 / P1.1 / P1.2 are closed / PASS.** The project has established native ChatGPT MCP discovery and actions, opaque document custody, signed HWPX delivery, OAuth-native secret-free invocation, durable restart-safe OAuth authority, and bounded existing-HWPX ingress. See the corresponding test ledgers.

**P2 is implementation/public PASS and awaits one native ChatGPT edit receipt.** P2 adds structured paragraph maps, explicit locator stability semantics, exact document revisions, candidate-validated atomic text-edit transactions, and semantic/structure diff receipts. See [`P2_TEST_LEDGER.md`](./P2_TEST_LEDGER.md).

```text
ChatGPT Web
→ durable OAuth 2.1 authority
→ caller-owned opaque document_id
→ structured section/paragraph map
→ stable-or-revision-bound paragraph locator
→ exact expected_revision
→ candidate-package validation
→ atomic HWPX replacement
→ semantic / structure receipts
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
| `get_document_map` | No | Return sections, paragraph locators, and semantic/structure receipts |
| `get_text` | No | Return whole-document or locator-targeted paragraph text |
| `apply_edits` | Yes | Apply one revision-guarded atomic text-edit transaction |
| `compare_document` | No | Compare prior semantic/structure receipts with the current revision |
| `export_document` | No* | Return a short-lived signed download URL |
| `delete_document` | Yes | Delete the caller-owned HWPX and metadata |

There are no password, passphrase, API-key, or access-token fields in MCP tool schemas. Authentication happens at the HTTP/MCP transport layer.

## P2 address contract

Paragraph locators use the form `p_<hash>`.

- `intrinsic-id`: when HWPX exposes a paragraph id, the locator derives from section identity plus that id and is expected to survive text-only edits while the id survives.
- `revision-bound-ordinal`: when no intrinsic id is available, the locator falls back to section plus paragraph ordinal. This is deliberately not claimed to survive later structural edits.

`get_document_map` also returns whole-document `semantic_sha256`, `structure_sha256`, per-paragraph text digests, section identity, paragraph index, and locator stability classification.

## P2 transaction contract

`apply_edits` currently admits `replace_paragraph_text` only.

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

Stale revisions, invalid operation sets, unknown locators, and candidate-validator failures leave the original document bytes unchanged. Formatting and structural edits remain out of scope until this text-addressing boundary is closed natively.

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

- `P2 Structured HWPX edit lifecycle CI` — ingress/auth regressions plus locator, revision, rollback, OAuth-native map→edit→targeted-read→compare→export→re-ingest lifecycle.
- `P2 Render public boundary verification` — public P2 version/health, durable OAuth metadata, `offline_access`, and unauthenticated MCP rejection. The workflow uses HTTP/1.1 and retry-on-transport-error because one GitHub-runner↔Render edge reset was observed while Render itself remained healthy.

See [`P2_TEST_LEDGER.md`](./P2_TEST_LEDGER.md) for canonical run/deploy receipts and the initial transport-failure classification.

## Security boundary

P2 is still deliberately narrow. It does not yet claim durable document bytes, structural editing, formatting, tables/images/equations, or native Hancom visual fidelity.

## Phase lineage

```text
P1     minimal valid HWPX + document_id + signed export
P1.1   OAuth-native secret-free lifecycle + authenticated ownership
P1.2   durable OAuth authority + bounded existing-HWPX ingress
P2     structured introspection + paragraph addressing + revision-safe text transactions
P2.x   structural/formatting operations after native P2 closure
P3     tables / images / equations
P4     renderer oracle and Hancom fidelity validation
```
