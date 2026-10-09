from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hwpx_mcp.evidence.p414_evidence_service import PRODUCT, SCHEMA, canonical_json, canonical_sha256, verify_signed_receipt
from p414_evidence_store import P414EvidenceStore

DB = os.environ.get("P414_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DB, reason="P4.14 durable-store integration requires P414_TEST_DATABASE_URL")


def _receipt(private: Ed25519PrivateKey, agent_id: str, key_id: str, *, job_id: str, nonce: str, captured_at: str) -> dict:
    now = datetime.now(timezone.utc)
    manifest = {"files": [{"fixture_id": "ci-fixture", "path": "fixture.hwpx", "sha256": "a" * 64, "bytes": 1, "lowering_family": "CI_ONLY"}]}
    payload = {"schema": SCHEMA, "protocol_version": "1.0", "product": PRODUCT, "job_id": job_id,
        "exact_head": "a" * 40, "source_manifest_sha256": canonical_sha256(manifest), "source_manifest": manifest,
        "hancom_version": "TEST_ONLY", "hancom_build": "TEST_ONLY", "hancom_executable_sha256": "c" * 64,
        "windows_version": "CI TEST ONLY", "windows_build": "0", "capture_agent_version": "1.0.0",
        "issued_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat(), "nonce": nonce,
        "source_files": [{"fixture_id": "ci-fixture", "path": "fixture.hwpx", "sha256": "a" * 64, "unchanged_after_capture": True}],
        "outputs": [{"fixture_id": "ci-fixture", "pdf_sha256": "d" * 64, "export_succeeded": True, "page_count": 1, "bytes": 64}],
        "capture_manifest_sha256": "e" * 64, "process_custody": {"global_kill_used": False, "owned_hwp_pids": []},
        "capture_status": "CAPTURED", "recovery_status": "COMPLETE", "visual_verdict": "PENDING",
        "visual_observations": {"human_adjudications": []}, "document_binding": None, "captured_at": captured_at, "test_only": True}
    return {"schema": SCHEMA, "agent_id": agent_id, "key_id": key_id, "signed_payload": payload,
        "signature_ed25519_b64": base64.b64encode(private.sign(canonical_json(payload))).decode("ascii"),
        "canonical_sha256": canonical_sha256(payload)}


def test_postgres_append_only_signature_replay_and_key_lifecycle():
    store = P414EvidenceStore(DB)
    agent_id = "pg-test-" + uuid.uuid4().hex
    key_id = "pg-key-" + uuid.uuid4().hex
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    store.register_key(agent_id=agent_id, key_id=key_id, public_key_ed25519_b64=base64.b64encode(public).decode("ascii"))
    registry = store.list_keys(active_only=True)
    job_id, nonce = "job-" + uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
    first = _receipt(private, agent_id, key_id, job_id=job_id, nonce=nonce, captured_at=datetime.now(timezone.utc).isoformat())
    validation = verify_signed_receipt(first, registry, allow_test_receipts=True)
    assert validation["accepted"]
    saved = store.record_attempt(first, validation)
    assert saved["accepted"] and saved["idempotent_retry"] is False
    retry = store.record_attempt(first, validation)
    assert retry["accepted"] and retry["idempotent_retry"] is True
    changed = _receipt(private, agent_id, key_id, job_id=job_id, nonce=nonce, captured_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat())
    changed_validation = verify_signed_receipt(changed, registry, allow_test_receipts=True)
    replay = store.record_attempt(changed, changed_validation)
    assert replay["accepted"] is False
    assert any(x["code"] == "REPLAYED_JOB_OR_NONCE" for x in replay["issues"])
    tampered = {**first, "signed_payload": {**first["signed_payload"], "hancom_build": "TAMPERED"}}
    bad = verify_signed_receipt(tampered, registry, allow_test_receipts=True)
    rejected = store.record_attempt(tampered, bad)
    assert rejected["accepted"] is False
    with psycopg.connect(DB) as conn:
        raw = conn.execute("SELECT raw_receipt::text,validation_result::text FROM hwpx_p414_receipt_attempt WHERE evidence_id=%s ORDER BY received_at DESC LIMIT 1", (canonical_sha256(tampered),)).fetchone()
        assert raw and "TAMPERED" in raw[0] and "SIGNATURE_INVALID" in raw[1]
        with pytest.raises(psycopg.Error):
            conn.execute("DELETE FROM hwpx_p414_receipt_attempt WHERE evidence_id=%s", (saved["evidence_id"],))
    revoked = store.revoke_key(key_id=key_id, reason="integration test rotation/revoke")
    assert revoked["status"] == "REVOKED"
    assert key_id not in store.list_keys(active_only=True)
    health = store.counts()
    assert health["accepted_receipt_count"] >= 1 and health["replay_rejection_count"] >= 1
