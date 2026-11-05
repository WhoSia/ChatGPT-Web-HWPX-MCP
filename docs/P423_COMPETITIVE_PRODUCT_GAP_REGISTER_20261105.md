# P4.23 — Competitive Capability Gap Register & Product-Focus Gate
**As of:** 2026-11-05 (KST) | **Type:** Product engineering backlog, not a research-paper roadmap

## Non-negotiable product outcome
A user submits a natural-language instruction, an existing HWPX or other source
file when relevant, and a desired document style. ChatGPT should produce an
editable, accurate, polished **HWPX** with usable preview, revisions, independent
validation, and deliverable bytes **without manual XML/paragraph-locator work**.

## Evidence and status legend
- **BASE**: Relevant implementation documented in source; reuse, do not rebuild.
- **PARTIAL**: Building blocks exist, but the complete user-facing workflow
  remains unverified or incomplete.
- **UNVERIFIED**: Code/claims exist but latest deployed runtime, exact-HEAD CI,
  real Hancom visual authority or user delivery has not met release acceptance.
- **GAP**: No complete implementation established by this audit. Do not infer
  complete absence from GitHub text-search misses; confirm with code+runtime tests.

The development branch is **NOT** the live Render service. PR test success is
not a claim of native Hancom fidelity, host attachment display, or user download.

## P0 — Actual HWPX authoring experience
| ID | Required user capability | Current status | Acceptance gate |
| --- | --- | --- | --- |
| DOC-01 | Natural request → valid finished editable HWPX → actual user download | PARTIAL/UNVERIFIED | End-to-end authenticated consumer opening of delivered bytes |
| DOC-02 | Existing uploaded school/government form, precisely anchored field and paragraph fill | PARTIAL | Template fixture: no unrelated text/geometry drift |
| DOC-03 | Reliable multi-page pagination, table splitting, widow/orphan and line wrapping | UNVERIFIED | Hancom-native all-page image review with no overflow |
| DOC-04 | Actual preview of every page before delivery | GAP/UNVERIFIED | Browser-visible page preview linked to exact document revision |
| DOC-05 | Visual change diff (before/after screenshots) with pinpointed repair | GAP/UNVERIFIED | Page-by-page render diff + reviewable corrections |
| DOC-06 | Automatically repair layout defects and re-render (bounded) | PARTIAL/UNVERIFIED | Real example: issue detected, fixed, independently rechecked |
| DOC-07 | Truly usable inline math, sentence punctuation, cases/matrix, baseline and equation font state | PARTIAL/UNVERIFIED | MRI human-edited equation corpus vs new output with Hancom PDF |
| DOC-08 | Formula-rich full science report without user manually correcting dozens of equations | GAP/UNVERIFIED | MRI end-to-end correction count and pixel/semantic checks |
| DOC-09 | Precise content insertion *inside* existing styled paragraphs | PARTIAL | Same paragraph retains pre/post text runs, math, memos and styles |
| DOC-10 | Images/charts/vector art with captions, text wrapping and intuitive position | PARTIAL/UNVERIFIED | RC report with native Hancom object geometry acceptance |
| DOC-11 | Complex nested/repeating tables across pages with style and totals intact | PARTIAL/UNVERIFIED | Three representative real multi-page business/school tables |
| DOC-12 | Accessible, publishable HWPX (alt text, heading navigation, table headers, language) | GAP/UNVERIFIED | Structured a11y report and supported safe fixes |
| DOC-13 | Reviewer's memos, tracked edits, accept/reject and collaboration complete | PARTIAL | Real round-trip including preserved anchors; unsupported tracked semantics explicitly blocked |
| DOC-14 | Final document quality rubric: typo, heading order, tables, captions, sources | PARTIAL | Human-read quality report, no fake native PASS |

