from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PHASE="P4.13"
PRODUCT="0.38.0-p4.13"
SCHEMA="chatgpt-web-hwpx-mcp/p413/continuous-hancom-evidence-service/v1"
BASELINE_PATH=Path(__file__).resolve().parents[2]/"benchmarks"/"p412_native_requalification.json"

def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8")
    ).hexdigest()

def load_promoted_baseline() -> dict:
    data=json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if data.get("phase")!="P4.12" or data.get("adjudication",{}).get("blocking_visual_promotion_authority")!="PASS":
        raise ValueError("P4.13 requires a promoted P4.12 native baseline")
    cases=list(data.get("cases") or [])
    if len(cases)!=5 or not all(c.get("native_capture_pass") for c in cases):
        raise ValueError("P4.12 baseline case custody incomplete")
    return data

def release_manifest() -> dict:
    b=load_promoted_baseline()
    result={
        "phase":PHASE,
        "product":PRODUCT,
        "schema":SCHEMA,
        "release_line":{
            "p411":"0.36.0-p4.11",
            "p412":"0.37.0-p4.12",
            "p413":"0.38.0-p4.13",
        },
        "native_visual_authority":"BLOCKING_PROMOTION_ENABLED_FROM_P4.12_BASELINE",
        "baseline_exact_head":b["exact_head"],
        "baseline_archive_sha256":b["archive_sha256"],
        "baseline_case_count":len(b["cases"]),
        "inherited_evidence":True,
        "fresh_p413_capture_required_for":"HANCOM_BUILD_OR_LOWERING_FAMILY_DRIFT",
        "authority":"P4.13_PUBLIC_RELEASE_MANIFEST",
    }
    result["release_manifest_sha256"]=_sha(result)
    return result

def evidence_health_summary() -> dict:
    b=load_promoted_baseline()
    cases=b["cases"]
    clean=[
        c for c in cases
        if c.get("native_capture_pass")
        and c.get("bar_visible")
        and c.get("kpi_visible")
        and not c.get("vector_escape")
        and not c.get("clipping")
        and not (c.get("novel_defects") or [])
    ]
    result={
        "phase":PHASE,
        "product":PRODUCT,
        "status":"PASS" if len(clean)==len(cases)==5 else "HOLD",
        "case_count":len(cases),
        "clean_case_count":len(clean),
        "visual_slo_status":b["adjudication"]["visual_slo_status"],
        "golden_requalification_status":b["adjudication"]["golden_requalification_status"],
        "blocking_visual_promotion_authority":b["adjudication"]["blocking_visual_promotion_authority"],
        "baseline_generated_at":b["capture"]["generated_at"],
        "baseline_exact_head":b["exact_head"],
        "authority":"P4.13_CONTINUOUS_HANCOM_EVIDENCE_HEALTH",
    }
    result["evidence_health_sha256"]=_sha(result)
    return result

def evaluate_native_evidence_receipt(receipt: dict) -> dict:
    required=["exact_head","hancom_version","source_manifest_sha256","capture_manifest_sha256","cases"]
    missing=[k for k in required if not receipt.get(k)]
    cases=list(receipt.get("cases") or [])
    issues=[]
    if missing:
        issues.append({"code":"MISSING_REQUIRED_FIELD","fields":missing})
    if len(str(receipt.get("exact_head") or ""))!=40:
        issues.append({"code":"INVALID_EXACT_HEAD"})
    for row in cases:
        if not row.get("case_id"):
            issues.append({"code":"MISSING_CASE_ID"})
        if not row.get("source_sha256") or not row.get("pdf_sha256"):
            issues.append({"code":"MISSING_HASH_CUSTODY","case_id":row.get("case_id")})
        if row.get("native_capture_pass") is not True:
            issues.append({"code":"NATIVE_CAPTURE_FAIL","case_id":row.get("case_id")})
    result={
        "phase":PHASE,
        "status":"PASS" if not issues and cases else "FAIL",
        "issues":issues,
        "case_count":len(cases),
        "authority":"P4.13_NATIVE_EVIDENCE_RECEIPT_VALIDATOR",
    }
    result["validated_receipt_sha256"]=_sha({"receipt":receipt,"issues":issues})
    return result

