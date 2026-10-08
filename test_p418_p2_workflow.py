from __future__ import annotations

import copy
import pytest

from p418_p2_workflow import compile_workflow

DOCS = [
    {"document_id": "target", "revision": 3},
    {"document_id": "template", "revision": 1},
]


def edit_task(**extra):
    return {"kind": "EDIT_INTENT", "intent": {"actions": [{"action": "replace_role_text", "role": "TITLE", "text": "New"}]}, **extra}


def spec(task, bindings=None):
    return {"steps": [{"task": task}], "input_bindings": bindings or {}}


def test_deterministic_resolution_and_draft_not_executable():
    workflow = spec(edit_task(), {"TARGET": "target"})
    a = compile_workflow(workflow, DOCS)
    b = compile_workflow(copy.deepcopy(workflow), list(reversed(DOCS)))
    assert a == b
    assert a["steps"][0]["task"]["document_id"] == "target"
    assert a["steps"][0]["task"]["expected_revision"] == 3
    assert a["mutation_count"] == 1
    assert a["executable"] is False
    assert a["status"] == "DRAFT_REQUIRES_SERVER_PREVIEW_AND_APPROVAL"


def test_requires_explicit_mutation_target():
    with pytest.raises(ValueError, match="TARGET selection"):
        compile_workflow(spec(edit_task()), DOCS)


def test_unknown_and_stale_mutation_targets_fail_closed():
    with pytest.raises(ValueError, match="stale"):
        compile_workflow(spec(edit_task(document_id="target", expected_revision=2)), DOCS)
    with pytest.raises(ValueError, match="missing"):
        compile_workflow(spec(edit_task(document_id="unknown", expected_revision=3)), DOCS)


def test_catalog_duplicate_and_invalid_revision_fail_closed():
    with pytest.raises(ValueError, match="unique"):
        compile_workflow(spec({"kind": "INSPECT", "document_id": "target"}), DOCS + [DOCS[0]])
    with pytest.raises(ValueError, match="nonnegative"):
        compile_workflow(spec({"kind": "INSPECT", "document_id": "target"}), [{"document_id": "target", "revision": True}])


def test_template_binding_and_unknown_template():
    draft = compile_workflow(
        spec({"kind": "TEMPLATE_FILL", "values": {"name": "Kim"}}, {"TEMPLATE": "template"}), DOCS
    )
    assert draft["steps"][0]["task"]["template_document_id"] == "template"
    with pytest.raises(ValueError, match="template missing"):
        compile_workflow(spec({"kind": "TEMPLATE_FILL", "template_document_id": "unknown", "values": {"x": 1}}), DOCS)


def test_multiple_mutation_steps_are_rejected():
    with pytest.raises(ValueError, match="multiple mutations"):
        compile_workflow({"steps": [{"task": {"kind": "CREATE", "plan": {"blocks": [1]}}}, {"task": {"kind": "CREATE", "plan": {"blocks": [2]}}}]}, DOCS)


def test_read_only_draft_is_never_execution_authorization():
    draft = compile_workflow(spec({"kind": "INSPECT", "document_id": "target"}), DOCS)
    assert draft["status"] == "READ_ONLY_DRAFT"
    assert draft["executable"] is False
    assert len(draft["draft_sha256"]) == 64


@pytest.mark.parametrize("change", [{"unknown": True}, {"steps": []}, {"steps": [None]}, {"input_bindings": {"TARGET": "missing"}}])
def test_invalid_workflow_input_fails_closed(change):
    original = spec({"kind": "INSPECT", "document_id": "target"})
    original.update(change)
    with pytest.raises(ValueError):
        compile_workflow(original, DOCS)


def test_explicit_target_cannot_override_selected_binding():
    with pytest.raises(ValueError, match="target binding conflicts"):
        compile_workflow(spec(edit_task(document_id="target", expected_revision=3), {"TARGET": "template"}), DOCS)


def test_template_binding_cannot_be_overridden():
    with pytest.raises(ValueError, match="template binding conflicts"):
        compile_workflow(spec({"kind": "TEMPLATE_FILL", "template_document_id": "target", "values": {"x": 1}}, {"TEMPLATE": "template"}), DOCS)


def test_reference_must_exist_and_match_binding():
    with pytest.raises(ValueError, match="reference missing"):
        compile_workflow(spec(edit_task(document_id="target", expected_revision=3, reference_document_id="unknown")), DOCS)
    with pytest.raises(ValueError, match="reference binding conflicts"):
        compile_workflow(spec(edit_task(document_id="target", expected_revision=3, reference_document_id="target"), {"REFERENCE": "template"}), DOCS)


def test_read_only_document_must_exist():
    with pytest.raises(ValueError, match="document missing"):
        compile_workflow(spec({"kind": "INSPECT", "document_id": "missing"}), DOCS)
