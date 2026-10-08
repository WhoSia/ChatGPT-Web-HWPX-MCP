from copy import deepcopy

import pytest

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow, _digest
from hwpx_mcp.orchestration.p418_p3_review_packet import prepare_native_edit_review_packet


def prepared():
    spec = {"steps": [{"task": {
        "kind": "EDIT_INTENT",
        "document_id": "document-1",
        "expected_revision": 3,
        "intent": {
            "goal": "제목 교체",
            "actions": [{"action": "replace_role_text", "role": "TITLE",
                         "text": "<approved> & complete new title"}],
            "preservation": {"required_grade": "TARGETED_PARTS_ONLY"},
        },
    }}]}
    draft = compile_workflow(spec, [{"document_id": "document-1", "revision": 3}])
    return {
        "owner": "authenticated-owner",
        "draft": draft,
        "preview": preview_workflow(draft),
        "staged_bindings": {"documents": [{
            "role": "document_id", "document_id": "document-1",
            "revision": 3, "sha256": "a" * 64,
        }]},
    }


def test_packet_displays_entire_action_and_never_grants_approval():
    packet = prepare_native_edit_review_packet(**prepared())
    assert packet["complete_task"]["intent"]["actions"][0]["text"] == "<approved> & complete new title"
    assert packet["requested_actions"][0]["role"] == "TITLE"
    assert packet["preservation"]["required_grade"] == "TARGETED_PARTS_ONLY"
    assert packet["source"]["source_sha256"] == "a" * 64
    assert packet["approval_granted"] is False
    assert packet["execution_allowed"] is False
    assert len(packet["review_packet_sha256"]) == 64
    assert "HOST_REVIEW_INPUT_ONLY" in packet["authority"]


def test_preview_tamper_and_wrong_binding_are_rejected():
    args = prepared()
    args["preview"]["effects"][0]["effect"] = "READ_ONLY"
    with pytest.raises(AdmissionError, match="preview"):
        prepare_native_edit_review_packet(**args)
    args = prepared()
    args["staged_bindings"]["documents"][0]["document_id"] = "other"
    with pytest.raises(AdmissionError, match="identity"):
        prepare_native_edit_review_packet(**args)


def test_missing_committed_source_hash_and_stale_revision_rejected():
    args = prepared()
    args["staged_bindings"]["documents"][0]["sha256"] = ""
    with pytest.raises(AdmissionError, match="SHA-256"):
        prepare_native_edit_review_packet(**args)
    args = prepared()
    args["staged_bindings"]["documents"][0]["revision"] = 4
    with pytest.raises(AdmissionError, match="revision differs"):
        prepare_native_edit_review_packet(**args)


def test_invalid_approval_lookalike_task_rejected():
    args = prepared()
    forged = deepcopy(args["draft"])
    forged["steps"][0]["task"]["intent"]["actions"][0]["text"] = "Never approved"
    forged["steps"][0]["task"]["task_sha256"] = _digest({
        k: v for k, v in forged["steps"][0]["task"].items() if k != "task_sha256"
    })
    forged.pop("draft_sha256")
    forged["draft_sha256"] = _digest(forged)
    args["draft"] = forged
    args["preview"] = preview_workflow(forged)
    with pytest.raises(AdmissionError, match="noncanonical task"):
        prepare_native_edit_review_packet(**args)
