from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

PHASE = "P4.11"
PRODUCT = "0.36.0-p4.11"
SCHEMA = "chatgpt-web-hwpx-mcp/p411/native-render-oracle/v1"

DEFECT_VECTOR_ESCAPE = "VECTOR_ESCAPE"
DEFECT_REGION_CLIP = "REGION_CLIP"
DEFECT_TEXT_DISAPPEARANCE = "TEXT_DISAPPEARANCE"
DEFECT_LABEL_VALUE_DETACHMENT = "LABEL_VALUE_DETACHMENT"
DEFECT_KPI_CONTAINER_COLLAPSE = "KPI_CONTAINER_COLLAPSE"
DEFECT_OBJECT_OVERLAP = "OBJECT_OVERLAP"
DEFECT_ALIGNMENT_DRIFT = "ALIGNMENT_DRIFT"
DEFECT_WHITESPACE_BLOWOUT = "WHITESPACE_BLOWOUT"
DEFECT_ARCHETYPE_ALIASING = "ARCHETYPE_ALIASING"
DEFECT_NATIVE_ONLY_SERIALIZATION = "NATIVE_ONLY_SERIALIZATION_DEFECT"
DEFECT_CAPTURE_ENVIRONMENT = "CAPTURE_ENVIRONMENT_DEFECT"

ALLOWED_REPAIRS = {
    "recalculate_local_coordinates",
    "adjust_width_height_bounded",
    "repair_padding_gap",
    "reassign_anchor_same_component",
    "substitute_certified_equivalent_primitive",
    "correct_z_order",
    "reconstruct_textbox_or_container",
}
FORBIDDEN_REPAIRS = {
    "change_document_meaning",
    "delete_semantic_content",
    "replace_visual_with_unrelated_prose",
    "change_equation_semantics",
    "change_archetype_intent",
    "suppress_failed_region",
}

def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False

def _box(region: dict) -> tuple[float, float, float, float] | None:
    vals = [region.get(k) for k in ("x", "y", "width", "height")]
    if not all(_finite(v) for v in vals):
        return None
    x, y, w, h = map(float, vals)
    return x, y, w, h

def _overlap(a: tuple[float,float,float,float], b: tuple[float,float,float,float]) -> float:
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    iw = max(0.0, min(ax+aw,bx+bw)-max(ax,bx))
    ih = max(0.0, min(ay+ah,by+bh)-max(ay,by))
    return iw * ih

def native_render_oracle_contract() -> dict:
    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": SCHEMA,
        "pipeline": [
            "EXACT_HEAD",
            "STRUCTURAL_BENCHMARK",
            "WINDOWS_HANCOM_CAPTURE",
            "PAGE_RASTER_EVIDENCE",
            "COMPONENT_REGION_REGISTRATION",
            "INVARIANT_AWARE_VISUAL_DIFF",
            "TYPED_DEFECT_ATTRIBUTION",
            "BOUNDED_REPAIR_PLAN",
            "NATIVE_RERENDER",
            "VISUAL_SLO_GATE",
            "PRODUCTION_PROMOTION",
        ],
        "defect_taxonomy": [
            DEFECT_VECTOR_ESCAPE, DEFECT_REGION_CLIP, DEFECT_TEXT_DISAPPEARANCE,
            DEFECT_LABEL_VALUE_DETACHMENT, DEFECT_KPI_CONTAINER_COLLAPSE,
            DEFECT_OBJECT_OVERLAP, DEFECT_ALIGNMENT_DRIFT, DEFECT_WHITESPACE_BLOWOUT,
            DEFECT_ARCHETYPE_ALIASING, DEFECT_NATIVE_ONLY_SERIALIZATION,
            DEFECT_CAPTURE_ENVIRONMENT,
        ],
        "allowed_repairs": sorted(ALLOWED_REPAIRS),
        "forbidden_repairs": sorted(FORBIDDEN_REPAIRS),
        "release_rule": (
            "STATIC_TEST_PASS_AND_STRUCTURAL_FIDELITY_PASS_AND_EXACT_HEAD_DOCKER_PASS_"
            "AND_NATIVE_CAPTURE_PASS_AND_VISUAL_SLO_PASS_AND_NO_UNADJUDICATED_NOVEL_DEFECT"
        ),
        "authority": "P4.11_CONTINUOUS_NATIVE_RENDER_ORACLE_CONTRACT",
    }
    result["contract_sha256"] = _sha(result)
    return result

