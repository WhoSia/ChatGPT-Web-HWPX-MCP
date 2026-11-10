"""P4.25 actual MCP workflow integration with owned durable revisions.

Synthetic byte contracts and isolated fakes, no deleted local artifacts,
Windows installation or a live Postgres database.
"""
from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hwpx_mcp.interfaces.p425_competitive_workflows import register_competitive_workflows

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

    def test_three_working_tools_registered(self):
        self.assertEqual(set(self.mcp.tools), {
            "read_document_structure", "preview_template_fill",
            "fill_template_and_deliver",
        })

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
                          "delivery_status": "READY_FOR_DOWNLOAD"},
        ):
            result = self.mcp.tools["fill_template_and_deliver"](
                DOCUMENT_ID, {"{{NAME}}": "홍길동"}, expected_revision=2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["revision"], 3)
        self.assertEqual(self.store.writes[0]["expected_revision"], 2)
        self.assertEqual(self.store.writes[0]["data"], UPDATED)
        self.assertEqual(result["download_url"], "https://example.test/signed.hwpx")

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


if __name__ == "__main__":
    unittest.main()
