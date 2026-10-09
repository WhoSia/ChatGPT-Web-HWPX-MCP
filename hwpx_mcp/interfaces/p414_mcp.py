from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timezone
from typing import Any

from mcp.types import ToolAnnotations

from hwpx_mcp.evidence.p414_evidence_service import (
    AGENT_VERSION,
    BASELINE_HEAD,
    BASELINE_PRODUCT,
    PRODUCT,
    PROTOCOL_VERSION,
    capture_agent_contract,
    compare_signed_receipt_to_promoted_baseline,
    document_native_trust_receipt,
    evaluate_release_capture_obligation,
    evaluate_rollback_authority,
    evidence_service_health,
    hancom_build_matrix,
    release_change_vectors,
    validate_capture_job,
    verify_signed_receipt,
)
from p414_evidence_store import P414EvidenceStore, default_database_url


def _release_vectors() -> tuple[dict, dict]:
    exact_head = os.environ.get("P414_RELEASE_EXACT_HEAD", os.environ.get("RENDER_GIT_COMMIT", "PENDING_EXACT_HEAD"))
    return release_change_vectors(exact_head=exact_head)


def register_p414_tools(core):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    store = getattr(core, "P414_EVIDENCE_STORE", None) or P414EvidenceStore(default_database_url())
    core.P414_EVIDENCE_STORE = store

    @core.mcp.tool(annotations=read)
    def get_p414_capture_agent_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **capture_agent_contract()}

    @core.mcp.tool(annotations=read)
    def validate_p414_capture_job(job_envelope: dict) -> dict:
        core._caller_subject()
        expected_head = os.environ.get("P414_RELEASE_EXACT_HEAD") or os.environ.get("RENDER_GIT_COMMIT") or None
        return {"ok": True, **validate_capture_job(job_envelope, expected_head=expected_head)}

    @core.mcp.tool(annotations=read)
    def validate_p414_signed_evidence_receipt(receipt: dict) -> dict:
        core._caller_subject()
        expected_head = os.environ.get("P414_RELEASE_EXACT_HEAD") or os.environ.get("RENDER_GIT_COMMIT") or None
        return {"ok": True, **verify_signed_receipt(receipt, store.list_keys(), expected_head=expected_head, allow_test_receipts=os.environ.get("P414_ALLOW_TEST_RECEIPTS") == "1")}

    @core.mcp.tool(annotations=write)
    def register_p414_capture_agent_key(agent_id: str, key_id: str, public_key_ed25519_b64: str, rotation_of: str = "") -> dict:
        core._caller_subject()
        try:
            raw = base64.b64decode(public_key_ed25519_b64, validate=True)
        except Exception as exc:
            raise ValueError("public_key_ed25519_b64 must be valid base64") from exc
        if len(raw) != 32 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}", agent_id) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}", key_id):
            raise ValueError("agent/key ids must be bounded identifiers and Ed25519 public key must be 32 bytes")
        return {"ok": True, **store.register_key(agent_id=agent_id, key_id=key_id, public_key_ed25519_b64=public_key_ed25519_b64, rotation_of=rotation_of or None)}

    @core.mcp.tool(annotations=write)
    def revoke_p414_capture_agent_key(key_id: str, reason: str) -> dict:
        core._caller_subject()
        if not reason.strip():
            raise ValueError("reason is required for revocation")
        return {"ok": True, **store.revoke_key(key_id=key_id, reason=reason)}

    @core.mcp.tool(annotations=write)
    def ingest_p414_signed_evidence_receipt(receipt: dict) -> dict:
        core._caller_subject()
        validation = verify_signed_receipt(receipt, store.list_keys(), expected_head=os.environ.get("P414_RELEASE_EXACT_HEAD") or os.environ.get("RENDER_GIT_COMMIT") or None, allow_test_receipts=os.environ.get("P414_ALLOW_TEST_RECEIPTS") == "1")
        stored = store.record_attempt(receipt, validation)
        if not stored.get("accepted"):
            return {"ok": False, **stored, "raw_receipt_preserved": True}
        return {"ok": True, **stored, "raw_receipt_preserved": True, "normalized_evidence_preserved": True}

    @core.mcp.tool(annotations=read)
    def get_p414_hancom_build_matrix() -> dict:
        core._caller_subject()
        return {"ok": True, **hancom_build_matrix(store.accepted_receipts())}

    @core.mcp.tool(annotations=read)
    def evaluate_p414_release_capture_obligation(explicit_high_risk: bool = False) -> dict:
        core._caller_subject()
        previous, candidate = _release_vectors()
        current_receipts = store.accepted_raw_receipts(exact_head=candidate["exact_head"])
        drifts = [compare_signed_receipt_to_promoted_baseline(receipt) for receipt in current_receipts]
        latest_drift = drifts[0] if drifts else None
        has_blocker = any(item.get("status") == "BLOCKING_REGRESSION" for item in drifts)
        unresolved_drift = has_blocker and not (latest_drift and latest_drift.get("status") == "NO_BLOCKING_DRIFT")
        return {"ok": True, **evaluate_release_capture_obligation(previous=previous, candidate=candidate, unresolved_drift=unresolved_drift, explicit_high_risk=explicit_high_risk)}

    @core.mcp.tool(annotations=read)
    def compare_p414_native_visual_drift(evidence_id: str) -> dict:
        core._caller_subject()
        stored = store.accepted_receipt_by_id(evidence_id)
        if not stored:
            return {"ok": True, "phase": "P4.14", "status": "EVIDENCE_NOT_FOUND", "evidence_complete": False, "authority": "P414_TYPED_NATIVE_VISUAL_DRIFT_ADJUDICATION"}
        current_head = os.environ.get("P414_RELEASE_EXACT_HEAD") or os.environ.get("RENDER_GIT_COMMIT") or None
        validation = verify_signed_receipt(stored["raw_receipt"], store.list_keys(), expected_head=current_head)
        if not validation.get("accepted"):
            return {"ok": True, **validation, "status": "EVIDENCE_UNTRUSTED", "evidence_complete": False}
        return {"ok": True, **compare_signed_receipt_to_promoted_baseline(stored["raw_receipt"]), "evidence_id": evidence_id}

    @core.mcp.tool(annotations=read)
    def get_p414_release_visual_authority() -> dict:
        core._caller_subject()
        previous, candidate = _release_vectors()
        obligation = evaluate_release_capture_obligation(previous=previous, candidate=candidate)
        matrix = hancom_build_matrix(store.accepted_receipts())
        current_cells = [c for c in matrix["cells"] if c.get("product") == PRODUCT and c.get("exact_head") == candidate["exact_head"] and c.get("capture_agent_version") == AGENT_VERSION]
        result = {"phase": "P4.14", "product": PRODUCT, "exact_head": candidate["exact_head"], "authority_class": "RELEASE_BASELINE_NATIVE_AUTHORITY", "inherited_from": {"product": BASELINE_PRODUCT, "exact_head": BASELINE_HEAD, "hancom_baseline_head": "da77daa9c3d21fffb37a0e3b600f46205e8de6f1"}, "fresh_capture_obligation": obligation["status"], "native_agent_cells": len(matrix["cells"]), "native_capture_protocol_certified": any(c.get("status") == "CERTIFIED" for c in current_cells), "current_agent_native_status": "CERTIFIED" if any(c.get("status") == "CERTIFIED" for c in current_cells) else "NATIVE_VERIFICATION_PENDING", "scope": "RELEASE_BASELINE_ONLY; NEVER IMPLIES PER_DOCUMENT_NATIVE_VERIFICATION", "authority": "P414_RELEASE_VISUAL_AUTHORITY"}
        return {"ok": True, **result}

    @core.mcp.tool(annotations=read)
    def evaluate_p414_rollback_authority(evidence_id: str, current_release: dict, target_release: dict, mode: str = "DRY_RUN", approval_ref: str = "") -> dict:
        core._caller_subject()
        stored = store.accepted_receipt_by_id(evidence_id)
        if not stored:
            return {"ok": True, "phase": "P4.14", "status": "DENIED", "authorized": False, "mode": mode, "execution_performed": False, "issues": [{"code": "SIGNED_NATIVE_EVIDENCE_NOT_FOUND"}], "authority": "P414_SIGNED_EVIDENCE_RELEASE_BOUND_ROLLBACK_AUTHORITY"}
        current_head = os.environ.get("P414_RELEASE_EXACT_HEAD") or os.environ.get("RENDER_GIT_COMMIT") or None
        validation = verify_signed_receipt(stored["raw_receipt"], store.list_keys(), expected_head=current_head)
        drift = compare_signed_receipt_to_promoted_baseline(stored["raw_receipt"]) if validation.get("accepted") else {"status": "EVIDENCE_INCOMPLETE"}
        return {"ok": True, **evaluate_rollback_authority(signed_evidence_validation=validation, drift_receipt=drift, current_release=current_release, target_release=target_release, mode=mode, approval_ref=approval_ref)}

    @core.mcp.tool(annotations=read)
    def get_p414_document_native_trust_receipt(document_id: str) -> dict:
        subject = core._caller_subject()
        metadata = core._load_metadata(document_id)
        core._require_owner(metadata)
        evidence = store.receipt_for_document(document_id=document_id, revision=int(metadata.get("revision") or 1), document_sha256=str(metadata.get("sha256") or ""))
        release_head = os.environ.get("P414_RELEASE_EXACT_HEAD") or os.environ.get("RENDER_GIT_COMMIT") or "PENDING_EXACT_HEAD"
        return {"ok": True, "authenticated_subject": subject, **document_native_trust_receipt(document_id=document_id, revision=int(metadata.get("revision") or 1), sha256=str(metadata.get("sha256") or ""), evidence=evidence, release_head=release_head)}

    @core.mcp.tool(annotations=read)
    def get_p414_evidence_service_health() -> dict:
        core._caller_subject()
        counts = store.counts()
        return {"ok": True, **evidence_service_health(store_mode=store.mode, key_count=counts["key_count"], revoked_key_count=counts["revoked_key_count"], receipt_count=counts["accepted_receipt_count"], replay_rejection_count=counts["replay_rejection_count"]), "receipt_attempt_count": counts["receipt_attempt_count"]}

    return {"phase": "P4.14", "product": PRODUCT, "store": store.mode, "tools_added": [
        "get_p414_capture_agent_contract", "validate_p414_capture_job", "validate_p414_signed_evidence_receipt",
        "register_p414_capture_agent_key", "revoke_p414_capture_agent_key", "ingest_p414_signed_evidence_receipt",
        "get_p414_hancom_build_matrix", "evaluate_p414_release_capture_obligation", "compare_p414_native_visual_drift",
        "get_p414_release_visual_authority", "evaluate_p414_rollback_authority", "get_p414_document_native_trust_receipt",
        "get_p414_evidence_service_health",
    ]}
