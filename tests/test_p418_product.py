from __future__ import annotations

import pytest

from mcp.types import CallToolResult, TextContent

from hwpx_mcp.interfaces.p418_mcp import _augment

from p418_product import (
    PRODUCT,
    document_agent_contract,
    normalize_document_task,
    prepare_document_task,
)


def test_contract_exposes_one_primary_product_surface():
    contract = document_agent_contract()
    assert contract["product"] == PRODUCT
    assert contract["product_goal"] == "ONE_PRIMARY_TASK_SURFACE_OVER_VERIFIED_EXISTING_HWPX_CAPABILITIES"
    assert contract["task_kinds"] == ["CREATE", "DELIVER", "EDIT_INTENT", "INSPECT", "TEMPLATE_FILL"]
    assert contract["safety"]["native_visual_pass_from_caller_metadata"] is False


def test_create_task_normalizes_defaults_deterministically():
    task = {"kind": "create", "plan": {"blocks": [{"type": "title", "text": "문서"}]}}
    a = normalize_document_task(task)
    b = normalize_document_task(task)
    assert a == b
    assert a["kind"] == "CREATE"
    assert a["filename"] == "document.hwpx"
    assert a["design_mode"] == "AUTO"
    assert len(a["task_sha256"]) == 64


def test_edit_intent_requires_revision_and_preserves_reference_payload():
    task = normalize_document_task(
        {
            "kind": "EDIT_INTENT",
            "document_id": "doc-1",
            "expected_revision": 4,
            "intent": {
                "actions": [
                    {"action": "replace_role_text", "role": "TITLE", "text": "새 제목"}
                ]
            },
            "reference_document_id": "reference-1",
            "reference_transfer": {"template": {"template_id": "x"}},
        }
    )
    assert task["expected_revision"] == 4
    assert task["reference_document_id"] == "reference-1"
    assert task["reference_transfer"]["template"]["template_id"] == "x"


def test_delivery_recovery_is_non_mutating_route():
    prepared = prepare_document_task(
        {"kind": "DELIVER", "document_id": "doc-1", "revision": 3}
    )
    assert prepared["mutation_expected"] is False
    assert prepared["native_handoff_expected"] is True
    assert prepared["route"] == "REVISION_BOUND_DELIVERY_ONLY_NO_MUTATION_REPLAY"


def test_inspect_views_are_bounded():
    task = normalize_document_task(
        {
            "kind": "INSPECT",
            "document_id": "doc-1",
            "views": ["summary", "semantic_graph", "document_map"],
        }
    )
    assert task["views"] == ["SUMMARY", "SEMANTIC_GRAPH", "DOCUMENT_MAP"]
    with pytest.raises(ValueError, match="unsupported inspect views"):
        normalize_document_task(
            {"kind": "INSPECT", "document_id": "doc-1", "views": ["RAW_DATABASE"]}
        )


@pytest.mark.parametrize(
    "task",
    [
        {},
        {"kind": "CREATE"},
        {"kind": "EDIT_INTENT", "document_id": "doc-1", "intent": {"actions": []}},
        {"kind": "TEMPLATE_FILL", "template_document_id": "doc-1"},
        {"kind": "DELIVER"},
        {"kind": "UNKNOWN"},
    ],
)
def test_invalid_tasks_fail_closed(task):
    with pytest.raises(ValueError):
        normalize_document_task(task)


def test_link_ttl_is_bounded():
    with pytest.raises(ValueError, match="link_ttl_seconds"):
        normalize_document_task(
            {"kind": "DELIVER", "document_id": "doc-1", "link_ttl_seconds": 30}
        )
    with pytest.raises(ValueError, match="link_ttl_seconds"):
        normalize_document_task(
            {"kind": "DELIVER", "document_id": "doc-1", "link_ttl_seconds": 7200}
        )



def test_product_facade_preserves_call_tool_structured_delivery_payload():
    original = {
        "ok": True,
        "document_id": "doc-1",
        "revision": 1,
        "delivery_status": "READY_FOR_DOWNLOAD",
        "download_url": "https://example.invalid/document.hwpx",
    }
    result = CallToolResult(
        content=[TextContent(type="text", text="delivery")],
        structuredContent=original,
        isError=False,
    )
    augmented = _augment(
        result,
        {
            "phase": "P4.18",
            "product": PRODUCT,
            "p418_task_kind": "CREATE",
            "p418_route": "P3.37_CREATE_VALIDATE_DELIVER",
        },
    )
    payload = augmented.model_dump(by_alias=True)["structuredContent"]
    assert payload["document_id"] == "doc-1"
    assert payload["delivery_status"] == "READY_FOR_DOWNLOAD"
    assert payload["download_url"].endswith(".hwpx")
    assert payload["p418_task_kind"] == "CREATE"
