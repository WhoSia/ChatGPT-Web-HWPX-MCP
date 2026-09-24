# P3.37 upstream capability harvest

Frozen reconnaissance date: 2026-09-24.

## Repositories inspected

| Repository | Frozen head | License observed | P3.37 decision |
|---|---|---|---|
| airmang/python-hwpx | 189a8b2f622d29ec93230fbd70203946d89a4f19 | Apache-2.0 | Keep as the core HWPX engine dependency. Prefer stable public primitives when they measurably replace weaker local XML work. |
| airmang/python-hwpx-automation | 8e8b95a8adff5d6a86e853a119a081c3c410512a | Apache-2.0 | Harvest workflow design now, especially declarative authoring and analyze→apply→verify form fill. Do not add a second overlapping custody/MCP stack yet. |
| treesoop/hwp-mcp | 4a93489d4f7dd316279b5f6f5d83014d9a8063f4 | MIT | Keep rhwp/WASM HWP/HWPX read/render as an alternate oracle/reference. Existing native HWP5 reader remains primary until measured replacement value exists. |
| deoksangcho/hwpx-mcp-server | 92cd24f5c18fbcc1a4a20cc3447e761d2bf8c1c5 | MIT | Harvest the small user-facing tool surface and explicit-file workflow shape. |
| Topabaem05/hwpx-mcp | 5993e014dd5bec68770379f2532ed0c1502a9952 | License not adjudicated in this receipt | Harvest only the gateway idea: tool_search/tool_describe/tool_call/route_and_call over a large backend capability inventory. No code copied. |

## Adopted in P3.37

1. Narrow product surface over a large backend. Four primary user-facing workflows are promoted: create+deliver, edit+deliver, template fill+deliver, unified Hangul intake.
2. Bytes before extensions. HWPX/HWP5 classification is based on package/signature evidence. This directly addresses the P3.36-R2-R2-R1 public-source .hwpx→HWP5 mismatch.
3. Copy/clone before template mutation. Template fill writes a new document and never mutates the source template.
4. Plan/validate/atomic apply receipts. Literal placeholder fill is deliberately narrower than python-hwpx-automation mixed-form fill, but follows the same fail-closed transaction principle.
5. No wholesale fork. Upstream code is not copied into this repository. Any later dependency or code reuse must preserve license and NOTICE obligations.

## Deferred harvest

- python-hwpx-automation mixed form resolution across native fields, labeled cells, canonical paths, and body anchors.
- Render/preview adapters as an optional self-check layer.
- Tool-RAG/gateway routing for the large advanced MCP surface.
- rhwp as a second HWP5 parser/render oracle where a differential test demonstrates concrete value.
