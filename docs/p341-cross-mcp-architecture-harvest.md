# P3.41 Cross-MCP Architecture Harvest

## Purpose

This note records architecture patterns worth transferring into ChatGPT Web HWPX MCP. It is not a feature checklist and it does not authorize wholesale copying. The criterion is whether a pattern strengthens HWPX-native authoring, page-composition evidence, mutation safety, delivery, or agent tool economy.

## Surveyed MCPs and transferable patterns

### mhackermsft/OfficeMCP (.NET)
Source: https://github.com/mhackermsft/OfficeMCP

- Progressive tool disclosure keeps the active tool surface small while retaining format-specific depth.
- A unified office-level API coexists with Word/Excel/PowerPoint-specific operations.
- Ordered rich reading keeps headings, paragraphs, tables, and images in document sequence instead of returning images through a detached side channel.

**HWPX transfer:** keep high-level authoring/design tools primary, expose low-level native primitives only when the task or evidence requires them. Preserve reading order in future visual/object inventories.

### ycnslh/office-mcp (streamable HTTP)
Source: https://github.com/ycnslh/office-mcp

- Formatting rules are published as MCP resources rather than repeated in every tool description.
- Storage is abstracted behind local/remote backends.
- Mutating calls return user-consumable signed delivery URLs.
- Per-request user context is separated from document-engine code.

**HWPX transfer:** move durable design-system guidance toward versioned resources/contracts; keep storage/delivery and document semantics separable; retain resource-style download delivery rather than leaking filesystem paths.

### SecurityRonin/docx-mcp
Source: https://github.com/SecurityRonin/docx-mcp

- Structural reading, tracked changes, comments, and change summaries are first-class.
- Document comparison produces an explicit change artifact rather than relying on opaque mutation success.
- Validation and review are part of the editing workflow.

**HWPX transfer:** continue receipt-first mutation and before/after evidence. Future page-layout mutation should emit a reviewable structural/render delta, not merely a success flag.

### knorq-ai/docx-mcp-server
Source: https://github.com/knorq-ai/docx-mcp-server

- Stable paragraph anchors avoid index-shift failures across multi-step edits.
- Page-layout operations are explicit rather than hidden inside generic formatting.

**HWPX transfer:** strengthen durable locator identity for page-composition repair. A page/raster locator must never substitute for a document-native locator when mutation authority is granted.

### Mavline/docx-mcp-server (TypeScript)
Source: https://github.com/mavline/docx-mcp-server

- OOXML parts are loaded on demand.
- Dirty-part optimization writes only modified package parts.
- Relationship/part/style/table/drawing logic is separated into modules.

**HWPX transfer:** add a future mutation-footprint certificate: which HWPX package parts changed, which were byte-identical, and whether the changed-part set is compatible with the requested repair.

### jwingnut/mcp-libre
Source: https://github.com/jwingnut/mcp-libre

- Native application integration through LibreOffice/UNO provides live document manipulation and visual feedback.
- Consolidated tools reduce agent routing burden.

**HWPX transfer:** treat the Hancom COM bridge as a durable native-world-contact adapter, not a disposable benchmark script. Keep the product tool surface consolidated even if the native adapter grows internally.

### mcp-z/mcp-pdf
Source: https://github.com/mcp-z/mcp-pdf

- Text measurement is available before final layout.
- PDF pages can be rendered to images as an explicit primitive.

**HWPX transfer:** P3.41 should eventually combine post-render diagnosis with bounded pre-layout measurement. Render-after-the-fact critique alone is insufficient for efficient composition.

### searaylee/office-mcp-server
Source: https://github.com/searaylee/office-mcp-server

- Templates can be learned and reused rather than only hard-coded.

**HWPX transfer:** defer template-learning to the P3.42/P3.43 corpus/design-system lineage, where learned patterns are separated from frozen evaluation specimens.

## P3.41 adoption decisions

1. **Adopt now — cross-language semantic parity.** Python remains the research/reference layer; Rust is the deterministic geometry kernel; TypeScript must execute the same golden-fixture decisions at runtime, not merely compile interfaces; PowerShell owns Windows/Hancom world-contact.
2. **Adopt now — locator authority separation.** Page-local PDF/raster locators remain observational. Automatic mutation requires durable HWPX identity.
3. **Adopt now — consolidated product surface.** Page-composition primitives should be internal; agent-facing tools remain small and high-level.
4. **Prepare successor — mutation-footprint certificate.** Inspired by dirty-part/conservative-mutation designs, later executable layout repair should record changed HWPX package parts and unrelated-part preservation.
5. **Prepare successor — design rules as resources.** P3.42/P3.43 may expose archetype/design-system contracts as versioned resources instead of expanding every tool schema.
6. **Prepare successor — pre-layout measurement.** Page-composition planning should eventually use text/table measurement before committing a pagination-sensitive mutation.
7. **Reject — language-count optimization.** A new language is added only when it owns a technically distinct boundary and can be parity-checked against shared semantics.

## Polyglot constitution

> Polyglot by comparative advantage, not by language count.

The scientific/product semantics are language-independent. Implementations may be specialized. A disagreement between Python, Rust, and TypeScript on a frozen geometry fixture is a regression and blocks P3.41 authority.
