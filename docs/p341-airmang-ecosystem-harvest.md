# P3.41 — airmang Ecosystem Architecture & Code Harvest

## Scope and method

This document records a repository-by-repository review of the public GitHub work under `airmang`, performed for ChatGPT Web HWPX MCP P3.41-R1. The goal is not to clone another stack or to count borrowed features. The goal is to identify ideas, implementation patterns, evidence disciplines, and packaging structures that can strengthen this repository.

Inventory reviewed: **15 public repositories**.

The review distinguishes four dispositions:

- **ADOPT NOW** — a pattern can strengthen P3.41 without expanding authority beyond evidence.
- **PREPARE SUCCESSOR** — useful, but belongs in P3.42+ or requires new world contact.
- **CONCEPT ONLY** — the idea is useful but the implementation should not be copied.
- **NO DIRECT TRANSFER / ANTI-PATTERN** — no useful HWPX transfer, or the observed implementation violates current safety/reproducibility standards.

No source file is wholesale copied into this repository. Architecture is re-expressed against our existing contracts, provenance, frozen benchmarks, and test rails.

## 1. python-hwpx

### What was inspected

The repository contains the core HWPX document library, large test/probe inventories, coverage/support ledgers, corpus measurement scripts, preservation contracts, renderer-neutral quality abstractions, and reverse-engineering evidence.

Key reviewed artifacts include:

- `docs/safe-write-contract.md`
- `docs/mutation-semantics.md`
- `docs/architecture/product-boundary.md`
- `docs/coverage-ledger.md`
- `docs/hancom-com-oracle.md`
- byte-identity/corpus scripts and the broader `probes/` lineage

### Strong patterns

1. **Measured, not asserted preservation.** A write receipt reports actual changed parts/ranges and verifies untouched-part identity rather than merely calling an operation "safe".
2. **Preservation grades are explicit.** Patch/rebuild/fallback are separate states; a requested strong grade can fail closed.
3. **No Silent True.** Package/open/reopen/visual verification states remain separate; unperformed visual verification is not a pass.
4. **Mutation semantics include rerun behavior.** Append, convergent, idempotent, and destructive behavior are documented rather than assumed.
5. **Probe → verdict → ledger.** Unsupported/native details are attacked with targeted probes, then promoted into a coverage/support statement only after evidence.
6. **Corpus denominator discipline.** Not-applicable cases are reported rather than silently excluded; measured claims state the denominator and write path.
7. **Product boundary as code.** Core/automation/skill ownership is checked with an explicit ledger and import/capability restrictions.

### Transfer to our repository

**ADOPT NOW / PREPARE SUCCESSOR**

- Keep P3.41 evidence layers explicit and non-scalar.
- P3.42 executable layout repair should issue a **mutation-footprint certificate**:
  expected changed HWPX parts, observed changed parts, unexpected parts, and untouched-part byte identity.
- P3.42 public-HWPX corpus work should use probe → verdict → coverage ledger rather than deriving capability from anecdotal documents.
- Add not-applicable/withheld cases to every corpus denominator.
- Keep core document semantics separate from Hancom/world-contact adapters and agent routing.

**Do not copy:** private byte-splice internals are not needed to obtain these governance benefits.

## 2. python-hwpx-automation

### What was inspected

- generated `docs/tool-contract.md`
- typed `ToolSpec`/classification contract
- explicit immutable `tool_bindings.py`
- preview/quality/render surfaces
- real-Hancom render submit/status/cancel/health
- resumable high-level workflow surfaces
- `visual_review_required` use across generation and quality paths

### Strong patterns

1. **One typed source of truth for the installed tool surface.** Names, lifecycle, profile, mutation flag, schemas, replacement/deprecation information and skill requirements derive from the same contract.
2. **Runtime drift detection.** Missing/unexpected tools, callable/schema/description mismatches and order drift are visible in health output.
3. **Explicit binding map.** Public tool name → implementation handler is immutable and checked for missing/unexpected/noncallable entries.
4. **Advanced/profile-gated tools.** Deep package inspection does not have to occupy the default agent surface.
5. **Real-render as an independent service.** Submit/status/cancel/health creates a durable boundary between authoring and native rendering.
6. **Visual review remains an explicit unresolved gate even when structural quality passes.**

