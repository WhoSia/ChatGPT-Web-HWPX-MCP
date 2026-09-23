# P3.35-R4: evidence to reusable style candidates

Formal scope: **Public HWPX Corpus Intake Registry, Source Provenance & Licensing Metadata, PDF Visual-Control Layer, Aesthetic Pattern Annotation, Cross-Institution Style Atlas & Evidence-Guided Template Synthesis**.

## Gate 0 and ancestry

Starting head `5a09848942c7aad29814e07dddedfed50e8d0640` failed lifecycle #849: a generated fixture contained one default empty structural paragraph and one textual body paragraph. The role extractor counted both as textual support. `7d847a15bf1df06931b29bd414c5c607e23bfc29` retains every assignment but excludes empty/whitespace paragraphs from role exemplar support. Eight paragraph tests and exact-head lifecycle #850 passed. This is a support-contract repair, not an assertion relaxation.

Render separately remained LIVE at P3.34 commit `19bfce6d29adaf8aba20487fcf4eeea3ed85575f`, deployment `dep-dapvu1rbc2fs73c7bi0g`. Its configured auto-deploy had not produced a P3.35 deployment. Classify this as `PRODUCTION_VERSION_STALE`/deployment lag, separately from 429/503 and feature regressions. R4 health includes `release_commit`; the production gate checks exact head, durable stores, OAuth discovery and unauthenticated MCP rejection. Eight health attempts use 10/20/40/60-second backoff, capped Retry-After, no nested retries, and workflow concurrency cancellation. The receipt records observed HTTP/version/head states without dumping remote bodies.

R4 reuses P3.35 typography, paragraph and role extraction, P3.0 encrypted PostgreSQL custody, P3.22 formatting validation/CAS/rollback and P3.33 artifact delivery. No new HWPX or graph mutation engine.

## Register, inspect and query

`register_corpus_source(metadata, document_id?, expected_receipt?)` freezes the owned durable revision's bytes for extraction. No caller filesystem paths, arbitrary URL fetching, or source redistribution. Without a document ID it records metadata only, with `BYTES_NOT_ACQUIRED` exclusion. Repeated identical intake is idempotent; changed records require the prior receipt hash. `get_corpus_source` reads current or historical revisions. `set_corpus_inclusion` appends a curator decision without erasing history. `query_corpus_registry` filters institution, family and inclusion status with 20-row pagination; coverage and duplicate relations remain available.

Required metadata: `source_id`, `original_filename`, `institution`, timezone-qualified `retrieved_at`, `access_status`. Optional title/family/URL, license statement and license URL, provenance notes, declared native status. Public access is independent of reuse rights. An explicit license claim requires both its statement and source; no unknown-rights record becomes open merely because it downloads. Even explicit-license records do not automatically authorize redistribution. Native status supplied by a caller remains declared, not independently verified.

Receipts carry package/parser/role status, exact byte hash, native profile hashes, source revision, controls and annotations. Canonical sorted JSON produces source receipt, registry and included-corpus hashes. All updates are append-only, owner-scoped, encrypted with source/owner-bound AAD in `hwpx_corpus_receipts`, and serialized by owner with receipt CAS. Maximum 500 sources per owner and 2 MB per source observation. Receipt/history queries do not reparse source files; derived observations remain available after document byte retention expires. The registry is not a permanent archive of original bytes.

An exact-byte duplicate retains all source receipts but receives one statistical vote (deterministic first source ID in the selected scope). The registry flags matching style fingerprints as **style similarity**, not semantic duplicate proof. Source attribution conflicts remain inspectable. For a large owner collection, list pages are bounded but atlas construction intentionally works on the bounded snapshot in memory; no background scraping or heavy indexing service is introduced.

Offline example:

```powershell
python scripts/corpus_intake.py --metadata corpus/public-seed-metadata.json --out artifacts/p335r4/registry.json
# Optional acquired local sources are named <source_id>.hwpx under --source-dir.
```

The small public seed contains official listings from MOIS, MOE and the National Museum of World Writing (published through MCST). These are metadata-only records: three observed listings, no invented binary hashes, parser success or PDF rendering. The MOE page states work-specific public attribution terms; the other two records retain unknown reuse rights. Exact URLs and observation scope are in `corpus/public-seed-metadata.json`. Public-file acquisition/curation remains separate from machinery verification.

## Visual controls and annotations

