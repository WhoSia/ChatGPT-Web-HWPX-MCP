# ChatGPT Web HWPX MCP — Product Authority

This file is the single compact repository-level authority note for product phase state. Historical phase diaries, test ledgers, native-capture packets, and long-form closure evidence belong in Project Drive, not in the repository root.

## Current product line

- Last independently observed production identifier: `0.43.0-p4.18` (observed 2026-10-09; **current deployed SHA and deployed functionality unverified**).
- GitHub code state: **P4.20 PR #14 and PR #15 MERGED to `main`**; **P4.21 PR #16 MERGED to `main` at `dc946b73aaa33a7e1606c701647709653e8c5a6a` on 2026-10-13 12:54 KST**. The subsequently performed docs-only reconciliation commit is tracked separately. **Exact-head P4.4 and P4.12 Docker release workflows failed due to public ECR HTTP 429 base-image metadata rate limiting**; other checks passed. **Full release gate NOT PASS / production feature parity, native Hancom visual evidence, consumer roundtrip HOLD**.
- Active development program: **P4.21 — Independent Native-Render Fidelity & Bounded Professional Document Repair**, with source/CI-only progress and unresolved native/live consumer gates.
- Production authority remains evidence-separated from native Hancom visual authority.
- Public HWPX acquisition evidence does not imply redistribution permission.
- Runtime/product code changes require normal exact-head CI; documentation-only hygiene commits do not retroactively change the tested runtime evidence.

## P4.19 package migration — merged, deployment separate

PR #13 merged to `main` at `c0d8a39d4306fb3abaf38a395052eedd5b445f8a` with a validated identical PR tree, 89 root Python modules and retained human-authored commits. The refactor changed the source layout; it did not establish an equivalent Render live runtime or native-world document delivery.

## P4.20 recovery — source merged (PR #14 and #15), production authority separate

