from __future__ import annotations

import os
import uuid

import pytest

from hwpx_mcp.orchestration.p418_p2_admission import (
    AdmissionError, DurableApprovalLedger, canonical_sha,
)

DATABASE_URL = os.getenv("P418_P2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="P418_P2_TEST_DATABASE_URL required for PostgreSQL integration")


def new_ledger():
    return DurableApprovalLedger(DATABASE_URL)


def stage(ledger, **overrides):
    data = dict(owner="test-owner-" + uuid.uuid4().hex, draft_sha256="a" * 64,
                preview_sha256="b" * 64, bound_inputs={"target": "doc1", "revision": 4},
                effect_scope="EDIT_INTENT", ttl_seconds=600)
    data.update(overrides)
    staged = ledger.stage(**data)
    return data, staged


def approve(ledger, input_, staged):
    return ledger.approve(owner=input_["owner"], workflow_id=staged["workflow_id"],
                          trusted_confirmation={"host_event": "confirmed"},
                          verify_confirmation=lambda owner, wid, receipt: (
                              owner == input_["owner"] and wid == staged["workflow_id"]
                              and receipt == {"host_event": "confirmed"}))


def claim(ledger, input_, staged, granted, **kw):
    d = dict(owner=input_["owner"], workflow_id=staged["workflow_id"],
             approval_key=granted["approval_key"],
             draft_sha256=input_["draft_sha256"],
             preview_sha256=input_["preview_sha256"], bound_inputs=input_["bound_inputs"],
             effect_scope=input_["effect_scope"], execution_key="stable-key-" + staged["workflow_id"],
             verify_live_bindings=lambda owner, bindings: owner == input_["owner"] and bindings == input_["bound_inputs"])
    d.update(kw)
    return ledger.claim(**d)


def test_confirmation_is_required_and_cross_owner_is_denied():
    db = new_ledger()
    inputs, staged = stage(db)
    with pytest.raises(AdmissionError, match="trusted host"):
        db.approve(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                   trusted_confirmation=True, verify_confirmation=lambda *_: False)
    grant = approve(db, inputs, staged)
    with pytest.raises(AdmissionError, match="not found for caller"):
        claim(db, inputs, staged, grant, owner="another-caller")


def test_changed_preview_revision_or_scope_cannot_use_grant():
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    for alteration in [
        {"preview_sha256": "f" * 64},
        {"bound_inputs": {"target": "doc1", "revision": 5}},
        {"effect_scope": "CREATE"},
        {"approval_key": "forged"},
    ]:
        with pytest.raises(AdmissionError, match="no longer matches"):
            claim(db, inputs, staged, grant, **alteration)


def test_double_submission_never_replays_mutation():
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    first = claim(db, inputs, staged, grant)
    second = claim(db, inputs, staged, grant)
    assert first["state"] == "CLAIMED" and first["replay"] is False
    assert second["state"] == "UNCERTAIN" and second["replay"] is False
    assert db.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])["state"] == "UNCERTAIN"


def test_verified_commit_is_delivery_only_on_retry_and_restart():
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    key = "stable-key-" + staged["workflow_id"]
    claim(db, inputs, staged, grant)
    result = {"document_id": "doc1", "revision": 5, "sha256": "f" * 64}
    with pytest.raises(AdmissionError, match="verified durable"):
        db.committed(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                     execution_key=key, result=result, verify_commit=lambda *_: False)
    db.committed(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                 execution_key=key, result=result, verify_commit=lambda owner, receipt: receipt == result)
    restarted = new_ledger()
    replay = claim(restarted, inputs, staged, grant)
    assert replay["state"] == "COMMITTED" and replay["replay"] is True
    recovered = restarted.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])
    assert recovered["recovery_route"] == "EXACT_REVISION_DELIVERY_ONLY"
    assert recovered["replay_allowed"] is False


def test_staging_bounds_are_enforced():
    db = new_ledger()
    with pytest.raises(AdmissionError, match="lifetime"):
        stage(db, ttl_seconds=86400)
    with pytest.raises(AdmissionError, match="effect scope"):
        stage(db, effect_scope="DELETE")
    assert canonical_sha({"a": 1, "b": 2}) == canonical_sha({"b": 2, "a": 1})


def test_approval_expiration_is_fail_closed():
    db = new_ledger()
    inputs, staged = stage(db)
    with db._connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE hwpx_p418_workflow_admission SET expires_at=NOW()-INTERVAL '1 second' WHERE workflow_id=%s",
                    (staged["workflow_id"],))
    with pytest.raises(AdmissionError, match="stale"):
        approve(db, inputs, staged)


def test_parallel_claims_allow_only_one_mutation_start():
    from concurrent.futures import ThreadPoolExecutor
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(lambda _: claim(new_ledger(), inputs, staged, grant), range(4)))
    assert sum(x["state"] == "CLAIMED" for x in states) == 1
    assert sum(x["state"] == "UNCERTAIN" for x in states) == 3
    assert all(x["replay"] is False for x in states)


def test_rejected_commit_cannot_change_state():
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    claim(db, inputs, staged, grant)
    with pytest.raises(AdmissionError, match="claim not found"):
        db.committed(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                     execution_key="wrong-execution", result={"revision": 5},
                     verify_commit=lambda *_: True)
    assert db.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])["state"] == "UNCERTAIN"


def test_unknown_outcome_can_be_reconciled_without_mutation_replay():
    db = new_ledger()
    inputs, staged = stage(db)
    granted = approve(db, inputs, staged)
    key = "stable-key-" + staged["workflow_id"]
    claim(db, inputs, staged, granted)
    assert db.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])["state"] == "UNCERTAIN"
    receipt = {"document_id": "doc1", "revision": 5, "sha256": "c" * 64}
    with pytest.raises(AdmissionError, match="independent durable"):
        db.reconcile_uncertain(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                               execution_key=key, result=receipt, verify_commit=lambda *_: False)
    assert db.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])["state"] == "UNCERTAIN"
    resolved = db.reconcile_uncertain(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                                      execution_key=key, result=receipt,
                                      verify_commit=lambda owner, payload: payload == receipt)
    assert resolved["mutation_replayed"] is False
    assert db.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])["recovery_route"] == "EXACT_REVISION_DELIVERY_ONLY"
    assert claim(db, inputs, staged, granted)["replay"] is True


def test_live_revision_revalidation_blocks_stale_claim():
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    with pytest.raises(AdmissionError, match="live owner and revision"):
        claim(db, inputs, staged, grant, verify_live_bindings=lambda *_: False)
    assert db.recover(owner=inputs["owner"], workflow_id=staged["workflow_id"])["state"] == "APPROVED"
