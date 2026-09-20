from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from p311_layout_fidelity import (
    adjudicate_layout_fidelity,
    build_hwpx_layout_receipt,
)


class P311LayoutFidelityTests(unittest.TestCase):
    def _fixture(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False)
        tmp.close()
        path = Path(tmp.name)
        section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:secPr>
    <hp:pagePr width="59528" height="84188" landscape="NARROWLY" gutterType="LEFT_ONLY">
      <hp:margin left="8504" right="8504" top="5668" bottom="4252" header="4252" footer="4252" gutter="0"/>
    </hp:pagePr>
  </hp:secPr>
  <hp:p id="1" pageBreak="1" columnBreak="0">
    <hp:run charPrIDRef="0"><hp:t>alpha<hp:lineBreak/>beta</hp:t></hp:run>
  </hp:p>
</hp:sec>
"""
        header = """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:fontfaces>
    <hh:fontface lang="HANGUL">
      <hh:font id="0" face="함초롬바탕" type="TTF"/>
    </hh:fontface>
  </hh:fontfaces>
</hh:head>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Contents/header.xml", header)
            archive.writestr("Contents/section0.xml", section)
        return path

    def test_page_geometry_and_hard_break_receipt(self):
        path = self._fixture()
        try:
            receipt = build_hwpx_layout_receipt(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(receipt["section_count"], 1)
        self.assertEqual(receipt["paragraph_count"], 1)
        section = receipt["sections"][0]
        self.assertEqual(section["page_width"], 59528)
        self.assertEqual(section["page_height"], 84188)
        self.assertEqual(section["text_frame_width"], 42520)
        self.assertEqual(section["text_frame_height"], 65764)
        self.assertEqual(receipt["hard_break_receipt"]["hard_line_breaks"], 1)
        self.assertEqual(receipt["hard_break_receipt"]["explicit_page_breaks"], 1)
        self.assertEqual(receipt["pagination_authority"], "EXTERNAL_RENDER_REQUIRED")
        self.assertTrue(receipt["font_inventory_sha256"])

    def test_non_hancom_cannot_promote_pixel_fidelity(self):
        structural = {
            "page_section_geometry_sha256": "g",
            "hard_break_receipt": {"sha256": "b"},
            "font_inventory_sha256": "f",
        }
        external = {
            "renderer": {"name": "LibreOffice", "version": "1", "hancom_native": False},
            "environment": {
                "font_environment_controlled": True,
                "source_font_inventory_sha256": "x",
                "target_font_inventory_sha256": "x",
            },
            "metrics": {
                "pagination_equal": True,
                "line_break_equal": True,
                "exact_pixel_match": True,
                "pixel_diff_ratio": 0.0,
                "mae": 0.0,
                "edge_disagreement": 0.0,
                "bbox_max_displacement_px": 0.0,
                "glyph_advance_max_delta_px": 0.0,
                "inline_baseline_max_delta_px": 0.0,
                "border_paint_diff_ratio": 0.0,
            },
            "calibration": {},
        }
        result = adjudicate_layout_fidelity(structural, external)
        self.assertEqual(result["verdict"], "PIXEL_RENDER_FIDELITY_HOLD")
        self.assertIn("HANCOM_NATIVE_RENDER_WORLD_CONTACT_HOLD", result["reason_chain"])

    def test_hancom_exact_pixel_evidence_can_promote(self):
        structural = {
            "page_section_geometry_sha256": "g",
            "hard_break_receipt": {"sha256": "b"},
            "font_inventory_sha256": "f",
        }
        external = {
            "renderer": {"name": "Hancom Hangul", "version": "2026", "hancom_native": True},
            "environment": {
                "font_environment_controlled": True,
                "source_font_inventory_sha256": "same",
                "target_font_inventory_sha256": "same",
            },
            "metrics": {
                "pagination_equal": True,
                "line_break_equal": True,
                "exact_pixel_match": True,
                "pixel_diff_ratio": 0.0,
                "mae": 0.0,
                "edge_disagreement": 0.0,
                "bbox_max_displacement_px": 0.0,
                "glyph_advance_max_delta_px": 0.0,
                "inline_baseline_max_delta_px": 0.0,
                "border_paint_diff_ratio": 0.0,
            },
            "calibration": {},
        }
        result = adjudicate_layout_fidelity(structural, external)
        self.assertEqual(result["verdict"], "PIXEL_RENDER_FIDELITY_PASS")
        self.assertEqual(result["authority"], "HANCOM_NATIVE_EXACT_PIXEL_AUTHORITY")

    def test_residual_is_attributed_without_overpromotion(self):
        structural = {
            "page_section_geometry_sha256": "g",
            "hard_break_receipt": {"sha256": "b"},
            "font_inventory_sha256": "f",
        }
        external = {
            "renderer": {"name": "Hancom Hangul", "version": "2026", "hancom_native": True},
            "environment": {
                "font_environment_controlled": True,
                "source_font_inventory_sha256": "same",
                "target_font_inventory_sha256": "same",
            },
            "metrics": {
                "pagination_equal": True,
                "line_break_equal": True,
                "exact_pixel_match": False,
                "pixel_diff_ratio": 0.01,
                "mae": 0.01,
                "edge_disagreement": 0.01,
                "bbox_max_displacement_px": 0.0,
                "glyph_advance_max_delta_px": 0.2,
                "inline_baseline_max_delta_px": 0.0,
                "border_paint_diff_ratio": 0.02,
            },
            "calibration": {
                "pixel_diff_tolerance_ratio": 0.02,
                "mae_tolerance": 0.02,
                "edge_disagreement_tolerance": 0.02,
                "glyph_advance_tolerance_px": 0.1,
                "border_paint_tolerance_ratio": 0.01,
            },
        }
        result = adjudicate_layout_fidelity(structural, external)
        self.assertEqual(result["verdict"], "PIXEL_RENDER_FIDELITY_HOLD")
        self.assertIn("FONT_METRIC_GLYPH_ADVANCE_DIVERGENCE", result["reason_chain"])
        self.assertIn("BORDER_PAINT_RASTER_RESIDUE", result["reason_chain"])


if __name__ == "__main__":
    unittest.main()
