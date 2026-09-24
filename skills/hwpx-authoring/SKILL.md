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
6. If render evidence or human review exists, pass it back into diagnosis. Never collapse static, rendered, and human evidence into one beauty score.
7. Call **plan_document_design_repairs**. Apply only supported, locator-bound repairs; leave capability gaps explicit.
8. Re-diagnose after every mutating repair transaction.
9. Deliver only after native validity and the relevant design gates are satisfied or the user accepts remaining warnings.

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
5. plan_document_design_repairs

Use apply_formatting/apply_table_edits/apply_advanced_table_edits only as repair escape hatches or when the user explicitly requests low-level control.

## Important boundary

A static preview PASS means native/layout mechanics look safe. It does **not** mean the document is visually excellent. Rendered pages or human review are stronger evidence for visual judgments.
