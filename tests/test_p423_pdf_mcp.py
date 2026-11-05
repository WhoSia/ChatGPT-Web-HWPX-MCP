"""P4.23 PDF MCP: source ownership and Windows-only native renderer boundary."""
import tempfile
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


if __name__ == "__main__":
    unittest.main()
