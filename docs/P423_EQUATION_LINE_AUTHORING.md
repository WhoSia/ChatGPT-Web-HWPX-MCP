# P4.23 native equation line — user-facing authoring

The `equation_line` document-plan block composes **multiple distinct native HWPX
EqEdit equations** in the **same paragraph**, with punctuation stored as plain
paragraph text between equations. This implements the user-accepted correction
from the MRI report: do not fuse unrelated equations with an EqEdit comma.

## Accepted composition plan

See [executable example](../examples/p423_mri_equation_line.json).

```json
{
  "blocks": [
    {
      "id": "two-components",
      "type": "equation_line",
      "parts": [
        {"latex": "x"},
        {"text": ", "},
        {"latex": "y"}
      ]
    }
  ]
}
```

The XML must contain *two* separate `hp:equation` elements with an intervening
`hp:t` holding exactly `, `. This is **not** equivalent to one equation
whose script contains `x, y`. If the document is centered or styled, those
properties belong to the containing paragraph.

Supported `parts` are exactly `{"latex": "..."}` and `{"text": "..."}`.
There must be between 1 and 64 parts. Text spans are limited to 4096
characters each. LaTeX conversion uses python-hwpx's verified converter;
unsupported commands must fail the atomic composition rather than silently
turn into substitute glyphs.

## What is not claimed

- This block does **not** invent `\\mathcal` or other unsupported glyphs.
- It does **not** automatically repair `rm`/ `it` in user expressions or
  parse EqEdit raw scripts from a model. Font state is delegated to the
  verified converter, while native-Hancom validation remains essential.
- The repo tests establish object and punctuation structure, not visual
  inter-glyph spacing and not PDF page-breaking fidelity.
- Production Render still runs the previous deployment until a deliberate
  approved release.

## Acceptance checks

1. Compose the example plan. Assert a single paragraph contains two native
   equations with a text run `, ` in the correct order.
2. Replace the separator with `· ` and ensure the plain text survives.
3. Request an unsupported LaTeX command; confirm there is no output HWPX.
4. Export through **native Hancom Office** and review line height, comma
   baseline, and paragraph centering.
5. Verify the HWPX and PDF retain the existing source document template when
   `template_path` is used, and do not silently alter adjacent content.
