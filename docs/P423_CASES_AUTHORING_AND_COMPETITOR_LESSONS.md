# P4.23 — Native cases authoring and competitor-informed typography

## User problem

Users should not need to manually type a growing list of `~` spaces to
align piecewise formulas. A Hancom EqEdit `cases` block is a true grid:
`&` separates columns, `#` separates rows. The native EqEdit `~`
represents a visible spacing token; the backtick is a smaller space. These
are not synonyms for `&` and should not replace structural alignment.

The currently tested `python-hwpx` authoring converter maps:

```text
LaTeX: \\begin{cases} x & x>0 \\\\ 0 & x\\leq0 \\end{cases}
EqEdit: cases {x & x > 0 # 0 & x leq 0}
```

See [upstream source tests](https://github.com/airmang/python-hwpx/blob/main/tests/test_equation_authoring.py) and [EqEdit token parser](https://github.com/airmang/python-hwpx/blob/main/src/hwpx/equation/eqedit.py). Do not assume the rendering engine reproduces every TeX spacing command.

## New product feature

Use a declarative `piecewise` block in the ordinary document plan:

```json
{"type": "piecewise",
 "rows": [
   {"expression": "x^2", "condition": "x>0"},
   {"expression": "0", "condition": "x\\leq0"}
 ]}
```

The MCP creates a single native HWPX equation via `document.shapes.add_equation`.
If the user **explicitly requests** extra spacing within the second column,
`"condition_gap": 1` to `4` adds that many `~` tokens. Default is 0;
never derive manual spacing from character counts. Inspect real Hancom PDF
before claiming visual alignment or stable baseline.

Each row also accepts `"condition_text": "양수"` as a mutually exclusive
alternative to `"condition"`. The MCP converts this literal through the
upstream verified `\\text{...}` path so ordinary Korean labels are upright;
dangerous control characters and malformed mixing are rejected.

The expression and condition inputs are **LaTeX**, not raw EqEdit.
The upstream converter rejects unsupported commands and incorrectly placed
bare `&`; legitimate inner matrix column separators are allowed.
Mixed one-column/two-column rows are rejected to avoid deceptive alignment.

## Competitive lessons applied

- `python-hwpx-automation`: high-level workflow compiler, not raw XML editing
  expected from the user.
- `kordoc`: test real visual output against Hancom, not merely XML syntax.
- `HwpForge`: expose per-document and reusable style preferences as structured
  data rather than scattered formatting patches.
- `korean-report-hwpx`: context-specific rules are distinct from universal
  rendering guarantees.
- `flamingo8006/hwpx-mcp`: provide one-call authoring, not 100+ calls for one
  case split.

Next product gates: native PDF and baseline alignment on MRI/cases examples,
actual template preservation, per-user style profile opt-in, identical
competitor tasks on same hardware and exact version. This branch is **not**
deployed to Render or an authorized visual oracle.
