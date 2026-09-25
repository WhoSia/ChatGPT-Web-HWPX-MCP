# Page Composition

Use this reference when page rhythm, density, whitespace, balance, or cross-page transitions matter.

## Workflow

1. Obtain real page evidence.
2. Use `get_page_composition_contract` for the declared archetype.
3. Run `diagnose_page_composition`.
4. Treat named findings as evidence signals, not a scalar aesthetics score.
5. Use `plan_render_guided_page_layout` only for reviewable AGENT_PLAN actions.
6. After a new render, use `compare_page_composition_diagnostics`.
7. If the phase requires human visual authority, present the criterion-bound review packet and wait for explicit user sign-off.

## Locator boundary

`page:N/block:M` locators extracted from PDF are page-local. They may support a finding such as `PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK`, but they do not establish that two blocks on different pages are the same HWPX paragraph.

Automatic mutation requires a durable document-native locator or a separately proven mapping.

## Repeated furniture

Headers, footers, and narrow page-number blocks should be separated from body-composition geometry when repeated edge evidence supports that classification. Keep the original capture receipt unchanged.

## Cross-archetype generalization

A shared coarse signature such as identical page counts and line counts is a review signal, not automatic failure. Inspect whether archetype differentiation exists at the page-composition level and record the human disposition.

Large first-page lower whitespace can be legitimate for short reports. Treat it as a bounded review signal unless stronger evidence shows a pagination defect.

## Polyglot implementation

Shared semantics are language-independent:

- Python: research/reference and capture normalization.
- Rust: deterministic geometry decisions.
- TypeScript: runtime/product contract parity.
- PowerShell: Hancom/Windows native-world-contact adapter.

A cross-language disagreement on a frozen fixture is a blocking regression.
