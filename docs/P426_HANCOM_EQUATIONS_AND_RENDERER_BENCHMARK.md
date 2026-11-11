# P4.26 — Hancom Developer Tools, Peer MCPs and Editable Equation Fidelity

**Date:** 2026-11-11  
**Research unit:** equation authoring, preview backends, and first-party tooling  
**Repository:** WhoSia/ChatGPT-Web-HWPX-MCP  
**Scope:** implementation decisions and public technical evidence, not a product marketing ranking

## 1. First-party Hancom technology

| Official developer offering | Evidence | Appropriate use in our architecture |
|---|---|---|
| HWP Automation (OLE/COM) | https://developer.hancom.com/hwpautomation | Native Windows Hancom generation/print/PDF reference, action/parameter APIs |
| ActionTable / HwpAutomation / ParameterSetTable / Event handler PDFs | linked from above | Exact COM action names and parameter set semantics for future Windows worker improvements |
| Web Hangeul drafting editor | https://developer.hancom.com/docsmenu | Potential browser-based interactive editing UI if licensed/integrated |
| Integrated Document Viewer | https://developer.hancom.com/tools | Potential browser viewer/conversion UX; not assumed free/embedded |
| Open source / OWPML model | https://www.hancom.co.kr/service/developer | XML representation and interchange research; distinguish official schemas from proprietary components |

**License boundary:** Hancom's official Automation guide describes free
noncommercial use by individuals. It says applications/solutions for commercial
purposes require separate Hancom approval/licensing. This repo does not
assume that the availability of an SDK/download means general commercial
redistribution rights. The browser editor/viewer are potential licensed
integrations, not libraries installed into P4.26.

## 2. Competitor equation workflows

| Source | Authoring path | Rendering | Product lesson |
|---|---|---|---|
| Dayoooun/hwpx-mcp | Explicit native HWP equation script insertion | HWPX package editing; platform viewer for visual result | Expose native script, don't silently flatten math to text |
| Topabaem05/hwpx-mcp | Windows COM HWP equation APIs; Python HWPX creation otherwise | Native Windows PDF path with platform variance | Document backend and exact platform restrictions |
| treesoop/hwp-mcp | rhwp/WASM OWPML equation extraction and document traversal | SVG/HTML rendering via rhwp | Keep math in flow and expose a renderer without requiring Windows |
| edwardkim/rhwp | HWP EqEdit expression AST: fractions, matrices, roots, integrals, summations | SVG/PNG/PDF and browser Canvas backends | Separate parser/script support from actual glyph/layout validation |
| **Our P3.21 + P4.26** | LaTeX → `hwpx.equation.latex_to_eqedit` → native HWPX equation object | Real Hancom COM PDF on supported Windows worker; optional rhwp SVG page preview | Preserve editable object and provide visible script digest + renderer authority |

Peer sources:
- https://github.com/Dayoooun/hwpx-mcp
- https://github.com/Topabaem05/hwpx-mcp
- https://github.com/treesoop/hwp-mcp
- https://github.com/edwardkim/rhwp
- https://github.com/edwardkim/rhwp/blob/main/mydocs/manual/cli_commands.md

The upstream authors' feature lists are claims made by those projects.
We did not import or redistribute any peer code in P4.26. Code copying
in a subsequent unit must carry appropriate upstream license notices.

## 3. Equation acceptance and known limits

The P4.26 `preview_native_equation_script` tool returns both LaTeX and
the actual HWP EqEdit script plus independent SHA-256 digests. It labels
the output `SCRIPT_COMPILATION_ONLY`, not a rendered image. The
`inspect_document_equations` tool reads actual persisted OWPML script,
paragraph location, base unit and object geometry from an owned revision.

GitHub Actions installed the repository's exact `python-hwpx` dependency
and exercised representative expressions:

- `V=IR` — plain math
- `\\frac{a+b}{c}` — fraction
- `\\sqrt{x^2+y^2}` — radicals
- `\\sum_{i=1}^{n} i` — summation
- `\\int_0^1 x^2 dx` — integral
- `\\begin{matrix}a&b\\\\c&d\\end{matrix}` — matrix

**Actual discovered incompatibility:** `\\,` (LaTeX thin-space)
caused `UnsupportedLatexError: unsupported LaTeX escape: \\,` in
the installed `hwpx.equation` parser. The P4.26 user-facing preview
now returns `LATEX_TO_EQEDIT_UNSUPPORTED` explicitly. It does not
silently strip math spacing, display a text approximation, or claim
that an HTML/SVG rendering is equivalent to a native editable equation.
Follow-up engineering can add a documented, opt-in dialect
normalization step shared with the actual document writer.

**Remaining tests:** piecewise, aligned multiline equations, matrix
brackets, summation sub/superscripts with Hangul text, baseline and
glyph metrics in Windows Hancom. No across-engine visual parity claim.

## 4. Rendering and delivery separation

1. P3.21 generates a real HWPX ZIP with editable OWPML objects.
2. P4.26 design tokens compile to the existing P4.23 native
   `style_profile` and P3.18 page setup. The P3.38 rich-plan compiler
   now carries that profile to P3.21 instead of dropping it.
3. P4.26 `assess_native_layout` flags approximate body-width issues.
   It is not a page renderer.
4. P4.26 optional `rhwp export-svg ... --json -p N` adapter can
   render a requested page when an external rhwp executable is present.
   It validates JSON output, retained source checksum and SVG page
   artifacts. `preview_document_svg_pages` can return bounded
   Base64 SVG page data for an authenticated document. Its authority is
   `THIRD_PARTY_SVG_NOT_NATIVE_HANCOM`.
5. P4.24 Windows Hancom COM worker remains the native PDF compatibility
   reference where actually installed. We do not silently launch
   Windows COM from a Linux-hosted MCP server or substitute SVG for PDF.
6. P3.33 HWPX artifact delivery uses a revision-bound MCP
   `ResourceLink`; user-facing ChatGPT host attachment handling must
   still be observed in a live client before calling it complete.

## 5. Evidence register

- Native test at GitHub Actions run `42932979939`: 59 P4.25 tests
  plus 29 P4.26 tests passed, including a real temporary HWPX
  typography+page-setup roundtrip.
- A later development CI run `42933734342`: 59 inherited P4.25 tests
  plus 36 P4.26 tests passed, including a real native bookmark
  and page-cross-reference test and MCP reference inspection.
- Renderer adapter tests employ a mocked `rhwp` process; an actual
  rhwp binary has **not** been installed or run by this development
  session. Real Windows PDF visual acceptance and live host
  downloadable-attachment acceptance are also **not established**.

## Next priorities

- Add explicit, shared equation dialect compatibility and style/glyph
  test corpus rather than unsupported macro guessing.
- Host-rendered, page-by-page SVG browsing with a real rhwp install,
  then independent native Hancom PDF comparison if licensed and
  available.
- Add stable reference keys and native refresh semantics; page-crossref
  cached values should not be treated as final page locations.
- Carry real MCP ResourceLink through to observable ChatGPT download.
