# P4.23 — Portable personal document styles (product workflow)

The P4.23 document composer accepts a **caller-supplied** `style_profile`
inside an ordinary `create_document_from_plan` or `generate_document`
plan. Its purpose is to make repeat HWPX authoring simple without requiring
the user to send dozens of per-paragraph formatting calls.

## Start from an accepted document style

An explicit JSON profile may override safe, bounded aspects of a preset:

```json
{
  "preset": "school-report",
  "style_profile": {
    "name": "science-report",
    "roles": {
      "body": {
        "run": {
          "size": 11,
          "font_by_script": {"hangul": "함초롬바탕", "latin": "Malgun Gothic"}
        },
        "paragraph": {"line_spacing_percent": 160}
      },
      "title": {
        "inherits": "body",
        "run": {"bold": true, "size": 20},
        "paragraph": {"alignment": "CENTER"}
      }
    },
    "page": {"margin_left_mm": 25, "margin_right_mm": 25},
    "equation_base_unit": 1250
  },
  "blocks": [{"id": "t", "type": "title", "text": "실험 보고서"}]
}
```

[Executable full example](../examples/p423_personal_science_report.json)

The style inheritance mechanism was informed by
[HwpForge's Blueprint model](https://github.com/ai-screams/HwpForge/blob/main/docs/guide/style-templates.md):
document content is authored independently of appearance, typography roles
inherit from named roles, and nearest explicit override wins. We did **not**
copy Rust source or adopt arbitrary YAML execution in the MCP.

## Precedence and non-surprises

- Built-in preset is the foundation.
- Profile is next; heading roles can explicitly inherit `body`.
- A given block's `run_format`/`paragraph_format` overrides the profile.
- Page setup overrides preset margins, but explicit `plan.setup` is last.
- Table defaults follow preset → profile → table-specific format.
- An equation's own `base_unit` overrides the profile's
  `equation_base_unit`.
- Unknown keys, unsupported font ranges, missing parent styles, inheritance
  cycles and non-JSON data are rejected *before* output replacement.
- A created HWPX retains its original authored content; a profile only
  changes permitted formatting. Receipts expose a canonical profile SHA-256,
  not a claim of visual acceptance.

## Portable personalization and privacy

This is **per-request opt-in personalization**, not ChatGPT memory and not a
server-side profile database. The user can save the JSON alongside a document
and resend it for reuse or make per-document overrides. No implicit ingestion
of private reports, no cross-user profile lookup, no automatic extraction of
preferences from unconsented documents, and no storage of the profile as a
publicly shareable corpus.

A future authenticated profile store would require CRUD, access control,
explicit consent, revision history, retention/deletion and isolation tests.
It should be implemented on the existing owner-scoped document infrastructure
rather than creating an unauthenticated public collection.

## Competitor lessons and limits

- [HwpForge](https://github.com/ai-screams/HwpForge): explicit
  type-checked style inheritance; **now implemented** at the role level.
- [kordoc agency pack](https://github.com/chrisryugj/kordoc/blob/main/docs/agency-pack.md):
  exemplar-guided institutional formats with warnings for outliers and
  remaining text; **not yet imported or claimed** in our user style profile.
- [python-hwpx-automation](https://github.com/airmang/python-hwpx-automation/blob/main/docs/skill-first-workflows.md):
  thin task-level orchestration over reusable, existing editing tools;
  do not proliferate 100+ separate user-facing tools.

The next gate is to run the JSON plan, compare native HWPX formatting
readback against the intent, and inspect the **real Hancom-rendered** PDF for
font substitution, line wrapping, table borders, equation baselines and
pagination. A source-level signature or passing parser test alone is not a
native visual quality certificate.
