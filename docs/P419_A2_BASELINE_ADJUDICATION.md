# P4.19 — AuthorBench A2 Frozen-Baseline Provenance Adjudication

## Scope and original failure

The AuthorBench A2 CI had failed with three independently detected static
defect families in A1 and a frozen admission requirement of at least four.
A2 had zero static findings. The evaluator incorrectly assumed that every
frozen A1 design defect had to be rediscovered by its P3.39 static diagnostic.

## Evidence and bounded correction

Two distinct A1 authorities were already sealed:

1. `p339_design_intelligence.diagnose_document_design` observes
   `TABLE_CELL_PADDING_TIGHT`, `TABLE_DENSITY_HIGH`, and
   `TABLE_HEADER_CONTRAST_WEAK` in the frozen A1 artifact.
2. `benchmarks/authorbench_a1_human_review.json` records the
   `SECTION_SEPARATION_WEAK` defect, among other editorial assessments,
   with `HUMAN_VISUAL_REVIEW_GROUND_TRUTH_NOT_AUTOMATIC_AESTHETIC_NORM`
   authority. The frozen review also explicitly declares that one narrative
   defect is not supported by automatic static detection.

A2 admission now unions the named, independently observed defect families
from these **tagged authorities**. It continues to require four distinct A1
families. Human findings are **not** relabelled as machine observations;
the reported A1 static and human code sets remain separate. The original
A1 artifact, review, and A2 generator are unchanged.

A2's no-survivors and high-severity checks still use the A2 static diagnostic
alone. Their PASS is only a **static generalization** result. A2 has no
contemporaneous human review for the same class of judgments and has no
approved native Hancom rendering in this CI. Consequently no human visual
or native rendered quality promotion follows from this correction.

## Anti-regression and release interpretation

- A provenance mismatch in the frozen A1 review now fails evaluation.
- The >=4 distinct-family requirement is unchanged.
- A controlled mutated A2 clone must still be detected and repaired before
  the complete workflow can pass.
- Native Hancom world contact and human review remain independently pending.
- A successful A2 benchmark CI is **not** proof of native visual fidelity,
  verified consumer delivery, or permission to deploy production.

This repairs baseline evidence accounting, not the quality threshold and
not the frozen specimen itself.