### Transfer

**ADOPT NOW**

- Our HWPX authoring skill now receives a structural skill/tool-surface drift validator.
- Keep high-level authoring/design tools primary rather than expanding the normal surface with every primitive.

**PREPARE SUCCESSOR**

- Generate a compact product tool-contract snapshot/hash from our actual MCP registry instead of maintaining high-level documentation by hand.
- If Hancom rendering becomes a persistent service, model it as a distinct adapter/service with content hash/idempotency rather than embedding process control in every phase.

**Reject:** matching the other project's large default tool count. Tool count is not a capability objective.

## 3. hwpx-plugins

### What was inspected

- canonical root `SKILL.md`
- `references/`
- `scripts/build_hwpx_plugins.py`
- `scripts/validate_hwpx_plugin.py`
- evidence contract
- generated Claude/Codex/OpenClaw/Hermes bundles and packaging structure

### Strong patterns

1. **Canonical source, generated host bundles.** Host-specific copies are products of a build, not independently edited sources.
2. **Sync manifest with source/destination hashes.** Generated files remain attributable to canonical inputs.
3. **Generated-file cleanup is bounded.** Rebuild removes files recorded by the previous sync manifest instead of deleting the whole workspace.
4. **Plugin validation is much broader than syntax.** Front matter, links, identity, version constraints, product claims, host manifests and generated output are checked.
5. **Skill is a routing layer.** Detailed workflows live in references rather than making the top-level skill an unbounded manual.
6. **Evidence contract is shared.** Open-safety, visual review and submission claims have explicit prerequisites.

### Transfer

**ADOPT NOW**

- Keep `skills/hwpx-authoring/SKILL.md` as routing/constitution and move detailed authority/page-composition rules to `references/`.
- Add a structural validator that cross-checks the skill against the actual MCP server surface and local references.

**PREPARE SUCCESSOR**

- If/when we publish host-specific skill bundles, generate them from one canonical source and emit a sync manifest; never hand-maintain parallel host copies.

## 4. DIVE

### What was inspected

- product README and `AGENTS.md`
- spec/source-of-truth hierarchy
- `decisionGatePolicy.ts`
- permission summary / expected-vs-written path divergence
- patch preview
- verification coach
- MCP provenance helper

### Strong patterns

1. **AI self-report is not verification evidence.**
2. **Evidence-grounded intervention.** Warnings appear because concrete project state justifies them, not because generic risk prose is easy to generate.
3. **Criterion coverage.** A single generic observation does not satisfy several acceptance criteria; each required criterion needs evidence.
4. **Different evidence grades remain distinct.** Automated test failure, preview/manual observation, and AI self-report do not collapse into one Boolean.
5. **Expected vs actual change scope.** Writes outside an approved expected set become a first-class divergence signal.
6. **Patch/diff before approval.** The user sees the consequence before an approval decision.
7. **Rollback availability is part of risk.**
8. **MCP provenance is surfaced as data.**
9. **Low friction by default; add friction at high-risk or unverified states.**

### Transfer

**ADOPT NOW**

- P3.41-R1 human review is criterion-bound. Machine/native evidence can motivate a criterion but does not satisfy `USER_VISUAL_OBSERVATION`.
- A final human PASS requires complete manual criterion coverage.
- Review warnings remain evidence-specific rather than generic.

**PREPARE SUCCESSOR**

- Page-layout mutation plans should declare expected package parts/locators; actual mutation footprint outside that set should be a divergence.
- Multi-backend receipts should expose tool/server provenance when it affects authority.

## 5. dive-school-vibe-builder

### What was inspected

