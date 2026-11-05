"""Existing HWPX templates outrank generic page-margin presets."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from hwpx_mcp.document.p318_document_setup import build_document_setup_map
from hwpx_mcp.document.p321_document_composer import (
    _setup_operations, compose_document_plan, validate_document_plan,
)


class P423TemplatePreservationTests(unittest.TestCase):
    def test_profileless_template_skips_preset_page_setup(self):
        plan = {"preset": "school-report", "blocks": [{"type": "paragraph", "text": "내용"}]}
        self.assertEqual(_setup_operations(plan, preserve_template_setup=True), [])

    def test_new_document_still_uses_report_preset(self):
        plan = {"preset": "school-report", "blocks": [{"type": "paragraph", "text": "내용"}]}
        self.assertTrue(any(op["op"] == "set_page_setup" for op in _setup_operations(plan)))

    def test_explicit_profile_page_override_remains_allowed(self):
        plan = {
            "preset": "school-report",
            "style_profile": {"page": {"margin_left_mm": 28}},
            "blocks": [{"type": "paragraph", "text": "내용"}],
        }
        ops = _setup_operations(plan, preserve_template_setup=True)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["margin_left_mm"], 28)


if __name__ == "__main__":
    unittest.main()
