from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from p2_document import apply_edits_atomic, build_document_map
from hwpx_mcp.evidence.p411_release_service import evaluate_release_candidate
from hwpx_mcp.rendering.p411_visual_oracle import evaluate_visual_slo

PHASE="P4.12"
PRODUCT="0.37.0-p4.12"
SCHEMA="chatgpt-web-hwpx-mcp/p412/native-visual-repair/v1"

UNSAFE_NATIVE_FAMILY="DRAWING_RECTANGLE_TEXTBOX_OVERLAY"
SAFE_NATIVE_FAMILY="PARAGRAPH_TEXT_VISUALIZATION"

def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    ).hexdigest()

def defect_eradication_contract() -> dict:
    result={
        "phase":PHASE,
        "product":PRODUCT,
        "schema":SCHEMA,
        "known_failures":{
            "vector_escape_cases":["p48-research_report","p48-technical_note"],
            "bar_native_visibility_fail":"5/5",
            "kpi_native_visibility_fail":"5/5",
        },
        "causal_hypothesis":{
            "unsafe_family":UNSAFE_NATIVE_FAMILY,
            "evidence":[
                "P4.9 structural geometry and post-materialization audits passed",
                "P4.10 real Hancom PDFs still showed vector escape and visual disappearance",
                "equation alignment primitives remained native-visible, isolating the defect to the drawing overlay family rather than global capture",
            ],
            "authority":"EVIDENCE_BOUND_CAUSAL_LOCALIZATION_NOT_UNIVERSAL_HANCOM_CLAIM",
        },
        "certified_substitution":{
            "bar_chart":{
                "from":UNSAFE_NATIVE_FAMILY,
                "to":SAFE_NATIVE_FAMILY,
                "semantic_invariants":["label_identity","value_identity","relative_order","relative_magnitude_order"],
            },
            "kpi_strip":{
                "from":UNSAFE_NATIVE_FAMILY,
                "to":SAFE_NATIVE_FAMILY,
                "semantic_invariants":["label_identity","value_identity","item_order"],
            },
        },
        "blocking_promotion_rule":[
            "exact_head_ci_pass",
            "exact_head_docker_pass",
            "full_lifecycle_pass",
            "production_boundary_pass",
            "native_capture_pass",
            "visual_slo_pass",
            "no_unadjudicated_novel_defect",
            "golden_negative_controls_requalified",
        ],
        "authority":"P4.12_NATIVE_VISUAL_DEFECT_ERADICATION_CONTRACT",
    }
    result["contract_sha256"]=_sha(result)
    return result

def causal_localization(component_type: str) -> dict:
    if component_type not in {"bar_chart","kpi_strip"}:
        raise ValueError("P4.12 causal localization only covers bar_chart/kpi_strip")
    result={
        "phase":PHASE,
        "component_type":component_type,
        "semantic_component":component_type,
        "lowering_family":UNSAFE_NATIVE_FAMILY,
        "serialized_object_family":"hp:rect/textbox drawing objects",
        "native_failure_family":"VECTOR_ESCAPE_OR_COMPONENT_DISAPPEARANCE",
        "substitution_family":SAFE_NATIVE_FAMILY,
        "confidence":"CALIBRATION_SUPPORTED",
        "authority":"P4.12_GEOMETRY_TO_RENDER_CAUSAL_LOCALIZATION",
    }
    result["localization_sha256"]=_sha(result)
    return result

def _bar_blocks(value: float, maximum: float) -> str:
    if maximum <= 0:
        count=1
    else:
        count=max(1,min(20,int(round((float(value)/maximum)*20))))
    return "■"*count

def compile_repaired_visual_payload(plan: dict) -> dict:
    kind=str(plan.get("type") or "")
    cid=str(plan.get("component_id") or "")
    if kind=="bar_chart":
        rows=list(plan.get("rows") or [])
        maximum=max((float(r.get("value") or 0) for r in rows),default=0.0)
        parts=[]
        semantic=[]
        for row in rows:
            label=str(row.get("label") or "").strip()
            value=float(row.get("value") or 0)
            if not label or not math.isfinite(value):
                raise ValueError("invalid bar semantic row")
            value_text=f"{value:g}"
            blocks=_bar_blocks(value,maximum)
            text=f"{label}  {blocks}  {value_text}"
            parts.append(text)
            semantic.append({"label":label,"value":value,"bar_blocks":len(blocks)})
        paragraph="   |   ".join(parts)
        result={
            "phase":PHASE,"component_id":cid,"type":kind,
            "paragraph_text":paragraph,
            "semantic_rows":semantic,
            "primitive_family":SAFE_NATIVE_FAMILY,
            "substituted_from":UNSAFE_NATIVE_FAMILY,
            "authority":"P4.12_CERTIFIED_TEXTUAL_BAR_SUBSTITUTION",
        }
    elif kind=="kpi_strip":
        items=list(plan.get("items") or [])
        semantic=[]
        parts=[]
        for item in items:
            label=str(item.get("label") or "").strip()
            value=str(item.get("value") or "").strip()
            if not label or not value:
                raise ValueError("invalid KPI semantic item")
            semantic.append({"label":label,"value":value})
            parts.append(f"▣ {label}  {value}")
        result={
            "phase":PHASE,"component_id":cid,"type":kind,
            "paragraph_text":"    ".join(parts),
            "semantic_items":semantic,
            "primitive_family":SAFE_NATIVE_FAMILY,
            "substituted_from":UNSAFE_NATIVE_FAMILY,
            "authority":"P4.12_CERTIFIED_TEXTUAL_KPI_SUBSTITUTION",
        }
    else:
        raise ValueError(f"unsupported repaired visual type: {kind}")
    result["payload_sha256"]=_sha(result)
    return result

