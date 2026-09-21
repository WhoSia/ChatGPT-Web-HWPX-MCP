# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for authenticated HWPX document creation, custody, validation, structured introspection, revision-safe editing, legacy HWP read/promotion, and fidelity testing from ChatGPT Web.

## What this repository contains

The GitHub repository is intentionally runtime-facing.

It contains:

- MCP server/runtime code
- HWPX/HWP parsing and edit modules
- durable OAuth/document-custody code
- tests and CI workflows
- required fixtures
- Windows/Hancom fidelity harnesses
- concise operational documentation

Historical phase ledgers, support packets, adjudication narratives, and long-form receipts are kept outside the runtime repository in the project Drive archive.

## Main capabilities

### Authenticated document lifecycle

- OAuth-protected MCP transport
- opaque document IDs
- bounded HWPX ingestion
- revision-safe mutation
- durable revision lineage
- signed export
- semantic/structure/formatting receipts

### HWPX editing

- paragraphs and text
- formatting and rich inline structure
- fields, hyperlinks and bookmarks
- tables
- pictures/objects
- equations
- bounded search/slice and bulk text plans

### Legacy HWP 5.x

- read-only native HWP parsing
- common document IR
- fidelity-graded extraction
- provenance-preserving HWP→HWPX promotion where authority is sufficient

### Hancom fidelity harness

The repository includes a Windows/Hancom capture lane for renderer evidence.

Current harness components include:

- self-materialized near-wrap fixture packs
- Hancom PDF export automation
- controlled PDF rasterization and line-box extraction
- artifact custody receipts
- positive-sensitivity calibration ladders
- font-file SHA-256 custody
- cross-version environment isolation
- cross-version boundary transport adjudication

Cross-version promotion is fail-closed: a second Hancom version must be captured under the same non-renderer environment before renderer-version authority can be promoted.

## Local run

Install runtime dependencies:

```bash
pip install -r requirements.txt
```

Run the authenticated server with the required deployment secrets/environment variables:

```bash
python server_p2.py
```

The canonical hosted service currently retains the historical Render hostname:

```text
https://chatgpt-web-hwpx-mcp-p0.onrender.com
```

Secrets are deployment-only and are not stored in this repository.

## Windows/Hancom replay

P3.15 uses one canonical cross-version runner:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\p315_run_cross_version_replay.ps1
```

The runner discovers installed `Hwp.exe` versions, freezes the same fixture bytes for both trials, cryptographically seals Windows font files before and after each replay, fresh-renders both Hancom versions, compares boundary transport, and emits a cross-version evidence ZIP.

If a second installation is not auto-detected, provide it explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\p315_run_cross_version_replay.ps1 -SecondHancomExe "C:\path\to\other\Hwp.exe"
```

Promotion remains closed unless the two trials have distinct Hancom versions/executable hashes while OS, machine, locale, DPI, rasterizer, fixture set, and cryptographic font-file custody all match.

## CI

The main lifecycle workflow compiles and tests the active HWPX/HWP runtime plus the renderer-fidelity adjudicators.

The fidelity harness does not simulate Hancom world contact in Linux CI. Real Hancom renderer authority comes only from sealed Windows capture evidence.

## Repository-record policy

Keep GitHub product-facing.

Do not add new phase-specific `*_TEST_LEDGER.md` files, historical support packets, or long-form phase diaries to this repository. Store those in the project Drive archive instead.

Raw world-contact artifacts should be preserved before adjudication.
