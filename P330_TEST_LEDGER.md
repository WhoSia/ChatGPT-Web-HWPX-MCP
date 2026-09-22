# P3.30 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.30 — Diagram Style Systems, Theme Tokens, Edge/Node Semantic Styling, Layout Policies, Template Parameterization & Production Diagram Design-System Expansion**

## Lineage

P3.30 promotes persistent P3.29 managed diagrams into a reusable design-system layer.

- P3.26 supplies bounded native stroke/fill/arrow styling.
- P3.28 supplies semantic node kinds.
- P3.29 supplies durable diagram/node/type identity and reconstructed static relations.
- P3.30 derives semantic style roles from those persistent identities and materializes themes into existing native HWPX style attributes.

P3.30 does **not** create a sidecar/private theme registry and does not create a second drawing engine.

## Theme semantics

Built-in themes:
- `classic`
- `mono`
- `presentation`

A theme name is an operation-level preset, not hidden document metadata.

Persistent results are the native:
- shape stroke attributes
- solid fill attributes
- line stroke attributes
- arrowhead attributes

Consequences:
- export/re-ingest preserves the materialized design result.
- a theme can be deterministically re-applied from semantic identity.
- P3.30 does not claim that the original theme name can be recovered from arbitrary bytes.

## Semantic roles

Node roles are inherited directly from P3.29 persisted `node_type`:
- process
- terminator
- decision
- data
- node

Edge role:
- `branch` iff the source managed node is a decision node.
- otherwise `flow`.

This role derivation survives locator rebinding because it depends on persistent semantic identity, not drawing order.

## Style tokens

Admitted node tokens:
- fill color
- fill alpha
- stroke color
- stroke width
- stroke style
- stroke alpha

Admitted edge tokens:
- stroke color
- stroke width
- stroke style
- stroke alpha
- arrowhead style
- arrowhead size
- arrowhead fill

P3.30 deliberately does not claim rich mixed-run `hp:drawText` typography authority.

## Layout policies

Built-in deterministic HWPUNIT policies:
- `compact`: gap_x 7600 / gap_y 5000
- `standard`: gap_x 10000 / gap_y 6500
- `spacious`: gap_x 14000 / gap_y 9000

Layouts remain:
- LEFT_TO_RIGHT
- TOP_DOWN

These are deterministic structural spacing policies, **not renderer-aware collision solving**.

### Collision-safe relayout repair

Initial P3.30 candidate exposed a real P3.29 invariant interaction:
- moving the first node directly to its final compact position could temporarily overlap the center of a not-yet-moved managed node.
- P3.29 correctly failed closed because transient duplicate centers make static-edge identity ambiguous.

Repair commit:
`22b737b7310e3ec80153ae210a9fd59428e8a988`

P3.30 layout policy now uses:
1. capture semantic edge pairs
2. remove managed static edges
3. move all managed nodes to unique remote staging coordinates
4. assign final policy coordinates
5. recreate edges from semantic source→target relations

This is a genuine invariant-preserving relayout, not a weakened collision check.

## Parameterized templates

Supported parameterized templates:
- `linear_process`
- `decision_gate`
- `org_triad`

Parameters:
- bounded label overrides keyed by known template node ids
- theme
- layout policy
- layout direction
- origin
- spacing overrides

Instantiation produces ordinary P3.29 managed nodes/relations, then materializes P3.30 styling. There is no template-only object model.

## Bulk design-system operation

`apply_design_system` combines:
- collision-safe layout policy
- semantic-role theme materialization

in one P3.30 atomic package transaction.

Fine-grained overrides remain available through:
- `restyle_node`
- `restyle_edge`

## MCP surface

Added:
- `get_diagram_design_system_contract`
- `get_diagram_design_system`
- `apply_diagram_design_system`

Production:
- version `0.9.0-p3.30`
- phase `P3.30`

New metadata receipt:
- `semantic_style_sha256`

Inherited receipts:
- `diagram_identity_sha256`
- `diagram_relation_sha256`

## Evidence gates

Closed in P3.30:
- rich mixed-run shape-text typography
- renderer-aware collision/page layout
- private XML/sidecar theme-name persistence
- native smart-connector style binding

Inherited closed boundaries remain closed:
- native `hp:connectLine` / subjectIDRef smart binding
- parallel managed-edge identity
- cross-anchor managed subgraphs
- polygon geometry-preserving bbox resize

## Regression

Dedicated P3.30 corpus: **8 source→target pairs**

1. theme-classic
2. theme-mono
3. semantic-node-style
4. semantic-edge-style
5. layout-compact
6. layout-spacious
7. parameterized-template
8. bulk-design-system

Unit coverage additionally verifies:
- semantic role reconstruction
- identity preservation under theme application
- custom node/edge overrides
- collision-safe layout policy
- private theme-registry fail-closed behavior

## OAuth lifecycle

Authenticated lifecycle:
1. operates on the P3.29 persistent diagram
2. applies `presentation` + `compact`
3. reads semantic node/edge roles and native effective styles
4. exports the HWPX
5. re-ingests it
6. verifies native materialized design styling remains present

The OAuth smoke therefore checks design persistence without claiming hidden theme-name persistence.

## Docker release smoke

P3.30 release smoke:
1. creates a parameterized `decision_gate`
2. overrides labels
3. applies `presentation`
4. uses `compact`
5. reopens the HWPX
6. verifies decision semantic role
7. verifies decision fill `#FFF0D6`
8. verifies two outgoing branch roles
9. verifies branch stroke `#D97706`

Production image chain:
**P3.21 → P3.30 PASS**

## Candidate failure and repair

First integrated candidate:
- lifecycle run `35703919190` / **#680 — FAILURE**
- failure localized to P3.30 design-system unit coverage
- cause: transient managed-node center collision during direct P3.29 relayout reuse
- all pre-P3.30 tests remained green

Repair:
- `22b737b7310e3ec80153ae210a9fd59428e8a988`
- collision-safe two-phase relayout described above

## Candidate confirmation

Hardened candidate head:
`22b737b7310e3ec80153ae210a9fd59428e8a988`

Lifecycle:
- run `35704134316`
- run number **#681**
- conclusion **SUCCESS**
- compile PASS
- release-smoke imports PASS
- unit suite PASS
- 8-pair P3.30 regression materialization PASS
- OAuth server/discovery PASS
- authenticated design-system application/read-back PASS
- export/re-ingest native style persistence PASS
- cleanup PASS

Production boundary:
- run `35704134170`
- run number **#680**
- conclusion **SUCCESS**

Candidate Render:
- deploy `dep-dap3l46gekts73fls7h0`
- exact commit `22b737b7310e3ec80153ae210a9fd59428e8a988`
- status **LIVE**

Docker logs explicitly show:
- P3.21 PASS
- P3.22 PASS
- P3.23 PASS
- P3.24 PASS
- P3.25 PASS
- P3.26 PASS
- P3.27 PASS
- P3.28 PASS
- P3.29 PASS
- P3.30 PASS

## Authority

`STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY`

No P3.30-specific Hancom-native visual batch has been executed.

P3.30 structural/native-attribute evidence does not imply:
- pixel fidelity
- native typography fidelity
- renderer-aware collision quality
- renderer-aware pagination quality
- native smart-routing fidelity

## Release-seal rule

This ledger commit is the final documentation seal.

The exact final head must independently repeat:
- lifecycle CI
- production public boundary
- exact-head Render deployment

before P3.30 is canonically closed.
