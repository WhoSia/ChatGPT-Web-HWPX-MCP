# P4.26 — Document Experience & Visual Fidelity: Professional Layout, Native Rendering and Seamless File Delivery

**Started:** 2026-11-11  
**Branch:** `development/p426-document-experience-visual-fidelity-20261111`  
**Base:** P4.25 tested research line, SHA `d1a908ef134cf3c2c9e9528e8d20659498f636bc`

## Outcome

Turn native HWPX composition into a polished, accessible document experience:
consistent design tokens → editable HWPX content → explicit rendering
capability → working MCP file handoff. Retain the P4.25 feature set
but promote page geometry, typography and equation-fidelity diagnostics
to product-level functions.

## Research units (independent evidence)

1. **A — Layout:** reusable named design-token sets; compile into P4.23
   `style_profile` and P3.18 page setup, not another HWPX writer.
   Page body geometry, table fit and image width must be checkable before
   native composition.
2. **B — Native rendering:** capability discovery and render-plan tools
   built on P4.24's actual Windows Hancom PDF bridge or a clearly
   identified optional alternative. Never call XML geometry estimates a
   real image preview. Do not recreate previously deleted local files.
3. **C — Seamless delivery:** the existing P3.33 MCP ResourceLink +
   authenticated revision download must remain directly usable from a
   one-call author/edit tool. Test against actual MCP runtime rather
   than assuming a returned URL appears as a downloadable attachment.
4. **D — Academic quality:** equations remain editable OWPML/HWP
   Equation Editor scripts; provide equation-script diagnostics,
   numbered captions and stable source/reference identifiers.

## Competitor and first-party technology map (2026-11-11)

- Dayoooun/hwpx-mcp: atomic ZIP/XML updates, text `lineseg` reset after
  editing, nested table handling, expression insertion as HWP script.
  **Adopt workflow principles; do not copy unknown upstream code**.
- Topabaem05/hwpx-mcp: Windows COM HWP equation support versus
  cross-platform `python-hwpx` creation; gateway tool search.
- treesoop/hwp-mcp + edwardkim/rhwp: text-in-order Markdown and
  OWPML equation rendering AST (fraction, radicals, arrays, sums,
  relations); optional WASM/CLI SVG/PDF previews. A rendered result is
  renderer-specific, not proof of Hancom equivalence.
- Hancom Developer portal (https://developer.hancom.com/docsmenu):
  HWP Automation (COM/OLE), web editor, document viewer/conversion
  solutions, OWPML/open-source resources.
- Hancom Automation manual:
  https://developer.hancom.com/hwpautomation — lists
  `HwpAutomation.pdf`, `ActionTable.pdf`, `ParameterSetTable.pdf`
  and event-handler guide. **Important license**: personal
  non-commercial Automation use is described as freely available;
  commercial products may require a separate Hancom license.
  Do not imply general commercial rights.

These notes use public claims in the official docs and peer READMEs;
no upstream source code was imported. A competitor's claims of
'perfect compatibility' are not our independent conformance result.

## Acceptance targets

- A single declared design token set controls native page margins,
  typography and heading hierarchy; its digest survives the P3.38
  compile path, not merely the outer request JSON.
- Bad page geometry, wide tables, or oversized images are identified
  before file creation; no automatic destructive edit.
- The native equation's source `latex`, generated EqEdit script and
  retained script digest are distinguishable; supported complex
  expression cases have readable acceptance tests.
- Actual native-generated HWPX reopens with table, picture and
  equation objects; screenshot/PDF behavior only claimed when
  independently rendered.
- MCP tool returns actual Pydantic `CallToolResult` with usable
  `ResourceLink` and retained revision identity.
- Keep exact P4.25 parity; no new signing system or fake PDF created.

**Non-goals**: use/deletion/recreation of the owner's removed
`C:\\p424-validation` directory or deleted survival-rate HWPX,
production deployment without an explicit release decision, or
inflating commit counts with cosmetic/no-op changes.
