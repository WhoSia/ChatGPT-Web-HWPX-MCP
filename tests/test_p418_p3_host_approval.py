from __future__ import annotations

import base64
from copy import deepcopy

import pytest

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError, canonical_sha
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from hwpx_mcp.orchestration.p418_p3_host_approval import TrustedNativeEditApprovalHost
from hwpx_mcp.orchestration.p418_p3_host_consent import verify_host_confirmation

SECRET = b"independent-host-signing-key-" + b"Z" * 40
PASSPHRASE = "independent-human-review-password-" + "P" * 24


def fixtures():
    draft = compile_workflow({"steps": [{"task": {
        "kind": "EDIT_INTENT", "document_id": "doc-1", "expected_revision": 7,
        "intent": {
            "goal": "Change title after explicit consent",
            "actions": [{"action": "replace_role_text",
                         "role": "TITLE", "text": "<new title>"}],
        },
    }}]}, [{"document_id": "doc-1", "revision": 7}])
    preview = preview_workflow(draft)
    bound_inputs = {"documents": [{
        "role": "document_id", "document_id": "doc-1",
        "revision": 7, "sha256": "a" * 64,
    }]}
    identities = {
        "draft_sha256": draft["draft_sha256"],
        "preview_sha256": preview["preview_sha256"],
        "binding_sha256": canonical_sha(bound_inputs),
        "effect_scope": "EDIT_INTENT",
    }
    saved = {"draft": draft, "preview": preview, "bound_inputs": bound_inputs}
    return saved, identities


class Ledger:
    def __init__(self, identity):
        self.identity = identity
        self.state = "STAGED"
        self.approvals = 0

    def get_staged_review_identity(self, *, owner, workflow_id):
        assert owner == "hwpx-owner" and workflow_id == "test-workflow-abcdef012345"
        if self.state != "STAGED":
            raise AdmissionError("already approved or aborted")
        return self.identity

    def approve_host_assertion(self, *, owner, workflow_id, envelope, host_secret):
        assert self.state == "STAGED"
        assert host_secret == SECRET
        assert verify_host_confirmation(
            secret=host_secret, envelope=envelope, owner=owner,
            workflow_id=workflow_id, draft_sha256=self.identity["draft_sha256"],
            preview_sha256=self.identity["preview_sha256"],
            effect_scope="EDIT_INTENT")
        self.state = "APPROVED"
        self.approvals += 1
        return {"approval_key": "never-expose-this-secret", "state": "APPROVED"}

    def abort_unclaimed(self, *, owner, workflow_id):
        self.state = "ABORTED"
        return {"state": self.state}


class Reviews:
    def __init__(self, saved):
        self.saved = saved
        self.auth_checks = 0

    def verify_host_passphrase(self, *, owner, workflow_id, supplied, expected):
        self.auth_checks += 1
        return supplied == expected and owner == "hwpx-owner"

    def load_staged(self, *, owner, workflow_id):
        return deepcopy(self.saved)


def controller():
    saved, identity = fixtures()
    ledger, reviews, effects = Ledger(identity), Reviews(saved), []

    def effect(**kwargs):
        assert kwargs["approval_key"] == "never-expose-this-secret"
        assert kwargs["owner"] == "hwpx-owner"
        effects.append(kwargs)
        return {"state": "COMMITTED", "mutation_executed": True,
                "result": {"document_id": "doc-1", "revision": 8, "receipt_id": "real"}}

    host = TrustedNativeEditApprovalHost(
        ledger=ledger, reviews=reviews, owner="hwpx-owner",
        review_passphrase=PASSPHRASE, signing_secret=SECRET,
        native_executor=effect)
    return host, ledger, reviews, effects


def test_explicit_review_then_one_time_approved_execution():
    host, ledger, _, effects = controller()
    review = host.inspect(workflow_id="test-workflow-abcdef012345", passphrase=PASSPHRASE)
    assert review["complete_task"]["intent"]["actions"][0]["text"] == "<new title>"
    assert review["approval_granted"] is False
    assert ledger.approvals == 0 and not effects
    result = host.approve_and_execute(
        workflow_id="test-workflow-abcdef012345", passphrase=PASSPHRASE,
        displayed_review_sha256=review["review_packet_sha256"])
    assert result["state"] == "COMMITTED"
    assert result["committed_revision"] == 8
    assert ledger.approvals == 1 and len(effects) == 1
    assert "approval_key" not in result
    assert "never-expose-this-secret" not in str(result)


def test_bad_password_and_review_digest_do_not_execute():
    host, ledger, _, effects = controller()
    with pytest.raises(AdmissionError, match="authentication"):
        host.inspect(workflow_id="test-workflow-abcdef012345", passphrase="wrong")
    with pytest.raises(AdmissionError, match="authentication"):
        host.approve_and_execute(
            workflow_id="test-workflow-abcdef012345", passphrase="wrong",
            displayed_review_sha256="a"*64)
    review = host.inspect(workflow_id="test-workflow-abcdef012345", passphrase=PASSPHRASE)
    with pytest.raises(AdmissionError, match="displayed human review changed"):
        host.approve_and_execute(
            workflow_id="test-workflow-abcdef012345", passphrase=PASSPHRASE,
            displayed_review_sha256="b"*64)
    assert ledger.approvals == 0 and effects == []
    assert review["execution_allowed"] is False


def test_denied_review_never_creates_approval():
    host, ledger, _, effects = controller()
    assert host.deny(
        workflow_id="test-workflow-abcdef012345",
        passphrase=PASSPHRASE)["state"] == "ABORTED"
    assert not effects
    with pytest.raises(AdmissionError):
        host.inspect(workflow_id="test-workflow-abcdef012345", passphrase=PASSPHRASE)
