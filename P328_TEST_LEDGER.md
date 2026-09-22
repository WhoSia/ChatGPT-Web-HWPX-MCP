# P3.28 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.28 — Shape Text & Labeled Nodes, Callouts, Declarative Diagram Plans, Flowchart/Org-Chart Macros & Production High-Level Diagram Authoring Expansion**

## Lineage

P3.28 is a high-level authoring promotion, not a second drawing/composition engine.

- P3.25 supplies drawing inventory plus native drawing/textbox geometry ancestry.
- P3.26 supplies dedicated native rect/ellipse/polygon/line styling/authoring support.
- P3.27 supplies bounded floating placement, static connectors and diagram composition.
- upstream python-hwpx supplies real-corpus-backed `HwpxOxmlShape.set_draw_text()` / `hp:drawText`.
- P3.28 promotes those primitives into labeled nodes, composite callouts, validated plans and reusable flowchart/org-chart macros.

## Native shape-text authority

Admitted shape-text host families:
- `rect`
- `ellipse`
- `polygon`

Admitted semantics:
- one native `hp:drawText` plain-text label
- bounded `textMargin`
- optional editable flag
- set/remove label on an existing admitted top-level shape
- label read-back + `shape_text_sha256`

Deferred:
- arbitrary mixed-run rich shape text
- unsupported host families without measured drawText ownership

## Labeled-node macros

Semantic node kinds compile to dedicated native shapes:
- `process` → rectangle
- `terminator` → ellipse
- `decision` → diamond polygon
- `data` → parallelogram polygon
- `node` → rounded rectangle

All authored nodes are floating, paragraph-anchored and carry native `hp:drawText`.

## Callout boundary

P3.28 does **not** invent an unmeasured native Hancom callout/autoshape family.

Admitted callout semantics are:
**COMPOSITE_CALLOUT = labeled native node + static pointer line**

The pointer is materialized geometry only. It does not carry smart endpoint binding or automatic rerouting.

## Declarative diagram plans

Supported layouts:
- `LEFT_TO_RIGHT`
- `TOP_DOWN`

Bounds:
- nodes: 1..32
- edges: 0..64
- unique bounded node ids
- no self-loop
- all edge endpoints must resolve inside the plan
- bounded HWPUNIT origins/gaps
- explicit node coordinates may override deterministic auto-placement

Validation returns:
- normalized layout
- node/edge counts
- node ids
- deterministic `plan_sha256`
- connector semantics receipt

Plan execution is revision-guarded and atomic at the package transaction boundary.

## Reusable macros

### Flowchart
- 2..32 steps
- string steps auto-promote first/last to terminators and intermediates to process nodes
- object steps may select admitted semantic node types
- default sequence edges may be overridden explicitly

### Org chart
- recursive id/label/children tree input
- bounded flattening into nodes/edges
- deterministic depth/rank placement
- compiles through the same validated diagram-plan path

## Evidence gates

Closed in P3.28:
- native callout/autoshape family
- smart connector routing / `subjectIDRef` endpoint binding
- arbitrary mixed-run rich text inside `hp:drawText`
- renderer-aware collision avoidance
- automatic page-break/page-overflow optimization

Authority remains structural until a P3.28-specific Hancom-native render batch is executed.

## Regression

Dedicated P3.28 corpus: **8 source→target pairs**

1. labeled-rect
2. labeled-ellipse
3. labeled-diamond
4. callout
5. plan-ltr
6. plan-topdown
7. flowchart
8. org-chart

Release smoke:
- creates a four-node Start → Work → Check → End flowchart
- reopens the HWPX
- requires exactly four labeled nodes
- verifies all native drawText labels

## MCP surface

Added:
- `get_high_level_diagram_contract`
- `validate_high_level_diagram_plan`
- `get_high_level_diagrams`
- `apply_high_level_diagrams`

Production version:
- `0.9.0-p3.28`
- phase `P3.28`

Authenticated OAuth lifecycle exercises the high-level diagram surface and participates in the existing map/edit/diff/export/re-ingest/cleanup chain.

## Candidate failure and repair

Initial integrated candidate failed because the server-facing validation alias shadowed/imported the P3.28 validator and recursively called itself.

Repair:
- commit `1ac642468ebb1057d3f772556cccd8ea59b860c8`
- message: `P3.28: fix diagram-plan validator alias recursion`
- lifecycle run **#648** subsequently completed SUCCESS.

This was a transport/integration alias bug, not a failure of native drawText or diagram-plan semantics.

## Historical-probe continuity repair

The old P3.9 HWP world-contact workflows were still waiting for literal server version `0.9.0-p3.9`, so every modern `server_p2.py` change made those otherwise-valid probes red.

P3.28 repaired this release-quality debt:
- version-specific startup assertion removed
- health gate now checks current ChatGPT-Web-HWPX-MCP identity + durable Postgres health
- matcher is phase-number independent, so later P3.x releases do not require another edit

Confirmed:
- P3.9 real-world control-graph / rich-promotion probe **#66 — SUCCESS**
- P3.9 nested-flow / round-trip fidelity probe **#59 — SUCCESS**

The probes exercised real HWP fixtures and OAuth-native parser/Common-IR/rich-promotion/nested-flow/equivalence paths on the current server.

## Candidate confirmation

Candidate head:
`93e122bb2a36f22cf89b04283552c76f379fa6b5`

Lifecycle:
- run **35692134254**
- run number **#654**
- conclusion **SUCCESS**
- compile PASS
- P3.28 unit coverage PASS
- 8-pair product regression materialization PASS
- OAuth server/discovery PASS
- authenticated high-level diagram lifecycle PASS
- export/re-ingest/cleanup PASS

Production boundary:
- run **35692134253**
- run number **#653**
- conclusion **SUCCESS**

Historical continuity:
- control-graph run **35692132101 / #66 — SUCCESS**
- nested-flow run **35692134252 / #59 — SUCCESS**

Candidate production runtime:
- deploy `dep-dap1blu0tbcc7381m8r0`
- commit `3882f133dccbd953edc7ab38f151f548be4b2e2c`
- status **LIVE**
- later candidate commits only changed historical-probe workflow gates, not runtime code

Docker release chain observed in the P3.28 image:
- P3.21 PASS
- P3.22 PASS
- P3.23 PASS
- P3.24 PASS
- P3.25 PASS
- P3.26 PASS
- P3.27 PASS
- P3.28 PASS

## Authority

`STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY`

No P3.28-specific Hancom-native visual batch has been executed. Native `hp:drawText` ownership and structural package/read-back evidence do not imply pixel/layout fidelity under Hancom rendering.

## Release-seal rule

This ledger commit is the documentation seal. The exact final head must independently repeat:
- lifecycle CI
- production public boundary
- exact-head Render deployment

before P3.28 is considered canonically closed.
