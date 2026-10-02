# P4.7 Render-Grounded Unified Authoring

P4.7 keeps the P4.6 principle **functionally deep, surface small** and raises the evidence bar for native equation expansion.

## Five-tool public surface

1. `get_authoring_v2_contract`
2. `inspect_equation_render_frontier`
3. `adjudicate_equation_render_evidence`
4. `compile_unified_authoring_plan`
5. `create_unified_document_and_deliver`

Low-level authoring and evidence tools remain available as expert escape hatches.

## Equation promotion rule

Official Hancom documentation confirms native equation commands including `rm`, `it`, `bold`, `rmbold`, `PILE/LPILE/RPILE`, `EQALIGN`, and local `COLOR {r,g,b}` forms. Documentation alone does not promote a LaTeX mapping.

P4.7 creates paired control/candidate HWPX fixtures using raw EqEdit **only inside the evidence harness**. Production authoring continues to reject raw EqEdit. A candidate needs exact source hashes, Hancom-native Windows PDF export, renderer executable custody, paired PDF hashes, observed visual difference, semantic-intent match, no clipping/corruption, and bounded human visual review.

Even a complete receipt returns **promotion eligible**, not automatically promoted. A separate code change and regression gate is still required.

Important correction from P4.6: LaTeX `align` must not be treated as merely a PILE mapping. Hancom documents a distinct `EQALIGN` command using `&` as an alignment mark. `EQALIGN` is therefore the primary experimental candidate; PILE/LPILE/RPILE remain separate vertical-stack primitives.

## Unified creation

For a new document, `create_unified_document_and_deliver` composes the rich/professional plan into a private HWPX candidate, resolves semantic anchors, applies the native equation/table/drawing bundle to that private candidate, validates the final package and preview-readiness state, and only then creates the durable revision.

```text
RICH PLAN + NATIVE BUNDLE
  -> PRIVATE COMPOSITION
  -> RESOLVE NATIVE ANCHORS
  -> APPLY NATIVE LANES
  -> FINAL VALIDATION + STATIC PREVIEW GATE
  -> REVISION 1 DURABLE COMMIT
  -> DELIVERY
```

A failed private candidate is deleted and never becomes a partial durable document.

## Human-visual benchmark

Human review is axis-based rather than a single beauty score:

- equation legibility
- math-style semantic match
- alignment-intent match
- table scanability
- drawing integration
- page rhythm/density
- overlap/clipping

Human review remains separate from package validity and native-render evidence.

## One-click onboarding target

The minimal intended path is:

1. connect the remote OAuth-protected MCP;
2. call `get_authoring_v2_contract` once;
3. call `create_unified_document_and_deliver` with one rich+native plan;
4. use the returned revision-bound HWPX;
5. only add render/human evidence when a visual-quality claim matters.

Delivery failure after commit is recovered with `deliver_document`, never by replaying the mutation.
