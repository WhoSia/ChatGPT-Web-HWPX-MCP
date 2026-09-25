---
name: hwpx-authoring
description: "Use for professional Korean HWPX document creation, redesign, template filling, or design review with ChatGPT Web HWPX MCP."
---

# HWPX Authoring Skill

## Goal

Produce an editable native HWPX that is not merely valid, but readable, professionally structured, and aligned with the user's intended document archetype.

## Required workflow

1. **Classify the document archetype** before choosing fonts, colors, or table styling.
2. **Plan semantic roles and narrative order**: title, summary, key judgment, sections, tables/callouts, conclusion, references.
3. Call **prepare_authoring_strategy**. Treat its design-system directives as the default contract.
4. Use **create_rich_document_and_deliver** for the first native artifact. Prefer a high-level rich plan over many low-level formatting calls.
5. Call **diagnose_document_design** before treating a structurally valid file as visually successful.
6. When page capture exists, call **diagnose_rendered_document_design** so validated page geometry is layered over the static diagnosis. Keep non-Hancom render evidence explicitly below Hancom-native world contact.
7. Call **plan_executable_document_design_repairs**. Prefer native, locator-bound repairs for table reading geometry, padding, header contrast, section separators, and safe column-width rebalancing.
8. Apply the bounded plan with **apply_document_design_repairs**. Do not reinterpret AGENT_PLAN actions as automatic mutation authority.
9. Re-render when native render authority is available, diagnose again, and use **compare_document_design_diagnostics** for before/after evidence. A static improvement is not a native-render improvement claim.
10. Deliver only after native validity and the relevant design gates are satisfied or the user accepts remaining warnings.

## Design constitution

- Semantic importance must have visual consequence.
- Long prose follows reading geometry, not centered symmetry.
- Dense blocks need width/padding/whitespace budget.
- Hierarchy should use multiple channels: size, weight, whitespace, rule/background, placement.
- Executive summary may appear early; formal conclusion belongs after the main development.
- Color, boxes, and icons encode meaning. They are not default decoration.
- Professional reports avoid emoji/icon ornament unless explicitly appropriate.
- The agent chooses archetype and semantic intent. The compiler should choose most raw formatting values.
- Prefer minimal evidence-bound repair over global restyling.

## Tool economy

For normal professional authoring, prefer:

1. get_document_design_intelligence_contract
2. prepare_authoring_strategy
3. create_rich_document_and_deliver
4. diagnose_document_design
5. diagnose_rendered_document_design when page evidence exists
6. plan_executable_document_design_repairs
7. apply_document_design_repairs
8. compare_document_design_diagnostics after re-render

Use apply_formatting/apply_table_edits/apply_advanced_table_edits only as repair escape hatches or when the user explicitly requests low-level control.

## Important boundary

A static preview PASS means native/layout mechanics look safe. It does **not** mean the document is visually excellent. Rendered pages or human review are stronger evidence for visual judgments.


## P3.40 rendered feedback boundary

- Use **compile_semantic_callout_block** when semantic emphasis is needed; it compiles to restrained native structure instead of decorative iconography.
- Long prose inside table cells may now be repaired through the nested-paragraph alignment lane rather than left as a capability gap.
- Header-row contrast and column-width policy are editorial bundles over existing native table primitives.
- Native before/after render verification requires two valid Hancom-native capture receipts. If either side is absent, report render verification as pending rather than infer it from static structure.


## P3.41 page-composition boundary

- After a real page capture exists, call **diagnose_page_composition** in addition to element-level P3.40 diagnosis when page rhythm, density, whitespace, or cross-page transitions matter.
- Use **get_page_composition_contract** to select the declared archetype and understand its bounded thresholds. These thresholds produce named evidence signals; they are not a beauty score.
- Use **plan_render_guided_page_layout** to turn page-level findings into reviewable layout policy. P3.41 deliberately keeps these as AGENT_PLAN: raster evidence alone does not authorize automatic page-break or narrative mutation.
- Use **compare_page_composition_diagnostics** only to claim before/after page-composition change when both sides carry the required evidence. Native Hancom authority must not be inferred from static structure.
- Repeating page furniture is separated from body-composition geometry using repeated edge evidence; do not treat headers, footers, or narrow page numbers as body density.
- Treat PDF-extracted `page:N/block:M` locators as page-local geometry only. They may justify `PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK`, but never promote that heuristic to cross-page paragraph identity without a durable document locator.
- Internal implementation follows polyglot-by-comparative-advantage: Python research/reference semantics, Rust deterministic geometry decisions, TypeScript product contract, PowerShell Hancom world contact. Cross-language disagreement is a regression, not an acceptable implementation detail.
