# P3.5 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.5 — Native HWP 5.x Read Custody, Common Document IR, Fidelity-Graded HWP→HWPX Promotion, Table/Equation/Object Recovery & Cross-Format Search/Extraction**

## Verdict

`IMPLEMENTATION_PASS / NATIVE_LIFECYCLE_PASS / PUBLIC_BOUNDARY_PASS / PRODUCTION_DEPLOYED / FAMILY_FIDELITY_EXPLICIT`

## Production

- Server version: `0.5.0-p3.5`
- Deploy: `dep-dan72regekts73funqv0`
- Deployed commit: `6af24db3329dfb3f0055d7e66f7c2c380aaed86f`
- Status: `live`
- Native lifecycle: `35440073500` — SUCCESS
- Public boundary: `35440073467` — SUCCESS

## Common Document IR

Schema: `who-common-document-ir/0.1`

Supported source families:

- HWPX durable document custody
- bounded HWP 5.x payloads

Block kinds:

- paragraph
- table
- equation
- picture / shape
- binary custody item

Each block includes:

- block id
- family kind
- explicit fidelity
- source receipt
- family data
- deterministic block SHA-256

## Fidelity lattice

`none < inventory < raw-preserved < structural < semantic < editable-native`

The lattice is used as an authority boundary, not a cosmetic score.

Current HWP 5.x authority:

- paragraph text — `semantic`
- table geometry — `structural`
- EqEdit script — `semantic`
- picture component — `inventory`
- shape payload custody — `raw-preserved`
- BinData streams — `inventory`

## HWP family recovery

### Tables

Recovered:

- row/column counts
- cell spacing
- table margins
- row sizes
- border-fill id
- repeat-header/page-break flags

Not yet certified:

- cell-content association
- merged-cell topology
- exact native HWPX table synthesis

### Equations

Recovered:

- EqEdit script
- script length
- attributes
- font size
- text color
- baseline
- source record receipt

Authority: `SEMANTIC_SCRIPT_RECOVERED / POSITION_PROMOTION_DEFERRED`

### Pictures / objects

Recovered:

- picture/shape record inventory
- payload SHA-256
- section/record provenance
- BinData stream inventory and custody SHA-256

Not yet certified:

- picture↔BinData exact linkage
- native geometry reconstruction
- editable HWPX picture synthesis

## Cross-format operations

Promoted MCP tools:

- `get_common_document_ir`
- `search_common_document`
- `get_common_document_slice`
- `extract_common_document`
- `assess_hwp5_promotion`

`extract_common_document` supports explicit minimum-fidelity gating so clients can require, for example, `structural` or `semantic` authority before consuming a block.

## Promotion semantics

HWP→HWPX promotion is deliberately asymmetric.

Allowed:

- semantic paragraph text → editable HWPX text
- source HWP SHA/version/flags/family receipts → derivative provenance metadata

Deferred:

- structural tables → editable native HWPX tables
- semantic equations → positioned editable native equations
- inventory pictures → editable native pictures

No lower-fidelity object is fabricated into a higher-fidelity HWPX object.

## Security

- Password/DRM/certificate-encrypted HWP content remains fail-closed.
- No password guessing or protection bypass.
- HWP binary source is never mutated.
- Bounded ingress remains enforced.

## Successor

**ChatGPT Web HWPX MCP P3.6 — HWP Control-Graph Reconstruction, Table-Cell/Paragraph Binding, BinData-Picture Linkage, Positioned Equation Recovery & Fidelity-Preserving Rich HWPX Promotion**
