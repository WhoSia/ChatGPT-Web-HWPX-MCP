from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p2_document import build_document_map
from p28_tables import apply_table_edits_atomic, build_table_map
from p339_design_intelligence import diagnose_document_design as diagnose_p339_document_design
from p340_feedback_loop import (
    apply_document_design_repairs_atomic,
    apply_nested_paragraph_alignment_atomic,
    compare_design_diagnostics,
    diagnose_document_with_render,
    plan_executable_editorial_repairs,
)

A1 = Path("artifacts/authorbench-a1-generative-ai-science.hwpx")
A2 = Path("artifacts/authorbench-a2-research-data-infrastructure.hwpx")
OUT = Path("artifacts/authorbench-a2-p340-evaluation.json")
PROBE_BEFORE = Path("artifacts/authorbench-a2-repair-probe-before.hwpx")
PROBE_AFTER = Path("artifacts/authorbench-a2-repair-probe-after.hwpx")
PROBE_DIAG_BEFORE = Path("artifacts/authorbench-a2-repair-probe-before-diagnostic.json")
PROBE_PLAN = Path("artifacts/authorbench-a2-repair-probe-plan.json")
PROBE_DIAG_AFTER = Path("artifacts/authorbench-a2-repair-probe-after-diagnostic.json")
PROBE_COMPARE = Path("artifacts/authorbench-a2-repair-probe-comparison.json")
CAPTURE_MANIFEST = Path("artifacts/authorbench-a2-hancom-capture-manifest.json")
HUMAN_PACKET = Path("artifacts/authorbench-a2-human-review-packet.json")

for path in (A1, A2):
    if not path.exists():
        raise RuntimeError(f"required benchmark artifact missing: {path}")

a1_frozen = diagnose_p339_document_design(A1, mode="POLISHED_REPORT")
a1_p340 = diagnose_document_with_render(A1, mode="POLISHED_REPORT")
a2 = diagnose_document_with_render(A2, mode="POLISHED_REPORT")

severity_high = {"HIGH", "CRITICAL"}
a1_high = sum(str(x.get("severity") or "").upper() in severity_high for x in a1_frozen["findings"])
a2_high = sum(str(x.get("severity") or "").upper() in severity_high for x in a2["findings"])
a1_codes = {str(x["code"]) for x in a1_frozen["findings"]}
a2_codes = {str(x["code"]) for x in a2["findings"]}

frozen_a1_failure_family = {
    "SECTION_HIERARCHY_CONTRAST_WEAK",
    "SECTION_SEPARATION_WEAK",
    "TABLE_CELL_PADDING_TIGHT",
    "TABLE_DENSITY_HIGH",
    "TABLE_HEADER_CONTRAST_WEAK",
}
observed_a1_family = sorted(frozen_a1_failure_family & a1_codes)
a2_survivors = sorted(frozen_a1_failure_family & a2_codes)

fresh_generalization_pass = bool(
    len(observed_a1_family) >= 4
    and not a2_survivors
    and a2_high <= a1_high
    and a2["finding_count"] < a1_frozen["finding_count"]
)
if not fresh_generalization_pass:
    raise RuntimeError(
        "A2 fresh generalization gate failed: "
        + json.dumps({
            "a1_findings": a1_frozen["finding_count"],
            "a2_findings": a2["finding_count"],
            "a1_high": a1_high,
            "a2_high": a2_high,
            "a1_observed_family": observed_a1_family,
            "a2_survivors": a2_survivors,
            "a2_codes": sorted(a2_codes),
        }, ensure_ascii=False)
    )

# A2 remains a clean fresh benchmark. The mutation challenge is a derived clone
# used only to verify that the P3.40 loop can detect and repair a controlled
# regression without contaminating the first-attempt generalization result.
shutil.copy2(A2, PROBE_BEFORE)
probe_doc = build_document_map(PROBE_BEFORE)
probe_tables = build_table_map(PROBE_BEFORE)
nested = [
    p for p in probe_doc["paragraphs"]
    if p.get("body_global_index") is None and len(str(p.get("text") or "").strip()) >= 18
]
if not nested:
    raise RuntimeError("A2 repair probe has no long nested paragraph target")
