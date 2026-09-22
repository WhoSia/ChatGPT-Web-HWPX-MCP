# P3.27 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.27 — Connectors, Group Transform Semantics, Object Alignment/Distribution, Reusable Diagram Blocks & Production Diagram-Composition Expansion**

## Lineage

P3.27 is a composition-layer promotion, not a second drawing engine.

- P3.25 supplies unified drawing inventory, floating placement and geometry read-back.
- P3.26 supplies dedicated native line/ellipse/polygon/arc authoring and drawing styling.
- upstream python-hwpx supplies real-corpus-backed `ContainerMember` + `add_container` group authoring.
- P3.27 adds bounded diagram composition on top of those authorities.

## Connector boundary

P3.27 does **not** claim native smart-connector authoring.

`hp:connectLine` remains evidence-gated because upstream real-document probes show:
- endpoint `subjectIDRef` binds to shape `instid`,
- offset/curSz/rendering matrices are not reconstructible from the available clean sample,
- the alternate unattached sample has a degenerate transform.

Admitted connector semantics are therefore **STATIC_LINE_CONNECTOR_ONLY**: a normal line is materialized between the current centers of two floating nodes. It does not automatically reroute after either node moves.

## Group authority

Admitted:
- new `hp:container` from explicit local rect/ellipse/polygon members
- group topology read-back
- rigid top-level group translation

Deferred:
- grouping arbitrary existing objects
- ungrouping existing groups
- group scaling/rebasing

## Alignment / distribution

- align: LEFT / CENTER / RIGHT / TOP / MIDDLE / BOTTOM
- distribute: HORIZONTAL / VERTICAL equal-center distribution
- scope: floating top-level drawings sharing one paragraph anchor

## Reusable diagram blocks

Bounded presets:
- `two_nodes`
- `three_stage`
- `decision_cluster`

## Regression

Dedicated P3.27 corpus: **6 source→target pairs**

1. group-create
2. group-translate
3. align
4. distribute
5. static-connector
6. diagram-block

## Candidate confirmation

Candidate head:
`ee847ba2baca8f4a8f2309f114f6770482f595f7`

Lifecycle:
- run **35680212983**
- run number **#636**
- conclusion **SUCCESS**
- compile PASS
- unit tests PASS
- six-pair product regression materialization PASS
- OAuth-protected server/discovery PASS
- authenticated diagram block write/read-back + rigid group translation PASS
- export/re-ingest/cleanup PASS

Production boundary:
- run **35680213085**
- run number **#635**
- conclusion **SUCCESS**

Render:
- deploy `dep-daoul4lg1s2s738oepgg`
- exact candidate commit `ee847ba2baca8f4a8f2309f114f6770482f595f7`
- status **LIVE**

Docker release chain:
- P3.21 PASS
- P3.22 PASS
- P3.23 PASS
- P3.24 PASS
- P3.25 PASS
- P3.26 PASS
- P3.27 PASS

## Authority

`STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY`

No P3.27-specific Hancom-native visual batch has been executed. Structural package/read-back evidence must not be promoted into native pixel/render fidelity.

## Release-seal rule

This ledger commit is the final documentation seal. The exact final head must independently repeat lifecycle, production-boundary and Render-live verification before P3.27 is considered canonically closed.
