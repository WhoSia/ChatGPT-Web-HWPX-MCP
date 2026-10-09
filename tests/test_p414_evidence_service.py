from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hwpx_mcp.evidence.p414_evidence_service import (
    AGENT_VERSION,
    BASELINE_HEAD,
    PRODUCT,
    PROTOCOL_VERSION,
    SCHEMA,
    canonical_json,
    canonical_sha256,
    capture_agent_contract,
    compare_native_visual_drift,
    document_native_trust_receipt,
    evaluate_release_capture_obligation,
    evaluate_rollback_authority,
    hancom_build_matrix,
    release_change_vectors,
    validate_capture_job,
    verify_signed_receipt,
)


def _signed_receipt(*, job_id="job-test-001", nonce="this-is-a-test-nonce-long-enough-123", now=None, status="CAPTURED", visual="PASS"):
    clock = now or datetime.now(timezone.utc)
    manifest = {"files": [{"fixture_id": "p48-lab_report", "path": "lab_report.hwpx", "sha256": "a" * 64, "bytes": 512, "lowering_family": "P4.8_SEMANTIC_COMPONENTS"}]}
    payload = {
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "product": PRODUCT,
        "job_id": job_id,
        "exact_head": "b" * 40,
        "source_manifest_sha256": canonical_sha256(manifest),
        "source_manifest": manifest,
        "hancom_version": "13.0.0.3622",
        "hancom_build": "13.0.0.3622",
        "hancom_executable_sha256": "c" * 64,
        "windows_version": "Windows 10 Home",
        "windows_build": "26200",
        "capture_agent_version": AGENT_VERSION,
        "issued_at": clock.isoformat(),
        "expires_at": (clock + timedelta(hours=1)).isoformat(),
        "nonce": nonce,
        "source_files": [{"fixture_id": "p48-lab_report", "path": "lab_report.hwpx", "sha256": "a" * 64, "unchanged_after_capture": True}],
        "outputs": [{"fixture_id": "p48-lab_report", "pdf_sha256": "d" * 64, "export_succeeded": True, "page_count": 2, "bytes": 128}],
        "capture_manifest_sha256": "e" * 64,
        "process_custody": {"parent_pid": 3, "owned_hwp_pids": [4], "terminated_owned_hwp_pids": [4], "global_kill_used": False},
        "capture_status": status,
        "recovery_status": "COMPLETE",
        "visual_verdict": visual,
        "visual_observations": {"human_adjudications": [{"fixture_id": "p48-lab_report", "status": visual, "reviewer": "tester", "reviewed_at": clock.isoformat()}]},
        "document_binding": {"document_id": "doc-1", "revision": 3, "document_sha256": "f" * 64},
        "captured_at": clock.isoformat(),
    }
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_b64 = base64.b64encode(public).decode("ascii")
    receipt = {"schema": SCHEMA, "agent_id": "win-test-agent", "key_id": "win-test-key", "signed_payload": payload, "signature_ed25519_b64": base64.b64encode(private.sign(canonical_json(payload))).decode("ascii"), "canonical_sha256": canonical_sha256(payload)}
    registry = {"win-test-key": {"agent_id": "win-test-agent", "public_key_ed25519_b64": public_b64, "status": "ACTIVE"}}
    return receipt, registry, private


def test_agent_contract_and_capture_job_validation():
    contract = capture_agent_contract()
    assert contract["protocol_version"] == PROTOCOL_VERSION
    assert "NO_WATCHER" in contract["source_access"]
    assert "NEVER_GLOBAL_KILL" in contract["process_custody"]
    manifest = {"files": [{"fixture_id": "p48-lab_report", "path": "lab_report.hwpx", "sha256": "a" * 64, "bytes": 20, "lowering_family": "P4.8"}]}
    now = datetime.now(timezone.utc)
    job = {"job_id": "job-test-001", "exact_head": "b" * 40, "product": PRODUCT, "source_root": "C:/capture/input", "source_manifest": manifest, "source_manifest_sha256": canonical_sha256(manifest), "hancom_build_expected": "13.0.0.3622", "issued_at": now.isoformat(), "expires_at": (now + timedelta(hours=2)).isoformat(), "nonce": "this-is-a-test-nonce-long-enough-123", "output_target": "C:/capture/output", "capture_kind": "FIVE_ARCHETYPE"}
    assert validate_capture_job(job, now=now)["status"] == "PASS"
    bad = {**job, "output_target": "C:/capture/input/results"}
    assert "OUTPUT_MUST_BE_OUTSIDE_SOURCE_ROOT" in {x["code"] for x in validate_capture_job(bad, now=now)["issues"]}
    bad = {**job, "source_manifest_sha256": "0" * 64}
    assert "SOURCE_MANIFEST_HASH_MISMATCH" in {x["code"] for x in validate_capture_job(bad, now=now)["issues"]}


