# P3.4 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.4 — Query-to-Locator Selection Plans, Multi-Hit Edit Preview, Atomic Bulk Text Mutation & Bounded Post-Edit Verification**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_LIFECYCLE_CI_PASS / PUBLIC_BOUNDARY_CODE_PASS / PRODUCTION_DEPLOY_PENDING_AT_SEAL`

## Promoted tools

- `plan_bulk_text_replace`
- `commit_bulk_text_replace`

## Authority contract

A bulk plan is bound to:

- document id
- current revision
- semantic SHA-256
- query and replacement
- case-sensitivity mode
- selected hit indexes
- selected locator/range/text receipts

The plan id is HMAC-authenticated. Commit recomputes the plan against the current revision and rejects stale or altered plans.

## Formatting safety

P3.4 intentionally does **not** implement bulk replacement by rewriting entire paragraphs.

Selected matches are translated into `replace_inline_text` operations and committed through the existing inline-range transaction engine. The preview candidate must preserve paragraph structure and inline-structure digests before a plan can be committed.

## Preview semantics

The preview path:

1. enumerates literal matches,
2. applies optional hit-index selection,
3. builds exact inline ranges,
4. materializes a temporary candidate HWPX,
5. validates the package,
6. compares semantic/structure/inline receipts,
7. returns a signed plan without durable mutation.

## Commit semantics

Commit requires the same plan id and expected revision and performs all selected operations in one CAS-guarded revision.

Bounded verification returns changed locators, text SHA-256 receipts, and capped post-edit text samples.

## Confirmatory CI

- P3.4 lifecycle run `35435632915` — SUCCESS.
- Latest integrated lifecycle run `35435829315` — SUCCESS, including legacy-HWP discovery additions.
- Public boundary code-path checks preceding production materialization remained successful.

## Next functional boundary

**ChatGPT Web HWPX MCP P3.5 — Native HWP 5.x Read Custody, Common Document IR, Fidelity-Graded HWP→HWPX Promotion & Legacy-Document Search/Extraction**
