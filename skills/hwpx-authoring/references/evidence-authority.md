# Evidence Authority

This reference defines evidence layering for HWPX authoring and review. It complements the routing rules in `../SKILL.md`.

## Authority ladder

Keep these layers distinct:

1. **Native structure** — the HWPX package and document model are structurally valid.
2. **Static diagnostic** — deterministic rules detect mechanically observable design risks.
3. **External render observation** — a non-Hancom renderer provides useful but non-native page evidence.
4. **Hancom-native render evidence** — an identified Hancom executable/version produced the PDF/page raster evidence.
5. **User visual observation** — the user inspected the relevant rendered pages and explicitly accepted, rejected, or qualified a criterion.
6. **Explicit design target** — the user states a desired visual outcome that may guide successor mutation.

Never collapse the ladder into one beauty score.

## No silent promotion

- If rendering was not performed, render verification is pending/not performed, not PASS.
- A static improvement does not imply a native-render improvement.
- Hancom-native render PASS does not imply human visual-review PASS.
- Page-local PDF/raster locators are observational geometry, not durable document identity.
- A heuristic warning may be dismissed by stronger visual/document evidence, but keep the original warning and its disposition in the receipt.

## Human review

A human-review packet should define stable criterion IDs, the machine evidence that motivated each criterion, and the evidence class needed to close it.

For P3.41-R1 the required criteria are:

- `first_page_whitespace`
- `archetype_differentiation`
- `page_boundary_integrity`
- `mechanical_styling`

All four require `USER_VISUAL_OBSERVATION` before a final human PASS. Machine evidence can support the question but cannot satisfy the manual evidence class.

## Mutation claims

When a repair is executed, report what was actually verified. Future pagination-sensitive repair should add a package-part mutation-footprint certificate: expected parts, observed changed parts, unexpected changed parts, and untouched-part byte identity.