def compare_evidence_drift(candidate: dict) -> dict:
    baseline=load_promoted_baseline()
    base_cases={c["case_id"]:c for c in baseline["cases"]}
    cand_cases={c.get("case_id"):c for c in candidate.get("cases") or [] if c.get("case_id")}
    drift=[]
    for case_id, base in sorted(base_cases.items()):
        cand=cand_cases.get(case_id)
        if not cand:
            drift.append({"case_id":case_id,"code":"CASE_MISSING"})
            continue
        if cand.get("source_sha256")!=base.get("source_sha256"):
            drift.append({"case_id":case_id,"code":"SOURCE_DRIFT"})
        if cand.get("pdf_sha256")!=base.get("pdf_sha256"):
            drift.append({"case_id":case_id,"code":"PDF_BYTE_DRIFT","severity":"DIAGNOSTIC"})
        for key in ["bar_visible","kpi_visible","native_capture_pass"]:
            if cand.get(key) is not True:
                drift.append({"case_id":case_id,"code":f"{key.upper()}_REGRESSION","severity":"BLOCKING"})
        for key in ["vector_escape","clipping"]:
            if cand.get(key) is True:
                drift.append({"case_id":case_id,"code":f"{key.upper()}_REGRESSION","severity":"BLOCKING"})
        if cand.get("novel_defects"):
            drift.append({"case_id":case_id,"code":"NOVEL_DEFECT","severity":"BLOCKING","detail":cand["novel_defects"]})
    blocking=[d for d in drift if d.get("severity")=="BLOCKING"]
    result={
        "phase":PHASE,
        "status":"HOLD" if blocking else "PASS",
        "drift_count":len(drift),
        "blocking_drift_count":len(blocking),
        "drift":drift,
        "baseline_exact_head":baseline["exact_head"],
        "authority":"P4.13_HANCOM_EVIDENCE_DRIFT_COURT",
    }
    result["drift_report_sha256"]=_sha(result)
    return result

def public_authoring_trust_status() -> dict:
    health=evidence_health_summary()
    manifest=release_manifest()
    result={
        "phase":PHASE,
        "product":PRODUCT,
        "status":"TRUST_BASELINE_ACTIVE" if health["status"]=="PASS" else "TRUST_HOLD",
        "structural_authority":"CI_AND_PACKAGE_VALIDATION",
        "native_visual_authority":"PROMOTED_BLOCKING_BASELINE",
        "evidence_health_sha256":health["evidence_health_sha256"],
        "release_manifest_sha256":manifest["release_manifest_sha256"],
        "fresh_capture_policy":"REQUIRED_ON_HANCOM_BUILD_OR_LOWERING_FAMILY_DRIFT",
        "authority":"P4.13_PUBLIC_AUTHORING_TRUST_STATUS",
    }
    result["trust_status_sha256"]=_sha(result)
    return result

def document_visual_authority_receipt(*, document_id: str, revision: int, sha256: str) -> dict:
    trust=public_authoring_trust_status()
    result={
        "phase":PHASE,
        "product":PRODUCT,
        "document_id":document_id,
        "revision":int(revision),
        "document_sha256":sha256,
        "release_visual_authority":trust["native_visual_authority"],
        "release_trust_status":trust["status"],
        "baseline_evidence_health_sha256":trust["evidence_health_sha256"],
        "scope":"RELEASE_BASELINE_AUTHORITY_NOT_PER_DOCUMENT_NATIVE_RENDER",
        "authority":"P4.13_DOCUMENT_VISUAL_AUTHORITY_RECEIPT",
    }
    result["receipt_sha256"]=_sha(result)
    return result
