"""The native-edit bridge is a trusted server-side seam, never an MCP tool."""
from __future__ import annotations

from copy import deepcopy

import pytest

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p3_native_edit_bridge import (
    execute_host_approved_native_edit,
)


class MemoryStore:
    def __init__(self):
        self.commits = {}

    def get_commit_receipt(self, document_id, revision):
        return self.commits.get((document_id, revision))


class Core:
    def __init__(self):
        self.owner = "subject"
        self.metadata = {"doc1": {"owner": "subject", "revision": 4, "sha256": "source-sha"}}
        self.DOCUMENT_STORE = MemoryStore()

    def _caller_subject(self):
        return "subject"

    def _load_metadata(self, doc):
        return self.metadata[doc]

    def _require_owner(self, metadata):
        if metadata["owner"] != self._caller_subject():
            raise PermissionError("wrong owner")


class Ledger:
    def __init__(self):
        self.state = "APPROVED"
        self.result = None
        self.claim_calls = 0

    def claim(self, **kw):
        self.claim_calls += 1
        if self.state == "COMMITTED":
            return {"state": "COMMITTED", "result": self.result}
        if self.state == "UNCERTAIN":
            return {"state": "UNCERTAIN"}
        if not kw["verify_live_bindings"](kw["owner"], kw["bound_inputs"]):
            raise AdmissionError("live binding verification failed")
        self.state = "CLAIMED"
        return {"state": "CLAIMED"}

    def committed(self, **kw):
        assert kw["verify_commit"](kw["owner"], kw["result"])
        self.result = dict(kw["result"])
        self.state = "COMMITTED"
        return {"result": self.result}

    def recover(self, **kw):
        self.state = "UNCERTAIN"
        return {"state": self.state}


def prepared():
    core, ledger = Core(), Ledger()
    task = {
        "kind": "EDIT_INTENT", "document_id": "doc1", "expected_revision": 4,
        "intent": {"actions": [{"action": "replace_role_text", "role": "TITLE", "text": "Reviewed"}]},
    }
    draft = compile_workflow({"steps": [{"task": task}]}, [{"document_id": "doc1", "revision": 4}])
    snapshot = {"documents": [{
        "role": "document_id", "document_id": "doc1",
        "revision": 4, "sha256": "source-sha",
    }]}
    calls = []

    def native_adapter(**kwargs):
        calls.append(deepcopy(kwargs))
        core.metadata["doc1"] = {"owner": "subject", "revision": 5, "sha256": "new-sha"}
        core.DOCUMENT_STORE.commits[("doc1", 5)] = {
            "document_id": "doc1", "revision": 5, "expected_revision": 4,
            "sha256": "new-sha", "receipt_id": "actual-commit-5",
            "audit_hash": "a" * 64,
        }
        return {"ok": True, "document_id": "doc1",
                "revision_before": 4, "revision_after": 5}

    opts = {
        "core": core, "ledger": ledger, "workflow_id": "workflow",
        "approval_key": "host-only-key", "draft": draft, "preview": preview_workflow(draft),
        "bound_inputs": snapshot, "execution_key": "stable-host-execution-key",
        "native_edit_adapter": native_adapter,
    }
    return opts, calls


def test_native_edit_commit_and_delivery_replay():
    opts, calls = prepared()
    first = execute_host_approved_native_edit(**opts)
    second = execute_host_approved_native_edit(**opts)
    assert first["state"] == "COMMITTED"
    assert first["mutation_executed"] is True
    assert second["delivery_only"] is True and second["mutation_executed"] is False
    assert first["result"]["receipt_id"] == "actual-commit-5"
    assert len(calls) == 1
    assert calls[0]["document_id"] == "doc1"


@pytest.mark.parametrize("tamper", ["owner", "revision", "sha", "role", "missing_sha"])
def test_stale_or_foreign_source_is_blocked_before_native_effect(tamper):
    opts, calls = prepared()
    if tamper == "owner":
        opts["core"].metadata["doc1"]["owner"] = "someone_else"
    elif tamper == "revision":
        opts["core"].metadata["doc1"]["revision"] = 5
    elif tamper == "sha":
        opts["bound_inputs"]["documents"][0]["sha256"] = "forged"
    elif tamper == "role":
        opts["bound_inputs"]["documents"][0]["role"] = "reference_document_id"
    else:
        opts["bound_inputs"]["documents"][0]["sha256"] = ""
    with pytest.raises(AdmissionError, match="(live binding|staged document)"):
        execute_host_approved_native_edit(**opts)
    assert not calls


def test_unverified_commit_never_returns_success():
    opts, calls = prepared()
    original = opts["native_edit_adapter"]

    def faulty(**kw):
        result = original(**kw)
        opts["core"].DOCUMENT_STORE.commits[("doc1", 5)]["receipt_id"] = ""
        return result

    opts["native_edit_adapter"] = faulty
    with pytest.raises(AdmissionError, match="not verified"):
        execute_host_approved_native_edit(**opts)
    assert len(calls) == 1
    assert opts["ledger"].state == "UNCERTAIN"
    assert execute_host_approved_native_edit(**opts)["state"] == "UNCERTAIN"
    assert len(calls) == 1


def test_refuse_different_commit_revision():
    opts, _calls = prepared()
    def invalid(**kw):
        return {"ok": True, "document_id": "doc1",
                "revision_before": 4, "revision_after": 6}
    opts["native_edit_adapter"] = invalid
    with pytest.raises(AdmissionError, match="differs from approved"):
        execute_host_approved_native_edit(**opts)
    assert opts["ledger"].state == "UNCERTAIN"


def test_reject_untrusted_kind_without_claim():
    opts, _ = prepared()
    draft = deepcopy(opts["draft"])
    draft["steps"][0]["task"]["kind"] = "CREATE"
    opts["draft"] = draft
    with pytest.raises(AdmissionError, match="only admits one EDIT_INTENT"):
        execute_host_approved_native_edit(**opts)
    assert opts["ledger"].claim_calls == 0
