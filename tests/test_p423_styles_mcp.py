"""P4.23 authenticated reference-style MCP contract tests."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx_mcp.interfaces.p423_styles_mcp import register_p423_style_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, **kwargs):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


class FakeCore:
    def __init__(self):
        self.mcp = FakeMCP()
        self.subjects = 0

    def _caller_subject(self):
        self.subjects += 1
        return "owner"


class P423StylesMCPTests(unittest.TestCase):
    def setUp(self):
        self.core = FakeCore()
        self.owned_calls = []
        def owned(document_id):
            self.owned_calls.append(document_id)
            return {"revision": 3, "sha256": "abc"}, Path("/private/owned.hwpx")
        register_p423_style_tools(self.core, owned_document=owned)
        self.tool = self.core.mcp.tools["get_p423_reference_style_candidate"]

    @patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference")
    def test_candidate_is_read_only_and_requires_approval(self, read):
        read.return_value = {
            "style_profile": {"name": "example", "roles": {}},
            "warnings": [],
            "status": "CANDIDATE_REQUIRES_USER_APPROVAL",
        }
        result = self.tool("doc_1", "example", expected_revision=3)
        self.assertTrue(result["ok"])
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["stored_preference"])
        self.assertFalse(result["document_modified"])
        self.assertEqual(self.owned_calls, ["doc_1"])
        self.assertEqual(self.core.subjects, 1)
        read.assert_called_once_with(Path("/private/owned.hwpx"), name="example")

    def test_reference_revision_mismatch_fails_before_extraction(self):
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                self.tool("doc_1", expected_revision=2)
            read.assert_not_called()

    def test_reference_rejects_noninteger_revision(self):
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                self.tool("doc_1", expected_revision=True)
            read.assert_not_called()

    def test_reference_rejects_missing_document_id(self):
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            with self.assertRaisesRegex(ValueError, "document_id"):
                self.tool("  ")
            read.assert_not_called()
            self.assertEqual(self.owned_calls, [])

    def test_reference_owner_error_blocks_extraction(self):
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            def deny(document_id):
                raise PermissionError("not your document")
            guarded = FakeCore()
            register_p423_style_tools(guarded, owned_document=deny)
            with self.assertRaises(PermissionError):
                guarded.mcp.tools["get_p423_reference_style_candidate"]("doc_foreign")
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
