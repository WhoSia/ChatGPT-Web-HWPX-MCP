import copy

from hwpx_mcp.evidence.p413_evidence_service import (
    compare_evidence_drift,
    document_visual_authority_receipt,
    evidence_health_summary,
    evaluate_native_evidence_receipt,
    load_promoted_baseline,
    public_authoring_trust_status,
    release_manifest,
)

def test_p412_promoted_baseline_is_clean():
    b=load_promoted_baseline()
    assert b["adjudication"]["blocking_visual_promotion_authority"]=="PASS"
    assert len(b["cases"])==5
    assert all(c["bar_visible"] and c["kpi_visible"] for c in b["cases"])
    assert not any(c["vector_escape"] or c["clipping"] for c in b["cases"])

def test_release_manifest_and_health():
    m=release_manifest()
    h=evidence_health_summary()
    assert m["product"]=="0.38.0-p4.13"
    assert m["inherited_evidence"] is True
    assert h["status"]=="PASS"
    assert h["clean_case_count"]==5

def test_receipt_validator_and_drift_court():
    b=load_promoted_baseline()
    receipt={
        "exact_head":"b"*40,
        "hancom_version":"13.0.0.3622",
        "source_manifest_sha256":"1"*64,
        "capture_manifest_sha256":"2"*64,
        "cases":copy.deepcopy(b["cases"]),
    }
    assert evaluate_native_evidence_receipt(receipt)["status"]=="PASS"
    same=compare_evidence_drift(receipt)
    assert same["blocking_drift_count"]==0
    bad=copy.deepcopy(receipt)
    bad["cases"][0]["bar_visible"]=False
    held=compare_evidence_drift(bad)
    assert held["status"]=="HOLD"
    assert held["blocking_drift_count"]>=1

def test_public_trust_and_document_receipt_scope():
    t=public_authoring_trust_status()
    assert t["status"]=="TRUST_BASELINE_ACTIVE"
    r=document_visual_authority_receipt(document_id="doc-1",revision=3,sha256="a"*64)
    assert r["scope"]=="RELEASE_BASELINE_AUTHORITY_NOT_PER_DOCUMENT_NATIVE_RENDER"
