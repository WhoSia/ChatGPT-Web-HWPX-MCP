# P4.8 Reusable Semantic Document Components

P4.8 raises authoring from individual HWPX blocks to reusable semantic document components while preserving the evidence boundaries established in P4.6–P4.7.

## Public surface

P4.8 exposes five high-level tools:

1. `get_component_authoring_contract`
2. `compile_document_components`
3. `plan_component_repairs`
4. `get_p48_distribution_quickstart`
5. `create_component_document_and_deliver`

The P4.7 unified-authoring and P4.6 native-authoring surfaces remain expert/compatibility layers.

## Component families

| Family | Component | Lowering |
| --- | --- | --- |
| prose | paragraph, callout | native paragraph formatting |
| semantic math | definition, theorem, lemma, proof | heading/body paragraphs + bookmarks |
| equation | equation | P4.6 verified LaTeX → native EqEdit only |
| equation reference | equation_reference | stable compiler label + equation bookmark |
| structured data | data_table | native table with semantic header |
| visualization | bar_chart | P3.26 filled polygons + P3.25 anchored layout/textboxes |
| visualization | kpi_strip | P3.25 textboxes + P3.26 solid fill/stroke |
| media | image | existing native picture/media lane |
| pagination | page_break | native page-break paragraph |

P4.8 does **not** claim a Hancom native chart-object implementation. Its admitted bar/KPI visualizations are deterministic compositions of already admitted native drawing primitives.

`line_chart`, `scatter_chart`, `pie_chart`, and `area_chart` fail closed with `UNSUPPORTED_CHART_PRIMITIVE`. Safe repair choices are data-table, admitted bar chart where semantically appropriate, or a caller/user supplied image.

## Semantic math

The compiler assigns stable labels before surface lowering. An equation component can declare `label: "energy"`; later `equation_reference` components resolve that label to the compiler-assigned equation number.

This is **not** claimed to be a dynamic Hancom equation-number field. The equation anchor receives a bookmark and the reference text is compiler-resolved. P4.7 pending candidates such as `bold`, `EQALIGN`, and other unrendered EqEdit vocabulary are not admitted by P4.8.

Unsupported LaTeX remains a typed compile blocker before mutation.

## Structural visual composition

A bar chart is lowered to:

```text
semantic series
  -> bounded row geometry
  -> native filled polygon per bar
  -> paragraph-relative layout
  -> native label/value textboxes
  -> reserved paragraph spacing budget
```

A KPI strip is lowered to bounded native textboxes with admitted solid fill/stroke styling.

The compiler reserves vertical paragraph budget to reduce overlap risk. Structural generation does not itself establish native-render or human visual authority.

## One-shot authoring

`create_component_document_and_deliver` performs:

```text
COMPONENT SPEC
  -> semantic compile / blockers
  -> P4.7 unified compile
  -> private rich HWPX composition
  -> optional P4.6 native bundle
  -> P4.8 visual primitive lowering
  -> final package validation
  -> static preview-readiness gate
  -> one durable revision 1
  -> delivery
```

Any failure before the durable commit deletes the private candidate.

## Interactive repair

`plan_component_repairs` is advisory and non-mutating. It returns safe alternatives for typed blockers. It never silently rewrites unsupported math or an unsupported chart into a different semantic object.

## Cross-archetype benchmark

The release benchmark materializes:

- TECHNICAL_NOTE
- RESEARCH_REPORT
- POLICY_BRIEF
- LAB_REPORT
- STUDY_GUIDE

Each generated HWPX exercises semantic prose/math, equation reference, native table, bar chart and KPI composition. The benchmark proves structural generation/editor-open safety only; render/human claims stay separate.

## Distribution

Minimal path:

```text
connect remote OAuth MCP
  -> get_component_authoring_contract
  -> create_component_document_and_deliver
  -> consume revision-bound HWPX
```

Use `compile_document_components` and `plan_component_repairs` when the caller needs preflight or interactive repair. Delivery recovery after a committed mutation remains `deliver_document`; never replay the mutation just to obtain another link.
