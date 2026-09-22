# P3.31 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.31 — Diagram Validation, Design-System Compliance, Graph Constraints, Accessibility/Readability Heuristics, Repair Plans & Production Diagram Quality-Assurance Expansion**

## Lineage

P3.31 does not create a third graph or drawing engine.

It promotes:
- P3.29 persistent managed node identity and reconstructed static relations
- P3.30 semantic roles and materialized native design-system attributes

into:
- bounded read-only validation
- deterministic QA receipts
- explicit safe repair plans
- revision-guarded repair application

All executable repairs delegate to already-authorized P3.30 design/layout primitives.

## Authority boundary

Authority:
`STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY`

P3.31 structural checks operate only on document-observable facts.

Admitted structural evidence:
- persisted node identity/type/label
- reconstructed managed edges
- graph connectivity/cycles/degrees
- exact materialized native style attributes
- native object bounding boxes
- center coordinates and HWPUNIT spacing

P3.31 does **not** promote:
- rendered pixel overlap
- rendered text/background color contrast
- font legibility
- subjective aesthetics
- Hancom-render pagination quality

Those remain native-render evidence gates.

## QA profiles

Built-in profiles:
- `baseline`
- `flow`
- `presentation`

Caller-overridable bounded constraints:
- require_nonempty_labels
- max_label_chars
- require_weakly_connected
- require_acyclic
- require_single_source
- require_single_sink
- max_in_degree
- max_out_degree
- min_center_spacing

## Structural checks

Findings are deterministic `ERROR` or `WARN`.

Graph/content:
- `EMPTY_LABEL`
- `LABEL_TOO_LONG`
- `DISCONNECTED_GRAPH`
- `ISOLATED_NODE`
- `CYCLE_PRESENT`
- `SOURCE_CARDINALITY`
- `SINK_CARDINALITY`
- `MAX_IN_DEGREE`
- `MAX_OUT_DEGREE`

Design-system compliance:
- `NODE_THEME_MISMATCH`
- `EDGE_THEME_MISMATCH`

Structural readability:
- `NATIVE_BBOX_OVERLAP`
- `CENTER_SPACING_BELOW_MINIMUM`

`passed` means no ERROR findings. WARN findings remain visible and receipt-bearing.

## Quality receipts

Per-diagram:
- `qa_sha256`
- inherited `diagram_identity_sha256`
- inherited `diagram_relation_sha256`
- inherited `semantic_style_sha256`

Whole document:
- `quality_sha256`

The QA receipt binds:
- diagram identity
- graph relations
- style state
- profile
- merged constraints
- expected theme
- ordered findings

## MCP surface

Added:
- `get_diagram_quality_assurance_contract`
- `get_diagram_quality`
- `validate_diagram_quality`
- `plan_diagram_repairs`
- `apply_diagram_repairs`

Production:
- version `0.9.0-p3.31`
- phase `P3.31`

## Repair semantics

Automatic semantic graph mutation remains closed.

P3.31 does **not** automatically:
- add/remove nodes
- add/remove semantic relations
- choose a different graph meaning
- rewrite labels to satisfy a semantic rule

Executable safe repairs are restricted to:
- `apply_layout_policy`
- `apply_theme`

Other graph/content findings are advisory.

Repair plans include:
- source QA hash
- profile
- merged constraints
- expected theme
- operations
- reasons
- advisory findings
- repair-plan hash

A source QA receipt mismatch fails closed as a stale repair plan.

## Repair composition invariant

P3.31 discovered that repair operation order matters.

Incorrect order:
1. apply theme
2. apply layout

is not stable because P3.30 layout reconstructs static edge objects and those new edge objects begin with P3.29 default stroke/arrow style.

Canonical safe order:
1. **layout first**
2. **theme last**

This ensures rebuilt edges receive the final semantic-role design tokens.

A dedicated combined-repair regression seals this ordering.

## Evidence gates

Closed in P3.31:
- `pixel_level_overlap`
- `color_contrast_accessibility`
- `font_legibility`
- `aesthetic_quality_score`
- `semantic_graph_repair`

Inherited closed boundaries remain closed:
- native smart `hp:connectLine` / subjectIDRef binding
- parallel managed edges
- cross-anchor managed subgraphs
- polygon geometry-preserving resize
- rich mixed-run shape text
- arbitrary existing-object group/ungroup

## Dedicated regression

P3.31 corpus: **8 source→target pairs**

1. flow-pass
2. theme-mismatch
3. theme-repair-plan
4. overlap-detect
5. spacing-warning
6. cycle-detect
7. disconnected-detect
8. label-budget

Unit coverage additionally verifies:
- style-compliant flow graph PASS
- disconnect/cycle/empty-label detection
- safe theme repair
- bbox-overlap repair planning
- combined layout→theme repair
- evidence-gate contract

## First production-workflow discovery: real bbox overlap

The initial P3.31 OAuth validation did not merely test a synthetic defect.

It discovered a real inherited P3.30 workflow condition:
- P3.29 had resized managed `work` to width 9000 HWPUNIT.
- P3.30 then used `compact` spacing of 7600.
- after subgraph clone + compact design application, `copy-work` and `end` native bounding boxes overlapped.

