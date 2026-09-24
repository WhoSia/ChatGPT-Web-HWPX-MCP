# P3.39 — Cross-format document MCP design harvest

This audit is architectural. It does not copy upstream implementation wholesale.

## SecurityRonin/docx-mcp

Useful pattern: a companion Skill teaches the agent the workflow, not only tool names. Its editing sequence explicitly requires structure inspection, exact targeting, audit, then save. The project also records hard-won layout/OOXML constraints such as table width and cell-margin reasoning.

Harvest: ship an HWPX authoring Skill and make verify-before-mutate part of the product contract.

## xpm-cmd/docgem-mcp

Useful patterns: high-level generators, theme presets, template scanning before filling, template-preserving bridges, and content-type heuristics. It separates theme/template assets from content payloads.

Harvest: prefer archetype/theme intent over dozens of raw style values; inspect template structure before fill.

## TheBatashev/MCP-Documents

Useful pattern: both one-shot complete-document generation and incremental session construction exist, while generated documents are exposed as resources.

Harvest: preserve both one-call authoring and lower-level iterative escape hatches; keep artifact delivery first-class.

## Topabaem05/hwpx-mcp

Useful pattern: deterministic tool-RAG gateway exposes search/describe/call rather than forcing the model to reason over the entire backend tool surface. Routing is deterministic/testable and tool identity is schema-sensitive.

Harvest: reduce agent cognitive load; high-level authoring tools and design contracts should be preferred over broad primitive discovery.

## mcpOffice

Useful pattern: acceptance is defined on a real file through the live MCP, not only helper scripts. Repository guidance makes runtime tool awkwardness itself a product defect instead of encouraging scratch workarounds.

Harvest: AuthorBench and OAuth/live-file acceptance remain product gates.

## Resulting P3.39 architecture

Agent intent
→ document archetype
→ semantic outline
→ authoring strategy
→ rich native builder
→ static design diagnostics
→ optional render/human evidence
→ minimal repair plan
→ re-diagnosis
→ native delivery.

Static diagnostics never claim rendered beauty. Human visual review remains high-value evidence but is not promoted to a universal aesthetic norm.