target_paragraph = max(nested, key=lambda p: len(str(p.get("text") or "")))
apply_nested_paragraph_alignment_atomic(
    PROBE_BEFORE,
    [str(target_paragraph["locator"])],
    alignment="CENTER",
)

probe_tables = build_table_map(PROBE_BEFORE)
body_cell = next(
    c
    for t in probe_tables["tables"]
    if int(t.get("rows") or 0) > 1
    for c in t["cells"]
    if int(c.get("row") or 0) > 0
)
apply_table_edits_atomic(
    PROBE_BEFORE,
    [{
        "op": "set_cell_margin",
        "table": next(t["locator"] for t in probe_tables["tables"] if body_cell in t["cells"]),
        "cell": body_cell["locator"],
        "left": 0,
        "right": 0,
        "top": 0,
        "bottom": 0,
    }],
    expected_revision=1,
    current_revision=1,
)

probe_before = diagnose_document_with_render(PROBE_BEFORE, mode="POLISHED_REPORT")
probe_codes = {str(x["code"]) for x in probe_before["findings"]}
if "TABLE_LONG_TEXT_CENTERED" not in probe_codes or "TABLE_CELL_PADDING_TIGHT" not in probe_codes:
    raise RuntimeError(f"controlled A2 probe did not expose intended findings: {sorted(probe_codes)}")

repair_plan = plan_executable_editorial_repairs(PROBE_BEFORE, probe_before)
if repair_plan["capability_gap_count"] != 0 or repair_plan["executable_count"] < 2:
    raise RuntimeError("P3.40 failed to compile controlled A2 probe defects to executable repairs")

shutil.copy2(PROBE_BEFORE, PROBE_AFTER)
repair_receipt = apply_document_design_repairs_atomic(
    PROBE_AFTER,
    repair_plan,
    expected_revision=1,
    current_revision=1,
)
probe_after = diagnose_document_with_render(PROBE_AFTER, mode="POLISHED_REPORT")
comparison = compare_design_diagnostics(probe_before, probe_after)
after_codes = {str(x["code"]) for x in probe_after["findings"]}
if "TABLE_LONG_TEXT_CENTERED" in after_codes or "TABLE_CELL_PADDING_TIGHT" in after_codes:
    raise RuntimeError(f"A2 repair probe defects survived repair: {sorted(after_codes)}")
if not comparison["high_severity_nonincrease"]:
    raise RuntimeError("A2 repair probe increased high-severity findings")

PROBE_DIAG_BEFORE.write_text(json.dumps(probe_before, ensure_ascii=False, indent=2), encoding="utf-8")
PROBE_PLAN.write_text(json.dumps(repair_plan, ensure_ascii=False, indent=2), encoding="utf-8")
PROBE_DIAG_AFTER.write_text(json.dumps(probe_after, ensure_ascii=False, indent=2), encoding="utf-8")
PROBE_COMPARE.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

