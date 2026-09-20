# P3.13-R1 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.13-R1 — Self-Materialized Render Fixture Pack, Near-Wrap Boundary Construction, Capture-Ready Artifact Manifest & Zero-Manual Pre-Hancom Bootstrap**

## Current verdict

`IMPLEMENTATION_PASS / SELF_MATERIALIZATION_PASS_BY_CONSTRUCTION / CAPTURE_READY_MANIFEST_PASS / BOUNDARY_LADDER_PASS / AUTO_BOUNDARY_SELECTOR_PASS / HANCOM_COM_BOOTSTRAP_BOUND / PDF_RASTER_LINEBOX_PIPELINE_BOUND / MAIN_CI_BOUND / ARTIFACT_WORKFLOW_BOUND / CI_CONFIRMATION_PENDING / FIRST_REAL_HANCOM_EXECUTION_REQUIRED`

## Self-materialized fixture pack

Canonical module:

`p313r1_fixture_pack.py`

The pack generator creates:

- `near-wrap-base`
- `near-wrap-plus-advance`
- `near-wrap-minus-frame`

Each canonical fixture receives:

- source HWPX
- target HWPX
- source/target SHA-256
- mutation receipt
- capture directory
- line-box placeholder
- font-inventory placeholder
- render-receipt template

No manual fixture authoring is required.

## Boundary construction

R1 does not guess one renderer-specific wrap threshold.

It materializes two independent calibration ladders:

### Advance ladder

Target primary character height is increased by:

`+0.20%, +0.40%, +0.60%, +0.80%, +1.00%, +1.20%, +1.60%, +2.00%`

### Frame ladder

Target right margin is increased by HWPUNIT deltas:

`71, 142, 213, 283, 354, 425, 567, 709`

The automatic selector chooses the smallest Hancom-observed candidate whose captured line topology diverges.

Authority:

`SMALLEST_OBSERVED_LINE_BREAK_DIVERGENCE`

## Stronger topology comparison

P3.12 line topology comparison was strengthened during R1.

When line text hashes or paragraph locators are available, equality now compares the ordered per-page line signatures, not only line counts.

A same-count but differently wrapped paragraph can therefore be detected.

## One-command materializer

`scripts/p313r1_materialize_pack.py`

Default output:

`artifacts/p313r1-hancom-capture-pack`

The directory is also sealed into:

`artifacts/p313r1-hancom-capture-pack.zip`

## Automated Hancom capture path

Official Hancom documentation supports PDF as a save target, and Hancom developer-forum examples show automation using `HWPFrame.HwpObject` with `SaveAs(..., "PDF")`.

R1 therefore adds a best-effort COM runner:

`scripts/p313r1_run_hancom_capture.ps1`

It:

1. creates an isolated Python virtual environment;
2. installs project and capture dependencies;
3. self-materializes all canonical and ladder HWPX files;
4. auto-detects `Hwp.exe` when possible;
5. opens source and target through `HWPFrame.HwpObject`;
6. exports each through Hancom PDF SaveAs;
7. rasterizes both PDFs at controlled DPI;
8. extracts PDF-observed line boxes and font identities;
9. computes pixel/layout residual metrics;
10. seals canonical fixture custody bundles;
11. runs automatic boundary selection;
12. writes `windows-hancom-run-summary.json`.

Per-document automation failure is recorded as `capture-failure.json` and is not promoted.

## Capture extraction

`scripts/p313r1_pdf_capture.py`

uses isolated capture requirements:

`requirements-capture.txt`

The extractor materializes:

- source/target page PNGs
- source/target raster SHA-256
- line text SHA-256 topology
- line bounding boxes
- baselines
- PDF-observed font inventory
- pixel disagreement ratio
- MAE
- edge disagreement
- max line-box displacement
- line-width advance proxy
- baseline displacement
- P3.12 render receipt

The PDF-derived geometry is downstream Hancom-PDF evidence, not direct internal Hancom layout-state introspection.

## Boundary finalization

`scripts/p313r1_select_boundary.py`

selects the smallest observed line-break divergence separately for the advance and frame ladders and writes:

`boundary-selection.json`

P3.14 is boundary-ready only when both ladders contain an observed transition.

## CI / artifact materialization

`.github/workflows/p313r1-fixture-pack.yml`

tests the R1 generator, materializes the complete pack, verifies its manifest, and publishes:

`p313r1-hancom-capture-pack`

as a GitHub Actions artifact.

The main lifecycle workflow also compiles and executes `test_p313r1_fixture_pack.py`.

## Repository receipts

- initial self-materializer: `e17a0a4a2a7ee17d7d7e316a00f725673be46cdc`
- boundary ladder + selector: `255a11048ef22c81d4990fc3f58a316178a11858`
- one-command materializer: `db98ae3d1080910e13c7aa06f1715b76f5550afb`
- materializer tests: `71e22d027200bccec7cdc8ebf86700f0258971b6`
- artifact workflow: `a2ccb2b1464665e8cddd826da687ecf4d42a0542`
- stronger topology comparison: `f2fffbdbe37af2f856bb187f0ace756e114d0942`
- isolated capture requirements: `2bc4b74aa235534388add87fee1a7b099e6d29d8`
- Hancom-PDF capture extractor: `1c5755d648088b3bb50487dfcd3ecb4d01f3f414`
- boundary finalizer: `e68fd4e31920c639f7fdf4f0074890e4d4bfcdef`
- one-command Windows Hancom runner: `853d145e8bb78cfdde8532531787ebd5f5042233`
- upload-ready captured evidence ZIP emission: `d6fbfa8395943b1c142ea6ab8a5c038f676b835a`
- expanded artifact workflow: `e769581cb6dc43484bdde017a8fd7255fd14090e`
- main CI regression binding: `d9fbf94338076f97898ea27b75df84d9ac6d0bb6`

At ledger creation time GitHub combined status for the current head remained empty, so CI success is not claimed.

## User boundary

All pre-Hancom fixture authoring, calibration-ladder construction, capture manifest construction and analysis scripts are now automated.

The first irreducible external action is execution on a Windows machine with Hancom Hangul installed.

## Successor

After first real capture:

**ChatGPT Web HWPX MCP P3.14 — First Trusted Hancom Capture Intake, Near-Wrap Sensitivity Execution, Fixture-Corpus Replay, Cross-Version Evidence Join & Conditional Pixel-Fidelity Promotion**
