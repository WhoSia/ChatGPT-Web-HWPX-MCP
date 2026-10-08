from __future__ import annotations

import os
import uuid

import pytest

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError, DurableApprovalLedger
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from hwpx_mcp.orchestration.p418_p3_review_store import DurableNativeReviewStore
from hwpx_mcp.orchestration.p418_p3_host_approval import TrustedNativeEditApprovalHost
from hwpx_mcp.orchestration.p418_p3_execution import execute_exact_approved_draft

URL = os.getenv("P418_P2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="real PostgreSQL required")
PASSPHRASE = "human-approved-only-" + "p" * 32
SIGNING_KEY = b"independent-host-signing-secret-" + b"q" * 42


def workflow():
    owner = "host-test-" + uuid.uuid4().hex
    doc = "owned-" + uuid.uuid4().hex
    draft = compile_workflow({"steps": [{"task": {
        "kind": "EDIT_INTENT", "document_id": doc, "expected_revision": 3,
        "intent": {"actions": [{"action": "replace_role_text",
                                "role": "TITLE", "text": "실제 승인 텍스트"}]},
    }}]}, [{"document_id": doc, "revision": 3}])
    preview = preview_workflow(draft)
    bindings = {"documents": [{"role": "document_id", "document_id": doc,
                                "revision": 3, "sha256": "a" * 64}]}
    ledger = DurableApprovalLedger(URL)
    record = ledger.stage(owner=owner, draft_sha256=draft["draft_sha256"],
                          preview_sha256=preview["preview_sha256"],
                          bound_inputs=bindings, effect_scope="EDIT_INTENT")
    wid = record["workflow_id"]
    store = DurableNativeReviewStore(URL, "review-store-" + "z" * 45)
    store.persist_staged(owner=owner, workflow_id=wid,
                         draft=draft, preview=preview, bound_inputs=bindings)
    return owner, doc, wid, ledger, store


def test_real_postgres_host_consent_executes_once_and_survives_restart():
    owner, doc, wid, ledger, store = workflow()
    mutations = []

    def perform(**args):
        return execute_exact_approved_draft(
            ledger=DurableApprovalLedger(URL), owner=owner,
            workflow_id=wid, approval_key=args["approval_key"],
            draft=args["draft"], preview=args["preview"],
            bound_inputs=args["bound_inputs"], execution_key=args["execution_key"],
            verify_live_bindings=lambda who, bindings: who == owner,
            execute_normalized_task=lambda task: (
                mutations.append(task) or {
                    "document_id": doc, "revision": 4,
                    "expected_revision": 3, "sha256": "b"*64,
                    "receipt_id": "durable-example", "audit_hash": "c"*64}),
            verify_durable_commit=lambda who, receipt:
                who == owner and receipt.get("receipt_id") == "durable-example",
        )

    host = TrustedNativeEditApprovalHost(
        ledger=ledger, reviews=store, owner=owner,
        review_passphrase=PASSPHRASE, signing_secret=SIGNING_KEY,
        native_executor=perform)
    review = host.inspect(workflow_id=wid, passphrase=PASSPHRASE)
    assert review["approval_granted"] is False
    result = host.approve_and_execute(
        workflow_id=wid, passphrase=PASSPHRASE,
        displayed_review_sha256=review["review_packet_sha256"])
    assert result["state"] == "COMMITTED" and result["committed_revision"] == 4
    assert len(mutations) == 1
    restarted = DurableApprovalLedger(URL)
    state = restarted.recover(owner=owner, workflow_id=wid)
    assert state["recovery_route"] == "EXACT_REVISION_DELIVERY_ONLY"
    assert state["replay_allowed"] is False
    with pytest.raises(AdmissionError):
        host.approve_and_execute(
            workflow_id=wid, passphrase=PASSPHRASE,
            displayed_review_sha256=review["review_packet_sha256"])
    assert len(mutations) == 1


def test_wrong_passphrase_locks_entire_staged_workflow():
    owner, doc, wid, ledger, store = workflow()
    for index in range(5):
        assert not store.verify_host_passphrase(
            owner=owner, workflow_id=wid,
            supplied="guess-" + str(index), expected=PASSPHRASE)
    assert not store.verify_host_passphrase(
        owner=owner, workflow_id=wid,
        supplied=PASSPHRASE, expected=PASSPHRASE)
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT failure_count FROM hwpx_p418_host_auth_attempt WHERE workflow_id=%s", (wid,))
        assert cur.fetchone()[0] == 5
