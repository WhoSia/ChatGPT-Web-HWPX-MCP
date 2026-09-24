# P3.37 feature-expansion charter

## Formal phase name

**ChatGPT Web HWPX MCP P3.37 — Deliverable-Grade HWPX Authoring, Native File Return, HWP5 Intake Bridge, Upstream Capability Harvest & End-to-End Document Production**

## Direction change

P3.36 evidence work remains available as a parallel or occasional lane. It is no longer the critical path. The product critical path is now: ask for a document → generate or edit it → return a usable native file.

## Upstream reconnaissance

- treesoop/hwp-mcp (MIT): HWP/HWPX read and render through rhwp/WASM, HWPX create/edit, template fill, Markdown conversion, image/equation handling, and cross-platform execution without Hancom. Primary reference for an HWP5 read/render bridge and document-flow traversal.
- airmang/python-hwpx + python-hwpx-automation (Apache-2.0): pure-Python HWPX object model, create/edit/save validation receipts, document-plan authoring, form filling, CLI/MCP separation, conformance testing, and explicit artifact-return workflows. Treat as first-class upstream dependency/reference instead of reimplementing stable primitives.
- deoksangcho/hwpx-mcp-server (MIT): small stateless filename-explicit MCP surface on python-hwpx. Useful for tool-shape comparison and low-friction local workflows.
- Topabaem05/hwpx-mcp (MIT): broad 120+ tool surface plus a routing gateway that hides most tools behind search/describe/call. Useful as capability inventory and evidence that very large flat MCP surfaces should be mediated.

No source should be copied wholesale. Follow license and NOTICE/attribution requirements; prefer dependency calls, adapter layers, or independently implemented interfaces.

## P3.37 minimum product contract

1. create_and_deliver_document — one call from semantic plan to durable .hwpx artifact and download/resource link.
2. edit_and_deliver_document — edit an owned or imported HWPX and return the revised native artifact in the same call.
3. fill_template_and_deliver — placeholder, field, or template fill with preservation receipt.
4. ingest_hangul_document — sniff bytes, not extension; classify HWPX vs HWP5 vs invalid.
5. HWP5 route — read/extract/render through a bounded adapter, with conversion to HWPX only when fidelity authority is explicit.
6. document_plan expansion — title, headings, paragraphs, lists, tables, images, equations, headers/footers, page setup, captions and controlled page breaks.
7. Artifact UX — every creation/edit operation returns native filename, revision/hash, validation summary and a direct deliverable resource link.
8. Keep P3.21 composer as canonical HWPX writer until an upstream primitive demonstrably improves fidelity or reduces duplicated code.

## First implementation order

Gate A — real file delivery: prove a user can ask for a small Korean report and receive a native .hwpx immediately.

Gate B — template/form workflow: fill a real HWPX form and return the edited file without separate delivery choreography.

Gate C — HWP5 sniff/read bridge: use the P3.36-R2-R2-R1 MOTIR mismatch as the regression fixture for byte sniffing and legacy-format routing.

Gate D — upstream harvest: map local primitives against python-hwpx, python-hwpx-automation and hwp-mcp; replace only duplicated or weaker internals where there is a concrete product gain.

Corpus/style research continues only when a feature decision actually needs new evidence.