def test_ed25519_receipt_rejects_tamper_wrong_key_and_expiry():
    receipt, registry, _ = _signed_receipt()
    assert verify_signed_receipt(receipt, registry)["accepted"] is True
    assert "EXACT_HEAD_MISMATCH" in {x["code"] for x in verify_signed_receipt(receipt, registry, expected_head="c" * 40)["issues"]}
    tampered = {**receipt, "signed_payload": {**receipt["signed_payload"], "hancom_build": "tampered"}}
    result = verify_signed_receipt(tampered, registry)
    assert result["accepted"] is False
    assert {x["code"] for x in result["issues"]} & {"CANONICAL_DIGEST_MISMATCH", "SIGNATURE_INVALID"}
    wrong_key = verify_signed_receipt(receipt, {"win-test-key": {"agent_id": "other-agent", "public_key_ed25519_b64": registry["win-test-key"]["public_key_ed25519_b64"]}})
    assert "UNKNOWN_OR_WRONG_KEY" in {x["code"] for x in wrong_key["issues"]}
    old = datetime.now(timezone.utc) - timedelta(days=2)
    expired, expired_registry, _ = _signed_receipt(now=old)
    assert "SIGNED_RECEIPT_EXPIRED" in {x["code"] for x in verify_signed_receipt(expired, expired_registry)["issues"]}


def test_native_capture_needs_custody_manifest_and_human_render_evidence():
    receipt, registry, _ = _signed_receipt()
    assert verify_signed_receipt(receipt, registry)["accepted"]
    receipt["signed_payload"]["visual_observations"] = {"human_adjudications": []}
    private = Ed25519PrivateKey.generate()
    # The altered payload cannot be accepted under the prior signature/key.
    assert not verify_signed_receipt(receipt, registry)["accepted"]
    pending, pending_keys, _ = _signed_receipt(visual="PENDING")
    assert verify_signed_receipt(pending, pending_keys)["accepted"] is True


def test_release_obligation_and_drift_gate_separate_diagnostic_from_blocking():
    previous, candidate = release_change_vectors(exact_head="b" * 40)
    obligation = evaluate_release_capture_obligation(previous=previous, candidate=candidate)
    assert obligation["status"] == "FRESH_CAPTURE_REQUIRED"
    assert obligation["blocks_promotion"] is False
    assert obligation["triggers"][0]["code"] == "CAPTURE_AGENT_PROTOCOL_CHANGE"
    no_change = evaluate_release_capture_obligation(previous=previous, candidate={**previous, "exact_head": "c" * 40})
    assert no_change["status"] == "NO_FRESH_CAPTURE_REQUIRED"
    source_change = evaluate_release_capture_obligation(previous=previous, candidate={**candidate, "source_fixture_manifest_sha256": "different"})
    assert source_change["status"] == "BLOCKING_CAPTURE_REQUIRED"
    base = {"release_identity": {"product": "old"}, "cases": [{"fixture_id": "f1", "source_sha256": "a" * 64}]}
    byte_only = compare_native_visual_drift(base, {"release_identity": {"product": "new"}, "capture_status": "CAPTURED", "cases": [{"fixture_id": "f1", "source_sha256": "a" * 64, "pdf_sha256": "b" * 64, "baseline_pdf_sha256": "c" * 64}]})
    assert byte_only["status"] == "NO_BLOCKING_DRIFT"
    hidden = compare_native_visual_drift(base, {"cases": [{"fixture_id": "f1", "source_sha256": "a" * 64, "semantic_visible": False}]})
    assert hidden["status"] == "BLOCKING_REGRESSION"
    assert any(x["code"] == "SEMANTIC_DISAPPEARANCE" for x in hidden["issues"])


