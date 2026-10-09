from __future__ import annotations

import hashlib
import json
from typing import Any

PHASE = "P4.11"
SCHEMA = "chatgpt-web-hwpx-mcp/p411/windows-capture-worker/v1"

def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

def capture_worker_contract() -> dict:
    result={
        "phase":PHASE,
        "schema":SCHEMA,
        "request_fields":[
            "job_id","exact_head","source_manifest_sha256","source_dir","output_dir",
            "hancom_version_expected","capture_kind"
        ],
        "receipt_fields":[
            "job_id","exact_head","hancom_version_observed","parent_pid","baseline_hwp_pids",
            "owned_hwp_pids","forced_cleanup_pids","source_count","pass_count","fail_count",
            "capture_manifest_sha256","started_at","finished_at"
        ],
        "ownership_rule":"ONLY_PIDS_CREATED_AFTER_WORKER_COM_ACTIVATION_MAY_BE_FORCE_CLEANED",
        "authority":"P4.11_WINDOWS_CAPTURE_WORKER_CONTRACT",
    }
    result["contract_sha256"]=_sha(result)
    return result

def validate_capture_request(request: dict) -> dict:
    required=capture_worker_contract()["request_fields"]
    missing=[key for key in required if request.get(key) in (None,"")]
    exact=str(request.get("exact_head") or "")
    issues=[]
    if missing:
        issues.append({"code":"MISSING_FIELDS","fields":missing})
    if exact and len(exact)!=40:
        issues.append({"code":"INVALID_EXACT_HEAD","value":exact})
    result={
        "phase":PHASE,
        "status":"PASS" if not issues else "FAIL",
        "issues":issues,
        "authority":"P4.11_CAPTURE_REQUEST_VALIDATOR",
    }
    result["request_validation_sha256"]=_sha(result)
    return result

def validate_capture_receipt(receipt: dict) -> dict:
    issues=[]
    owned={int(x) for x in receipt.get("owned_hwp_pids") or []}
    forced={int(x) for x in receipt.get("forced_cleanup_pids") or []}
    baseline={int(x) for x in receipt.get("baseline_hwp_pids") or []}
    if not forced.issubset(owned):
        issues.append({"code":"FORCED_CLEANUP_NOT_OWNED","pids":sorted(forced-owned)})
    if forced & baseline:
        issues.append({"code":"PREEXISTING_PROCESS_TOUCHED","pids":sorted(forced&baseline)})
    if int(receipt.get("fail_count") or 0) != 0:
        issues.append({"code":"CAPTURE_FAILURES","fail_count":int(receipt.get("fail_count") or 0)})
    manifest=str(receipt.get("capture_manifest_sha256") or "")
    if len(manifest)!=64:
        issues.append({"code":"INVALID_CAPTURE_MANIFEST_HASH"})
    result={
        "phase":PHASE,
        "status":"PASS" if not issues else "FAIL",
        "issues":issues,
        "authority":"P4.11_CAPTURE_RECEIPT_VALIDATOR",
    }
    result["capture_receipt_validation_sha256"]=_sha(result)
    return result