`pair_corpus_visual_control` validates source hash, PDF hash, renderer/version/route/time and bounded positive page geometry. Remote metadata is always `DECLARED_UNVERIFIED`; a caller cannot self-assert inspected bytes. `inspect_pdf_control` is an offline optional PyMuPDF adapter from `requirements-capture.txt`: it checks actual PDF bytes, page dimensions and interpretable text-bounding-box density proxies while leaving renderer-route provenance declared. These proxies are neither true ink coverage nor beauty scores. Missing PDF controls are supported explicitly.

`annotate_corpus_source` accepts native XML, render-control, human-note and heuristic evidence types. Computed native role/body size ratios identify their method and source hash. Submitted notes remain declared. Render notes must bind to a paired control; heuristic/native submitted observations require method ID/version/parameters/applicability/confidence. Pairwise human notes can refer to another accessible source. `compare_corpus_visual_controls` reports page/route metadata differences, never a pixel equivalence or native-fidelity verdict. Native Hancom PDF export/open/resave for the public seed remains unobserved.

## Atlas and synthesis

`query_style_atlas` filters role, institution, source family and run/paragraph dimension. It returns every regime through pagination, document support, text-volume support, institution-balanced support, concentration and entropy. Minority regimes are retained. Per-source typography/paragraph distributions expose within-document variation; institution strata expose within-institution variation. No dominant regime becomes a normative or aesthetic winner.

`synthesize_corpus_templates` has three modes:

- `EXPLICIT_EXEMPLAR`: requested source and roles; missing roles fail explicitly.
- `CORPUS_SUPPORTED`: alternative single-role presets passing minimum document/share thresholds.
- `COHERENT_BUNDLE`: requested roles must co-occur with identical presets in supporting documents of the same institution. Independently common roles are never silently mixed across institutions.

Each candidate includes a template hash, included-corpus hash, source receipts, dimension provenance, support, compatibility and unresolved/readback-only fields, with authority `EVIDENCE_GUIDED_TEMPLATE_CANDIDATE`. `plan_corpus_template_transfer` recomputes the selected candidate against the current owner registry and rejects stale corpus hashes. It emits only existing `set_run_format`/`set_paragraph_format` operations and the target revision. Apply with `apply_formatting` for existing validation/CAS/rollback, then `deliver_document` for the actual file. Native-only tabs and non-invertible script dimensions are not promoted into write keys. The plan is evidence-bound at creation; document revision CAS remains the authority at application.

## One long-lived Windows environment

All ten historical capture/replay runners use `scripts/common/EnvBootstrap.ps1`. Default: `%LOCALAPPDATA%\ChatGPT-Web-HWPX-MCP\venv\py312`, external to clone and generated evidence. Override with absolute `HWPX_MCP_VENV`; set `HWPX_MCP_PYTHON` if Python 3.12 discovery needs an explicit base interpreter. New clones reuse the same path. Dependencies synchronize only when canonical core/capture/dev requirements hashes change; the receipt records Python, fingerprint and last successful synchronization. Failed installs do not advance it. A lock prevents concurrent updates. Paths with spaces are supported.

`-RebuildVenv` explicitly recreates a registered environment only after matching its receipt and checking against junctions/unsafe paths. ABI mismatch/corruption does not silently create another phase environment. Generated native packs include a small source-only `runtime/` plus hashed runtime manifest and requirements, never Python binaries, caches or a virtual environment. Use analyzers under `runtime/scripts/` with `--pack` for existing evidence. For new captures choose a NEW `-OutDir`; never rematerialize over native evidence. The portable runtime uses the same external environment.

`scripts/test_shared_environment.ps1` tests external defaults, overrides, spaces, unchanged/changed fingerprints, reuse across clone paths, explicit rebuild, unsupported ABI and unsafe rebuild rejection. Lifecycle CI runs this on Windows. No existing user environment or archived evidence is deleted by migration.

## Storage and archive policy

GitHub: code, tests, workflows, small metadata and deterministic materializers. Drive: unique native captures, before/after bytes, meaningful PDF controls, selected public originals and provenance. `scripts/artifact_retention_manifest.py ROOT --out inventory.json` inventories hashes and KEEP/KEEP_REVIEW/REGENERATE/DISCARD recommendations; it performs no deletion or upload. Ambiguous originals default to review. Environment/cache retention is independent of evidence custody.

The connected Drive archive currently exposes its curation manifest but not the named native capture ZIPs. This observation is not a complete audit of every Drive location. Archive byte verification is required before deleting any unique native evidence. Reproducible R4 reports are generated locally rather than uploaded as redundant archives.
