# P3.32 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.32 — Existing-Diagram Recognition, Semantic Adoption, Managed-Graph Promotion, Legacy Diagram Refactoring & Production Brownfield Diagram Expansion**

## Lineage

P3.32 does not introduce a second diagram engine.

It promotes:
- P3.25 native drawing inventory and intrinsic object identity
- P3.28 native shape labels
- P3.29 persistent managed-node identity and exact-center static relations
- P3.30 materialized native design-system operations
- P3.31 structural QA

into a conservative brownfield adoption layer for existing HWPX diagrams.

Core separation:

`recognition != ownership != promotion != refactoring`

Recognition is read-only. Ownership changes only through an explicit, stale-safe promotion transaction.

## Authority boundary

Authority:
`STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY`

P3.32 observes only native HWPX structure:
- top-level labeled rect/ellipse/polygon objects
- stable paragraph anchors
- intrinsic drawing `id/instid`
- native object geometry
- native static lines
- exact line-endpoint ↔ node-center coincidence
- existing P3.29 ownership carriers

P3.32 does **not** infer diagrams from rendered pixels or visual resemblance.

## Recognition semantics

A brownfield candidate is a connected component satisfying:
1. at least two unmanaged labeled top-level nodes
2. one paragraph anchor
3. at least one native static line
4. both line endpoints terminate exactly at unique unmanaged node centers
5. no P3.29 marker already owns those nodes

Recognition itself performs no mutation.

Each candidate receives:
- `candidate_id`
- `candidate_sha256`
- node and edge evidence
- promotable/HOLD verdict
- explicit hold reasons

Whole-document recognition receives:
- source document SHA-256
- `recognition_sha256`

## Promotion gates

Automatic promotion fails closed for:
- `NODE_LIMIT_EXCEEDED`
- `EDGE_LIMIT_EXCEEDED`
- `NODE_CENTER_COLLISION`
- `PARALLEL_EDGE_AMBIGUITY`
- `REVISION_BOUND_NODE_LOCATOR`
- `NAME_CARRIER_OCCUPIED`

The `NAME_CARRIER_OCCUPIED` gate is deliberate.

P3.29 persists managed semantic identity in:
`hp:drawText@name`

Therefore P3.32 refuses to overwrite a non-empty pre-existing name carrier on an unmanaged shape.

## Adoption plan

`plan_diagram_adoption` is read-only.

It seals:
- source document SHA-256
- source recognition SHA-256
- source candidate SHA-256
- candidate id
- requested managed diagram id
- exact locator set
- source intrinsic id/instid receipts
- caller-supplied or conservative node id/type bindings
- observed static relations
- adoption-plan SHA-256

Default type mapping is deliberately conservative:
- ellipse → `terminator`
- rect → `process`
- polygon → generic `node`

A caller may explicitly bind a polygon to `decision` or `data` when external semantics are known.

## Managed-graph promotion

`promote_diagram_candidate`:
1. checks document revision
2. re-runs recognition
3. checks source document/recognition/candidate hashes
4. checks exact candidate locator set
5. mutates a temporary HWPX copy
6. writes only P3.29 identity carriers to `hp:drawText@name`
7. re-opens through P3.29 lifecycle reconstruction
8. requires node/edge cardinality closure
9. validates the HWPX package
10. atomically commits only on success

Promotion does not rewrite:
- visible labels
- object geometry
- object fill/stroke style
- intrinsic id/instid
- observed static line geometry

Mutation scope:
`HP_DRAWTEXT_NAME_ONLY`

## Legacy refactoring

Refactoring is available only **after** managed promotion.

Admitted meaning-preserving operations:
- P3.30 `apply_layout_policy`
- P3.30 `apply_theme`

Canonical composition order remains:
1. layout
2. theme

The refactor plan seals source managed identity and relation hashes.
After application, P3.32 requires the managed relation hash to remain unchanged.

P3.32 does not automatically:
- add/remove semantic nodes
- add/remove semantic relations
- infer graph meaning
- rewrite labels
- change node semantic type from visual appearance
- merge/split ambiguous brownfield components

## MCP surface

Added:
- `get_brownfield_diagram_contract`
- `recognize_existing_diagrams`
- `plan_diagram_adoption`
- `promote_diagram_candidate`
- `plan_legacy_diagram_refactor`
- `apply_legacy_diagram_refactor`

Production target:
- version `0.10.0-p3.32`
- phase `P3.32`

Read-only calls do not advance revision.
Promotion and refactoring each advance revision exactly once.

## Evidence gates

Closed in P3.32:
- rendered-pixel / computer-vision diagram recognition
- occupied `drawText@name` carrier overwrite
- cross-anchor adoption
- semantic graph auto-repair
- native smart `hp:connectLine` / subjectIDRef adoption
- parallel managed edges

Inherited gates remain closed:
- pixel-level overlap certification
- rendered color-contrast / WCAG certification
- font legibility
- aesthetic scoring
- rich mixed-run shape text
- polygon geometry-preserving resize
- native callout-autoshape authority
- arbitrary existing-object group/ungroup
- tracked-change accept/reject/protection
- column insertion
- second Hancom-version replay
- future multi-class native-render batch

## Dedicated regression

P3.32 corpus: **8 source→target pairs**

1. `recognize-pass`
2. `promote-pass`
3. `occupied-name-hold`
4. `stale-plan`
5. `mixed-managed-unmanaged`
6. `refactor-layout-theme`
7. `reingest-managed`
8. `unconnected-shapes-no-candidate`

Unit coverage additionally verifies:
- recognition is byte-preserving
- occupied name carrier fails closed
- native object locators survive promotion
- observed relation survives promotion
- stale source invalidates adoption
- managed and unmanaged graphs on one anchor remain separated
- layout→theme refactor preserves relations
- export/copy re-ingest preserves promoted managed identity
- evidence-gate contract

## OAuth production target

Authenticated P3.32 lifecycle extends the inherited P3.28→P3.31 production document:
1. detect the still-unmanaged P3.28 flowchart
2. identify the candidate by its four visible labels
3. build explicit label→semantic-id/type bindings
4. plan adoption without mutation
5. promote via identity-carrier-only transaction
6. reacquire a 4-node / 3-edge P3.29 managed graph
7. plan standard-layout + classic-theme legacy refactor
8. apply layout→theme
9. verify relation preservation
10. export HWPX
11. re-ingest
12. reacquire the promoted managed graph through P3.32 recognition inventory

## Release-seal rule

This ledger is initially a pre-release execution ledger.

Canonical closure requires the exact final head to establish:
- compile PASS
- full unit suite PASS
- P3.32 8-pair corpus PASS
- P3.32 release smoke PASS
- authenticated OAuth recognition→plan→promotion→refactor PASS
- export/re-ingest managed-adoption persistence PASS
- inherited production Docker lineage PASS
- lifecycle CI SUCCESS
- production public boundary SUCCESS
- exact-head Render deployment LIVE
- canonical Notion writeback
