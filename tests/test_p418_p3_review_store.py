"""Real PostgreSQL encrypted review custody integration, not a mocked ledger."""
from __future__ import annotations

import json
import os
import uuid

import pytest

from hwpx_mcp.orchestration.p418_p2_admission import (
    AdmissionError, DurableApprovalLedger,
)
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from hwpx_mcp.orchestration.p418_p3_review_store import DurableNativeReviewStore

URL = os.getenv("P418_P2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="P418_P2_TEST_DATABASE_URL required")


def fixture():
    owner = "test-human-review-" + uuid.uuid4().hex
    draft = compile_workflow({"steps": [{"task": {
        "kind": "EDIT_INTENT", "document_id": "doc-native",
        "expected_revision": 5,
        "intent": {"goal": "Rewrite approved title",
                   "actions": [{"action": "replace_role_text",
                                "role": "TITLE", "text": "민감 작업 대상 문구"}]},
        "lease_token": "test-sensitive-lease-token",
    }}]}, [{"document_id": "doc-native", "revision": 5}])
    preview = preview_workflow(draft)
    bound = {"documents": [{
        "role": "document_id", "document_id": "doc-native",
        "revision": 5, "sha256": "a" * 64,
    }]}
    ledger = DurableApprovalLedger(URL)
    staged = ledger.stage(
        owner=owner, draft_sha256=draft["draft_sha256"],
        preview_sha256=preview["preview_sha256"],
        bound_inputs=bound, effect_scope="EDIT_INTENT")
    return owner, draft, preview, bound, ledger, staged["workflow_id"]


def test_encrypted_review_round_trip_and_owner_scope():
    owner, draft, preview, bound, ledger, wid = fixture()
    secret = "isolated-review-encryption-test-" + "s" * 48
    store = DurableNativeReviewStore(URL, secret)
    store.persist_staged(owner=owner, workflow_id=wid,
                         draft=draft, preview=preview, bound_inputs=bound)
    restarted = DurableNativeReviewStore(URL, secret)
    loaded = restarted.load_staged(owner=owner, workflow_id=wid)
    assert loaded == {"draft": draft, "preview": preview, "bound_inputs": bound}
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT encrypted_review FROM hwpx_p418_native_review WHERE workflow_id=%s", (wid,))
        encrypted = bytes(cur.fetchone()[0])
    assert b"test-sensitive-lease-token" not in encrypted
    assert "민감 작업 대상 문구".encode() not in encrypted
    with pytest.raises(AdmissionError, match="missing"):
        restarted.load_staged(owner="other-owner", workflow_id=wid)
    with pytest.raises(AdmissionError):
        DurableNativeReviewStore(URL, secret + "-incorrect").load_staged(owner=owner, workflow_id=wid)
    ledger.abort_unclaimed(owner=owner, workflow_id=wid)
    with pytest.raises(AdmissionError, match="no longer available"):
        restarted.load_staged(owner=owner, workflow_id=wid)


def test_review_cannot_override_canonical_staging_or_replace_snapshot():
    owner, draft, preview, bound, _ledger, wid = fixture()
    store = DurableNativeReviewStore(URL, "review-custody-" + "k" * 40)
    altered = json.loads(json.dumps(bound))
    altered["documents"][0]["sha256"] = "f" * 64
    with pytest.raises(AdmissionError, match="differs"):
        store.persist_staged(owner=owner, workflow_id=wid,
                             draft=draft, preview=preview, bound_inputs=altered)
    store.persist_staged(owner=owner, workflow_id=wid,
                         draft=draft, preview=preview, bound_inputs=bound)
    with pytest.raises(Exception):
        store.persist_staged(owner=owner, workflow_id=wid,
                             draft=draft, preview=preview, bound_inputs=bound)
    assert store.load_staged(owner=owner, workflow_id=wid)["draft"] == draft