def test_matrix_is_build_version_indexed_and_visual_pending_holds():
    receipt, registry, _ = _signed_receipt(visual="PENDING")
    validation = verify_signed_receipt(receipt, registry)
    row = {**receipt["signed_payload"], "accepted": validation["accepted"], "evidence_id": validation["raw_receipt_sha256"]}
    matrix = hancom_build_matrix([row])
    cell = matrix["cells"][0]
    assert cell["status"] == "HOLD"
    assert cell["hancom_build"] == "13.0.0.3622"
    assert matrix["prior_certified_release"]["exact_head"] == BASELINE_HEAD
    assert matrix["inherited_release_baseline_is_not_agent_cell"]
    assert hancom_build_matrix([])["status"] == "UNKNOWN"
    other_build = hancom_build_matrix([{**row, "hancom_build": "13.0.0.9999"}])
    assert other_build["status"] == "HOLD" and other_build["incompatible_builds"] == ["13.0.0.9999"]
    blocked = hancom_build_matrix([{**row, "visual_verdict": "PASS", "visual_observations": {"human_adjudications": [{"fixture_id": "p48-lab_report", "defects": ["CLIPPING"]}]}}])
    assert blocked["cells"][0]["status"] == "REGRESSION"


def test_rollback_requires_signed_native_evidence_and_release_identity():
    release = {"release_id": "current", "product": PRODUCT, "exact_head": "a" * 40, "render_deploy_id": "dep-current"}
    from hwpx_mcp.evidence.p414_evidence_service import release_identity_seed
    target = release_identity_seed()
    drift = {"status": "BLOCKING_REGRESSION", "drift_receipt_sha256": "d" * 64}
    denied = evaluate_rollback_authority(signed_evidence_validation={"accepted": False}, drift_receipt=drift, current_release=release, target_release=target)
    assert denied["status"] == "DENIED"
    signed = {"accepted": True, "evidence_id": "e" * 64, "exact_head": "a" * 40}
    dry = evaluate_rollback_authority(signed_evidence_validation=signed, drift_receipt=drift, current_release=release, target_release=target)
    assert dry["status"] == "DRY_RUN_AUTHORIZED" and dry["execution_performed"] is False
    assert evaluate_rollback_authority(signed_evidence_validation=signed, drift_receipt=drift, current_release=release, target_release=target, mode="APPROVED_EXECUTION")["status"] == "DENIED"
    assert evaluate_rollback_authority(signed_evidence_validation=signed, drift_receipt=drift, current_release=release, target_release=target, mode="APPROVED_EXECUTION", approval_ref="approved-by-operator-42")["status"] == "APPROVED_EXECUTION_AUTHORIZED"


def test_document_trust_receipt_never_inherits_per_document_native_status():
    pending = document_native_trust_receipt(document_id="doc-1", revision=3, sha256="f" * 64)
    assert pending["authority_class"] == "NATIVE_VERIFICATION_PENDING"
    assert pending["release_product"] == "0.39.0-p4.14"
    evidence = {"accepted": True, "test_only": False, "product": PRODUCT, "exact_head": "b" * 40, "visual_verdict": "PASS", "document_binding": {"document_id": "doc-1", "revision": 3, "document_sha256": "f" * 64}, "evidence_id": "e" * 64, "hancom_build": "13.0.0.3622", "captured_at": "2026-10-02T00:00:00Z", "capture_status": "CAPTURED"}
    verified = document_native_trust_receipt(document_id="doc-1", revision=3, sha256="f" * 64, evidence=evidence, release_head="b" * 40)
    assert verified["authority_class"] == "PER_DOCUMENT_NATIVE_VERIFIED"
    assert verified["evidence_receipt_id"] == "e" * 64
    mismatch = document_native_trust_receipt(document_id="doc-1", revision=4, sha256="f" * 64, evidence=evidence, release_head="b" * 40)
    assert mismatch["authority_class"] == "NATIVE_VERIFICATION_PENDING"
    synthetic = document_native_trust_receipt(document_id="doc-1", revision=3, sha256="f" * 64, evidence={**evidence, "test_only": True}, release_head="b" * 40)
    assert synthetic["authority_class"] == "NATIVE_VERIFICATION_PENDING"
