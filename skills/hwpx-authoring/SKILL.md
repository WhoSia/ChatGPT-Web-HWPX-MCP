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
8. Apply the bounded plan with **apply_document_design_repairs**. P3.42 requires a measured mutation-footprint certificate and fail-closed preservation-grade enforcement before the atomic commit. Do not reinterpret AGENT_PLAN actions as automatic mutation authority.
9. Inspect the returned `mutation_footprint`; for bounded design repair require `TARGETED_PARTS_ONLY` unless the contract explicitly says otherwise.
10. Re-render when native render authority is available, diagnose again, and use **compare_document_design_diagnostics** for before/after evidence. A package-preservation PASS is not a native-render improvement claim.
11. Deliver only after native validity and the relevant design gates are satisfied or the user accepts remaining warnings.

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
8. get_mutation_footprint_contract / certify_document_revision_mutation_footprint when auditing durable revisions
9. compare_document_design_diagnostics after re-render

Use apply_formatting/apply_table_edits/apply_advanced_table_edits only as repair escape hatches or when the user explicitly requests low-level control.

## Important boundary

A static preview PASS means native/layout mechanics look safe. It does **not** mean the document is visually excellent. Rendered pages or human review are stronger evidence for visual judgments. Use [evidence authority](references/evidence-authority.md) when a claim depends on render or human evidence.


## P3.40 rendered feedback boundary

- Use **compile_semantic_callout_block** when semantic emphasis is needed; it compiles to restrained native structure instead of decorative iconography.
- Long prose inside table cells may now be repaired through the nested-paragraph alignment lane rather than left as a capability gap.
- Header-row contrast and column-width policy are editorial bundles over existing native table primitives.
- Native before/after render verification requires two valid Hancom-native capture receipts. If either side is absent, report render verification as pending rather than infer it from static structure.


## P3.41 page-composition boundary

- After real page capture exists, use **get_page_composition_contract** → **diagnose_page_composition** when page rhythm, density, whitespace, balance, or transitions matter.
- Use **plan_render_guided_page_layout** only for reviewable AGENT_PLAN actions; raster evidence alone does not authorize page-break or narrative mutation.
- After re-render, use **compare_page_composition_diagnostics** and preserve the evidence authority of both sides.
- For locator limits, repeated furniture, cross-archetype signals, human-review criteria, and polyglot semantics, follow [page composition](references/page-composition.md) and [evidence authority](references/evidence-authority.md).


## P3.42 mutation/corpus evidence boundary

- Treat **get_mutation_footprint_contract** as the package-preservation constitution. A generic success flag is weaker than a measured part footprint.
- **apply_document_design_repairs** now fails before commit when observed package-part changes escape its locator-derived expected scope.
- Use **certify_document_revision_mutation_footprint** only when an expected scope is independently known; do not invent the scope after seeing the diff.
- Use **get_corpus_evidence_contract** → **query_corpus_coverage_ledger** when making corpus-support claims. `WITHHELD` and `NOT_APPLICABLE` remain in the denominator.
- Use **query_evidence_grounded_design_generalizations** only for descriptive cross-document candidates. Frequency is not design authority and structural evidence is not visual evidence.
- Follow [mutation footprint](references/mutation-footprint.md), [corpus evidence](references/corpus-evidence.md), and [evidence authority](references/evidence-authority.md) for claim boundaries.


## Cross-MCP and polyglot implementation rule

- External document MCP patterns are harvested in `docs/p341-cross-mcp-architecture-harvest.md`; copy architecture lessons, not entire implementations.
- Prefer stable document-native locators over shifting block indexes for multi-step edits.
- Preserve mutation footprint: future executable page-layout repair should report which HWPX package parts changed and which remained byte-identical.
- Use pre-layout measurement when a reliable native/portable measurement primitive exists; do not rely only on post-render critique.
- Polyglot roles are semantic boundaries, not badges: Python reference/research, Rust exact geometry, TypeScript runtime/product contract, PowerShell Hancom bridge. Add another language only when it owns a real boundary.


## P3.43 organization/template policy boundary

- Use **get_organization_template_adaptation_contract** before treating a house style or institutional template as a design system.
- Normalize hard/soft rules with **validate_organization_design_policy**. Hard constraints outrank preferences and corpus frequency.
- Use **plan_organization_template_migration** before mutation; source receipts must still match the current corpus registry.
- **apply_organization_template_migration** requires P3.42 footprint enforcement plus semantic/structure and immutable-part postconditions before commit.
- Use **adjudicate_cross_template_generalization** only with explicit DISCOVERY/HOLDOUT labels; WITHHELD remains in the denominator.
- Follow [organization/template policy](references/organization-template-policy.md), [mutation footprint](references/mutation-footprint.md), and [evidence authority](references/evidence-authority.md).


## P3.44 autonomous authoring boundary

- Prefer **get_autonomous_authoring_contract** → **start_autonomous_professional_authoring** when the user wants a finished professional document rather than individual editing calls.
- Treat the returned run as a bounded resumable state machine. `WAIT_RENDER` and `WAIT_HUMAN` are evidence pauses, not failures and not permission to invent a PASS.
- Recover state with **get_autonomous_authoring_run** and resume only with the exact run SHA using **resume_autonomous_professional_authoring**.
- Automatic repair is allowed only for locator-bound executable plans, within the repair budget, with P3.42 preservation PASS and any applicable P3.43 organization policy still admissible.
- A repair after render invalidates that render. Re-render the new revision before delivery when render evidence is required.
- Rust owns the production repair/delivery gate; TypeScript independently mirrors state-machine semantics and blind AuthorBench scoring; Python is the HWPX-native adapter; PowerShell/Hancom owns native world contact.
- Follow [autonomous authoring](references/autonomous-authoring.md), [organization/template policy](references/organization-template-policy.md), [mutation footprint](references/mutation-footprint.md), and [evidence authority](references/evidence-authority.md).


## P3.45 document transaction runtime boundary

- Use **get_document_transaction_runtime_contract** before orchestrating multi-step edits that need replay, incremental invalidation, capability negotiation, or external-evidence pauses.
- Express high-level work as declarative Authoring IR and call **compile_document_transaction**; do not manually reorder nodes after compilation.
- Advance bounded work with **advance_document_transaction**. Mutation nodes are never cache-reused, and external-world-contact nodes stop at `WAIT_EXTERNAL`.
- Resolve external nodes only with revision-bound measured receipts through **resolve_document_transaction_external**. Replay never fabricates Hancom/render evidence.
- Use **replay_document_transaction** for read-only time travel and **get_document_transaction_observability** for operational state; observation timestamps are outside deterministic event hashes.
- Use **abort_document_transaction** for explicit cancellation. Never infer a commit after an interrupted RUNNING node.
- Extension manifests are declarations only: validate with **validate_document_runtime_extension**; no arbitrary extension code is loaded. Host adapters remain allow-listed.
- Follow [document transaction runtime](references/document-transaction-runtime.md), [mutation footprint](references/mutation-footprint.md), and [evidence authority](references/evidence-authority.md).