capture_manifest = {
    "schema": "authorbench/a2/p340-hancom-capture-manifest/v1",
    "phase": "P3.40",
    "purpose": "native before/after render verification without altering fresh A2 generalization authority",
    "fixtures": [
        {
            "fixture_id": "AUTHORBENCH_A2_FRESH",
            "path": str(A2),
            "role": "FRESH_FIRST_COMPLETED_ARTIFACT",
        },
        {
            "fixture_id": "AUTHORBENCH_A2_REPAIR_PROBE_BEFORE",
            "path": str(PROBE_BEFORE),
            "role": "CONTROLLED_REPAIR_REGRESSION_BEFORE",
        },
        {
            "fixture_id": "AUTHORBENCH_A2_REPAIR_PROBE_AFTER",
            "path": str(PROBE_AFTER),
            "role": "CONTROLLED_REPAIR_REGRESSION_AFTER",
        },
    ],
    "required_authority": {
        "renderer_hancom_native": True,
        "executable_sha256_required": True,
        "positive_dpi_required": True,
        "page_raster_sha256_required": True,
        "before_after_same_font_environment_preferred": True,
    },
    "current_status": "PENDING_EXTERNAL_HANCOM_WORLD_CONTACT",
    "non_claim": "Static diagnostic improvement is not a native rendered improvement claim.",
}
CAPTURE_MANIFEST.write_text(json.dumps(capture_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

human_packet = {
    "schema": "authorbench/a2/human-review-packet/v1",
    "phase": "P3.40",
    "status": "PENDING_HUMAN_REVIEW",
    "compare": [
        str(A1),
        str(A2),
    ],
    "review_prompts": [
        "Is title/section hierarchy immediately legible without reading numbering?",
        "Do tables prioritize reading flow over geometric symmetry?",
        "Are padding and whitespace sufficient at normal viewing size?",
        "Does the callout encode priority without decorative excess?",
        "Does the page sequence feel coherent from summary through final recommendation?",
        "Is any page visibly crowded, imbalanced, or mechanically styled?",
    ],
    "authority": "HUMAN_REVIEW_REQUEST_NOT_MACHINE_VERDICT",
}
HUMAN_PACKET.write_text(json.dumps(human_packet, ensure_ascii=False, indent=2), encoding="utf-8")

payload = {
    "schema": "authorbench/a2/p340-evaluation/v1",
    "phase": "P3.40",
    "fresh_generalization": {
        "verdict": "PASS",
        "a1_finding_count": a1_frozen["finding_count"],
        "a2_finding_count": a2["finding_count"],
        "a1_high_count": a1_high,
        "a2_high_count": a2_high,
        "a1_frozen_failure_family_observed": observed_a1_family,
        "a2_frozen_failure_family_survivors": a2_survivors,
        "a2_codes": sorted(a2_codes),
        "authority": "FROZEN_P3.39_A1_BASELINE_VS_P3.40_A2",
    },
    "diagnostic_reconciliation_audit": {
        "a1_p339_finding_count": a1_frozen["finding_count"],
        "a1_p340_finding_count": a1_p340["finding_count"],
        "a1_p340_codes": sorted(str(x["code"]) for x in a1_p340["findings"]),
        "a2_p340_finding_count": a2["finding_count"],
        "a2_p340_codes": sorted(a2_codes),
        "authority": "DIAGNOSTIC_EVOLUTION_REPORTED_SEPARATELY_FROM_FRESH_DOCUMENT_GENERALIZATION",
    },
    "repair_probe": {
        "before_finding_count": probe_before["finding_count"],
        "after_finding_count": probe_after["finding_count"],
        "executable_count": repair_plan["executable_count"],
        "capability_gap_count": repair_plan["capability_gap_count"],
        "repair_receipt_sha256": repair_receipt["repair_receipt_sha256"],
        "resolved": comparison["resolved"],
        "introduced": comparison["introduced"],
        "high_severity_nonincrease": comparison["high_severity_nonincrease"],
        "native_rerender_verified": comparison["native_rerender_verified"],
        "render_claim": comparison["render_claim"],
        "authority": "CONTROLLED_NATIVE_MUTATION_REGRESSION",
    },
    "render_world_contact": {
        "status": "PENDING_EXTERNAL_HANCOM_WORLD_CONTACT",
        "manifest": str(CAPTURE_MANIFEST),
    },
    "human_review": {
        "status": "PENDING_HUMAN_REVIEW",
        "packet": str(HUMAN_PACKET),
    },
    "a1_immutability": "FROZEN_SOURCE_UNCHANGED",
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
