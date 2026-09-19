# P3.3 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.3 — Large-Document Bounded Navigation, Replay-Safe Creation & Agent-Cost Reduction**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_LIFECYCLE_CI_PASS / PRODUCTION_CODE_DEPLOYED / PUBLIC_EDGE_RELIABILITY_INHERITED_HOLD`

## Features promoted

### search_document_text

- paragraph-level text search
- case-sensitive or case-insensitive mode
- bounded maximum result count
- bounded surrounding context
- paragraph index + revision-bound locator
- text SHA-256 per hit
- current revision + semantic SHA-256 receipt

### get_document_slice

- bounded paragraph windows
- maximum 200 paragraphs per call
- optional locators
- absolute paragraph indexes
- `has_more` and `next_start_paragraph`
- current revision + semantic SHA-256 receipt

### replay-safe create_document

`create_document` accepts optional `request_id`.

For the same authenticated owner:

- same request id + same normalized create payload → same durable document and `idempotent_replay=true`
- same request id + different payload → deterministic idempotency conflict
- document id is derived through HMAC rather than exposing the request id directly

This closes the most important lost-response hole in restart-aware creation.

## Confirmatory CI

Native lifecycle run:

- `35435187083` — SUCCESS

The P3.3 lifecycle covers:

- OAuth-native tool discovery
- P3.3 version/capabilities
- idempotent create replay
- bounded text search
- bounded document slice
- existing revision-safe edits
- existing rich-object surfaces
- durable lineage operations
- export/re-ingest/cleanup

## Production materialization

Render deploy:

- `dep-dan5eq8ae00c73diq5b0`
- commit `dfb34c09d5aed73b55fffbcd006a21dbf7efa9cb`
- status `live`

The server code in that deployment contains the P3.3 navigation and replay-safe creation surfaces.

Public uninterrupted tool execution remains subject to the separately documented R3 Render Free-instance edge instability.

## Performance interpretation

P3.3 reduces unnecessary agent payload and repeated parsing cost by allowing the client to:

`search → bounded slice → targeted locator → mutation`

instead of always:

`full document map → full-text materialization → mutation`

The full map remains authoritative when complete structural context is actually required.

## Next functional boundary

**ChatGPT Web HWPX MCP P3.4 — Query-to-Locator Selection Plans, Multi-Hit Edit Preview, Atomic Bulk Text Mutation & Bounded Post-Edit Verification**

P3.4 should build directly on P3.3 search/slice so an agent can locate many intended edits, preview the exact affected paragraphs, and commit them in one revision-safe transaction instead of N separate round trips.
