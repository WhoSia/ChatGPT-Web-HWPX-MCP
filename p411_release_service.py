from __future__ import annotations

import hashlib
import json
from typing import Any

PHASE="P4.11"
PRODUCT="0.36.0-p4.11"
SCHEMA="chatgpt-web-hwpx-mcp/p411/release-promotion-service/v1"

def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    ).hexdigest()

def release_promotion_contract() -> dict:
    result={
        "phase":PHASE,
        "product":PRODUCT,
        "schema":SCHEMA,
        "modes":["SHADOW_NONBLOCKING","BLOCKING"],
        "required_evidence":[
            "exact_head","static_test_pass","full_lifecycle_pass","exact_head_docker_pass",
            "production_boundary_pass","native_capture_pass","visual_slo_status",
            "novel_unadjudicated"
        ],
        "shadow_semantics":"SERVICE_MAY_DEPLOY_WHILE_VISUAL_AUTHORITY_REMAINS_HELD",
        "blocking_semantics":"VISUAL_SLO_FAILURE_PREVENTS_PRODUCTION_PROMOTION",
        "authority":"P4.11_RELEASE_PROMOTION_SERVICE_CONTRACT",
    }
    result["contract_sha256"]=_sha(result)
    return result

def evaluate_release_candidate(evidence: dict, *, mode: str="SHADOW_NONBLOCKING") -> dict:
    mode=str(mode or "SHADOW_NONBLOCKING").upper()
    if mode not in {"SHADOW_NONBLOCKING","BLOCKING"}:
        raise ValueError("unsupported P4.11 release mode")
    exact=str(evidence.get("exact_head") or "")
    machine_ready=all([
        len(exact)==40,
        bool(evidence.get("static_test_pass")),
        bool(evidence.get("full_lifecycle_pass")),
        bool(evidence.get("exact_head_docker_pass")),
        bool(evidence.get("production_boundary_pass")),
    ])
    native_capture=bool(evidence.get("native_capture_pass"))
    visual_slo=str(evidence.get("visual_slo_status") or "").upper()=="PASS"
    novel=int(evidence.get("novel_unadjudicated") or 0)
    visual_authority=machine_ready and native_capture and visual_slo and novel==0

    if mode=="BLOCKING":
        deployable=visual_authority
    else:
        deployable=machine_ready

    if visual_authority:
        verdict="PRODUCTION_PROMOTION_ELIGIBLE"
    elif deployable and mode=="SHADOW_NONBLOCKING":
        verdict="SERVICE_DEPLOYABLE_VISUAL_AUTHORITY_HOLD"
    else:
        verdict="HOLD"

    result={
        "phase":PHASE,
        "product":PRODUCT,
        "mode":mode,
        "verdict":verdict,
        "deployable":deployable,
        "visual_authority_promoted":visual_authority,
        "machine_release_ready":machine_ready,
        "native_capture_pass":native_capture,
        "visual_slo_pass":visual_slo,
        "novel_unadjudicated":novel,
        "exact_head":exact or None,
        "authority":"P4.11_RELEASE_PROMOTION_SERVICE",
    }
    result["release_candidate_sha256"]=_sha(result)
    return result
