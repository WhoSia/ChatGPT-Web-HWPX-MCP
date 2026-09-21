# P3.14 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.14 — First Trusted Hancom Capture Intake, Near-Wrap Sensitivity Execution, Fixture-Corpus Replay, Cross-Version Evidence Join & Conditional Pixel-Fidelity Promotion**

## Current verdict

`FIRST_HANCOM_WORLD_CONTACT_PASS / 19_OF_19_CAPTURE_PASS / MANIFEST_HASH_38_OF_38_PASS / RENDER_RECEIPT_HASH_PASS / CANONICAL_CUSTODY_PASS / BASELINE_EXACT_PIXEL_PASS / ADVANCE_SENSITIVITY_PASS / FRAME_SENSITIVITY_PASS / CROSS_VERSION_WORLD_CONTACT_HOLD / GLOBAL_PIXEL_FIDELITY_PROMOTION_HOLD`

## Evidence packet

Uploaded capture bundle SHA-256:

`899040f3f32c0d63c95729c573455104b01ba4b7a9ddaf409baed799793aa795`

Uploaded summary SHA-256:

`d44ae0c08787056f4a0651720d8ee9cb68bed46fb79b1a084cbca3a5050b8508`

Renderer:

- Hancom Hangul
- version `13.0.0.3622`
- executable SHA-256 `91541f8c16e592516d0265c795b565a14a2cacef0b64f616b0626f54f3d3ece2`
- 144 DPI
- Hancom SaveAs PDF
- controlled PyMuPDF 1.28.2 rasterization

Execution:

- expected runs: 19
- succeeded: 19
- failed: 0
- boundary ready: true

## Integrity replay

Independent intake replay verified:

- manifest source/target document hashes: 38/38 matched
- render receipts checked: 19
- render-receipt document/raster hash mismatches: 0
- canonical custody bundles checked: 3
- canonical custody artifact hash mismatches: 0

Therefore the first external Hancom packet is internally joinable to its manifest, render receipts and canonical custody artifacts.

## Baseline exactness

`near-wrap-base`:

- pagination equal: true
- line-break topology equal: true
- exact pixel match: true
- pixel diff ratio: 0
- MAE: 0
- edge disagreement: 0

This establishes exact replay for the unchanged baseline under the captured Hancom/PDF/raster environment.

It does not establish blanket exactness for arbitrary edits.

## Positive-sensitivity execution

### Advance perturbation

Observed ladder:

- +0.20%: topology equal
- +0.40%: topology equal
- +0.60%: topology equal
- +0.80%: topology equal
- +1.00%: topology equal
- **+1.20%: first topology divergence**
- +1.60%: topology divergence
- +2.00%: topology divergence

Selected boundary:

`advance-10120`

At the selected transition:

- pagination remains equal
- line-break topology diverges
- pixel diff ratio: `0.05395237762167887`
- glyph-advance max delta proxy: `191.73284912109375 px`

### Frame perturbation

Observed ladder:

- +71 HWPUNIT: topology equal
- +142 HWPUNIT: topology equal
- +213 HWPUNIT: topology equal
- **+283 HWPUNIT: first topology divergence**
- +354 HWPUNIT: topology divergence
- +425 HWPUNIT: topology divergence
- +567 HWPUNIT: topology divergence
- +709 HWPUNIT: topology divergence

Selected boundary:

`frame-283`

At the selected transition:

- pagination remains equal
- line-break topology diverges
- pixel diff ratio: `0.05068495888248284`
- glyph-advance max delta proxy: `185.41949462890625 px`

These controls reject a dead oracle that reports universal equivalence.

## Canonical evidence receipt

Sealed at:

`fixtures/p314_first_hancom_capture_receipt.json`

Repository receipt:

`3df8cc593cf4881c7615bea37c6c20d1fe75f18f`

## Adjudicator

`p314_capture_intake.py`

Repository receipt:

`25fffedc8432a16a2b0bc68f1b58b582ba70afb2`

The adjudicator requires:

- all expected captures succeed,
- no manifest/hash/custody mismatch,
- exact unchanged baseline,
- both positive controls cross a real observed boundary,
- Hancom renderer identity and executable receipt.

One-version evidence yields:

`FIRST_HANCOM_WORLD_CONTACT_PASS_CROSS_VERSION_HOLD`

At least two distinct Hancom versions are required before the conditional pixel-fidelity promotion candidate can reopen.

## Tests

`test_p314_capture_intake.py`

Repository receipt:

`7fb324c6c30bd01fe30fbafa2cef4138d2d8dc18`

Tests cover:

- first world-contact PASS with cross-version HOLD,
- dead-oracle sensitivity failure,
- fatal integrity mismatch,
- second-version promotion reopening.

Main lifecycle CI binding:

`83cba898520a1389e96f0755f14dd940ef7677ef`

## Authority ceiling

The capture packet contains one Hancom version only:

`13.0.0.3622`

Therefore:

`CROSS_VERSION_WORLD_CONTACT_HOLD`

and

`GLOBAL_PIXEL_FIDELITY_PROMOTION_HOLD`

remain binding.

Font evidence in this first packet is PDF-observed font identity/size rather than a cryptographic hash of the installed Windows font file. This is retained as an explicit environment-custody limitation.

## Successor

**ChatGPT Web HWPX MCP P3.15 — Second Hancom-Version Replay Design, Environment-Delta Isolation, Cross-Version Boundary Transport, Font-File Custody Upgrade & Pixel-Fidelity Promotion Reopening**