- `skills/dive-builder/SKILL.md`
- `skills/dive-builder/references/workflow.md`
- dependency-free `harness.mjs`
- composable `dive-webapp` skill
- skill evaluation cases
- `verify-package.mjs`

### Strong patterns

1. **Short canonical skill + references.**
2. **Composable specialization.** The webapp skill adds constraints without creating a second state machine.
3. **PASS vs MANUAL-PASS.** Tool evidence and user observation are explicit different states.
4. **Failure history is retained.** A later pass does not erase the failed attempt.
5. **Structural validator is honest about scope.** A static package check explicitly says it is not cloud/runtime E2E evidence.
6. **Dependency-free local harness.** Structural checks are cheap, deterministic and safe to run often.
7. **No destructive re-init of existing work.** Existing plans/agent instructions are preserved and merged.
8. **Real skill-evaluation scenarios are kept separate from local unit tests.**

### Transfer

**ADOPT NOW**

- Add a lightweight structural validator for `hwpx-authoring`: front matter, local references, balanced fences, required tool routing and actual server tool presence.
- Validator success explicitly does not claim native-render or human-review success.

**PREPARE SUCCESSOR**

- Add behavioral skill-evaluation scenarios for new-document authoring, brownfield editing, native-render unavailability, and residual-human-review cases.

## 6. EasyOCRCodex

A staged Codex build plan decomposes a Windows OCR application into scaffold → data model → annotation → alignment → OCR → batch → export → UI → logging → persistence → smoke → packaging → installer → sample → release checklist. Each stage names target files and a verification command.

**Transfer: CONCEPT ONLY.** Continue phase/capability decomposition with explicit verification commands. Do not adopt the weak provenance model or assume a local command equals a product/world-contact claim.

## 7. MEETutorial

MakeCode/Minecraft educational content packaging and tutorial links.

**Transfer: NO DIRECT CORE TRANSFER.** The useful abstraction is that lesson/content assets can remain separate from the execution engine. This reinforces skill/reference separation but supplies no HWPX implementation.

## 8. Minecraft

Small MakeCode exercises demonstrate recursive generation/backtracking and recursive nested construction.

**Transfer: NO DIRECT HWPX TRANSFER.** Educational algorithm examples only.

## 9. Bareun_Linux

A minimal Bareun morphology client/demo.

**Transfer: ANTI-PATTERN for current standards.** The inspected public source contains hard-coded credential material. Do not reproduce or migrate those values. Our connectors, examples and corpus tooling should keep secrets out of source and logs.

## 10. AIEDAP_Bareun

Archived training material that explicitly orders prerequisites: generate source data first, then run the analysis notebook/material.

**Transfer: CONCEPT ONLY.** Corpus pipelines should record upstream artifact prerequisites and refuse to imply a downstream result exists when intake/materialization has not occurred.

## 11. tutorial-test

MakeCode extension/tutorial packaging.

**Transfer: NO DIRECT CORE TRANSFER.** Host-specific packaging is relevant only at the abstract level already captured by the plugin/skill build model.

## 12. Streamlitapp

Small CSV upload/visualization demo.

**Transfer: NO MEANINGFUL TRANSFER.** It does not add evidence, document-model, mutation, or packaging patterns relevant to the HWPX MCP.

## 13. BareunPyQt5

A GUI template dominated by Qt Designer-generated UI plus handwritten controller/event code.

**Transfer: LOW-PRIORITY CONCEPT.** Generated presentation assets and handwritten behavior should remain separable. Our current MCP already separates native document/compiler logic from product/API orchestration more strongly.

## 14. assignment

Public repository is empty.

**Transfer: NONE.**

## 15. autodiagnosis

Legacy Selenium UI automation with brittle selectors and hard-coded personal/credential material.

**Transfer: ANTI-PATTERN.** Do not borrow. It reinforces the need for secret-free fixtures, stable native/API contracts over UI-coordinate automation, and explicit environment/user boundaries.

# Cross-repository synthesis

