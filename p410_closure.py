from __future__ import annotations

import hashlib
import json
from typing import Any

PHASE = "P4.10"
PRODUCT = "0.35.0-p4.10"
SCHEMA = "chatgpt-web-hwpx-mcp/p410/native-visual-closure/v1"


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def closure_contract() -> dict:
    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": SCHEMA,
        "inherits": {
            "p48_product_phase": "CLOSED",
            "p48_machine_world_contact": "PASS",
            "p48_human_visual_failure": "RETAINED_AS_GENESIS_REGRESSION_EVIDENCE",
            "p49_geometry_safe_lowering": "IMPLEMENTED",
            "p49_visual_certificate": "REQUIRED_PRE_MUTATION",
            "p49_post_materialization_audit": "REQUIRED_PRE_DELIVERY",
            "p49_owned_process_capture": "AVAILABLE",
        },
        "closure_axes": [
            "EXACT_HEAD_CI",
            "EXACT_HEAD_DOCKER",
            "PUBLIC_PRODUCTION_BOUNDARY",
            "NATIVE_HANCOM_RECAPTURE",
            "HUMAN_VISUAL_ADJUDICATION",
            "GEOMETRY_AUTHORITY_PROMOTION",
        ],
        "promotion_policy": (
            "STRUCTURAL_AND_CI_EVIDENCE_MAY_PROMOTE_DEPLOYABILITY_BUT_NATIVE_VISUAL_AUTHORITY_"
            "REQUIRES_HANCOM_RENDER_PLUS_HUMAN_ADJUDICATION"
        ),
        "p47_high_level_mapping_hold": [
            "bold_to_mathbf_or_boldsymbol",
            "eqalign_to_full_latex_align",
        ],
        "authority": "P4.10_CLOSURE_COURT_CONTRACT",
    }
    result["contract_sha256"] = _sha(result)
    return result


def adjudicate_closure(evidence: dict | None) -> dict:
    contract = closure_contract()
    if not evidence:
        result = {
            "phase": PHASE,
            "product": PRODUCT,
            "status": "HUMAN_RENDER_EVIDENCE_PENDING",
            "deployable": False,
            "geometry_authority_promoted": False,
            "held": ["native_hancom_recapture", "human_visual_adjudication"],
            "authority": "NO_CLOSURE_WITHOUT_EVIDENCE",
        }
        result["adjudication_sha256"] = _sha(result)
        return result

    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")

    exact_head = str(evidence.get("exact_head") or "")
    ci_ok = bool(evidence.get("exact_head_ci_pass"))
    docker_ok = bool(evidence.get("exact_head_docker_pass"))
    production_ok = bool(evidence.get("production_boundary_pass"))
    native = evidence.get("native_hancom") or {}
    human = evidence.get("human_visual") or {}

    native_ok = (
        bool(native.get("capture_pass"))
        and int(native.get("fail_count") or 0) == 0
        and int(native.get("pdf_count") or 0) > 0
        and len(str(native.get("manifest_sha256") or "")) == 64
    )
    human_status = str(human.get("status") or "").upper()
    human_ok = human_status in {"PASS", "PASS_WITH_RESIDUALS"}
    lab_repaired = bool(human.get("lab_report_vector_escape_absent"))
    bar_repaired = bool(human.get("bar_label_value_preserved"))
    kpi_repaired = bool(human.get("kpi_card_preserved"))

    deployable = len(exact_head) == 40 and ci_ok and docker_ok and production_ok
    geometry_promoted = deployable and native_ok and human_ok and lab_repaired and bar_repaired and kpi_repaired

    held = []
    if not deployable:
        held.append("exact_head_release_boundary")
    if not native_ok:
        held.append("native_hancom_recapture")
    if not human_ok:
        held.append("human_visual_adjudication")
    if native_ok and human_ok and not geometry_promoted:
        held.append("geometry_repair_evidence_incomplete")

    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "status": "CLOSED" if geometry_promoted else "HOLD",
        "exact_head": exact_head or None,
        "deployable": deployable,
        "geometry_authority_promoted": geometry_promoted,
        "held": held,
        "p47_high_level_mapping_hold": contract["p47_high_level_mapping_hold"],
        "authority": (
            "P4.10_NATIVE_VISUAL_CLOSURE_PASS"
            if geometry_promoted
            else "P4.10_CLOSURE_HOLD_EVIDENCE_BOUND"
        ),
    }
    result["adjudication_sha256"] = _sha(result)
    return result
