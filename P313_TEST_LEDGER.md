# P3.13 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.13 — Trusted Windows/Hancom Capture Runner, Artifact-Custody Chain, Near-Wrap Positive-Sensitivity Corpus, Cross-Version Hancom Replay & Pixel-Fidelity Promotion Trial**

## Current verdict

`IMPLEMENTATION_PASS / TRUSTED_RUNNER_IDENTITY_PASS / ARTIFACT_CUSTODY_CHAIN_PASS / NEAR_WRAP_SENSITIVITY_SPEC_PASS / CROSS_VERSION_REPLAY_GATE_PASS / MCP_SURFACE_BOUND / PRODUCTION_PACKAGING_BOUND / CI_CONFIRMATION_PENDING / WINDOWS_HANCOM_CAPTURE_NOT_YET_EXECUTED / CROSS_VERSION_WORLD_CONTACT_HOLD / PIXEL_RENDER_FIDELITY_HOLD`

## Trusted Windows/Hancom runner identity

P3.13 adds `p313_capture_custody.py` and the Windows custody sealer:

`scripts/p313_windows_capture.ps1`

A trusted runner identity binds:

- Windows OS name/version
- machine id
- Hancom version
- Hancom executable SHA-256
- capture harness SHA-256
- capture user
- locale
- display scale

Non-Windows runner identities are rejected by the P3.13 trusted-runner lane.

The PowerShell script intentionally does not depend on undocumented Hancom GUI/API automation.
A site-specific renderer adapter must first produce the render artifacts; the P3.13 script seals those artifacts into the canonical custody format.

## Artifact custody chain

Canonical bundle schema:

`chatgpt-web-hwpx-mcp/capture-bundle/p3.13/v1`

Required artifact roles:

- source-document
- target-document
- source-raster
- target-raster
- line-box-capture
- font-inventory
- render-receipt

Optional custody artifacts include source/target PDF and runner log.

Every artifact carries:

- safe relative path
- SHA-256
- byte length
- semantic role

Each bundle may point to exactly one previous bundle SHA-256.
`verify_custody_chain` requires the first bundle to have no parent and every later bundle to point to the immediately preceding canonical bundle hash.

Authority:

`APPEND_ONLY_CAPTURE_CUSTODY_CHAIN`

## Near-wrap positive-sensitivity corpus

The corpus is sealed independently at:

`fixtures/p313_near_wrap_corpus.json`

Three roles are fixed:

1. `near-wrap-base` — stable baseline;
2. `near-wrap-plus-advance` — a one-run advance perturbation must trigger soft-wrap divergence;
3. `near-wrap-minus-frame` — a text-frame-width contraction must trigger soft-wrap divergence.

Promotion requires:

- baseline remains line-break exact,
- plus-advance divergence is detected,
- minus-frame divergence is detected.

A renderer that reports every fixture as equivalent therefore fails sensitivity certification rather than being rewarded for apparent invariance.

## Cross-version replay gate

P3.13 requires at least two distinct Hancom renderer versions.

The cross-version trial can yield:

- `CROSS_VERSION_EXACT_PIXEL_PROMOTION_CANDIDATE`
- `CROSS_VERSION_CALIBRATED_RENDER_AUTHORITY`
- `CROSS_VERSION_PIXEL_FIDELITY_HOLD`

Exact promotion candidacy requires:

- all trials have valid sealed world contact,
- every trial independently earns `PIXEL_RENDER_FIDELITY_PASS`,
- at least two distinct Hancom versions are present,
- near-wrap positive-sensitivity controls pass.

Without sensitivity certification, even two exact-looking Hancom trials remain HOLD.

## MCP surface

Server version:

`0.9.0-p3.13`

New tools:

- `get_near_wrap_sensitivity_spec()`
- `validate_render_capture_custody(bundle)`
- `verify_render_capture_chain(bundles)`
- `adjudicate_cross_version_render_replay(document_id, trials, sensitivity)`

These extend the P3.12 layout/world-contact tools rather than weakening them.

## Tests

`test_p313_capture_custody.py` covers:

1. Windows-only trusted runner identity;
2. complete artifact custody bundle;
3. valid append-only custody chain;
4. custody-chain break rejection;
5. two-control sensitivity corpus constitution;
6. positive-sensitivity certification;
7. exact cross-version candidate with sensitivity;
8. cross-version HOLD without sensitivity.

P3.13 lifecycle CI compiles and executes P3.11, P3.12, and P3.13 fidelity tests.

## Repository receipts

- trusted runner/custody/replay implementation: `39ff60379bc98a4308dc58450ab3488e2c67c961`
- custody/replay tests: `bd4787e78536e285fb7381c53b411a4ae73559bd`
- MCP surface + server version: `09dd2e7a7ed90110aed9e522299ac23c7804eb1c`
- Windows capture bundle sealer: `5e4ccc6715b76b802a5291c149e9f05510a2dd3c`
- production image packaging: `1a44fe951d64d19bd212863d537ac87898a9047d`
- lifecycle CI binding: `f403599506ff2108fe29af26e84d92eb468d6ccd`
- public-boundary P3.13 binding: `0a548ded2034ec8586ee520376099ff8ff93ef0e`
- near-wrap corpus manifest: `fd2502bed18ed4f5d1f001c9af1f0ab7b8ddb25b`

At ledger creation time GitHub combined status had not published checks for the current head.

Render production remained on P3.9 deployment:

`dep-dancnnbbc2fs73dvebi0`

No P3.13 production or genuine Hancom-capture authority is claimed yet.

## Authority boundary

P3.13 now specifies and validates the path by which genuine Windows/Hancom evidence may earn authority.

It has not yet executed a genuine Hancom capture in this environment.

Therefore the canonical state remains:

`WINDOWS_HANCOM_CAPTURE_NOT_YET_EXECUTED / CROSS_VERSION_WORLD_CONTACT_HOLD / PIXEL_RENDER_FIDELITY_HOLD`

## Successor

**ChatGPT Web HWPX MCP P3.14 — First Trusted Hancom Capture Intake, Near-Wrap Sensitivity Execution, Fixture-Corpus Replay, Cross-Version Evidence Join & Conditional Pixel-Fidelity Promotion**