The strongest recurring architecture is not a particular Python class. It is a sequence of authority boundaries:

```text
probe / inspect
→ typed or declared plan
→ preview / expected scope
→ bounded execution
→ measured mutation receipt
→ structural/open verification
→ native render where relevant
→ explicit human observation where required
→ durable ledger / handoff
```

This aligns strongly with the existing P3.39–P3.41 direction, but exposes three gaps worth closing.

## Gap A — mutation-footprint authority

Current executable design repair proves semantic/structure invariants and can compare rendered results, but it does not yet publish a general package-part footprint contract.

**P3.42 placement**

- new neutral helper around HWPX package before/after bytes
- expected changed part set from repair plan
- observed changed/added/removed parts
- unexpected part changes fail closed for a strong preservation claim
- untouched-part payload identity count
- optional changed-range evidence where a safe coordinate system exists
- receipt remains independent of whether visual quality improved

## Gap B — skill/tool contract drift

The authoring skill names a preferred high-level tool path, but before P3.41 this guidance had no explicit structural cross-check against the server source.

**P3.41 adoption**

- `skills/hwpx-authoring/references/` carries detailed authority and page-composition rules.
- `scripts/validate_hwpx_authoring_skill.py` checks front matter, local links/references, required guidance and actual `server_p2.py` tool presence.
- CI success is labeled structural only; it cannot promote render or human authority.

**P3.42/P3.43 successor**

Generate a compact tool-contract artifact from the registered MCP surface and bind the canonical skill bundle to its contract hash.

## Gap C — evidence-bound human review

P3.41 native page diagnostics already separated native authority from human authority, but open-ended questions were weaker than criterion coverage.

**P3.41-R1 adoption**

- stable visual-review criterion IDs
- machine signal(s) attached to the criterion that they motivate
- required evidence class = `USER_VISUAL_OBSERVATION`
- final PASS fails closed if any criterion lacks manual evidence
- machine/native PASS cannot silently satisfy a human criterion

# Placement map

| Borrowed pattern | Our location | Timing |
|---|---|---|
| Criterion-bound human evidence | `p341r1_adjudicate.py` | P3.41-R1 |
| Skill routing + references | `skills/hwpx-authoring/` | P3.41-R1 |
| Skill/tool drift validator | `scripts/validate_hwpx_authoring_skill.py` + P3.41 CI | P3.41-R1 |
| Cross-language geometry parity | Python/Rust/TypeScript golden fixture rail | already P3.41 |
| Hancom native adapter boundary | PowerShell capture + future service adapter | P3.41, expand later |
| Mutation footprint certificate | package before/after verifier | P3.42 |
| Probe → verdict → coverage ledger | public HWPX corpus research | P3.42 |
| Generated tool-contract hash | MCP registry + skill package | P3.42/P3.43 |
| Design rules as resources | product resource surface | P3.42/P3.43 |
| Host bundle generation | future distributable skill/plugin packaging | only when needed |
| Live Hancom session authority | optional live-host bridge | later, evidence-gated |

# Explicit non-adoptions

- No target number of languages.
- No target number of MCP tools.
- No wholesale import of another repository's workflow engine.
- No copying of credential-bearing examples or personal data.
- No UI-selector automation where a stable native/package/API contract exists.
- No claim that structural skill validation proves real host behavior.
- No replacement of frozen A1/A2/A3 evidence with post-hoc regenerated artifacts.
- No automatic human-review PASS from machine evidence.

# Research conclusion

The airmang ecosystem is most useful to this project as a **discipline of boundaries**: core vs automation vs skill, expected vs actual mutation, static vs native vs human evidence, canonical source vs generated bundle, probe vs promoted capability, and tool success vs verified outcome.

P3.41-R1 adopts the pieces that strengthen those boundaries without widening scientific or product claims. P3.42 should carry the deeper engineering transfers: mutation-footprint receipts, public-corpus coverage ledgers, and generated skill/tool contract binding.