def build_golden_registry(calibration: dict) -> dict:
    archetypes = []
    for row in calibration.get("archetypes") or []:
        visual = row.get("human_visual") or {}
        forbidden = []
        if visual.get("vector_escape") is True:
            forbidden.append(DEFECT_VECTOR_ESCAPE)
        if visual.get("bar_series_visible") is False:
            forbidden.append(DEFECT_LABEL_VALUE_DETACHMENT)
        if visual.get("kpi_card_visible") is False:
            forbidden.append(DEFECT_KPI_CONTAINER_COLLAPSE)
        archetypes.append({
            "case_id": row["case_id"],
            "source_sha256": row["source_sha256"],
            "native_pdf_sha256": row["pdf_sha256"],
            "baseline_status": "KNOWN_FAIL" if forbidden else "KNOWN_PASS",
            "observed_defects": forbidden,
            "authority": "P410_HUMAN_CALIBRATION",
        })
    equations = [{
        "case_id": f"equation:{row['variant_id']}",
        "source_sha256": row["source_sha256"],
        "native_pdf_sha256": row["pdf_sha256"],
        "expected_alignment": row["expected_alignment"],
        "observed_alignment": row["observed_alignment"],
        "baseline_status": "KNOWN_PASS" if row.get("human_visual_status") == "PASS" else "KNOWN_FAIL",
        "authority": "P410_HUMAN_ALIGNMENT_CALIBRATION",
    } for row in calibration.get("equations") or []]
    result = {
        "phase": PHASE,
        "schema": "chatgpt-web-hwpx-mcp/p411/golden-registry/v1",
        "archetypes": archetypes,
        "equations": equations,
        "case_count": len(archetypes) + len(equations),
        "authority": "VERSIONED_GOLDEN_CORPUS_REGISTRY",
    }
    result["registry_sha256"] = _sha(result)
    return result

def region_provenance(component_id: str, page: int, role: str, *,
                      x: float, y: float, width: float, height: float,
                      object_locator: str | None = None,
                      semantic_group_id: str | None = None) -> dict:
    result = {
        "phase": PHASE,
        "component_id": component_id,
        "semantic_group_id": semantic_group_id,
        "page": int(page),
        "role": role,
        "x": float(x), "y": float(y), "width": float(width), "height": float(height),
        "object_locator": object_locator,
        "authority": "COMPONENT_TO_NATIVE_PAGE_REGION_PROVENANCE",
    }
    result["region_sha256"] = _sha(result)
    return result

def detect_native_visual_defects(observation: dict) -> dict:
    page_width = float(observation.get("page_width") or 0)
    page_height = float(observation.get("page_height") or 0)
    regions = list(observation.get("regions") or [])
    vectors = list(observation.get("vectors") or [])
    issues: list[dict] = []

    for vec in vectors:
        length = float(vec.get("length") or 0)
        intended = bool(vec.get("intended"))
        if length > max(page_width, page_height) * 0.18 and not intended:
            issues.append({"code": DEFECT_VECTOR_ESCAPE, "component_id": vec.get("component_id"),
                           "detail": "unintended long vector exceeds native-page threshold", "evidence": vec})

    boxes = []
    for region in regions:
        b = _box(region)
        if b is None:
            continue
        x,y,w,h = b
        cid = str(region.get("component_id") or "")
        role = str(region.get("role") or "")
        if x < 0 or y < 0 or x+w > page_width or y+h > page_height:
            issues.append({"code": DEFECT_REGION_CLIP, "component_id": cid, "role": role,
                           "detail": "registered component region exceeds page bounds", "evidence": region})
        expected_text = region.get("expected_text")
        observed_text = region.get("observed_text")
        if expected_text not in (None, "") and not str(observed_text or "").strip():
            issues.append({"code": DEFECT_TEXT_DISAPPEARANCE, "component_id": cid, "role": role,
                           "detail": "semantic text expected but absent in native evidence", "evidence": region})
        if role in {"bar_label","bar_value"} and region.get("attached_to_shape") is False:
            issues.append({"code": DEFECT_LABEL_VALUE_DETACHMENT, "component_id": cid, "role": role,
                           "detail": "bar label/value is not attached to its semantic shape", "evidence": region})
        if role == "kpi_card" and region.get("container_visible") is False:
            issues.append({"code": DEFECT_KPI_CONTAINER_COLLAPSE, "component_id": cid, "role": role,
                           "detail": "KPI semantic container collapsed in native render", "evidence": region})
        expected_alignment = str(region.get("expected_alignment") or "")
        observed_alignment = str(region.get("observed_alignment") or "")
        if expected_alignment and observed_alignment and expected_alignment != observed_alignment:
            issues.append({"code": DEFECT_ALIGNMENT_DRIFT, "component_id": cid, "role": role,
                           "detail": "native alignment differs from promoted contract", "evidence": region})
        boxes.append((region,b))

    for i,(ra,ba) in enumerate(boxes):
        if ra.get("allow_overlap"):
            continue
        for rb,bb in boxes[i+1:]:
            if rb.get("allow_overlap"):
                continue
            if str(ra.get("component_id")) == str(rb.get("component_id")) and _overlap(ba,bb) > 0:
                allowed={str(ra.get("role")),str(rb.get("role"))}
                if allowed not in [
                    {"kpi_card","kpi_label"},{"kpi_card","kpi_value"},
                    {"bar_shape","bar_label"},{"bar_shape","bar_value"},
                ]:
                    issues.append({"code": DEFECT_OBJECT_OVERLAP,
                                   "component_id": ra.get("component_id"),
                                   "detail": "unexpected overlap inside semantic component",
                                   "roles":[ra.get("role"),rb.get("role")]})

    used_height = float(observation.get("used_height") or 0)
    semantic_height = float(observation.get("semantic_content_height") or 0)
    if semantic_height > 0 and used_height / semantic_height > 1.8:
        issues.append({"code": DEFECT_WHITESPACE_BLOWOUT, "component_id": observation.get("document_id"),
                       "detail": "native page flow expands far beyond semantic content height",
                       "ratio": used_height / semantic_height})

    result = {
        "phase": PHASE,
        "schema": SCHEMA,
        "status": "PASS" if not issues else "FAIL",
        "issue_count": len(issues),
        "issues": issues,
        "authority": "TYPED_NATIVE_VISUAL_DEFECT_DETECTOR",
    }
    result["defect_receipt_sha256"] = _sha(result)
    return result

