"""P4.25 actual MCP workflow integration with owned durable revisions.

Synthetic byte contracts and isolated fakes, no deleted local artifacts,
Windows installation or a live Postgres database.
"""
from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hwpx_mcp.interfaces.p425_competitive_workflows import register_competitive_workflows, markdown_to_rich_plan

SOURCE = b"PK" + b"synthetic-hwpx" * 10
UPDATED = b"PK" + b"synthetic-filled-hwpx" * 10
OWNER = "synthetic-owner"
DOCUMENT_ID = "doc_" + "a" * 24


class FakeMcp:
    def __init__(self):
        self.tools = {}
    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class FakeStore:
    def __init__(self):
        self.row = {
            "document_id": DOCUMENT_ID, "owner_subject": OWNER,
            "revision": 2, "sha256": hashlib.sha256(SOURCE).hexdigest(),
            "bytes": SOURCE, "expires_at_epoch": 1900000000,
        }
        self.writes = []
    def load_current(self, _document_id):
        return self.row
    def put_revision(self, **kwargs):
        self.writes.append(kwargs)
        if kwargs["expected_revision"] != self.row["revision"]:
            raise RuntimeError("CAS_CONFLICT")
        self.row = {**self.row, "revision": kwargs["revision"],
                    "sha256": hashlib.sha256(kwargs["data"]).hexdigest(),
                    "bytes": kwargs["data"]}
        return {"receipt_id": "synthetic-commit"}


