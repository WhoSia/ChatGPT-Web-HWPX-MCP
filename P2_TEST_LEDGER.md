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

## Current verdict

```text
STRUCTURED_DOCUMENT_INTROSPECTION = PASS
PARAGRAPH_ADDRESS_CONTRACT = PASS
INTRINSIC_ID_LOCATOR_CONTINUITY_TEXT_ONLY = PASS
REVISION_BOUND_FALLBACK_SEMANTICS = PASS
EXACT_REVISION_PRECONDITION = PASS
STALE_REVISION_REJECTION = PASS
ATOMIC_MULTI_EDIT_COMMIT = PASS
VALIDATOR_BEFORE_COMMIT = PASS
ROLLBACK_BYTE_PRESERVATION = PASS
SEMANTIC_DIFF_RECEIPT = PASS
STRUCTURE_DIGEST_RECEIPT = PASS
OAUTH_NATIVE_P2_CI_LIFECYCLE = PASS
RENDER_P2_DEPLOYMENT = PASS
PUBLIC_P2_BOUNDARY = PASS

CHATGPT_NATIVE_P2_TOOL_SURFACE = PENDING_NATIVE_RECEIPT
STRUCTURAL_EDITS = HOLD
FORMATTING = HOLD
TABLE_IMAGE_EQUATION_OPERATIONS = HOLD
DURABLE_DOCUMENT_OBJECT_STORAGE = HOLD
HANCOM_RENDERER_FIDELITY_ORACLE = HOLD
```

## Promotion rule

P2 is **IMPLEMENTATION PASS / PUBLIC PASS**. Global closure requires one native ChatGPT Web receipt through the existing custom app:

1. call `p2_capabilities()` and observe version `0.3.0-p2`;
2. create a small document at revision 1;
3. obtain its paragraph map and one locator;
4. execute a locator-targeted `replace_paragraph_text` with `expected_revision=1`;
5. observe revision 2 and a semantic diff;
6. read the same locator and observe the replacement text without reauthorizing OAuth.

If those native steps pass, P2 may be closed and formatting/structural operations may begin in the next phase.
