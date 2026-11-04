# P4.23 — Human-corrected EqEdit acceptance protocol

This is an **evidence workflow**, not a promise that XML validity proves native
Hangul rendering. Treat three independent authorities separately.

1. **Package correctness**: ZIP and section XML parse, equation scripts extract.
2. **Edit preservation**: paragraph count and text fragment hashes match when
   an equation-only edit was intended. A mismatch is a review finding, not
   necessarily an error: the RC heading-numbering repair intentionally changed
   text content while preserving the document structure.
3. **Native visual correctness**: render through Hancom Office and compare the
   PDF to a human-accepted target. In-Hancom manual edits can be a provisional
   reference without being a certified visual result.

## Before-and-after workflow

- Keep the original and human-edited HWPX private in the designated Drive
  custody area; do not add complete school reports to the public repository.
- Use `extract_equations()` on each version and verify counts and ordering.
- Use `pair_equations()` to produce hash-only change receipts. The result
  explicitly marks index alignment as **unverified**. Even matching counts and
  partial unchanged anchors do not establish correspondence if a reordered
  script was also modified.
- Use `inspect_document_shell()` and `compare_document_shell()` to detect
  unexpected changes to paragraph count, text fragment boundaries, raw
  non-equation text, and equation count.
- Manually review only the equation excerpts suitable for a public golden
  corpus. Record source version, equation index, actual EqEdit script,
  acceptance status, and separate native-PDF evidence.
- Never auto-insert `rm` or `it` solely because the scanner sees a
  potential upright tail; braces do **not** reset Hancom font state.
- When a conversion is unsupported, preserve the input and return a typed
  unsupported result rather than silently substituting a new expression.

## Verified product cases

- MRI, human-edited: 70 native equations, 71 paragraphs; 122 non-equation
  text fragments in the sampled local copy.
- RC circuit report: 32 paragraphs and 1 native equation in each of the
  original and heading-fix candidate. Text digests intentionally differ;
  this is **not** a failure of the heading-fix acceptance criterion.

## Deployment gates

- Latest commit CI must finish, including the P4.23 tests.
- No bot-attributed commits or unexpected changes to main/Render.
- Ensure runtime dependency and third-party license notices remain intact.
- Obtain a Hancom PDF for at least one representative native equation,
  inline punctuation boundary, equation box, and existing-template edit.
- Keep the PR in draft until the user approves the release criteria.

Source references: [python-hwpx parser](https://github.com/airmang/python-hwpx/blob/main/src/hwpx/equation/eqedit.py)
and [Hancom OWPML resources](https://developer.hancom.com/opensources).