## P0 — Personalization and reference templates
| ID | Capability | Current status | Acceptance |
| --- | --- | --- | --- |
| PER-01 | JSON per-request style profile → real HWPX output | PARTIAL/UNVERIFIED | Actual runtime use + formatting readback + Hancom PDF |
| PER-02 | Role-based style inheritance (body/title/heading) | PARTIAL/UNVERIFIED | Native source and visual verification, no inherited cycle |
| PER-03 | Extract single owned reference HWPX style as **reviewable candidate** | PARTIAL/UNVERIFIED | Owner-checked MCP preview and zero disclosure of source prose |
| PER-04 | Explicitly approve candidate → create HWPX in one MCP call | PARTIAL/UNVERIFIED | Live source-revision guard, host-confirmed approval, same bytes |
| PER-05 | User-owned persistent profile list/create/update/delete/rename | GAP | Authenticated CRUD, consent, version, revoke, deletion and tenant isolation |
| PER-06 | Multiple exemplar HWPX (3–10) → consensus style/organization pack | GAP | Role-level agreement, outliers, retained-text warning, human approval |
| PER-07 | Styles by organization/teacher/document type, not one global preference | GAP | Deterministic precedence and scoped override with UI |
| PER-08 | Learn corrections from before/after user-approved HWPX | PARTIAL | Specific rule extraction + explicit approval + no other-person leakage |
| PER-09 | Private reusable template library, version and rollback | PARTIAL/GAP | Owner-scoped list, version, defaults, rollback, delete |
| PER-10 | Design tokens/color/font presets and typography gallery | PARTIAL/GAP | One user choice reflected consistently in all native objects |

## P1 — Document agent, convenience and interoperability
| ID | Capability | Current status | Acceptance |
| --- | --- | --- | --- |
| AGT-01 | One natural-language call plans/executes/verifies/delivers | PARTIAL | At most 1–3 user-facing steps for common tasks |
| AGT-02 | Skill-first recipes for school report, scientific article, official notice, resume, form | GAP/PARTIAL | Document-specific runnable skill with expected quality checks |
| AGT-03 | Preview/dry-run approval and understandable diff | PARTIAL | No mutation before explicit approval for sensitive edits |
| AGT-04 | Undo/redo and rollback to a precise verified revision | PARTIAL | Live rollback and immutable revision integrity |
| AGT-05 | Batch data bindings, loops, conditions and repeated sections from JSON/CSV | GAP/UNVERIFIED | Template + 100-row test → 100 separately valid HWPX files |
| AGT-06 | Data-connected content (tables/charts with source provenance) | PARTIAL | Spreadsheet/CSV input → native chart/table with traceable values |
| AGT-07 | Markdown/HTML → rich native HWPX, including tables and math | GAP/UNVERIFIED | Complex markdown fidelity corpus |
| AGT-08 | DOCX ↔ HWPX and HWP 5.x → HWPX with format preservation | GAP/UNVERIFIED | Office/Hancom roundtrip, no unsupported silent substitution |
| AGT-09 | HWPX → PDF/PNG and image thumbnails reliably accessible in ChatGPT Web | PARTIAL/UNVERIFIED | Same exact SHA, Hancom capture, returned preview |
| AGT-10 | PDF/OCR/scanned forms → editable HWPX semantic structure | GAP | Multi-column OCR and forms/tables tested against human truth |
| AGT-11 | HWPX semantic compare with DOCX/PDF source | PARTIAL/GAP | Block-by-block meaningful differences and lost-feature report |
| AGT-12 | Public searchable document knowledge/RAG citations to source paragraphs | PARTIAL/GAP | Retrieval grounded to stable document revision and page anchors |
| AGT-13 | Multi-user collaboration, comments and role-based workflow | PARTIAL | Proven safe shared access, concurrent conflicts and approval policies |
| AGT-14 | Privacy redaction/PII scrub, metadata cleanup, sharing safety | GAP/UNVERIFIED | Verify underlying text is truly removed and not just obscured |

## P1/P2 — Professional publishing, operations and developer experience
| ID | Capability | Current status | Acceptance |
| --- | --- | --- | --- |
| PUB-01 | PDF/A, watermark, encryption, optimized PDF and page selection | GAP/UNVERIFIED | Validated PDF output with visual/metadata QA |
| PUB-02 | Footnotes, references, numbered captions, TOC that refresh on open | BASE/PARTIAL | Real native open/resave and update |
| PUB-03 | Institution language lint, style lint, terminology and citation checker | GAP/PARTIAL | User-configurable actionable findings, zero fake corrections |
| PUB-04 | Template/document version tagging and browsing | PARTIAL | Authorized searchable gallery, preview, rollback |
| OPS-01 | Exact-head CI, all test suites and source→Render deployment parity | UNVERIFIED | CI green; live SHA exact; smoke-tested release |
| OPS-02 | Independent native Hancom PDF visual test and consumer-openability | UNVERIFIED | All pages observed, same input, paired baseline |
| OPS-03 | Reproducible external competitor benchmark with equal tasks/runtime | GAP | Measured success, corrections, latency, tokens, artifact validity |
| OPS-04 | Cross-platform rendering and explicit capability fallbacks | PARTIAL/GAP | Windows/Mac/Linux matrix, no false equivalence |
| OPS-05 | API/tool discovery without overwhelming agents with dozens of tools | PARTIAL | User-task discovery, concise skill routing, token cost |
| OPS-06 | Reliability dashboard (failure modes, retries, costs, error reporting) | PARTIAL/GAP | Telemetry with protected data, error budgets, real incidents |
| OPS-07 | Formal release, setup/onboarding, tutorial and sample gallery | PARTIAL | New user independently completes 3 representative jobs |

