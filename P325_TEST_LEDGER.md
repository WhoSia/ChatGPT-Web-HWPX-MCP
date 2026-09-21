# P3.25 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.25 — Drawing Shapes, Text Boxes & Anchored Object Layout, Wrap/Z-Order, Grouping, Geometry Editing & Production Drawing-Layer Expansion**

## Lineage

P3.25 is a product re-promotion, not a new drawing engine.

- P2.9 ancestry: picture/media custody, floating placement, position offsets, text wrap, z-order, resize.
- P3.9 ancestry: native rectangle textbox promotion, anchor and HWPUNIT geometry receipts.
- P3.25: unified drawing-object map and revision-safe production transaction layer.

## Admitted structural surface

- inventory: `pic / rect / ellipse / line / polygon / arc / container`
- authoring: `insert_textbox`, `insert_rectangle`
- layout: anchor position, treat-as-character state, relation/alignment, offsets, wrap/text-flow, z-order, lock
- geometry: rectangle/picture resize; rotation and flip where native child elements exist
- lifecycle: remove drawing object
- receipts: `drawing_structure_sha256`, `drawing_geometry_sha256`, object rebinding

## Evidence gates

The following remain fail-closed:

- `group_objects`
- `ungroup_objects`
- `insert_generic_shape`

Existing containers/groups are inventoried, but group authoring is not promoted without measured child-transform and ownership custody.

## Regression

Dedicated P3.25 corpus: **6 source→target pairs**

1. textbox-create
2. rectangle-create
3. anchored-layout
4. wrap-zorder
5. geometry-rotation-flip
6. remove-object

## Release-image gate

Docker release image executes:

- P3.21 release smoke — PASS
- P3.22 release smoke — PASS
- P3.23 release smoke — PASS
- P3.24 release smoke — PASS
- P3.25 release smoke — PASS

The first P3.25 Docker attempt failed before semantics were exercised because the new smoke script omitted the repository-root Python import bootstrap. That was corrected in `d003c583852b968740482dbe0272d6cbaca59e39`; the next exact-head build passed P3.25 smoke.

## Confirmatory lifecycle

Commit: `d003c583852b968740482dbe0272d6cbaca59e39`

GitHub Actions lifecycle:
- run: **35668551099**
- run number: **#615**
- conclusion: **SUCCESS**
- compile: PASS
- unit tests: PASS
- product regression materialization: PASS
- OAuth protected server: PASS
- unauthenticated rejection/discovery: PASS
- authenticated map/edit/diff/export/re-ingest/cleanup: PASS
- P3.25 OAuth textbox creation + drawing read-back: PASS through the integrated client

Production public boundary:
- run: **35668551094**
- run number: **#614**
- conclusion: **SUCCESS**
- production version wait: PASS
- protected-resource metadata: PASS
- authorization-server metadata + offline_access: PASS
- unauthenticated MCP rejection: PASS

## Production

Render service: `srv-daiimp8ae00c73em8tjg`

Deploy:
- `dep-daos0d6gekts73erff5g`
- commit `d003c583852b968740482dbe0272d6cbaca59e39`
- status: **LIVE**

## Authority

`STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY`

A P3.25-specific Hancom-native rendering batch has not been executed. No native visual/pixel fidelity claim is promoted from structural receipts alone.
