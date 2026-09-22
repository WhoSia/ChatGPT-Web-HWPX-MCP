# P3.29 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.29 — Diagram Object Identity, Node/Edge Patch Editing, Relayout/Resize, Template Libraries, Subgraph Operations & Production Diagram Lifecycle Expansion**

## Lineage

P3.29 promotes P3.28 one-shot semantic diagram authoring into a persistent edit lifecycle.

- P3.25 supplies intrinsic drawing identity, locators and bounded native geometry mutation.
- P3.27 supplies floating placement and static center-to-center connector geometry.
- P3.28 supplies semantic node kinds, native `hp:drawText` ownership and declarative graph authoring.
- P3.29 adds durable semantic node identity, reconstructed edge relations, patch editing, deterministic relayout, templates and subgraph operations.

It does not create a second drawing engine or a private sidecar registry.

## Durable semantic identity

P3.29-managed nodes persist identity in the existing native shape-text carrier:

`hp:drawText@name = p329|<diagram_id>|<node_id>|<node_type>`

Visible label text remains independent.

Properties:
- diagram/node ids are bounded and validated.
- semantic node type is persisted rather than re-inferred from native family.
- locators may change after export/re-ingest; semantic identity is reacquired from the HWPX bytes.
- one managed diagram is constrained to one paragraph anchor.

The authenticated OAuth lifecycle explicitly exports and re-ingests a P3.29 document, then reacquires:
- diagram id
- exact node ids
- semantic node types
- reconstructed managed relations

from the re-ingested document.

## Managed edge semantics

P3.29 does **not** claim native smart connector binding.

Managed edges are normal native lines whose absolute start/end points exactly match the current centers of two managed nodes.

Read-back reconstructs:
`source -> target`

Geometry-changing operations:
- move
- admitted resize
- relayout

delete and regenerate affected managed static edges from semantic source/target pairs.

Deferred:
- native `hp:connectLine` / `subjectIDRef` binding
- automatic native rerouting
- parallel managed edges between the same ordered node pair
- cross-anchor managed subgraphs

## Patch lifecycle

Admitted:
- create managed diagram
- add/remove node
- patch node label
- patch floating position
- resize admitted node families
- add/remove edge
- deterministic whole-diagram relayout

Polygon bbox resize is **EVIDENCE_GATE_CLOSED** because changing only `sz/orgSz/curSz` does not rebase polygon point geometry. P3.29 therefore does not claim a geometry-preserving decision/data polygon resize.

## Template library

Built-in bounded templates:
- `linear_process`
- `decision_gate`
- `org_triad`

Template instantiation produces ordinary P3.29-managed nodes and relations; there is no separate template-only object model.

## Subgraph operations

Admitted:
- `move_subgraph`
- `clone_subgraph`
- `remove_subgraph`

Clone behavior:
- copies persisted semantic node type
- creates new bounded node ids through a caller-provided prefix
- clones internal selected-node relations
- does not infer polygon semantics from geometry

## Bounds

- nodes per managed diagram: **32**
- edges per managed diagram: **64**
- transaction operations: **1..32**

These match the P3.28 declarative compiler ceiling rather than advertising a wider unreachable P3.29 limit.

## MCP surface

Added:
- `get_diagram_lifecycle_contract`
- `get_diagram_lifecycle`
- `apply_diagram_lifecycle`

Production:
- version `0.9.0-p3.29`
- phase `P3.29`

Metadata receipts:
- `diagram_identity_sha256`
- `diagram_relation_sha256`

## Regression

Dedicated P3.29 corpus: **8 source→target pairs**

1. identity-reopen
2. node-patch
3. edge-patch
4. relayout
5. template
6. move-subgraph
7. clone-subgraph
8. remove-subgraph

Unit coverage additionally verifies polygon-resize fail-closed behavior.

## Docker release smoke

P3.29 release smoke:
1. instantiates `linear_process`
2. patches `work` to `Review`
3. moves that node
4. clones the `start/work` subgraph
5. reopens the HWPX
6. reacquires semantic node ids and relations
7. verifies `copy-start->copy-work`

Production image chain:
**P3.21 → P3.29 PASS**

## Candidate confirmation

Hardened candidate head:
`3a28965b359fac2cb353994d6d9480d1d87cdfc7`

Lifecycle:
- run `35701382162`
- run number **#669**
- conclusion **SUCCESS**
- compile PASS
- release-smoke import PASS
- P3.29 unit coverage PASS
- 8-pair product regression materialization PASS
- OAuth server/discovery PASS
- authenticated template → node patch/resize → subgraph clone PASS
- export/re-ingest semantic identity + relation recovery PASS
- cleanup PASS

Production boundary at P3.29 version:
- run `35701382133`
- run number **#668**
- conclusion **SUCCESS**

Hardened exact-head Render:
- deploy `dep-dap36d80cd8s73bj7qqg`
- commit `3a28965b359fac2cb353994d6d9480d1d87cdfc7`
- status **LIVE**
- Docker P3.29 release smoke PASS

## Authority

`STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY`

No P3.29-specific Hancom-native visual batch has been executed.

Structural package semantics, persistent identity and export/re-ingest recovery do not imply:
- pixel fidelity
- native smart-routing fidelity
- renderer-aware collision avoidance
- renderer-aware page layout.

## Release-seal rule

This ledger commit is the final documentation seal.

The exact final head must independently repeat:
- lifecycle CI
- production public boundary
- exact-head Render deployment

before P3.29 is canonically closed.
