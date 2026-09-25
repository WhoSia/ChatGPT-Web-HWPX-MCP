# P3.42 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.42 — Mutation-Footprint Certification, Expected-vs-Actual Package-Part Divergence, Preservation-Grade Enforcement, Public HWPX Corpus Probe→Verdict→Coverage Ledger & Evidence-Grounded Design Generalization**

## Inherited authority

- P3.35-R4 corpus registry, source provenance, licensing boundary, XML/style observations, style atlas, template candidates and optional visual controls.
- P3.40 executable native editorial repair and semantic/structure invariants.
- P3.41 page-composition grammar, polyglot-by-comparative-advantage rule, frozen AuthorBench A3 custody and Hancom-native world contact.
- P3.41-R1 human visual review closes with residual first-page whitespace and coarse archetype-rhythm differentiation; those residuals are successor design inputs, not retroactive P3.41 failures.

## New preservation explanandum

A mutation can preserve semantic/structure hashes while still rewriting package parts outside its intended scope. P3.42 therefore separates:

1. operation success;
2. HWPX package validity;
3. semantic/structure invariants;
4. **expected package-part scope**;
5. **observed changed/added/removed package parts**;
6. untouched common-part payload identity;
7. optional untouched ZIP-record metadata identity;
8. render/human evidence.

No lower layer silently promotes a higher one.

## Mutation-footprint certificate

Canonical implementation: `p342_mutation_footprint.py`.

### Grades

Strongest to weakest:

`PACKAGE_IDENTICAL > TARGETED_PARTS_ONLY > PACKAGE_VALID_ONLY`

- **PACKAGE_IDENTICAL** — whole-container SHA-256 identical.
- **TARGETED_PARTS_ONLY** — every observed changed/added/removed payload part is inside an independently declared exact scope and every untouched common-part payload is byte-identical.
- **PACKAGE_VALID_ONLY** — archives are inspectable but targeted preservation is unproved or contradicted.

### Exact-scope policy

- exact HWPX package paths only;
- no wildcards;
- no path traversal;
- additions/removals require separate explicit admission;
- missing required changes are divergence;
- ZIP record metadata is reported separately from payload identity.

### Atomic repair enforcement

The product `apply_document_design_repairs` no longer commits directly through P3.40. It routes through the P3.42 wrapper:

`original → temp candidate → P3.40 native repair → locator-derived expected scope → measured ZIP-part diff → preservation-grade enforcement → atomic replace`.

A grade below `TARGETED_PARTS_ONLY` blocks the original-file commit.

## Durable revision audit

New MCP surface:

- `get_mutation_footprint_contract`
- `certify_document_revision_mutation_footprint`

The revision auditor reads retained durable bytes, checks the current caller against both revision owners, measures the exact package delta, and applies the requested preservation grade. It is an audit surface; expected scope must not be invented after inspecting the diff.

## Corpus evidence constitution

Canonical implementation: `p342_corpus_evidence.py`.

P3.42 reuses the P3.35 owner-scoped registry; it does not create a competing corpus store.

### Probe IDs

- `BYTES_ACQUIRED`
- `PACKAGE_VALID`
- `PARSER_READBACK`
- `ROLE_EVIDENCE`
- `REUSE_RIGHTS_EXPLICIT`
- `PDF_CONTROL_BYTES_INSPECTED`
- `STRUCTURAL_STYLE_GENERALIZATION`
- `VISUAL_STYLE_GENERALIZATION`

### Verdicts

`PASS / FAIL / WITHHELD / NOT_APPLICABLE`

Every registered source remains in the source-level denominator. Metadata-only, withheld and not-applicable cases do not disappear from the ledger.

Exact-byte duplicate provenance remains visible, while the inherited P3.35 atlas grants one statistical style vote per exact byte specimen.

### New MCP surface

- `get_corpus_evidence_contract`
- `query_corpus_coverage_ledger`
- `query_evidence_grounded_design_generalizations`

Design generalizations are descriptive candidates only. Cross-institution support, document share, volume share and institution-balanced share remain separate. Structural XML support and inspected-PDF visual support remain separate evidence classes. There is no automatic design winner.

## Prospective public-HWPX denominator

`corpus/p342-public-corpus-metadata.json` freezes a 10-source official-page denominator before binary acquisition.

Policy:

- official page listing is evidence that a source is listed;
- it is **not** binary acquisition;
- public download is **not** automatically attachment-wide redistribution permission;
- metadata-only sources must remain `WITHHELD` for package/parser/design probes;
- the seed does not perform network fetching during CI.

`scripts/p342_public_corpus_ledger.py` materializes the deterministic denominator-preserving ledger and fails if metadata-only records acquire unsupported binary evidence.

## Polyglot constitution

- **Python** — package inventory, expected-scope reconstruction, corpus/probe orchestration, MCP integration.
- **Rust** — independent exact preservation-grade kernel.
- **TypeScript** — product-facing evidence contract plus independent preservation-grade kernel.
- **PowerShell** — inherited Windows/Hancom native-world-contact adapter.

Golden semantics: `benchmarks/p342_footprint_grade_golden.tsv`.

Rust/TypeScript disagreement with the shared grade fixture is a CI failure. Language count is not a quality target.

## Agent contract

`skills/hwpx-authoring/` now routes bounded repair through measured mutation-footprint review and corpus claims through the probe/coverage ledger. Detailed policy lives in:

- `references/mutation-footprint.md`
- `references/corpus-evidence.md`
- `references/evidence-authority.md`

The skill validator checks the modular registered surface rather than assuming every tool definition lives directly in `server_p2.py`.

## Test rails

Dedicated workflow: `.github/workflows/p342-ci.yml`.

It gates:

- Python compilation;
- P3.42 footprint/unit/integration tests;
- real composer → nested-table locator → native repair → exact package-part footprint;
- corpus denominator/generalization tests;
- P3.35 registry/atlas regression;
- P3.40 feedback-loop regression;
- P3.42 MCP registration + durable owner-bound revision audit;
- Rust exact-grade parity;
- TypeScript contract + exact-grade parity;
- inherited PowerShell/Hancom bridge parsing;
- authoring Skill/reference/tool-surface validation;
- public metadata denominator materialization;
- evidence artifact upload.

Inherited P3.40/P3.41/lifecycle/OAuth/production rails remain independent gates.

## External architecture harvest

P3.42 selectively re-expresses the strongest public `airmang/python-hwpx` patterns already audited in P3.41:

- measured, not asserted preservation;
- changed-part receipt;
- no-silent-true verification layers;
- probe → verdict → coverage ledger;
- explicit product/core/automation/skill boundaries.

No upstream application file is vendored wholesale.

## Development authority

Current intended authority once all exact-head gates pass:

`MUTATION_FOOTPRINT_CERTIFICATION_PASS / TARGETED_PART_PRESERVATION_ENFORCEMENT_PASS / CORPUS_PROBE_VERDICT_LEDGER_PASS / DESCRIPTIVE_GENERALIZATION_PIPELINE_PASS / PUBLIC_METADATA_DENOMINATOR_PASS`.

Not yet implied:

- public corpus binary-acquisition coverage;
- broad visual-style generalization from public sources;
- universal aesthetic authority;
- Hancom-native verification of every public source;
- changed-range identity inside a changed XML part.
