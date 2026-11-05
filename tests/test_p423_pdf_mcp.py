"""P4.23 PDF MCP: source ownership and Windows-only native renderer boundary."""
import tempfile
import base64
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx_mcp.interfaces.p423_pdf_mcp import register_p423_native_pdf_tools


class FakeMCP:
    def __init__(self): self.tools = {}
    def tool(self, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


class FakeCore:
    def __init__(self):
        self.mcp = FakeMCP()
        self.calls = 0
    def _caller_subject(self):
        self.calls += 1
        return "owner"


class P423PdfMCPTests(unittest.TestCase):
    def setUp(self):
        self.core = FakeCore()
        self.owned_calls = []
        def owned(doc):
            self.owned_calls.append(doc)
            return {"revision": 2}, Path("/owned/reference.hwpx")
        register_p423_native_pdf_tools(self.core, owned_document=owned)
        self.tool = self.core.mcp.tools["export_p423_owned_hwp_as_native_pdf"]

    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.native_pdf_capability")
    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.export_native_hwp_pdf")
    def test_linux_returns_explicit_unavailable_without_rendering(self, export, capability):
        capability.return_value = {"available": False}
        result = self.tool("doc_1", 2)
        self.assertEqual(result["code"], "WINDOWS_HANCOM_AGENT_REQUIRED")
        self.assertFalse(result["native_pdf_created"])
        self.assertEqual(self.owned_calls, ["doc_1"])
        export.assert_not_called()

    def test_revision_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "revision changed"):
            self.tool("doc_1", 1)

    def test_missing_document_id_rejected_before_ownership(self):
        with self.assertRaisesRegex(ValueError, "document_id"):
            self.tool(" ", 2)
        self.assertEqual(self.owned_calls, [])

    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.native_pdf_capability")
    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.export_native_hwp_pdf")
    def test_windows_native_pdf_return_is_bound_to_authorized_revision(self, export, capability):
        capability.return_value = {"available": True}
        payload = b"%PDF-1.7\\n" + b"native-simulated-test" * 8
        def fake_export(source, destination):
            destination.write_bytes(payload)
            return {"status": "PDF_CREATED_UNREVIEWED", "pdf_sha256": hashlib.sha256(payload).hexdigest()}
        export.side_effect = fake_export
        result = self.tool("doc_1", 2)
        self.assertTrue(result["ok"])
        self.assertEqual(base64.b64decode(result["pdf_base64"]), payload)
        self.assertEqual(result["pdf_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["native_visual_acceptance"], "NOT_ADJUDICATED")
        self.assertEqual(result["source_revision"], 2)

    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.native_pdf_capability")
    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.export_native_hwp_pdf")
    def test_large_pdf_cannot_be_inlined_or_claimed_delivered(self, export, capability):
        from hwpx_mcp.interfaces.p423_pdf_mcp import MAX_INLINE_PDF_BYTES
        capability.return_value = {"available": True}
        def fake_export(source, destination):
            destination.write_bytes(b"%PDF-" + b"X" * MAX_INLINE_PDF_BYTES)
            return {"status": "PDF_CREATED_UNREVIEWED", "pdf_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
        export.side_effect = fake_export
        response = self.tool("doc_1", 2)
        self.assertFalse(response["ok"])
        self.assertEqual(response["code"], "PDF_TOO_LARGE_FOR_INLINE_DELIVERY")
        self.assertNotIn("pdf_base64", response)

    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.native_pdf_capability")
    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.export_native_hwp_pdf")
    def test_concurrent_revision_change_blocks_stale_pdf_handoff(self, export, capability):
        capability.return_value = {"available": True}
        payload = b"%PDF-1.7\\n" + b"native-simulated-test" * 8

        def fake_export(source, destination):
            destination.write_bytes(payload)
            return {"pdf_sha256": hashlib.sha256(payload).hexdigest()}

        export.side_effect = fake_export
        calls = [0]

        def changing_owner(doc):
            calls[0] += 1
            return {"revision": 2 if calls[0] == 1 else 3}, Path("/owned/reference.hwpx")

        second = FakeCore()
        register_p423_native_pdf_tools(second, owned_document=changing_owner)
        with self.assertRaisesRegex(ValueError, "revision changed during native export"):
            second.mcp.tools["export_p423_owned_hwp_as_native_pdf"]("doc_1", 2)
        self.assertEqual(calls[0], 2)

    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.native_pdf_capability")
    @patch("hwpx_mcp.interfaces.p423_pdf_mcp.export_native_hwp_pdf")
    def test_worker_receipt_hash_mismatch_prevents_inline_delivery(self, export, capability):
        capability.return_value = {"available": True}

        def fake_export(source, destination):
            destination.write_bytes(b"%PDF-1.7\\n" + b"native-simulated-test" * 8)
            return {"pdf_sha256": "0" * 64}

        export.side_effect = fake_export
        with self.assertRaisesRegex(ValueError, "does not match worker receipt"):
            self.tool("doc_1", 2)

    def test_invalid_revision_type_does_not_lookup_document(self):
        with self.assertRaisesRegex(ValueError, "expected_revision"):
            self.tool("doc_1", True)
        self.assertEqual(self.owned_calls, [])


if __name__ == "__main__":
    unittest.main()
