# P3.36-R2-R2 — Multi-container presentation-role recovery

P3.36-R2-R2 repairs one bounded failure discovered prospectively in R2-R1: documents whose visible title or heading is carried inside a table or other nested HWPX container can expose no native heading metadata and no body-level hierarchy signal.

## Constitutional rule

The repair is not a lower global threshold.

1. Run the existing body/native presentation-role pass first.
2. If that pass yields at least one TITLE or HEADING, nested-container recovery is disabled.
3. Only when primary hierarchy is exactly zero, inspect a bounded early-document nested-container window.
4. Promote at most one nested paragraph: centered + size contrast => TITLE; otherwise centered + strong bold header contrast => HEADING.
5. Record strategy, confidence, evidence and recovered locator.
6. Never rewrite native semantic role truth and never use prose meaning to choose the role.

This makes the recovery layer fail-closed and avoids converting ordinary table cells into headings throughout a document.

## Container evidence

The feature extractor records structural ancestry from native section XML: immediate container, bounded ancestor path, whether the paragraph is inside a table/cell, and whether it is nested. The hierarchy inference consumes only structural position and typography/alignment evidence.

## Second generation benchmark

A generated-HWPX benchmark creates a long table with no body-level title/heading, formats the first nested cell as a prominent centered title, then re-reads the native HWPX. Both INSTITUTIONAL_COMPATIBILITY and POLISHED_REPORT must remain mechanically valid, preserve long-table behavior, recover the nested TITLE through the bounded second pass, and keep aesthetic_verdict = NOT_ADJUDICATED.

## Evidence interpretation

The R2-R1 9-document holdout has already been observed. Re-evaluating those documents after this repair is rescue/regression evidence only, not a new prospective generalization result.

A new Batch-03 source-group holdout is therefore presealed before byte intake. Any failure on Batch-03 must be preserved and deferred; no post-open threshold tuning is permitted in R2-R2.

## Visual controls

Visual evidence remains separate from native semantics. Exact official HWPX/PDF pairs in Batch-03 may measure render/design correspondence. They do not convert common public-document appearance into a beauty norm, and explicit polished design requests retain higher design authority.
