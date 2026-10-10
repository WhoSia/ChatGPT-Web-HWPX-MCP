# ChatGPT Web HWPX MCP P4.21 — Independent Native-Render Fidelity & Bounded Professional Document Repair: Cross-Renderer Falsification, Typography–Pagination Invariants, Semantic Preservation & Human Acceptance

**Study state:** PROSPECTIVE STUDY FORMALLY OPEN — no new native capture or independent human verdict collected.
**Lineage:** P4.11 render oracle + P4.20 quality court (baseline commit 950bff8d).
**Deployment:** PR #15 and Render production remain HOLD. P4.21 development is on a separate research branch.

## Scientific primitive

When can a syntactically valid and semantically preserved HWPX be judged
professionally usable *in the actual editor*? Can a bounded repair procedure
improve that outcome on independent documents, or does it simply shift
artifacts and errors between regions, fonts, pages and renderers?

P4.11 provides a typed defect vocabulary and provisional bounded repairs.
P4.20 provides native structural validation, revision-safe mutation and
non-promoting mechanical evidence. Neither proves prospective generalization
to unseen documents and render conditions. P4.21 targets this remaining gap.

## Five rival hypotheses

1. **Mechanical-pass rival.** A structurally valid package still contains
   native-only clipped text, missing figure labels or font substitutions.
2. **Repair-rival.** Apparent improvements arise from moving hard defects
   elsewhere or silently changing table/equation/footnote semantics.
3. **Generalization-rival.** Improvements disappear on independently sampled
   documents not present in P4.11/P4.20 calibration.
4. **Renderer-rival.** Improvements depend on font availability, Hancom build,
   or an alternative layout engine rather than the repair itself.
5. **Acceptance-rival.** A mechanically clean render is nonetheless
   rejected by blinded human readers on professional usability.

The null includes no benefit at equal compute/repair budget; no metric or
threshold may be retroactively tuned on confirmatory cases.

## Locked study design

- Pilot: 12 new independent HWPX documents, 3 from each of academic reports,
  long tables, equation-heavy notes, and image/footnote composites.
- Confirmatory: 24 further independent HWPX documents, 6 per archetype.
- P4.11 known-calibration sources and P4.20 synthetic fixtures are excluded.
  The archived source hashes from P4.11 are stored in the companion manifest.
  No pilot/confirmatory source SHA-256 may repeat.
- Four-cell **2 x 2 design**, never a confounded single before/after pair:
  (baseline and candidate) x (Hancom and an independent native-capable
  alternative layout engine). If no second engine demonstrably preserves HWPX
  semantics, leave cross-renderer identification on HOLD rather than counting
  PDFium/Poppler rasterization as another HWPX layout implementation.
- Separate cross-*version* Hancom comparison is permitted, but it cannot
  replace the cross-*renderer* factorial test.
- Each renderer's before/after artifacts, fonts, engine build, operating
  system, printer and page settings must be matched and hash recorded.
  Explicitly flag drifting font environments, builds or artifacts.
- Maximum two whitelisted repair actions per source, equal resource budget
  for every rival approach, fixed repair selection and seed before observing
  confirmatory outcomes. Provenance and fresh capture are mandatory.
- Minimum two independently blinded human judges. Record individual judgments,
  disagreements and acceptance grounds; no LLM may substitute for them.

## Capture, evaluation and falsification

For each page retain exact document SHA-256, capture timestamp, independent
host provenance, renderer version/build, font inventory hash, raster SHA-256,
resolution, extracted paragraph-line/page boundaries, table split identities,
equation object and script, floating anchor and caption relationships,
footnote references, and source-to-render alignment.

**Do not merge dimensions into a scalar beauty score.** Report: text
disappearance; clipping; object overlap; unintended reflow; page splits;
font substitution; equation and table preservation; accessibility/readability
judgments; human pairwise acceptance; independent renderer agreement.
Page-flow change is descriptive, not intrinsically a defect. A document may
reflow acceptably while still obeying semantic invariants.

A repaired image must be genuinely recaptured in the intended renderer.
A metadata field asserting that a capture was attested has **zero authority**
without an independently verified chain. Pixel hashes bind claimed bytes,
but cannot establish that Hancom ran. Likewise, the shadow-court unit tests
use synthetic strings and **must not be counted as native evidence**.

## Prespecified hard stopping rules

Immediate FAIL: content deletion or semantic/equation changes; prohibited
repair; missing text, fatal clipping, new hard defect, contaminated split,
altered capture environment, reused raster, or failed source binding.

HOLD: no native capture, missing independent observer, unavailable genuine
cross-layout engine, unresolved cross-version disagreement, human panel
unavailable, or unreproduced baseline. With no verified source, report
HOLD and never release.

Full native publication acceptance requires independent artifact attestation,
typed visual SLO, preserved semantics, 2 independent human judgments, and
no novel unadjudicated hard defect. The Python court in this phase is
**permanently shadow-only** and cannot issue deployment authorization.

## Runbook — small number of expensive experiments

1. Version control protocol, 36 empty case slots and adversarial unit tests.
2. Collect approved genuinely independent source HWPX files, audit uniqueness
   and freeze actual enrollment without accessing confirmatory renders.
3. Run structural controls and 12 pilot source captures on genuine Windows
   Hancom. Verify independent custody from outside the evaluation engine.
4. If alternative native engine is viable, run factorial controls. If not,
   publish a cross-renderer identification HOLD and continue within-engine
   Hancom cross-version experiments without relabeling the inference.
5. Diagnose first observed rival failures. Commit code changes in batches.
   Use GitHub Actions for deliberately selected evidence milestones, not
   after every small development commit.
6. Lock repair budget/evaluation before starting the 24 independent cases;
   retain every negative result, abstention, and human disagreement.

**Ownership and safety:** Do not merge P4.20 PR #15, auto-deploy Render,
alter operational Neon backups, rewrite branches, or claim a tested
Windows/Hancom rendering session from synthetic fixtures.
