"""P4.26 hosted MCP SVG preview contracts, synthetic owned HWPX only."""
from __future__ import annotations

import base64
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hwpx_mcp.interfaces import p426_visual_preview as visual

DOC = "doc_" + "f" * 24
OWNER = "render-test-owner"


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class VisualPreviewToolTests(unittest.TestCase):
    def setUp(self):
        self.mcp = FakeMcp()
        self.row = {
            "owner_subject": OWNER, "revision": 3,
            "bytes": b"PK synthetic owned HWPX data",
        }
        self.core = SimpleNamespace(
            mcp=self.mcp, _caller_subject=lambda: OWNER,
            _paths=lambda doc: (doc, None),
            DOCUMENT_STORE=SimpleNamespace(load_current=lambda doc: self.row),
        )
        visual.register_visual_preview(self.core)

    def test_registered_tools_and_explicit_native_versus_svg_distinction(self):
        with patch.object(visual, "rhwp_capability", return_value={"available": False}), patch.object(
            visual, "native_pdf_capability",
            return_value={"engine": "HANCOM_HWP_EXE_COM", "available": False},
        ):
            result = self.mcp.tools["get_document_render_options"]()
        self.assertEqual(set(self.mcp.tools), {
            "get_document_render_options", "preview_document_svg_pages",
        })
        self.assertEqual(result["native_hancom_pdf"]["engine"], "HANCOM_HWP_EXE_COM")
        self.assertEqual(result["preview_fidelity"], "RHWP_ALTERNATIVE_RENDERER")

    def test_no_optional_renderer_does_not_fake_preview(self):
        with patch.object(visual, "rhwp_capability", return_value={"available": False}):
            result = self.mcp.tools["preview_document_svg_pages"](DOC)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "RENDERER_NOT_INSTALLED")
        self.assertFalse(result["native_pdf_created"])

    def test_real_svg_bytes_returned_as_page_bound_data(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><text>synthetic</text></svg>'
        def fake_renderer(source, output, **kwargs):
            self.assertEqual(kwargs["page_index"], 2)
            generated = output / "page.svg"
            generated.write_bytes(svg)
            return {"pages": [{"page": 2, "path": str(generated),
                               "bytes": len(svg),
                               "sha256": hashlib.sha256(svg).hexdigest(),
                               "overflow_cell_lines": 0}]}
        with patch.object(visual, "rhwp_capability", return_value={"available": True}), patch.object(
            visual, "render_svg_manifest", side_effect=fake_renderer,
        ):
            result = self.mcp.tools["preview_document_svg_pages"](
                DOC, max_pages=1, start_page=2,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["pages"][0]["page"], 2)
        self.assertEqual(base64.b64decode(result["pages"][0]["svg_base64"]), svg)
        self.assertFalse(result["native_pdf_created"])
        self.assertFalse(result["client_visual_display_verified"])

    def test_foreign_document_cannot_be_previewed(self):
        self.row["owner_subject"] = "unrelated-owner"
        with self.assertRaises(FileNotFoundError):
            self.mcp.tools["preview_document_svg_pages"](DOC)

    def test_invalid_page_range_refused(self):
        with self.assertRaisesRegex(ValueError, "START_PAGE"):
            self.mcp.tools["preview_document_svg_pages"](DOC, start_page=-1)
        with self.assertRaisesRegex(ValueError, "PAGE_LIMIT"):
            self.mcp.tools["preview_document_svg_pages"](DOC, max_pages=99)


if __name__ == "__main__":
    unittest.main()
