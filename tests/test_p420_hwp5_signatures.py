"""Pure HWP5-to-HWPX signature contract after facade extraction."""
from __future__ import annotations

import unittest

from hwpx_mcp.document.hwp5_style_signatures import (
    _canonical_font_face,
    _canonical_color,
    _hwp_colorref_to_hex,
    _hwp_run_format_subset,
    _hwp_paragraph_format_subset,
    _hwp_style_signature,
    _hwp_paragraph_style_signature,
    _hwpx_paragraph_style_signature,
    _hwp_rel_to_horizontal,
    _hwp_rel_to_vertical,
)


class Hwp5StyleSignatureTests(unittest.TestCase):
    def test_canonicalization(self):
        self.assertEqual(_canonical_font_face("  ＡＢＣ  Gothic  "), "abc gothic")
        self.assertIsNone(_canonical_font_face(None))
        self.assertEqual(_canonical_color(" ff00cc "), "#FF00CC")
        self.assertEqual(_hwp_colorref_to_hex(0x123456), "#563412")

    def test_nonsemantic_hwp_style_does_not_claim_precision(self):
        self.assertEqual(_hwp_run_format_subset({"char_shape": {"fidelity": "provenance"}}), {})
        self.assertEqual(_hwp_paragraph_format_subset({}), {})

    def test_hwp_style_signature_retains_text(self):
        receipt = _hwp_style_signature({"text": "한글", "char_shape": {"fidelity": "provenance"}})
        self.assertEqual(receipt["text"], "한글")
        self.assertIsNone(receipt["font"])

    def test_hwp_paragraph_zero_defaults(self):
        receipt = _hwp_paragraph_style_signature({})
        self.assertEqual(receipt["indent_left_mm"], 0)
        self.assertEqual(receipt["spacing_after_pt"], 0)

    def test_hwpx_missing_margin_and_unsupported_unit(self):
        receipt = _hwpx_paragraph_style_signature({
            "paragraph_property": {"alignment": {"horizontal": "JUSTIFY"},
                                   "margin_values": {"left": {"value": 23, "unit": "POINT"}}}
        })
        self.assertEqual(receipt["alignment"], "JUSTIFY")
        self.assertEqual(receipt["indent_left_mm"], 0)

    def test_native_relative_position_mappings(self):
        self.assertEqual(_hwp_rel_to_horizontal(2), "COLUMN")
        self.assertEqual(_hwp_rel_to_vertical(0), "PAPER")


if __name__ == "__main__":
    unittest.main()
