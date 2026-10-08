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


def test_committed_replay_does_not_require_old_current_revision():
    db = new_ledger()
    inputs, staged = stage(db)
    grant = approve(db, inputs, staged)
    key = "stable-key-" + staged["workflow_id"]
    claim(db, inputs, staged, grant)
    receipt = {"document_id": "doc1", "revision": 5, "sha256": "e" * 64}
    db.committed(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                 execution_key=key, result=receipt, verify_commit=lambda *_: True)
    replay = claim(db, inputs, staged, grant,
                   verify_live_bindings=lambda *_: False)
    assert replay["state"] == "COMMITTED"
    assert replay["replay"] is True
    assert replay["result"]["revision"] == 5


def test_abort_is_owner_scoped_and_only_before_claim():
    db = new_ledger()
    inputs, staged = stage(db)
    with pytest.raises(AdmissionError, match="cannot be aborted"):
        db.abort_unclaimed(owner="someone-else", workflow_id=staged["workflow_id"])
    assert db.abort_unclaimed(owner=inputs["owner"], workflow_id=staged["workflow_id"])["state"] == "ABORTED"
    with pytest.raises(AdmissionError, match="stale"):
        approve(db, inputs, staged)
    inputs2, staged2 = stage(db)
    granted = approve(db, inputs2, staged2)
    claim(db, inputs2, staged2, granted)
    with pytest.raises(AdmissionError, match="cannot be aborted"):
        db.abort_unclaimed(owner=inputs2["owner"], workflow_id=staged2["workflow_id"])


def test_host_signed_consent_is_one_shot_and_scope_bound():
    import base64, hashlib, hmac, json, time
    db = new_ledger()
    inputs, staged = stage(db)
    host_secret = b"isolated-host-secret-" + b"s" * 40
    now = int(time.time())
    payload = {
        "version": "p418-p3-host-consent-v1", "subject": inputs["owner"],
        "workflow_id": staged["workflow_id"],
        "draft_sha256": inputs["draft_sha256"],
        "preview_sha256": inputs["preview_sha256"],
        "effect_scope": inputs["effect_scope"],
        "issued_at": now, "expires_at": now + 45,
        "decision": "APPROVE",
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode()
    signature = base64.urlsafe_b64encode(
        hmac.new(host_secret, b"p418-p3-consent-v1\0" + raw, hashlib.sha256).digest()
    ).decode().rstrip("=")
    envelope = {"payload": payload, "signature": signature}
    altered = {"payload": {**payload, "effect_scope": "CREATE"}, "signature": signature}
    with pytest.raises(AdmissionError, match="host assertion"):
        db.approve_host_assertion(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                                  envelope=altered, host_secret=host_secret)
    approved = db.approve_host_assertion(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                                         envelope=envelope, host_secret=host_secret)
    assert approved["state"] == "APPROVED"
    with pytest.raises(AdmissionError, match="unavailable"):
        db.approve_host_assertion(owner=inputs["owner"], workflow_id=staged["workflow_id"],
                                  envelope=envelope, host_secret=host_secret)


def test_p3_host_approved_execution_crosses_real_postgres_and_restarts():
    import base64, hashlib, hmac, json, time
    from hwpx_mcp.orchestration.p418_p3_execution import execute_approved_once
    db = new_ledger()
    inputs, staged = stage(db)
    now = int(time.time())
    secret = b"trusted-independent-host-secret-" + b"t" * 32
    payload = {
        "version": "p418-p3-host-consent-v1", "subject": inputs["owner"],
        "workflow_id": staged["workflow_id"],
        "draft_sha256": inputs["draft_sha256"],
        "preview_sha256": inputs["preview_sha256"],
        "effect_scope": inputs["effect_scope"],
        "issued_at": now, "expires_at": now + 90, "decision": "APPROVE",
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode()
    sig = hmac.new(secret, b"p418-p3-consent-v1\0" + raw, hashlib.sha256).digest()
    envelope = {"payload": payload, "signature": base64.urlsafe_b64encode(sig).decode().rstrip("=")}
    approval = db.approve_host_assertion(owner=inputs["owner"],
        workflow_id=staged["workflow_id"], envelope=envelope, host_secret=secret)
    effects = []
    kwargs = dict(owner=inputs["owner"], workflow_id=staged["workflow_id"],
        approval_key=approval["approval_key"], draft_sha256=inputs["draft_sha256"],
        preview_sha256=inputs["preview_sha256"], bound_inputs=inputs["bound_inputs"],
        effect_scope=inputs["effect_scope"], execution_key="P3-host-integration-" + staged["workflow_id"],
        verify_live_bindings=lambda who, bound: who == inputs["owner"] and bound == inputs["bound_inputs"],
        perform_authorized_effect=lambda: (effects.append("ONE") or {"commit_receipt": "verified", "revision": 5}),
        verify_durable_commit=lambda who, receipt: who == inputs["owner"] and receipt.get("commit_receipt") == "verified")
    first = execute_approved_once(ledger=db, **kwargs)
    second = execute_approved_once(ledger=new_ledger(), **kwargs)
    assert first["state"] == "COMMITTED" and first["mutation_executed"]
    assert second["delivery_only"] and not second["mutation_executed"]
    assert effects == ["ONE"]


def test_p3_postgres_unknown_commit_requires_manual_reconciliation():
    from hwpx_mcp.orchestration.p418_p3_execution import execute_approved_once
    db = new_ledger()
    inputs, staged = stage(db)
    approval = approve(db, inputs, staged)
    effects = []
    def ambiguous():
        effects.append("MAYBE_COMMITTED")
        raise RuntimeError("network failure after possible commit")
    args = dict(ledger=db, owner=inputs["owner"], workflow_id=staged["workflow_id"],
        approval_key=approval["approval_key"], draft_sha256=inputs["draft_sha256"],
        preview_sha256=inputs["preview_sha256"], bound_inputs=inputs["bound_inputs"],
        effect_scope=inputs["effect_scope"], execution_key="P3-uncertain-" + staged["workflow_id"],
        verify_live_bindings=lambda *_: True,
        perform_authorized_effect=ambiguous,
        verify_durable_commit=lambda *_: True)
    with pytest.raises(RuntimeError):
        execute_approved_once(**args)
    assert execute_approved_once(**{**args, "ledger": new_ledger()})["state"] == "UNCERTAIN"
    assert effects == ["MAYBE_COMMITTED"]
