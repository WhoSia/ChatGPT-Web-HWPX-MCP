"""P4.25 native formatting and Markdown interchange MCP contract tests.

No Hancom/Windows or deleted local validation artifact. The actual
native formatting and document readers are mocked at their interface.
"""
from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hwpx_mcp.interfaces.p425_format_interchange import (
    register_format_interchange_tools, document_to_markdown,
    tables_to_markdown,
)

DOC = "doc_" + "z" * 24
OWNER = "synthetic-format-owner"
RAW = b"PK" + b"synthetic-hwpx" * 20
REVISED = b"PK" + b"synthetic-formatted-hwpx" * 20


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class FakeStore:
    def __init__(self):
        self.owner = OWNER
        self.revision = 2
        self.writes = []

    def load_current(self, document_id):
        assert document_id == DOC
        return {
            "document_id": DOC, "owner_subject": self.owner,
            "revision": self.revision, "sha256": hashlib.sha256(RAW).hexdigest(),
            "bytes": RAW, "expires_at_epoch": 1900000000,
            "metadata": {"filename": "report.hwpx", "owner_subject": OWNER},
        }

    def put_revision(self, **kwargs):
        self.writes.append(kwargs)
        return {"ok": True}


class FormattingInterchangeTests(unittest.TestCase):
    def setUp(self):
        self.mcp = FakeMCP()
        self.store = FakeStore()
        self.core = SimpleNamespace(
            mcp=self.mcp, DOCUMENT_STORE=self.store,
            _caller_subject=lambda: OWNER,
            _paths=lambda doc_id: (None, None) if doc_id == DOC else None,
            validate_hwpx_package=lambda path, **kwargs: {"valid": True},
        )
        register_format_interchange_tools(self.core)

    def test_four_real_tools_registered(self):
        self.assertEqual(set(self.mcp.tools), {
            "inspect_document_formatting",
            "format_document_and_deliver",
            "export_document_markdown", "preview_document_formatting",
        })

    def test_formatting_reader_returns_native_locator_and_runs(self):
        fmt = {
            "formatting_sha256": "b" * 64,
            "property_counts": {"char": 2, "para": 1, "style": 1},
            "paragraphs": [
                {"locator": "p0", "container": "section-body",
                 "section_index": 0, "paragraph_index": 0,
                 "paragraph_property": {"align": "CENTER"},
                 "style_property": {"name": "본문"},
                 "runs": [{"run_index": 0, "text": "연구"}]},
            ],
        }
        with patch("hwpx_mcp.document.p22_formatting.build_formatting_map",
                   return_value=fmt):
            got = self.mcp.tools["inspect_document_formatting"](DOC)
        self.assertEqual(got["paragraphs"][0]["locator"], "p0")
        self.assertEqual(got["paragraphs"][0]["runs"][0]["text"], "연구")
        self.assertEqual(got["property_counts"]["char"], 2)

    def test_formatting_preview_uses_native_operation_normalizer(self):
        native_map = {
            "formatting_sha256": "d" * 64,
            "paragraphs": [{"locator": "p0", "runs": [
                {"run_index": 0, "text": "실험"}]}],
        }
        normalized = [{"op": "set_run_format", "target": "p0",
                       "run_indexes": [0], "format": {"bold": True}}]
        with patch("hwpx_mcp.document.p22_formatting.build_formatting_map",
                   return_value=native_map), patch(
            "hwpx_mcp.document.p22_formatting._normalize_formatting_operations",
            return_value=normalized,
        ) as norm:
            result = self.mcp.tools["preview_document_formatting"](
                DOC, [{"op": "set_run_format", "target": "p0",
                       "format": {"bold": True}}],
            )
        norm.assert_called_once()
        self.assertFalse(result["committed"])
        self.assertEqual(result["operation_count"], 1)
        self.assertEqual(result["targets"][0]["target"], "p0")
        self.assertEqual(self.store.writes, [])

    def test_formatting_edit_commits_one_revision_and_delivers_attachment(self):
        def fake_edit(path, operations, **kwargs):
            self.assertEqual(path.read_bytes(), RAW)
            self.assertEqual(operations[0]["op"], "set_run_format")
            path.write_bytes(REVISED)
            return {
                "formatting_changed": True, "semantic_changed": False,
                "operation_count": 1,
                "after": {"formatting_sha256": "c" * 64},
            }

        delivery = {
            "filename": "report.hwpx", "bytes": len(REVISED),
            "download_url": "https://example.test/report.hwpx",
            "download_expires_at": "2026-11-10T23:59:00Z",
            "sha256": hashlib.sha256(REVISED).hexdigest(),
            "mime_type": "application/hwp+zip",
            "revision": 3, "delivery_status": "READY_FOR_DOWNLOAD",
        }
        with patch("hwpx_mcp.document.p22_formatting.apply_formatting_atomic",
                   side_effect=fake_edit), patch(
            "hwpx_mcp.delivery.p333_file_delivery.export_revision",
            return_value=delivery,
        ):
            result = self.mcp.tools["format_document_and_deliver"](
                DOC, expected_revision=2,
                operations=[{"op": "set_run_format", "target": "p0",
                             "format": {"font": "함초롬바탕", "bold": True}}],
            )
        self.assertTrue(result.structuredContent["formatting_changed"])
        self.assertFalse(result.structuredContent["text_changed"])
        self.assertEqual(result.content[1].type, "resource_link")
        self.assertEqual(self.store.writes[0]["expected_revision"], 2)
        self.assertEqual(self.store.writes[0]["data"], REVISED)

    def test_cas_conflict_refuses_edit_without_mutation(self):
        with self.assertRaisesRegex(RuntimeError, "REVISION_CONFLICT"):
            self.mcp.tools["format_document_and_deliver"](
                DOC, expected_revision=1,
                operations=[{"op": "set_run_format", "target": "p0",
                             "format": {"bold": True}}],
            )
        self.assertEqual(self.store.writes, [])

    def test_cross_owner_denied_before_formatting_read(self):
        self.store.owner = "another-owner"
        with self.assertRaises(FileNotFoundError):
            self.mcp.tools["inspect_document_formatting"](DOC)
        self.assertEqual(self.store.writes, [])

    def test_markdown_export_and_limit_are_explicit(self):
        paragraphs = {
            "sections": [{"section_index": 0}],
            "semantic_sha256": "a" * 64,
            "paragraphs": [
                {"section_index": 0, "paragraph_index": 0,
                 "container": "section-body", "text": "# 본문"},
                {"section_index": 0, "paragraph_index": 1,
                 "container": "tc", "text": "표 셀"},
            ],
        }
        with patch("hwpx_mcp.document.p2_document.build_document_map",
                   return_value=paragraphs), patch(
            "hwpx_mcp.document.p27_tables.build_table_map",
            return_value={"tables": []},
        ):
            got = self.mcp.tools["export_document_markdown"](DOC, max_chars=14)
        self.assertTrue(got["truncated"])
        self.assertIn("\\# 본문", got["markdown"])
        self.assertEqual(got["representation"],
                         "TEXT_SEMANTIC_NOT_NATIVE_PAGINATION")

    def test_empty_or_overlong_limits_rejected(self):
        for args in ({"max_chars": 0}, {"max_chars": 300000}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.mcp.tools["export_document_markdown"](DOC, **args)
        for args in ({"offset": -1}, {"limit": 0}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.mcp.tools["inspect_document_formatting"](DOC, **args)


class MarkdownSemanticsTests(unittest.TestCase):
    def test_literal_heading_is_escaped(self):
        doc = {"sections": [{}], "paragraphs": [
            {"section_index": 0, "paragraph_index": 0,
             "container": "section-body", "text": "# literal heading"},
        ]}
        result = document_to_markdown(doc)
        self.assertTrue(result["markdown"].startswith("\\#"))

    def test_native_table_grid_preserves_rows_columns_and_escapes_pipes(self):
        source = {"tables": [{
            "rows": 2, "cols": 2,
            "cells": [
                {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "변수"},
                {"row": 0, "col": 1, "row_span": 1, "col_span": 1, "text": "값"},
                {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "a|b"},
                {"row": 1, "col": 1, "row_span": 1, "col_span": 1, "text": "42"},
            ],
        }]}
        table = tables_to_markdown(source)
        self.assertIn(r"a\|b", table["markdown"])
        self.assertIn("| 열 1 | 열 2 |", table["markdown"])
        self.assertEqual(table["table_count"], 1)
        self.assertEqual(table["merged_cell_warnings"], [])

    def test_merged_cell_explicitly_reports_markdown_limitation(self):
        source = {"tables": [{
            "rows": 2, "cols": 2,
            "cells": [{"row": 0, "col": 0, "row_span": 2,
                       "col_span": 2, "text": "병합 영역"}],
        }]}
        table = tables_to_markdown(source)
        self.assertEqual(table["merged_cell_warnings"][0]["row_span"], 2)
        self.assertEqual(table["merged_cell_warnings"][0]["col_span"], 2)

    def test_nested_cell_annotation_makes_fidelity_limit_clear(self):
        doc = {"sections": [{}], "paragraphs": [
            {"section_index": 0, "paragraph_index": 0,
             "container": "tc", "text": "값"},
        ]}
        result = document_to_markdown(doc)
        self.assertIn("nested tc", result["markdown"])
        self.assertFalse(result["nontext_objects_included"])
        self.assertEqual(document_to_markdown(doc, include_table_cells=False)["markdown"], "")


if __name__ == "__main__":
    unittest.main()
