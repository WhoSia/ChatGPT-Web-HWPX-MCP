import pytest

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError
from hwpx_mcp.orchestration.p418_p3_execution import execute_approved_once


class Ledger:
    def __init__(self):
        self.state = "APPROVED"
        self.receipt = None
        self.calls = 0

    def claim(self, **kwargs):
        self.calls += 1
        if self.state == "COMMITTED":
            return {"state": "COMMITTED", "result": self.receipt}
        if self.state in ("CLAIMED", "UNCERTAIN"):
            return {"state": "UNCERTAIN"}
        assert kwargs["verify_live_bindings"](kwargs["owner"], kwargs["bound_inputs"])
        self.state = "CLAIMED"
        return {"state": "CLAIMED"}

    def committed(self, **kwargs):
        assert self.state == "CLAIMED"
        assert kwargs["verify_commit"](kwargs["owner"], kwargs["result"])
        self.receipt = dict(kwargs["result"])
        self.state = "COMMITTED"
        return {"result": self.receipt}

    def recover(self, **kwargs):
        assert kwargs["owner"] == "owner"
        if self.state == "CLAIMED":
            self.state = "UNCERTAIN"
        return {"state": self.state}


def invoke(db, effect, **extra):
    payload = {
        "ledger": db, "owner": "owner", "workflow_id": "w",
        "approval_key": "host-key", "draft_sha256": "a"*64,
        "preview_sha256": "b"*64, "bound_inputs": {"revision": 2},
        "effect_scope": "EDIT_INTENT", "execution_key": "stable",
        "verify_live_bindings": lambda owner, b: owner == "owner" and b["revision"] == 2,
        "perform_authorized_effect": effect,
        "verify_durable_commit": lambda owner, result: (
            owner == "owner" and result.get("commit_receipt") == "verified")
    }
    payload.update(extra)
    return execute_approved_once(**payload)


def test_first_commit_then_retry_never_mutates_again():
    db = Ledger()
    calls = []
    def effect():
        calls.append("mutated")
        return {"commit_receipt": "verified", "revision": 3}
    assert invoke(db, effect)["mutation_executed"] is True
    again = invoke(db, effect, verify_live_bindings=lambda *_: False)
    assert again["delivery_only"] is True
    assert again["mutation_executed"] is False
    assert calls == ["mutated"]


def test_commit_unknown_is_quarantined_instead_of_replayed():
    db = Ledger()
    calls = []
    def effect():
        calls.append("maybe-committed")
        raise RuntimeError("lost connection after document commit")
    with pytest.raises(RuntimeError):
        invoke(db, effect)
    result = invoke(db, effect)
    assert result["state"] == "UNCERTAIN"
    assert result["requires_reconciliation"] is True
    assert calls == ["maybe-committed"]


def test_unverified_receipt_is_quarantined():
    db = Ledger()
    with pytest.raises(AdmissionError, match="not verified"):
        invoke(db, lambda: {"commit_receipt": "unproven"})
    assert db.state == "UNCERTAIN"


def test_missing_trusted_host_callbacks_fail_without_claim():
    db = Ledger()
    with pytest.raises(AdmissionError, match="trusted host"):
        invoke(db, lambda: {}, verify_live_bindings=None)
    assert db.calls == 0
