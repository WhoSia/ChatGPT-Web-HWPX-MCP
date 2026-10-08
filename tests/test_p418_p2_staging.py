from __future__ import annotations

from types import SimpleNamespace

import pytest

import p418_mcp
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, annotations):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class FakeCore:
    def __init__(self):
        self.mcp = FakeMCP()
        self.DOCUMENT_STORE = SimpleNamespace(database_url="postgresql://unreached")
        self.documents = {"doc1": {"revision": 4, "sha256": "abc", "owner": "subject"}}

    def _caller_subject(self):
        return "subject"

    def _load_metadata(self, document_id):
        return self.documents[document_id]

    def _require_owner(self, metadata):
        if metadata["owner"] != self._caller_subject():
            raise PermissionError("not owner")


def registered():
    core = FakeCore()
    no_op = lambda *args, **kwargs: {}
    p418_mcp.register_p418_tools(
        core, create_adapter=no_op, edit_intent_adapter=no_op,
        template_fill_adapter=no_op, deliver_adapter=no_op,
        inspect_adapter=no_op, semantic_graph_adapter=no_op,
        document_map_adapter=no_op,
    )
    return core


def sample():
    d = compile_workflow({"steps": [{"task": {
        "kind": "EDIT_INTENT", "document_id": "doc1", "expected_revision": 4,
        "intent": {"actions": [{"action": "replace_role_text", "role": "TITLE", "text": "Hi"}]}
    }}]}, [{"document_id": "doc1", "revision": 4}])
    return d, preview_workflow(d)


def test_staging_never_returns_approval(monkeypatch):
    core = registered()
    class StubStore:
        def __init__(self, url):
            assert url == "postgresql://unreached"
        def stage(self, **kwargs):
            assert kwargs["owner"] == "subject"
            assert kwargs["bound_inputs"]["documents"][0]["revision"] == 4
            return {"workflow_id": "w", "state": "STAGED", "approval_granted": False}
    monkeypatch.setattr(p418_mcp, "get_durable_approval_ledger", lambda url: StubStore(url))
    draft, preview = sample()
    response = core.mcp.tools["stage_p418_document_workflow"](draft, preview)
    assert response["approval_granted"] is False
    assert response["authority"] == "SERVER_VERIFIED_STAGING_ONLY_NO_APPROVAL_OR_EXECUTION"


def test_staging_fails_after_source_revision_drift():
    core = registered()
    draft, preview = sample()
    core.documents["doc1"]["revision"] = 5
    with pytest.raises(AdmissionError, match="revision changed"):
        core.mcp.tools["stage_p418_document_workflow"](draft, preview)


def test_staging_rejects_modified_preview_and_wrong_owner():
    core = registered()
    draft, preview = sample()
    changed = dict(preview, preview_sha256="f" * 64)
    with pytest.raises(AdmissionError, match="does not match"):
        core.mcp.tools["stage_p418_document_workflow"](draft, changed)
    core.documents["doc1"]["owner"] = "other"
    with pytest.raises(PermissionError, match="not owner"):
        core.mcp.tools["stage_p418_document_workflow"](draft, preview)


def test_staging_rejects_inconsistent_normalized_task_digest():
    from copy import deepcopy
    from hwpx_mcp.orchestration.p418_p2_workflow import _digest
    core = registered()
    draft, _ = sample()
    forged = deepcopy(draft)
    forged["steps"][0]["task"]["intent"]["actions"][0]["text"] = "Unauthorized"
    forged.pop("draft_sha256")
    forged["draft_sha256"] = _digest(forged)
    forged_preview = preview_workflow(forged)
    with pytest.raises(AdmissionError, match="canonically compiled"):
        core.mcp.tools["stage_p418_document_workflow"](forged, forged_preview)


def test_staging_without_explicit_role_binding_still_supported(monkeypatch):
    core = registered()
    class StubStore:
        def __init__(self, url):
            assert url == "postgresql://unreached"
        def stage(self, **kwargs):
            return {"workflow_id": "fresh", "state": "STAGED", "approval_granted": False}
    monkeypatch.setattr(p418_mcp, "DurableApprovalLedger", StubStore)
    draft, preview = sample()
    assert draft["resolved_inputs"] == {}
    result = core.mcp.tools["stage_p418_document_workflow"](draft, preview)
    assert result["state"] == "STAGED"
