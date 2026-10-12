"""P4.21 in-process live server API integration: create, preview, format, compare."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import server as core
import server_p2 as api
from tests.test_p337_product_workflow import MemoryRevisions


def test_public_create_preview_approved_format_change_and_quality_delta():
    with tempfile.TemporaryDirectory() as tmp:
        storage = MemoryRevisions()
        with (patch.object(core, "OBJECT_DIR", Path(tmp)),
              patch.object(core, "DOCUMENT_STORE", storage),
              patch.object(core, "DOWNLOAD_SECRET", "p421-ci-only"),
              patch.object(core, "_caller_subject", return_value="p421-ci")):
            create = api.create_and_deliver_document(
                {"preset": "academic-report", "blocks": [
                    {"id": "title", "type": "title", "text": "서식 품질 연구"},
                    {"id": "intro", "type": "heading", "level": 1, "text": "관측 결과"},
                    {"id": "body", "type": "paragraph", "text": "명시적 수정을 검증한다."},
                ]}, filename="p421-qa.hwpx", request_id="p421-ci-create",
                design_mode="",
            ).structured_content
            assert create["delivery_status"] == "READY_FOR_DOWNLOAD"
            authoring = create["product_context"]["authoring"]
            assert authoring["professional_plan_review"]["mutated_plan"] is False
            assert authoring["quality_after_creation"]["status"] == "PASS_STRUCTURE_HOLD_RELEASE"
            doc_id = create["document_id"]
            preview = api.preview_professional_formatting(doc_id)
            assert preview["revision"] == 1
            assert preview["automatic_repairs_applied"] is False
            assert preview["quality_before"]["document_sha256"] == create["sha256"]
            source = api.get_document_map(doc_id)
            heading = next(x for x in source["paragraphs"] if x["text"] == "관측 결과")
            operation = {"op": "set_paragraph_format",
                         "target": heading["locator"],
                         "format": {"alignment": "CENTER"}}
            applied = api.apply_formatting(doc_id, 1, [operation])
            assert applied["revision_after"] == 2
            assert applied["explicit_user_operations"] == 1
            assert applied["semantic_changed"] is False
            assert applied["structure_changed"] is False
            assert applied["quality_comparison"]["count_delta"]["paragraphs"] == 0
            assert applied["quality_comparison"]["before"]["counts"] == applied["quality_comparison"]["after"]["counts"]
            assert api.get_document_map(doc_id)["revision"] == 2
            assert api.get_document_map(doc_id)["semantic_sha256"] == source["semantic_sha256"]
            assert api.get_document_map(doc_id)["structure_sha256"] == source["structure_sha256"]
            try:
                api.apply_formatting(doc_id, 1, [operation])
            except ValueError as exc:
                assert "Stale revision" in str(exc)
            else:
                raise AssertionError("stale revision must fail")
            assert api.get_document_map(doc_id)["revision"] == 2


def test_product_edit_returns_quality_after_actual_text_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        storage = MemoryRevisions()
        with (patch.object(core, "OBJECT_DIR", Path(tmp)),
              patch.object(core, "DOCUMENT_STORE", storage),
              patch.object(core, "DOWNLOAD_SECRET", "p421-ci-only"),
              patch.object(core, "_caller_subject", return_value="p421-ci")):
            created = api.create_and_deliver_document(
                {"preset": "academic-report", "blocks": [
                    {"type": "title", "text": "변경 검사"},
                    {"type": "paragraph", "text": "이전 문장"},
                ]}, filename="p421-edit.hwpx", request_id="p421-ci-edit",
                design_mode="",
            ).structured_content
            doc_id = created["document_id"]
            before = api.get_document_map(doc_id)
            target = next(x["locator"] for x in before["paragraphs"] if x["text"] == "이전 문장")
            edited = api.edit_and_deliver_document(
                doc_id, 1, [{"op": "replace_paragraph_text", "target": target,
                             "text": "수정한 문장"}]
            ).structured_content
            assert edited["delivery_status"] == "READY_FOR_DOWNLOAD"
            diff = edited["product_context"]["quality_comparison"]
            assert diff["before"]["counts"] == diff["after"]["counts"]
            assert diff["before"]["document_sha256"] != diff["after"]["document_sha256"]
            assert diff["semantic_preservation"] == "NOT_CERTIFIED_FOR_USER_AUTHORED_EDITS"
            assert api.get_document_map(doc_id)["revision"] == 2
            assert "수정한 문장" in api.get_document_map(doc_id)["paragraphs"][-1]["text"]