def execute_repaired_visual_plans(path: Path, visual_plans: list[dict], bindings: dict[str,dict]) -> list[dict]:
    receipts=[]
    for plan in visual_plans:
        binding=bindings.get(str(plan.get("anchor_block_id") or ""))
        if not binding:
            raise ValueError(f"visual anchor block missing: {plan.get('anchor_block_id')}")
        anchor=str(binding["locator"])
        payload=compile_repaired_visual_payload(plan)
        tx=apply_edits_atomic(
            path,
            [{"op":"insert_paragraph_after","target":anchor,"text":payload["paragraph_text"]}],
            expected_revision=1,current_revision=1,validator=None,
        )
        receipt={
            **payload,
            "anchor_locator":anchor,
            "text_transaction":{
                "semantic_changed":tx.get("semantic_changed"),
                "structure_changed":tx.get("structure_changed"),
            },
            "authority":"P4.12_NATIVE_PARAGRAPH_SUBSTITUTION_EXECUTED",
        }
        receipt["receipt_sha256"]=_sha(receipt)
        receipts.append(receipt)
    return receipts

def audit_repaired_visuals(path: Path, receipts: list[dict]) -> dict:
    doc=build_document_map(path)
    texts=[str(p.get("text") or "") for p in doc.get("paragraphs") or []]
    issues=[]
    for receipt in receipts:
        expected=str(receipt.get("paragraph_text") or "")
        if expected not in texts:
            issues.append({
                "code":"REPAIRED_VISUAL_TEXT_MISSING",
                "component_id":receipt.get("component_id"),
                "detail":"exact repaired visual paragraph was not materialized",
            })
        if receipt.get("primitive_family") != SAFE_NATIVE_FAMILY:
            issues.append({
                "code":"UNSAFE_VISUAL_PRIMITIVE_REINTRODUCED",
                "component_id":receipt.get("component_id"),
            })
    result={
        "phase":PHASE,
        "status":"PASS" if not issues else "FAIL",
        "issue_count":len(issues),
        "issues":issues,
        "paragraph_count":len(texts),
        "primitive_family":SAFE_NATIVE_FAMILY,
        "authority":"P4.12_POST_MATERIALIZATION_TEXT_VISUAL_AUDIT_NOT_NATIVE_RENDER_AUTHORITY",
    }
    result["materialized_repair_audit_sha256"]=_sha(result)
    return result

def requalify_golden_corpus(native_observations: list[dict]) -> dict:
    rows=[]
    all_pass=True
    for obs in native_observations:
        defects=obs.get("defects") or {"issues":[]}
        slo=evaluate_visual_slo(defects,novel_unadjudicated=int(obs.get("novel_unadjudicated") or 0))
        pass_case=(
            bool(obs.get("native_capture_pass"))
            and slo.get("status")=="PASS"
            and bool(obs.get("bar_visible",True))
            and bool(obs.get("kpi_visible",True))
            and not bool(obs.get("vector_escape",False))
        )
        all_pass=all_pass and pass_case
        rows.append({
            "case_id":obs.get("case_id"),
            "status":"REQUALIFIED" if pass_case else "HOLD",
            "visual_slo_status":slo.get("status"),
        })
    result={
        "phase":PHASE,
        "status":"PASS" if rows and all_pass else "HOLD",
        "case_count":len(rows),
        "cases":rows,
        "authority":"P4.12_GOLDEN_NEGATIVE_CONTROL_REQUALIFICATION",
    }
    result["requalification_sha256"]=_sha(result)
    return result

def evaluate_blocking_promotion(evidence: dict) -> dict:
    golden=evidence.get("golden_requalification") or {}
    release=evaluate_release_candidate({
        "exact_head":evidence.get("exact_head"),
        "static_test_pass":bool(evidence.get("exact_head_ci_pass")),
        "full_lifecycle_pass":bool(evidence.get("full_lifecycle_pass")),
        "exact_head_docker_pass":bool(evidence.get("exact_head_docker_pass")),
        "production_boundary_pass":bool(evidence.get("production_boundary_pass")),
        "native_capture_pass":bool(evidence.get("native_capture_pass")),
        "visual_slo_status":evidence.get("visual_slo_status"),
        "novel_unadjudicated":int(evidence.get("novel_unadjudicated") or 0),
    },mode="BLOCKING")
    golden_pass=golden.get("status")=="PASS"
    promoted=bool(release.get("deployable")) and golden_pass
    result={
        "phase":PHASE,
        "status":"BLOCKING_PRODUCTION_PROMOTION_AUTHORITY" if promoted else "HOLD",
        "promotion_eligible":promoted,
        "release_service":release,
        "golden_requalification_pass":golden_pass,
        "authority":"P4.12_BLOCKING_VISUAL_PROMOTION_COURT",
    }
    result["blocking_promotion_sha256"]=_sha(result)
    return result