class CompetitorPatternToolsTests(unittest.TestCase):
    def setUp(self):
        self.mcp = FakeMcp()
        self.store = FakeStore()
        self.core = SimpleNamespace(
            mcp=self.mcp, DOCUMENT_STORE=self.store,
            _caller_subject=lambda: OWNER,
            _load_metadata=lambda _doc: {
                "document_id": DOCUMENT_ID, "owner_subject": OWNER,
                "revision": self.store.row["revision"],
                "sha256": self.store.row["sha256"],
            },
            validate_hwpx_package=lambda path, **kwargs: {
                "valid": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
        register_competitive_workflows(self.core)

    def test_native_rich_authoring_callback_reused_by_report_presets(self):
        self.assertTrue(callable(self.core._p425_create_rich_document_and_deliver))
        self.assertIs(
            self.core._p425_create_rich_document_and_deliver,
            self.mcp.tools["create_rich_document_and_deliver"],
        )

    def test_eleven_working_tools_registered(self):
        self.assertEqual(set(self.mcp.tools), {
            "read_document_structure", "preview_template_fill",
            "fill_template_and_deliver", "find_document_text",
            "replace_text_and_deliver", "create_and_deliver_document",
            "create_rich_document_and_deliver",
            "list_document_tables", "edit_table_and_deliver",
            "discover_hwpx_workflows", "create_from_markdown_and_deliver",
        })

    def test_discovery_recommends_table_edit_in_korean(self):
        result = self.mcp.tools["discover_hwpx_workflows"]("표 셀 수정", limit=3)
        self.assertTrue(result["ok"])
        self.assertIn("edit_table_and_deliver",
                      [item["tool"] for item in result["matching_workflows"]])
        self.assertFalse(result["executes_mutations"])

    def test_discovery_recommends_one_call_report_authoring(self):
        result = self.mcp.tools["discover_hwpx_workflows"]("rich report", limit=3)
        self.assertEqual(result["matching_workflows"][0]["tool"],
                         "create_rich_document_and_deliver")

    def test_discovery_invalid_limit_does_not_execute_any_edit(self):
        with self.assertRaisesRegex(ValueError, "LIMIT"):
            self.mcp.tools["discover_hwpx_workflows"]("table", limit=100)
        self.assertEqual(self.store.writes, [])

    def test_create_and_deliver_one_call(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "document_id": DOCUMENT_ID,
                    "idempotent_replay": False}
        self.core.create_document = create
        exported = {
            "revision": 1, "sha256": "a" * 64,
            "filename": "new.hwpx", "mime_type": "application/hwp+zip",
            "download_url": "https://example.test/new.hwpx",
            "delivery_status": "READY_FOR_DOWNLOAD",
            "download_expires_at": "2026-11-10T23:59:00Z", "bytes": 256,
        }
        with patch("hwpx_mcp.delivery.p333_file_delivery.export_revision",
                   return_value=exported):
            result = self.mcp.tools["create_and_deliver_document"](
                "새 한글 문서입니다.", title="제목",
                filename="new.hwpx", request_id="test-replay-key")
        self.assertEqual(result.structured_content["download_url"], exported["download_url"])
        self.assertEqual(calls[0]["request_id"], "test-replay-key")
        self.assertFalse(result.structured_content["native_pdf_created"])

    def test_rich_composer_commits_document_and_returns_resource_link(self):
        self.core._new_document_id = lambda: DOCUMENT_ID
        self.core.sanitize_filename = lambda filename: filename
        self.core._paths = lambda document_id: (self._rich_output, self._rich_meta)
        self.core._metadata = lambda document_id, **kwargs: {
            "document_id": document_id, "owner_subject": OWNER,
            "revision": 1, "expires_at_epoch": 1900000000,
            "filename": kwargs["filename"],
        }
        writes = []
        self.core._write_metadata = lambda doc, meta: writes.append((doc, meta)) or {"receipt_id": "rich"}
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            self._rich_output = Path(temp) / "new.hwpx"
            self._rich_meta = Path(temp) / "new.json"
            self.core.validate_hwpx_package = lambda path, **kwargs: {
                "valid": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": len(path.read_bytes()),
            }
            def compose(path, plan, **kwargs):
                path.write_bytes(UPDATED)
                return {"block_count": 2}
            with patch("hwpx_mcp.orchestration.p338_rich_builder.compile_rich_document_plan",
                       return_value={"plan": {"blocks": []}, "plan_sha256": "f" * 64,
                                     "block_count": 2, "section_count": 1}), patch(
                "hwpx_mcp.document.p321_document_composer.compose_document_plan",
                side_effect=compose), patch(
                "hwpx_mcp.delivery.p333_file_delivery.export_revision",
                return_value={"filename": "report.hwpx", "download_url": "https://example.test/rich",
                              "download_expires_at": "2026-11-10T23:59:00Z",
                              "bytes": len(UPDATED), "mime_type": "application/hwp+zip",
                              "sha256": hashlib.sha256(UPDATED).hexdigest(),
                              "revision": 1, "delivery_status": "READY_FOR_DOWNLOAD",
                          "download_expires_at": "2026-11-10T23:59:00Z", "bytes": 256},
            ):
                result = self.mcp.tools["create_rich_document_and_deliver"](
                    {"sections": [{"blocks": [{"type": "heading", "text": "연구"}]}]},
                    "report.hwpx")
            self.assertEqual(self._rich_output.read_bytes(), UPDATED)
            self.assertEqual(len(writes), 1)
            self.assertEqual(result.structured_content["rich_block_count"], 2)
            self.assertEqual(result.content[1].type, "resource_link")

    def test_create_and_deliver_rejects_empty_body(self):
        with self.assertRaisesRegex(ValueError, "DOCUMENT_TEXT_REQUIRED"):
            self.mcp.tools["create_and_deliver_document"]("  ")

    def test_preview_returns_matches_without_writing(self):
        example = {"operation_count": 2, "matches": {"{{NAME}}": 2},
                   "plan_sha256": "f" * 64}
        with patch("hwpx_mcp.interfaces.p425_competitive_workflows.plan_literal_placeholder_fill", return_value=example):
            result = self.mcp.tools["preview_template_fill"](
                DOCUMENT_ID, {"{{NAME}}": "홍길동"})
        self.assertEqual(result["matches"]["{{NAME}}"], 2)
        self.assertFalse(result["committed"])
        self.assertEqual(len(self.store.writes), 0)

    def test_filled_template_commits_revision_and_delivers_link(self):
        def fake_fill(source, output, values, **kwargs):
            self.assertEqual(source.read_bytes(), SOURCE)
            output.write_bytes(UPDATED)
            return {"fill_sha256": "e" * 64, "operation_count": 1,
                    "matches": {"{{NAME}}": 1}}
        with patch("hwpx_mcp.interfaces.p425_competitive_workflows.fill_template_atomic", side_effect=fake_fill), patch(
            "hwpx_mcp.delivery.p333_file_delivery.export_revision",
            return_value={"download_url": "https://example.test/signed.hwpx",
                          "filename": "filled.hwpx", "mime_type": "application/hwp+zip",
                          "delivery_status": "READY_FOR_DOWNLOAD",
                          "download_expires_at": "2026-11-10T23:59:00Z", "bytes": 256},
        ):
            result = self.mcp.tools["fill_template_and_deliver"](
                DOCUMENT_ID, {"{{NAME}}": "홍길동"}, expected_revision=2)
        self.assertTrue(result.structured_content["ok"])
        self.assertEqual(result.structured_content["revision"], 3)
        self.assertEqual(self.store.writes[0]["expected_revision"], 2)
        self.assertEqual(self.store.writes[0]["data"], UPDATED)
        self.assertEqual(result.structured_content["download_url"], "https://example.test/signed.hwpx")

    def test_batch_replace_reuses_template_edit_commit(self):
        def fake_fill(source, output, values, **kwargs):
            self.assertEqual(values, {"old": "new", "{{DATE}}": "2026-11-10"})
            output.write_bytes(UPDATED)
            return {"fill_sha256": "e" * 64, "operation_count": 2,
                    "matches": {"old": 1, "{{DATE}}": 1}}
        with patch("hwpx_mcp.interfaces.p425_competitive_workflows.fill_template_atomic", side_effect=fake_fill), patch(
            "hwpx_mcp.delivery.p333_file_delivery.export_revision",
            return_value={"download_url": "https://example.test/doc.hwpx",
                          "filename": "doc.hwpx", "mime_type": "application/hwp+zip",
                          "delivery_status": "READY_FOR_DOWNLOAD",
                          "download_expires_at": "2026-11-10T23:59:00Z", "bytes": 256},
        ):
            result = self.mcp.tools["replace_text_and_deliver"](
                DOCUMENT_ID, {"old": "new", "{{DATE}}": "2026-11-10"},
                expected_revision=2)
        self.assertEqual(result.structured_content["revision"], 3)
        self.assertEqual(result.structured_content["operation_count"], 2)

    def test_find_text_in_body_and_table(self):
        sample = {"paragraphs": [
            {"locator": "p_body", "section_index": 0, "paragraph_index": 0,
             "container": "section-body", "text": "자연어 검색"},
            {"locator": "p_cell", "section_index": 0, "paragraph_index": 1,
             "container": "tc", "text": "표 안에서도 검색"},
        ]}
        with patch("hwpx_mcp.document.p2_document.build_document_map", return_value=sample):
            result = self.mcp.tools["find_document_text"](
                DOCUMENT_ID, "검색")
        self.assertEqual(result["total_matches"], 2)
        self.assertEqual(result["matches"][1]["container"], "tc")

    def test_list_tables_returns_cell_grid(self):
        fixture = {"tables": [
            {"locator": "t_1", "table_index": 0, "rows": 2, "cols": 2,
             "caption_text": "측정표",
             "cells": [
                 {"locator": "c_1", "row": 0, "col": 0,
                  "row_span": 1, "col_span": 1, "text": "실험"},
             ]},
        ]}
        with patch("hwpx_mcp.document.p27_tables.build_table_map", return_value=fixture):
            result = self.mcp.tools["list_document_tables"](DOCUMENT_ID)
        self.assertEqual(result["table_count"], 1)
        self.assertEqual(result["tables"][0]["cells"][0]["text"], "실험")

    def test_table_edit_commits_one_revision_with_file_attachment(self):
        def edit(path, operations, **kwargs):
            self.assertEqual(operations[0]["op"], "set_cell_text")
            path.write_bytes(UPDATED)
            return {"operation_count": 1, "table_structure_changed": False,
                    "table_format_changed": False}
        with patch("hwpx_mcp.document.p27_tables.apply_table_edits_atomic", side_effect=edit), patch(
            "hwpx_mcp.delivery.p333_file_delivery.export_revision",
            return_value={"filename": "table.hwpx",
                          "download_url": "https://example.test/table.hwpx",
                          "download_expires_at": "2026-11-10T23:59:00Z",
                          "bytes": len(UPDATED), "mime_type": "application/hwp+zip",
                          "sha256": hashlib.sha256(UPDATED).hexdigest(),
                          "revision": 3, "delivery_status": "READY_FOR_DOWNLOAD",
                          "download_expires_at": "2026-11-10T23:59:00Z", "bytes": 256},
        ):
            result = self.mcp.tools["edit_table_and_deliver"](
                DOCUMENT_ID, expected_revision=2,
                operations=[{"op": "set_cell_text", "table": "t_1",
                             "cell": "c_1", "text": "결과"}])
        self.assertEqual(result.structured_content["revision"], 3)
        self.assertEqual(result.structured_content["operation_count"], 1)
        self.assertEqual(self.store.writes[0]["expected_revision"], 2)
        self.assertEqual(result.content[1].type, "resource_link")

    def test_stale_revision_refused_before_edit(self):
        with self.assertRaisesRegex(RuntimeError, "REVISION_CONFLICT"):
            self.mcp.tools["fill_template_and_deliver"](
                DOCUMENT_ID, {"{{NAME}}": "홍길동"}, expected_revision=1)
        self.assertEqual(self.store.writes, [])

    def test_unowned_document_refused_before_edit(self):
        self.store.row["owner_subject"] = "different-owner"
        with self.assertRaises(PermissionError):
            self.mcp.tools["preview_template_fill"](
                DOCUMENT_ID, {"{{NAME}}": "홍길동"})

    def test_structure_reader_returns_bounded_paragraphs(self):
        example = {
            "sections": [{"section": "Contents/section0.xml", "paragraph_count": 2}],
            "paragraph_count": 2,
            "paragraphs": [
                {"locator": "p_1", "section_index": 0, "paragraph_index": 0,
                 "container": "section-body", "text_sha256": "a" * 64, "text": "본문"},
                {"locator": "p_2", "section_index": 0, "paragraph_index": 1,
                 "container": "tc", "text_sha256": "b" * 64, "text": "표 셀"},
            ],
            "semantic_sha256": "c" * 64,
        }
        with patch("hwpx_mcp.document.p2_document.build_document_map", return_value=example):
            result = self.mcp.tools["read_document_structure"](
                DOCUMENT_ID, offset=1, limit=1)
        self.assertEqual(result["paragraphs"][0]["text"], "표 셀")
        self.assertIsNone(result["next_offset"])
        self.assertEqual(result["pagination"], "PARAGRAPH_OFFSET_NOT_NATIVE_PAGE_NUMBER")

    def test_read_structure_can_omit_text(self):
        example = {
            "sections": [], "paragraph_count": 1,
            "paragraphs": [{"locator": "p_1", "section_index": 0,
                            "paragraph_index": 0, "container": "section-body",
                            "text_sha256": "a" * 64, "text": "SECRET"}],
            "semantic_sha256": "c" * 64,
        }
        with patch("hwpx_mcp.document.p2_document.build_document_map", return_value=example):
            result = self.mcp.tools["read_document_structure"](
                DOCUMENT_ID, include_text=False)
        self.assertNotIn("text", result["paragraphs"][0])

    def test_read_bounds(self):
        for args in ({"offset": -1}, {"limit": 0}, {"limit": 1000}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.mcp.tools["read_document_structure"](DOCUMENT_ID, **args)


class MarkdownToNativePlanTests(unittest.TestCase):
    def test_headings_lists_and_tables_compile_to_native_blocks(self):
        sample = "# 연구 보고서\n\n연구 목적\n\n- 가설\n1. 측정\n\n| 변수 | 값 |\n| --- | --- |\n| 온도 | 27 |"
        plan = markdown_to_rich_plan(sample)
        blocks = plan["sections"][0]["blocks"]
        self.assertEqual([b["type"] for b in blocks],
                         ["heading", "paragraph", "list_item", "list_item", "table"])
        self.assertEqual(blocks[0]["level"], 1)
        self.assertEqual(blocks[-1]["cells"][1], ["온도", "27"])

    def test_escaped_pipe_is_not_a_table_column_break(self):
        sample = "| 명칭 | 값 |\n| --- | --- |\n| a\\|b | 42 |"
        blocks = markdown_to_rich_plan(sample)["sections"][0]["blocks"]
        self.assertEqual(blocks[0]["cols"], 2)
        self.assertEqual(blocks[0]["cells"][1][0], "a|b")

    def test_table_width_mismatch_fails_before_any_doc_creation(self):
        sample = "| A | B |\n| --- | --- |\n| only-one |"
        with self.assertRaisesRegex(ValueError, "ROW_WIDTH_MISMATCH"):
            markdown_to_rich_plan(sample)

    def test_empty_markdown_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "TEXT_REQUIRED"):
            markdown_to_rich_plan("   ")


if __name__ == "__main__":
    unittest.main()
