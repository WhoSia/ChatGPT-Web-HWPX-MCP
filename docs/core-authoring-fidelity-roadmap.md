# Product Recalibration — Core Authoring Fidelity Before More Rare Lanes

## Why

P3.34 proved that evidence-gated rare-feature promotion works, but rare lanes must
not crowd out the product goal: ordinary users should be able to create and edit
normal Hancom documents with high native fidelity.

After P3.34-R3, the default roadmap shifts to **core authoring fidelity**.

## Current production-capable core surface

### Character / run formatting
- bold, italic, underline, text color, font face, font size, highlight
- strike, underline shape/color, strike shape
- horizontal ratio
- letter spacing / tracking
- shadow, superscript/subscript, outline, emboss, engrave
- whole-run and bounded character-range formatting
- copy/normalize run formatting

### Paragraph formatting
- alignment
- percent line spacing
- left/right/first-line indents
- spacing before/after
- outline level
- keep-with-next / keep-lines
- page/column break controls
- paragraph bottom border
- tab stops + automatic left/right tabs
- bounded paragraph-format copying

### Tables
- create/delete
- merge cells / split merged cell
- cell text
- cell shading / borders
- equalize rows/columns
- insert row by clone
- delete row / delete column
- explicit column widths / autofit
- cell properties, margins, size, border/fill, gradient
- repeat header
- row properties / row height
- vertical alignment
- table page-break mode
- table-wide borders/shading
- P3.34-R1 bounded native column insertion: LEFT/RIGHT, count=1

### Page / section composition
- page size and margins
- columns / column gaps and widths
- headers / footers and removal
- page numbering and restarts
- section start numbering
- add/remove section

### Objects
- image insert/replace/remove, sizing and placement
- textbox / rectangle authoring
- line, ellipse, polygon, arc authoring
- drawing layout / resize / rotation / flip / removal
- stroke/fill/shadow/arrowhead styling
- new group authoring from local member specs and rigid group translation
- diagram composition/lifecycle/design-system layers

### Delivery
- create/edit/validate/export/re-ingest
- revision-bound signed HWPX delivery
- exact-byte HTTP attachment verification

## High-value fidelity gaps to attack next

These are not necessarily absent APIs; many already exist structurally but need
systematic Hancom-native fidelity certification and better bounded semantics.

1. **Typography**
   - exact native letter-spacing units/ranges and zero/negative/positive round-trip
   - Korean/Latin/Hanja font-face mapping and fallback behavior
   - font size, ratio, script, underline/strike combinations
   - mixed-run preservation and style-property deduplication

2. **Paragraph geometry**
   - line-spacing modes beyond the current percent surface
   - exact before/after spacing and first-line/hanging indent semantics
   - tab leader/type semantics and mixed tab stops
   - style inheritance versus direct formatting

3. **Tables**
   - count>1 native column insertion
   - insertion through vertical/horizontal merge combinations
   - split-cell row/column semantics
   - width redistribution versus table-width growth
   - autofit / explicit width / margins interaction
   - complex borders, cell padding, header/page-break behavior
   - mixed rich text inside cells

4. **Common object/layout fidelity**
   - image crop and aspect-ratio semantics
   - textbox inner margins and text formatting
   - object anchoring/wrapping under paragraph/page reflow
   - existing object group/ungroup (P3.34-R3)

## Roadmap correction

- Finish **P3.34-R3** tightly; do not open a long sequence of additional rare
  review/security lanes by default.
- Next major phase:
  **P3.35 — Core Authoring Fidelity, Typography & Paragraph Geometry, Table Editing Completeness, Native Round-Trip Certification & Production Document UX**
- Suggested sequence:
  - **P3.35-R1:** Character Spacing, Font Face/Size, Mixed-Run Native Fidelity
  - **P3.35-R2:** Paragraph Spacing, Line Spacing, Indents, Tabs & Style Inheritance
  - **P3.35-R3:** Table Width/Autofit/Merge-Split/Insertion Native Fidelity
  - **P3.35-R4:** Images/Textboxes/Anchoring/Wrap & Page-Layout Fidelity
  - **P3.35-R5:** End-to-End normal-document authoring benchmark + Hancom open/resave + direct delivery

Rare-feature lanes remain available, but they are now secondary unless they block
normal document authoring.
