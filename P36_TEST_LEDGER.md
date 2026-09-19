# P3.6 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.6 — HWP Control-Graph Reconstruction, Table-Cell/Paragraph Binding, BinData–Picture Linkage, Positioned Equation Recovery & Fidelity-Preserving Rich HWPX Promotion**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_CI_PASS / REAL_HWP_CONTROL_GRAPH_PASS / REAL_RICH_PROMOTION_PASS / PRODUCTION_DEPLOY_PENDING_AT_SEAL`

## Server

- Version: `0.6.0-p3.6`
- Original HWP binaries remain read-only.
- Rich promotion materializes a new HWPX derivative.
- Family promotion is conditional on observed linkage closure; ambiguous families remain deferred provenance.

## Control graph

P3.6 reconstructs:

- `CTRL_HEADER` control id, common geometry, instance id, paragraph anchor
- table `HWPTAG_TABLE` ownership
- table-cell `LIST_HEADER` coordinates, spans, dimensions, margins, border-fill id
- cell → paragraph ownership
- EqEdit record → control → positioned paragraph anchor
- picture record → control geometry → BinItem id
- DocInfo BinData metadata → `BinData/BINxxxx.*` custody
- explicit graph edges for family ownership, cell containment, paragraph containment, and binary references

## Table adjudication

Real source: `table-001.hwp`, 23,040 bytes.

World-contact result:

- table-cell/paragraph binding: **closed**
- control count: 3
- graph edge count: 9
- rich promotion: 1 table promoted, 0 deferred
- final HWPX inventory: 1 native table

Two real-HWP defects were found and fixed during P3.6:

1. caption/list headers under a table control were initially misclassified as cell headers;
2. covered physical cells in merged regions were initially interpreted as independent logical cells.

The final parser only accepts cell LIST_HEADER records after the table geometry record and normalizes subordinate covered cells before synthesis. Visible subordinate content remains fail-closed.

Failed table promotion is rolled back rather than leaving a partial table in the derivative.

## Equation adjudication

Real source: `eq-01.hwp`, 16,384 bytes.

World-contact result:

- equation anchor/position binding: **closed**
- control count: 7
- graph edge count: 5
- rich promotion: 3 equations promoted, 0 deferred
- final HWPX inventory: 3 native equations

Each promoted equation preserves the recovered EqEdit script and is placed under a paragraph anchor derived from the owning HWP control. Source control geometry remains in the promotion authority chain.

## Picture / BinData adjudication

Real source: `test-image.hwp`, 22,016 bytes.

Observed:

- 5 picture records
- all 5 reference BinItem id 1
- all 5 resolve to `BinData/BIN0001.bmp`
- all 5 have control geometry
- paragraph anchors close independently for picture ordinals 0..4

World-contact result:

- picture/BinData/geometry binding: **closed**
- control count: 7
- graph edge count: 10
- rich promotion: 5 pictures promoted, 0 deferred
- final HWPX inventory: 5 native pictures + 5 media items

The source BMP is 212×202 pixels. Because the HWPX media engine accepts PNG/JPEG, P3.6 uses a bounded BMP→PNG transform for this lane:

- pixel limit: 20,000,000
- source SHA-256: `dfc98c6df0f7cbbf7ae253a1e0a32fda732b3f2a0c0093fb4867bc52a779a9ea`
- output PNG SHA-256: `33bfa65008b8db032916b7e7eaa77aec9fc2c0c3c40bcdf242a47c77710fe12d`
- source/output formats and dimensions are stored in per-picture promotion receipts

This is a format transform, not a claim of byte-identical media preservation.

## Official HWP real-file contact

Official Hancom HWP 5.x document was downloaded ephemerally during CI and removed after the run.

Observed:

- source bytes: 342,528
- source version: 5.1.0.1
- paragraph blocks: 1
- BinData inventory: 38
- recovered binary assets: 27
- Common IR blocks: 39
- semantic-or-better blocks: 1

This official sample provides independent real-container/parser contact, while the separate table/equation/picture fixtures exercise rich-family reconstruction.

## Real-world OAuth-native world contact

Workflow: `35442008034` — **SUCCESS**

The workflow:

1. downloads real HWP files only to ephemeral runner storage;
2. validates CFB signatures;
3. parses the official HWP source natively;
4. starts the OAuth-protected P3.6 MCP server;
5. invokes `get_hwp5_control_graph` and `assess_hwp5_promotion`;
6. invokes `materialize_hwp5_rich_derivative`;
7. verifies final HWPX table/equation/object maps;
8. deletes the derivative documents;
9. deletes all external HWP fixture files from the runner.

## Native CI

- `35442019079` — SUCCESS
- includes bounded BMP→PNG transformation test and pixel-bound rejection
- prior P3.6 lifecycle runs also validate discovery, HWPX editing, durable custody, Common IR, and HWP parser primitives

## Authority earned

P3.6 earns:

- HWP control-graph reconstruction
- table-cell/paragraph binding on the tested real table fixture
- positioned EqEdit recovery on the tested real equation fixture
- picture→BinData linkage and control geometry on the tested real image fixture
- conditional native HWPX promotion for all three families
- bounded/provenance-preserving BMP→PNG media adaptation
- fail-closed family-specific promotion receipts

P3.6 does **not** claim universal byte-perfect HWP→HWPX round-trip fidelity across arbitrary HWP files or all HWP control families.

## Successor

**ChatGPT Web HWPX MCP P3.7 — HWP Run/Style Recovery, Header/Footer/Footnote/Endnote Controls, Nested Text-Box/Object Graph, Cross-Format Round-Trip Fidelity Oracle & Rich Promotion Expansion**