**Source chronology audit (rechecked after 2026-10-13 12:54 KST):** [P4.20 PR #14](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/14) merged **2026-10-09 23:25 KST** at `1b28199b21b72a392e791863b82cab850e750f69`; [P4.20 PR #15](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/15) merged **2026-10-12 15:11 KST** at `950bff8d3ed16f1d6eda20e190b2b32cd8280733`; **[P4.21 PR #16](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/16) merged 2026-10-13 12:54 KST** at `dc946b73aaa33a7e1606c701647709653e8c5a6a`. The prior Draft observation is a valid historical snapshot, NOT the current source state. On exact merge SHA, [P4.4](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/38343908674) and [P4.12](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/actions/runs/38343908727) Docker jobs failed to pull `public.ecr.aws` image metadata with **429 Too Many Requests / Data limit exceeded**, NOT due to a demonstrated HWPX runtime exception. **This is GitHub source/CI evidence, not a successful Render deploy, native Hancom screenshot or live consumer edit certificate**. Last independently observed Render identifier remains historical `0.43.0-p4.18`; public GitHub Releases list returned none; P4.18-P3 consumer content/delivery HOLD remains.

**Historical program predecessor: ChatGPT Web HWPX MCP P4.19 — Durable Document Lifecycle, Post-Commit Audit Persistence, Verifiable Delivery, Expiration-Aware Workflow Recovery & End-to-End Release Closure**

P4.19 source code is **MERGED**, while P4.20 addresses its post-merge regression and runtime integration failures. P4.18-P3 has an independently
retrieved revision-2 durable commit receipt and version history from the
human-approved production edit, but content preservation and downloadable file
delivery have **not** passed. P4.18-P3 PRODUCT CLOSURE remains **HOLD**, not
retroactively passed.

P4.19's retained product priority is a useful end-user document product, not merely more
byte-count assertions. First vertical slice: owner-scoped read-only
`get_document_workspace` aggregation of expiry, current revision, durable
receipt and version history, with truthful delivery status. Unexpired document
ownership is mandatory; no mutation, recovery, or download is inferred from
the overview.

P4.20 P4.21 continuing verification must distinguish source CI, real external fixture availability, deployed exact SHA, native Hancom world-contact and consumer file acquisition. Product roadmap and engineering priorities are documented in
[README.md](README.md). Every runtime promotion still needs exact-head
testing and actual production contact. GitHub Actions is test-only, never
a committing contributor. Small bounded fixes can land directly on main; major changes use short-lived PR branches. The separate p332-brownfield historical branch is retained by explicit user choice.

## P4.17 phase state

| Phase | State | Authority |
| --- | --- | --- |
| P4.17-P1 — Representative HWPX Corpus Acquisition, XML/Package Feature Extraction, Render-Pair Alignment, Document Archetype Census, Style-Grammar Mining & Ground-Truth Document Intelligence Dataset | **HOLD-CLOSED** | Kernel, exact-head Docker and lifecycle passed. Frozen multi-institution live-corpus criterion (`>=4 documents / >=2 institutions`) remained unmet and was not weakened. Reopen only with improved official-source transport or fresh source availability. |
| P4.17-P2 — Semantic Structure Recovery, Section/Role Hierarchy Induction, Repeated Layout Grammar Discovery, Native Component Classification, Cross-Document Structural Alignment & Corpus-Grounded Document Schema Inference | **CLOSED** | Semantic graph, hierarchy recovery, repeated-layout grammar, component classification, alignment and schema inference integrated with MCP/lifecycle. |
| P4.17-P3 — Intent-Aware Document Transformation Planning, Semantic-Graph-to-Native Edit Compilation, Reference-Conditioned Structure & Style Transfer, Constraint-Preserving Minimal Mutation, Template/Archetype Adaptation, Cross-Document Pattern Reuse, Repair-Aware Plan Validation & Corpus-Grounded Authoring Decision Engine | **CLOSED** | Code authority `3805680899e96e4492efb7d465230ee861110dca`: P4.17 corpus-kernel PASS, exact-head Docker PASS, full lifecycle PASS, Windows PASS. Remaining live-official-corpus failure belongs to the frozen P1 HOLD-CLOSED lane. |

| P4.17-P4 — Verified Native Transformation Execution, Transactional Semantic-to-HWPX Mutation, Constraint-Enforced Plan Realization, Mutation-Footprint & Fidelity Receipt Composition, Render-Grounded Post-Edit Validation, Automatic Repair/Replan Loops, Reference-Conditioned Authoring Execution & End-to-End Intent→Plan→Edit→Verify Document Intelligence | **CLOSED** | Runtime/code authority `25383e5c5f343a45a411ed24977da4d1923c691c`; release/production authority `27d63035d05cac2f44e4ef77489aae43a3db4289`. P4.17 CI #59 SUCCESS, full lifecycle #1512 SUCCESS, Windows SUCCESS, production boundary #1497 SUCCESS, Render deploy `dep-db2u41h42hec73ftvqmg` LIVE. Direct native edits, delegate-only reference/repair execution, bounded replanning, mutation-footprint/fidelity/semantic receipts, and P4.14-bound post-edit native authority composition are implemented. Caller-supplied render metadata cannot self-authorize native PASS. |

## Active authority boundaries

`RELEASE_AUTHORITY != DOCUMENT_AUTHORITY`

`ARTIFACT_IDENTITY != NATIVE_VISUAL_FIDELITY`

`SERVER_CLAIM != CONSUMER_VERIFIED_CLAIM`

`STRUCTURAL_SEMANTIC_INFERENCE != NATIVE_VISUAL_TRUTH`

`PLAN_AUTHORITY != EXECUTION_AUTHORITY`

`EXECUTION_AUTHORITY != NATIVE_VISUAL_AUTHORITY`

Transformation planning must fail closed or delegate when the existing native edit stack cannot support an operation. P3.17 fidelity classification, P3.42 mutation-footprint evidence, and P3.43 constraint-preserving style transfer remain reusable lower-level authority layers.

## Historical lineage

The following repository-root ledgers were retired from active source control after archival because they describe closed historical phases rather than current executable authority:

- P1 / P1.1 / P1.2 test ledgers
- P3.25, P3.27–P3.32 test ledgers
- P3.41–P3.49 test ledgers
- P3.44 AuthorBench freeze marker
- P4.1–P4.4 product/test ledgers

Earlier product phases remain available through Git history and the Drive archive. Their removal from the root does not erase commit history, CI runs, artifacts, or release evidence.

## Archive location

Project Drive → `90_ARCHIVE` → `Repository Ledger Archive` → **ChatGPT Web HWPX MCP — Archived Repository Ledgers**

The archive preserves each retired Markdown file verbatim with its Git blob SHA.

## Repository hygiene rule

Do not create new phase-specific `*_TEST_LEDGER.md` files in the repository root. Update this file only with compact current authority, boundary changes, and phase closure state. Put detailed phase evidence in CI artifacts, Git history, Notion, and the Project Drive archive.


## P4.18 phase state

| Phase | State | Authority |
| --- | --- | --- |
| P4.18-P1 — Unified End-User Document Task Facade, One-Call Create/Edit/Template/Deliver/Inspect Workflows, Verified Execution Composition, Native HWPX Handoff, Revision-Safe Delivery Recovery & Production Product Surface | **CLOSED** | Runtime/release authority `8e96c333d610d41fc8a1c0e1c2c9ed371158c83e`. P4.18 CI #7 SUCCESS, full lifecycle #1532 SUCCESS, production boundary #1517 SUCCESS. Render deploy `dep-db2uq3142hec7380cqgg` LIVE. Product `0.43.0-p4.18` exposes one primary typed task facade over verified create, edit-intent, template-fill, deliver and inspect capabilities while preserving revision guards, fail-closed routing, P4.17 execution receipts and native-authority separation. |

P4.18-P1 product rule: normal users should not need to compose the legacy low-level MCP tool graph manually. The facade routes bounded typed tasks onto already verified lower-level capabilities and returns structured HWPX delivery handoffs.
