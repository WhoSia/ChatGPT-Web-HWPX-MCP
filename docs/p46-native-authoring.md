# P4.6 Native Authoring Quickstart

P4.6 makes equations, tables, and drawings easier to author without exposing their package internals as the normal workflow.

## Small public surface

For native authoring, prefer five high-level tools:

1. `get_native_authoring_contract`
2. `inspect_native_authoring_capabilities`
3. `compile_native_authoring_bundle`
4. `apply_native_authoring_bundle`
5. `get_real_document_generation_benchmark`

The older low-level tools remain available as compatibility and expert escape hatches.

## One-call mixed authoring

A bundle may contain `equations`, `tables`, and `drawings`. Compilation resolves supported semantic anchors, audits equation capability, and refuses evidence-gated operations before mutation. Application is performed on a temporary HWPX and commits only after final package validation.

The product contract is:

```text
ONE HIGH-LEVEL BUNDLE
  -> PREFLIGHT ALL LANES
  -> MUTATE TEMPORARY HWPX
  -> VALIDATE FINAL PACKAGE
  -> COMMIT ONCE
  -> ONE DURABLE REVISION
```

A failure before the final commit does not authorize a partial durable revision.

## Equation policy

P4.6 accepts LaTeX as **semantic input**, not as a claim that Hancom implements the whole LaTeX language.

Verified examples include:

- fractions: `\\frac{a}{b}`
- roots: `\\sqrt{x}`, indexed roots
- superscripts/subscripts
- integrals, sums, common operators and Greek symbols
- `matrix`, `pmatrix`, `bmatrix`, `vmatrix`
- `cases`
- `\\left ... \\right`
- selected accents such as `\\bar`, `\\vec`, `\\hat`
- plain text literals supported by the upstream verified converter

Hancom's official equation documentation also exposes native script commands `rm`, `it`, `bold`, and `rmbold`, plus vertical pile commands `PILE/LPILE/RPILE` and a `COLOR {r,g,b}` form. P4.6 records these as **documented native candidates**, but they do not bypass the render-certification gate. In particular, `\\mathbf`/bold-symbol intent may have a future `bold` mapping, while `align` may overlap with the PILE family; neither is auto-authored yet.

Known typed refusals include:

- `\\mathbb` — blackboard bold; no corresponding official EqEdit font-style command found in the reviewed command/font documentation
- `\\mathcal` — calligraphic style; no corresponding official EqEdit font-style command found in the reviewed command/font documentation
- `align`
- `Bmatrix` / `Vmatrix`
- `\\widehat` / `\\widetilde`
- `\\overbrace`
- `\\xrightarrow`
- `array`
- other commands outside the render-verified EqEdit vocabulary

The refusal policy is deliberate:

```text
UNSUPPORTED LATEX INTENT
  != PLAIN-TEXT SUBSTITUTION
  != IMAGE SUBSTITUTION
  != QUIET STYLE LOSS

UNSUPPORTED LATEX INTENT
  -> EXPLICIT ABSTENTION
  -> PRESERVE SOURCE
  -> REQUIRE AN EXPLICIT ALTERNATIVE OR NEW NATIVE EVIDENCE
```

This is especially important for mathematical styles: `\\mathbb{R}` must not quietly become `R`, and `\\mathcal{F}` must not quietly become ordinary `F`.

## Tables and drawings

P4.6 does not create a second table or drawing engine. It routes high-level requests to the existing native HWPX transaction authorities.

Table authoring includes creation, text, merges/splits, row/column operations admitted by the backend, cell geometry, margins, border/fill, and deletion. Evidence-gated operations remain closed.

Drawing authoring currently admits native text boxes and rectangles plus bounded layout/geometry transforms. Generic arbitrary-shape fabrication and grouping remain evidence-gated rather than guessed.

## Real-document benchmark

The P4.6 gate generates four HWPX artifacts:

- `technical-note-native-math.hwpx`
- `public-form-table.hwpx`
- `diagrammatic-report.hwpx`
- `mixed-native-authoring.hwpx`

The benchmark requires editor-open safety and native structural maps. It also verifies that unsupported equation semantics remain abstentions.

These checks are **not** a claim of Hancom-native visual perfection. Native render capture and human visual review remain stronger evidence layers.

## Distribution model

The production service remains a remote OAuth-protected Streamable HTTP MCP. A client should normally discover capabilities and use the high-level authoring surface rather than learn HWPX XML or internal object locators.

For a general document request:
- use the established rich/professional authoring workflow for narrative structure and design;
- use the P4.6 native bundle for equations/tables/drawings;
- diagnose/preview after generation when visual quality matters;
- deliver only after the relevant structural, render, and human evidence gates required by the task.