def evaluate_visual_slo(defects: dict, *, novel_unadjudicated: int = 0) -> dict:
    counts: dict[str,int] = {}
    for issue in defects.get("issues") or []:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    hard_zero = [
        DEFECT_VECTOR_ESCAPE, DEFECT_REGION_CLIP, DEFECT_TEXT_DISAPPEARANCE,
        DEFECT_LABEL_VALUE_DETACHMENT, DEFECT_KPI_CONTAINER_COLLAPSE,
        DEFECT_OBJECT_OVERLAP, DEFECT_ALIGNMENT_DRIFT,
    ]
    failures = {code: counts.get(code,0) for code in hard_zero if counts.get(code,0) != 0}
    if novel_unadjudicated:
        failures["UNADJUDICATED_NOVEL_DEFECT"] = int(novel_unadjudicated)
    result = {
        "phase": PHASE,
        "status": "PASS" if not failures else "FAIL",
        "counts": counts,
        "failures": failures,
        "slo": {code: 0 for code in hard_zero},
        "authority": "P4.11_VISUAL_SLO_EVALUATOR",
    }
    result["visual_slo_sha256"] = _sha(result)
    return result

def plan_bounded_repairs(defects: dict) -> dict:
    mapping = {
        DEFECT_VECTOR_ESCAPE:["substitute_certified_equivalent_primitive","recalculate_local_coordinates"],
        DEFECT_REGION_CLIP:["adjust_width_height_bounded","reassign_anchor_same_component"],
        DEFECT_TEXT_DISAPPEARANCE:["reconstruct_textbox_or_container"],
        DEFECT_LABEL_VALUE_DETACHMENT:["recalculate_local_coordinates","repair_padding_gap","reconstruct_textbox_or_container"],
        DEFECT_KPI_CONTAINER_COLLAPSE:["reconstruct_textbox_or_container","correct_z_order"],
        DEFECT_OBJECT_OVERLAP:["repair_padding_gap","recalculate_local_coordinates","correct_z_order"],
        DEFECT_ALIGNMENT_DRIFT:["recalculate_local_coordinates"],
        DEFECT_WHITESPACE_BLOWOUT:["repair_padding_gap","reassign_anchor_same_component"],
    }
    actions=[]
    for issue in defects.get("issues") or []:
        options=[x for x in mapping.get(issue.get("code"),[]) if x in ALLOWED_REPAIRS]
        actions.append({
            "component_id": issue.get("component_id"),
            "defect": issue.get("code"),
            "allowed_actions": options,
            "automatic_mutation": bool(options),
            "requires_native_rerender": True,
        })
    result={
        "phase":PHASE,
        "actions":actions,
        "action_count":len(actions),
        "forbidden_actions":sorted(FORBIDDEN_REPAIRS),
        "authority":"BOUNDED_REPAIR_PLAN_SEMANTICS_PRESERVED",
    }
    result["repair_plan_sha256"]=_sha(result)
    return result

def evaluate_shadow_release_gate(*, static_test_pass: bool, structural_fidelity_pass: bool,
                                 exact_head_docker_pass: bool, native_capture_pass: bool,
                                 visual_slo: dict, novel_unadjudicated: int = 0,
                                 blocking: bool = False) -> dict:
    eligible = all([
        static_test_pass, structural_fidelity_pass, exact_head_docker_pass,
        native_capture_pass, visual_slo.get("status") == "PASS",
        int(novel_unadjudicated) == 0,
    ])
    result={
        "phase":PHASE,
        "mode":"BLOCKING" if blocking else "SHADOW_NONBLOCKING",
        "promotion_eligible":eligible,
        "release_blocked":bool(blocking and not eligible),
        "inputs":{
            "static_test_pass":static_test_pass,
            "structural_fidelity_pass":structural_fidelity_pass,
            "exact_head_docker_pass":exact_head_docker_pass,
            "native_capture_pass":native_capture_pass,
            "visual_slo_pass":visual_slo.get("status") == "PASS",
            "novel_unadjudicated":int(novel_unadjudicated),
        },
        "authority":"P4.11_SHADOW_RELEASE_PROMOTION_GATE" if not blocking else "P4.11_BLOCKING_RELEASE_PROMOTION_GATE",
    }
    result["promotion_gate_sha256"]=_sha(result)
    return result

def load_calibration(path: Path = Path("benchmarks/p411_native_calibration.json")) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
