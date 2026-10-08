import copy
import pytest

from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import correct_workflow, preview_workflow

DOCS = [{"document_id": "owned", "revision": 7}]
SPEC = {"steps": [{"task": {"kind": "EDIT_INTENT", "document_id": "owned",
        "expected_revision": 7, "intent": {"actions": [{"action": "replace_role_text",
        "role": "TITLE", "text": "Original"}]}}}]}


def test_preview_is_deterministic_and_never_approval():
    draft = compile_workflow(SPEC, DOCS)
    first = preview_workflow(draft)
    assert first == preview_workflow(draft)
    assert first["mutation_count"] == 1
    assert first["execution_allowed"] is False
    assert first["approval_status"] == "NOT_REQUESTED"


def test_modified_draft_is_rejected():
    draft = compile_workflow(SPEC, DOCS)
    altered = copy.deepcopy(draft)
    altered["steps"][0]["effect"] = "READ_ONLY"
    with pytest.raises(ValueError, match="integrity"):
        preview_workflow(altered)


def test_correction_invalidates_prior_preview_and_does_not_mutate_original():
    before = preview_workflow(compile_workflow(SPEC, DOCS))
    outcome = correct_workflow(SPEC, [{"path": ["steps", 0, "task", "intent", "actions", 0, "text"], "value": "Revised"}], DOCS)
    after = preview_workflow(outcome["draft"])
    assert before["preview_sha256"] != after["preview_sha256"]
    assert SPEC["steps"][0]["task"]["intent"]["actions"][0]["text"] == "Original"
    assert outcome["prior_approvals_valid"] is False
    assert outcome["execution_allowed"] is False


@pytest.mark.parametrize("path", [
    ["approved", "x"], ["steps", 0, "task", "task_sha256"],
    ["steps", 0, "task", "intent", "missing"],
    ["steps", -1, "task", "intent"], ["input_bindings", "UNKNOWN"]
])
def test_illegal_corrections_are_rejected(path):
    with pytest.raises(ValueError):
        correct_workflow(SPEC, [{"path": path, "value": True}], DOCS)


def test_stale_correction_fails_when_catalog_revision_changes():
    with pytest.raises(ValueError, match="stale"):
        correct_workflow(SPEC, [{"path": ["steps", 0, "task", "expected_revision"], "value": 7}],
                         [{"document_id": "owned", "revision": 8}])


def test_self_hashed_forged_effect_cannot_pass_preview():
    from hwpx_mcp.orchestration.p418_p2_workflow import _digest
    draft = compile_workflow(SPEC, DOCS)
    forged = copy.deepcopy(draft)
    forged["steps"][0]["effect"] = "READ_ONLY"
    forged.pop("draft_sha256")
    forged["draft_sha256"] = _digest(forged)
    with pytest.raises(ValueError, match="effect mismatch"):
        preview_workflow(forged)


def test_self_hashed_forged_count_cannot_pass_preview():
    from hwpx_mcp.orchestration.p418_p2_workflow import _digest
    draft = compile_workflow(SPEC, DOCS)
    forged = copy.deepcopy(draft)
    forged["mutation_count"] = 0
    forged.pop("draft_sha256")
    forged["draft_sha256"] = _digest(forged)
    with pytest.raises(ValueError, match="mutation count"):
        preview_workflow(forged)