## Already existing (do not duplicate merely because a competitor has it)
- Authenticated owner-scoped document identity and durable revisions.
- Atomic composition/edit, CAS guards, idempotency and encrypted custody.
- Existing HWPX paragraph/run/table/picture/equation/annotation/bookmark/TOC
  and many diagram primitives.
- Read-only HWP 5.x and document semantic, formatting and corpus maps.
- Existing P3.35 per-role style-exemplar analysis.
- Existing P4.18 document orchestration, preview/admission and review framework.
- Existing infrastructure for Hancom/native capture custody (not the same
  as a passing live visual/render gate).
- Existing draft P4.23 style profiles, cases/inline equation_line and
  reference candidate/approved creation (not yet proven in deployed runtime).

## Lessons grounded in competitor documentation
- **kordoc**: multi-sample agency packs, OCR/IR, document diff, government
  language/structure checks, direct render and empirically scored quality.
- **HwpForge**: blueprint inheritance, typed style rules, Markdown mapping.
- **python-hwpx-automation**: skill-first task procedures, single atomic mixed
  form transaction, dry-run/review/verify, copy-first reference preservation.
- **Dayoooun and flamingo8006**: many granular HWPX edit tools, but raw tool
  count is not a customer success metric.
- **Carbone**: JSON-backed template repetition, conditional sections,
  versioned template library, batch output and PDF finishing.
- **GenOffice**: visible editor session and headless CLI+skill+MCP access.
- **DOCX/PDF skills**: mandatory render→inspect every page→repair→rerender,
  accessibility, comments/revisions, true redaction, page-level diff.
- **Adobe Acrobat / Canva / Google Docs / Smallpdf**: rich UX, edit/review,
  conversion/export and template-oriented workflows.

## Mandatory focus order: no opportunistic feature drift
**Gate 0 (stop new feature proliferation):** exact P4.23 HEAD CI, reported
failures fixed; verify current Render/live version; require real existing-form
HWPX output and openable delivery; do not merge without proof.

**Gate 1 (one vertical slice):** take the user's MRI or another consented
HWPX reference → extract profile → explicit approval → populate existing
template with native inline/cases equations → render every page → inspect →
repair → deliver exact verified artifact. Record actual manual edits.

**Gate 2 (reuse):** owner-scoped profile and institution style pack with
versioned user control; only after Gate 1 works for single references.

**Gate 3 (interoperability/scale):** OCR, DOCX/PDF conversion, template batch
generation and advanced PDF processing, prioritized by measured user demand.

Do not turn this into a speculative paper or a second parallel renderer.
Implement only the next bottleneck in the verified user-facing flow.

## Primary sources
- Our [PRODUCT_AUTHORITY](../PRODUCT_AUTHORITY.md), [FEATURE_CATALOG](FEATURE_CATALOG.md),
  [ARCHITECTURE](ARCHITECTURE.md).
- https://github.com/chrisryugj/kordoc (including docs/agency-pack.md)
- https://github.com/ai-screams/HwpForge (docs/guide/style-templates.md)
- https://github.com/airmang/python-hwpx-automation (docs/skill-first-workflows.md)
- https://github.com/Dayoooun/hwpx-mcp
- https://github.com/flamingo8006/hwpx-mcp
- https://github.com/carboneio/carbone-mcp
- https://github.com/genspark-ai/genoffice
- Local DOCX and PDF production skills (render/inspect/repair, visual-diff,
  accessibility, redaction and delivery workflows).

This is a **capability register**, not a claim each feature is absent from
every repository path, or that any competitor has been experimentally beaten.