P3.31 correctly emitted:
`NATIVE_BBOX_OVERLAP`

The test was not weakened.

The authenticated repair flow was changed to request:
- `standard` collision-safe layout
- `mono` theme

while explicitly retaining `require_weakly_connected=false` because the two-component cloned graph is intentional.

## Second discovery: theme-before-layout composition loss

The first combined repair implementation applied:
1. mono theme
2. standard layout

The layout repaired overlap but reconstructed static edges with P3.29 default style:
- color `#444444`
- width `283`
- no arrowhead

P3.31 post-validation correctly reported three `EDGE_THEME_MISMATCH` warnings.

Repair planner was changed to:
1. layout
2. theme

and a combined regression was added.

## Third discovery: P3.29 stale physical edge leakage

The combined regression then exposed a deeper inherited P3.29 lifecycle defect.

Old P3.29 behavior:
1. capture semantic edge pairs
2. mutate node geometry
3. ask the post-mutation graph to identify/remove old managed edges
4. rebuild semantic edges

Once a node moved, the old line endpoints no longer landed on current node centers.
Therefore the old physical line became invisible to center-based managed-edge reconstruction and survived in the HWPX.
A new edge was then added.

Later geometry could make the stale line coincide with centers again, turning it back into a recognized duplicate edge and triggering:
`managed edge already exists: start->work`

This was a real ancestry primitive bug.

Repair commit:
`76cc7d888dd24d5df5081163461d09811c61327e`

P3.29 geometry-changing paths now:
1. capture current semantic pairs
2. remove currently recognized managed edge locators **before geometry mutation**
3. mutate geometry using captured node locators
4. recreate relations from semantic pairs after mutation

Repaired paths:
- `patch_node`
- `relayout_diagram`
- `move_subgraph`

This prevents stale physical edge leakage without weakening semantic identity checks.

## OAuth production smoke

Authenticated P3.31 lifecycle:
1. operate on inherited P3.29/P3.30 `oauth` managed diagram
2. validate under baseline profile with intentional weak-connectivity exemption
3. detect native bbox overlap
4. detect expected `mono` theme mismatch
5. generate a two-operation safe repair plan
6. apply collision-safe standard layout
7. materialize mono theme last
8. revalidate to zero ERROR / zero WARN
9. export HWPX
10. re-ingest
11. reacquire managed graph identity/relations/style
12. re-run the same P3.31 QA contract
13. confirm zero ERROR / zero WARN after re-ingest

## Docker release smoke

P3.31 release smoke:
1. create managed `linear_process`
2. validate flow constraints
3. detect expected presentation-theme mismatch
4. generate safe theme repair
5. materialize presentation style
6. reopen
7. verify:
   - PASS
   - zero ERROR
   - zero WARN
   - source = `start`
   - sink = `end`

Production Docker chain:
**P3.21 → P3.31 PASS**

## Failed candidates and what they established

### Candidate A — OAuth overlap discovery
Lifecycle:
- `35706298337` / #695 — FAILURE at authenticated OAuth step
- compile PASS
- unit PASS
- P3.31 corpus PASS
- server/discovery PASS

Cause:
P3.31 detected real `NATIVE_BBOX_OVERLAP` in the inherited OAuth fixture.

### Candidate B — repair composition discovery
Lifecycle:
- `35706609611` / #696 — FAILURE at authenticated OAuth step
- unit/corpus/server PASS

Cause:
theme-before-layout lost edge styling after layout reconstructed static edges.

### Candidate C — stale physical edge discovery
Head:
`b5d6588ef704e1a646bb2be055858ca18039d9bb`

Lifecycle:
- `35706883983` / #698 — FAILURE in the new combined-repair unit test

Cause:
P3.29 geometry mutation had left stale physical static lines behind.

### Hardened candidate
Head:
`76cc7d888dd24d5df5081163461d09811c61327e`

Lifecycle:
- `35707103461`
- run number **#699**
- conclusion **SUCCESS**
- compile PASS
- release-smoke imports PASS
- full unit suite PASS
- P3.31 8-pair regression materialization PASS
- OAuth server/discovery PASS
- authenticated QA validate→plan→repair→revalidate PASS
- export/re-ingest QA persistence PASS
- cleanup PASS

Production boundary:
- `35707103323`
- run number **#698**
- conclusion **SUCCESS**

Candidate Render:
- `dep-dap446rtqb8s73f94270`
- exact commit `76cc7d888dd24d5df5081163461d09811c61327e`
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
- P3.31 PASS

## Authority

`STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY`

No P3.31-specific Hancom-native visual batch has been executed.

P3.31 does not claim:
- visual accessibility certification
- WCAG contrast certification
- native font legibility
- pixel collision freedom
- visual aesthetics
- smart connector routing fidelity

## Release-seal rule

This ledger commit is documentation-only.

The exact final head must independently repeat:
- lifecycle CI
- production public boundary
- exact-head Render deployment

before P3.31 is canonically closed.
