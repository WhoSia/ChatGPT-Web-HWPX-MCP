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
- page-margin geometry with revision/CAS protection
- paper size/orientation and section page setup
- section creation/removal
- header/footer stories and automatic page numbers
- multi-column layout and page-number restart controls
- native bullet/numbered lists and outline hierarchy
- named-style application
- table/picture/equation captions
- bookmarks, page cross-references, and Hancom-native TOC fields
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

Fidelity authority is layered. Renderer-independent HWPX structural evidence is kept separate from renderer evidence. P3.16 established version-indexed exact authority for Hancom 13.0.0.3622 under the sealed environment; global cross-version promotion remains fail-closed until a second Hancom version is captured under the same non-renderer environment.

P3.17-P3.19 turn that evidence into product behavior:

- `get_production_fidelity_contract` exposes the current edit-class authority envelope.
- `assess_edit_plan_fidelity` classifies a planned edit before mutation.
- `get_document_fidelity_profile` composes document-specific structural receipts with the production contract.
- `get_page_geometry` and `apply_page_geometry` expose revision-safe page-margin editing.
- `get_document_setup` and `apply_document_setup` expose atomic paper/orientation, header/footer, page-number, section, and multi-column editing.
- `get_structured_publishing` and `apply_structured_publishing` expose native lists, named styles, captions, bookmarks, page cross-references, TOC fields, and outline hierarchy.
- Native TOC/CROSSREF authoring delegates to `python-hwpx.tools.toc_author`, whose contract is based on Hancom-authored gold documents; this repository owns the transaction, locator, custody, and regression layers rather than duplicating that field format.
- CI materializes document-level regression corpora for general editing, document setup, and structured publishing.

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

Native Hancom replay is an evidence batch, not a requirement for every feature commit. Normal feature development and regression run in Python/Linux CI; Windows PowerShell is used only when a group of edit classes is ready for native-render certification or when renderer-specific behavior must be diagnosed.

The completed P3.16 single-version stability runner is archived in the project Drive rather than kept on the active runtime surface. Its promoted authority remains recorded in the canonical Drive receipt.

Cross-version reopening remains available through the P3.15 runner:

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
