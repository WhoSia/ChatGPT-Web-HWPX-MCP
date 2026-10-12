"""P4.21 prospective renderer experiment, fail-closed and shadow-only.

This module inspects reported observations. It cannot prove a real Hancom
invocation or attest raster origin. Such authority must come from an
independent external custodian.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Mapping, Sequence

from hwpx_mcp.rendering.p411_visual_oracle import (
    ALLOWED_REPAIRS, FORBIDDEN_REPAIRS, detect_native_visual_defects,
)

SCHEMA = "chatgpt-web-hwpx-mcp/p421/prospective-render-court/v1"
SHA = re.compile(r"^[a-f0-9]{64}$")
ARCHETYPES = ("academic_report", "long_table", "equation_heavy", "image_footnote")
COHORTS = {"pilot": 12, "confirmatory": 24}
HARD = frozenset({
    "VECTOR_ESCAPE", "REGION_CLIP", "TEXT_DISAPPEARANCE",
    "LABEL_VALUE_DETACHMENT", "KPI_CONTAINER_COLLAPSE",
    "OBJECT_OVERLAP", "ALIGNMENT_DRIFT",
    "NATIVE_ONLY_SERIALIZATION_DEFECT",
})


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def registration_contract() -> dict:
    """Allocate study slots, but invent no sources, people, or observations."""
    slots = [
        {"case_id": f"p421-{phase}-{family}-{n:02d}",
         "cohort": phase, "archetype": family, "state": "UNENROLLED"}
        for phase, per_family in (("pilot", 3), ("confirmatory", 6))
        for family in ARCHETYPES
        for n in range(1, per_family + 1)
    ]
    receipt = {
        "schema": SCHEMA,
        "phase": "P4.21",
        "mode": "PROSPECTIVE_SHADOW",
        "cohorts": dict(COHORTS),
        "archetypes": list(ARCHETYPES),
        "slots": slots,
        "max_repairs_per_case": 2,
        "min_independent_human_reviewers": 2,
        "independent_sources_required": True,
        "no_cross_cohort_reuse": True,
        "production_release_eligible": False,
        "authority": "UNENROLLED_PREREGISTRATION",
    }
    receipt["registration_sha256"] = digest(receipt)
    return receipt


def audit_enrollment(
    registration: Mapping[str, Any],
    enrolled: Sequence[Mapping[str, Any]],
    *, disallowed_source_hashes: Sequence[str] = (),
) -> dict:
    """Reject leaked sources, unknown slots and post-hoc split changes."""
    slots = {x["case_id"]: x for x in registration["slots"]}
    used_ids: set[str] = set()
    used_sources: set[str] = set(disallowed_source_hashes)
    issues: list[dict] = []
    for row in enrolled:
        cid = str(row.get("case_id") or "")
        source = str(row.get("source_sha256") or "")
        if cid not in slots or cid in used_ids:
            issues.append({"code": "UNKNOWN_OR_DUPLICATE_SLOT", "case_id": cid})
        used_ids.add(cid)
        if not SHA.fullmatch(source):
            issues.append({"code": "INVALID_SOURCE_HASH", "case_id": cid})
        elif source in used_sources:
            issues.append({"code": "SOURCE_REUSE_OR_LEAKAGE", "case_id": cid})
        used_sources.add(source)
        if cid in slots and (
            row.get("cohort") != slots[cid]["cohort"]
            or row.get("archetype") != slots[cid]["archetype"]
        ):
            issues.append({"code": "ASSIGNMENT_DRIFT", "case_id": cid})
    return {
        "status": ("FAIL_ENROLLMENT" if issues else
                   "READY_FOR_CAPTURE" if len(used_ids) == len(slots) else
                   "HOLD_UNFILLED_COHORT"),
        "registered_count": len(slots),
        "enrolled_count": len(used_ids),
        "issues": issues,
        "production_release_eligible": False,
    }


def _capture_errors(capture: Mapping[str, Any]) -> list[str]:
    problems = []
    for key in ("artifact_sha256", "raster_sha256", "font_inventory_sha256"):
        if not SHA.fullmatch(str(capture.get(key) or "")):
            problems.append("INVALID_" + key.upper())
    for key in ("capture_id", "renderer_engine", "renderer_version",
                "host_environment_id"):
        if not capture.get(key):
            problems.append("MISSING_" + key.upper())
    if not isinstance(capture.get("page_break_locators"), list):
        problems.append("MISSING_PAGE_FLOW")
    if not isinstance(capture.get("observation"), dict):
        problems.append("MISSING_VISUAL_OBSERVATION")
    return problems


def adjudicate_shadow_trial(trial: Mapping[str, Any]) -> dict:
    """Evaluate structural admissibility and defects, never world authority."""
    before = trial.get("baseline") or {}
    after = trial.get("candidate") or {}
    issues: list[str] = []
    if not SHA.fullmatch(str(trial.get("source_sha256") or "")):
        issues.append("INVALID_SOURCE")
    if not SHA.fullmatch(str(trial.get("semantic_sha256_before") or "")):
        issues.append("MISSING_SEMANTIC_CERTIFICATE")
    if trial.get("semantic_sha256_before") != trial.get("semantic_sha256_after"):
        issues.append("SEMANTIC_DRIFT")
    repairs = trial.get("repairs") or []
    if not isinstance(repairs, list) or len(repairs) > 2:
        issues.append("REPAIR_BUDGET_EXCEEDED")
    else:
        for op in repairs:
            if not isinstance(op, dict) or (
                op.get("action") not in ALLOWED_REPAIRS
                or op.get("action") in FORBIDDEN_REPAIRS
            ):
                issues.append("UNAUTHORIZED_REPAIR")
    for label, capture in (("BASELINE", before), ("CANDIDATE", after)):
        issues.extend(label + "_" + e for e in _capture_errors(capture))
    if before.get("capture_id") == after.get("capture_id"):
        issues.append("CAPTURE_REUSE")
    comparison = "CROSS_RENDERER_CANDIDATE"
    if before.get("renderer_engine") == after.get("renderer_engine"):
        comparison = "CROSS_VERSION_ONLY"
    rasterizers = {"pdfium", "poppler", "ghostscript", "pdf-rasterizer"}
    if any(str(x.get("renderer_engine") or "").lower() in rasterizers
           for x in (before, after)):
        comparison = "RASTERIZER_NOT_LAYOUT_ENGINE"
    if comparison != "CROSS_RENDERER_CANDIDATE":
        issues.append(comparison)
    before_codes: list[str] = []
    after_codes: list[str] = []
    if not issues:
        for capture, destination in ((before, before_codes),
                                     (after, after_codes)):
            defects = detect_native_visual_defects(capture["observation"])
            destination.extend(str(x["code"]) for x in defects["issues"])
        if (set(after_codes) & HARD) - set(before_codes):
            issues.append("NOVEL_HARD_DEFECT")
        if set(after_codes) & HARD:
            issues.append("UNRESOLVED_HARD_DEFECT")
    result = {
        "schema": SCHEMA,
        "case_id": trial.get("case_id"),
        "status": ("FAIL_PRELIMINARY_COURT" if issues else
                   "HOLD_EXTERNAL_ATTESTATION_AND_HUMAN_REVIEW"),
        "issues": sorted(set(issues)),
        "comparison": comparison,
        "baseline_defects": sorted(before_codes),
        "candidate_defects": sorted(after_codes),
        "page_breaks_before": before.get("page_break_locators"),
        "page_breaks_after": after.get("page_break_locators"),
        "page_flow_changed": (before.get("page_break_locators") !=
                              after.get("page_break_locators")),
        "font_environment_changed": (
            before.get("font_inventory_sha256") !=
            after.get("font_inventory_sha256")
        ),
        "renderer_claim_is_unverified": True,
        "independent_human_review_observed": False,
        "production_release_eligible": False,
        "authority": "P421_SHADOW_METADATA_COURT",
    }
    result["receipt_sha256"] = digest(result)
    return result
