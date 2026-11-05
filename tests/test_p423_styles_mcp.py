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

    def approved_tool(self, create_adapter):
        core = FakeCore()
        def owned(document_id):
            return {"revision": 3, "sha256": "src-hash"}, Path("/private/owned.hwpx")
        register_p423_style_tools(core, owned_document=owned, create_adapter=create_adapter)
        return core.mcp.tools["create_p423_document_with_approved_reference_style"]

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

    def test_reference_preview_does_not_write_profile(self):
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            read.return_value = {"style_profile": {"name": "a"}, "warnings": ["unsupported"]}
            receipt = self.tool("doc_1")
            self.assertEqual(receipt["reference_revision"], 3)
            self.assertEqual(receipt["reference_sha256"], "abc")
            self.assertEqual(receipt["candidate"]["warnings"], ["unsupported"])
            self.assertIn("create_document_from_plan", receipt["next_step"])

    def test_reference_extractor_failure_does_not_fake_candidate(self):
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            read.side_effect = ValueError("reference has no portable supported style roles")
            with self.assertRaisesRegex(ValueError, "no portable"):
                self.tool("doc_1", expected_revision=3)

    def test_approved_style_creates_using_existing_atomic_adapter(self):
        created = []
        def create(plan, **kwargs):
            created.append((plan, kwargs))
            return {"ok": True, "document_id": "new_doc"}
        tool = self.approved_tool(create)
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            read.return_value = {"style_profile": {"name": "lab"}, "style_profile_sha256": "a" * 64, "warnings": []}
            receipt = tool("reference_doc", 3, "a" * 64, {"blocks": [{"type": "paragraph", "text": "보고서"}]}, filename="lab.hwpx")
        self.assertEqual(receipt["document_id"], "new_doc")
        self.assertEqual(created[0][0]["style_profile"], {"name": "lab"})
        self.assertEqual(created[0][1]["filename"], "lab.hwpx")
        self.assertEqual(receipt["reference_style"]["approved_profile_sha256"], "a" * 64)

    def test_approved_style_requires_exact_fingerprint_before_creating(self):
        created = []
        tool = self.approved_tool(lambda *args, **kwargs: created.append(args))
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            read.return_value = {"style_profile": {"name": "lab"}, "style_profile_sha256": "a" * 64}
            with self.assertRaisesRegex(ValueError, "not approved"):
                tool("reference_doc", 3, "b" * 64, {"blocks": [{"type": "paragraph", "text": "Hi"}]})
        self.assertEqual(created, [])

    def test_approved_style_rejects_implicit_style_override(self):
        tool = self.approved_tool(lambda *args, **kwargs: {"ok": True})
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            with self.assertRaisesRegex(ValueError, "implicit style_profile"):
                tool("reference_doc", 3, "a" * 64, {"style_profile": {"name": "surprise"}, "blocks": []})
            read.assert_not_called()

    def test_approved_style_rejects_wrong_revision_without_extraction(self):
        tool = self.approved_tool(lambda *args, **kwargs: {"ok": True})
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                tool("reference_doc", 2, "a" * 64, {"blocks": []})
            read.assert_not_called()

    def test_approved_style_handles_custom_profile_name(self):
        tool = self.approved_tool(lambda *args, **kwargs: {"ok": True})
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            read.return_value = {"style_profile": {"name": "My Lab"}, "style_profile_sha256": "c" * 64}
            tool("reference_doc", 3, "c" * 64, {"blocks": []}, profile_name="My Lab")
            read.assert_called_once_with(Path("/private/owned.hwpx"), name="My Lab")

    def test_approved_style_rejects_invalid_digest_format(self):
        tool = self.approved_tool(lambda *args, **kwargs: {"ok": True})
        with patch("hwpx_mcp.interfaces.p423_styles_mcp.profile_from_reference") as read:
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                tool("reference_doc", 3, "XYZ", {"blocks": []})
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
