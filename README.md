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

### ChatGPT-native HWPX creation

- `get_document_plan_contract` exposes the declarative composition schema.
- `validate_document_plan` checks a plan without creating bytes.
- `create_document_from_plan` compiles an ordered block plan into one validated HWPX in a single atomic creation call.
- blank-document and owned-template append modes
- ordered paragraph/heading/list/table/equation/picture/page-break/section-break blocks
- preset document setup and formatting
- block-id references such as `$block:introduction` for bookmarks, cross-references and annotations
- dependency ordering for setup, formatting, references, native TOC and annotations
- idempotent replay through `request_id`
- private-candidate build: failed plans never partially commit a document

The language model remains responsible for deciding the document's content and structure. The MCP is the deterministic compiler/backend that turns that plan into HWPX.

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
- footnotes and endnotes
- anchored review memos/comments
- one- and two-level index marks
- external hyperlinks and bookmark navigation
- measured DATE/PATH/MAILMERGE/proofreading reference fields
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

P3.17-P3.22 turn that evidence into product behavior:

- `get_production_fidelity_contract` exposes the current edit-class authority envelope.
- `assess_edit_plan_fidelity` classifies a planned edit before mutation.
- `get_document_fidelity_profile` composes document-specific structural receipts with the production contract.
- `get_page_geometry` and `apply_page_geometry` expose revision-safe page-margin editing.
- `get_document_setup` and `apply_document_setup` expose atomic paper/orientation, header/footer, page-number, section, and multi-column editing.
- `get_structured_publishing` and `apply_structured_publishing` expose native lists, named styles, captions, bookmarks, page cross-references, TOC fields, and outline hierarchy.
- Native TOC/CROSSREF authoring delegates to `python-hwpx.tools.toc_author`, whose contract is based on Hancom-authored gold documents; this repository owns the transaction, locator, custody, and regression layers rather than duplicating that field format.
- `get_annotation_apparatus` and `apply_annotation_apparatus` expose footnotes/endnotes, memos, index marks, hyperlinks/bookmarks, and measured rich reference fields for academic/report publishing.
- Annotation authoring delegates to public `python-hwpx` note/reference/field APIs where available; unsupported field grammars remain fail-closed rather than guessed.
- `create_document_from_plan` is the high-level ChatGPT-native composition surface: the LLM supplies a declarative block plan and the MCP resolves block identities, dependency order, native objects, publishing fields, validation and atomic commit.
- `get_review_workflow` and `apply_review_workflow` expose native tracked insert/delete/replace, CLICKHERE form fields, check boxes, highlights/proofreading marks, and document metadata through the same revision/CAS transaction boundary.
- Review support is deliberately fail-closed: tracked-change accept/reject, tracking-only toggles/protection passwords, radio/command-button authoring, and document-history-part authoring are not guessed.
- `get_advanced_tables` and `apply_advanced_table_edits` re-promote the earlier P2.7/P2.8 table primitives into a product layer with merge/split, row operations, width/height, borders/fills, vertical alignment, repeating headers, page-break state, and advanced-layout receipts. Arbitrary column insertion remains evidence-gated.
- `get_story_layer` and `apply_story_layer` re-promote the P3.18 header/footer/page-number primitives into section-scoped story ownership: BOTH/EVEN/ODD variants, first-page visibility policy, variant page numbering, and section-boundary story configuration.
- P3.24 does not invent a FIRST header/footer story. HWPX story variants remain BOTH/EVEN/ODD; first-page behavior is expressed through section visibility (`hideFirstHeader`, `hideFirstFooter`, `hideFirstPageNum`).
- CI materializes document-level regression corpora for general editing, document setup, structured publishing, annotation apparatus, one-shot composition, review workflow, advanced tables, and section stories.

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
