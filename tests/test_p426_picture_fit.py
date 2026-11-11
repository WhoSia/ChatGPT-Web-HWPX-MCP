"""Opt-in native figure fitting without resampling embedded PNG/JPEG data."""
from __future__ import annotations

import base64
import unittest
import tempfile
from pathlib import Path
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p29_objects import build_object_map

from hwpx_mcp.orchestration.p426_layout_preflight import fit_native_pictures_to_body
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan


class PictureFitTests(unittest.TestCase):
    def test_only_oversized_figures_scaled_and_ratio_preserved(self):
        blocks = [
            {"id": "wide", "type": "picture", "width": 80000, "height": 40000,
             "content_base64": "c29tZQ=="},
            {"id": "small", "type": "picture", "width": 12000, "height": 6000},
            {"type": "table", "width": 80000, "height": 5000},
        ]
        result = fit_native_pictures_to_body(blocks, "science-lab")
        self.assertEqual(result["adjusted_count"], 1)
        self.assertLess(result["blocks"][0]["width"], 80000)
        self.assertAlmostEqual(result["blocks"][0]["width"] / result["blocks"][0]["height"], 2, places=3)
        self.assertEqual(result["blocks"][1]["width"], 12000)
        self.assertEqual(result["blocks"][2]["width"], 80000)
        self.assertEqual(blocks[0]["width"], 80000)
        self.assertEqual(result["blocks"][0]["content_base64"], "c29tZQ==")
        self.assertFalse(result["pixel_data_resampled"])

    def test_opt_in_report_interface_changes_only_native_picture_geometry(self):
        img = ("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0k"\n               "AAAAFElEQVR4nGMUscn7z8DAwMDEAAUAGa4BwYhFMToAAAAASUVORK5CYII=")
        kwargs = dict(title="그림 폭 검증", layout="science-lab", sections=[{
            "heading": "결과", "content": [{
                "type": "figure", "image_format": "png",
                "content_base64": img, "width": 80000,
                "height": 40000, "caption": "연구 그래프",
            }],
        }])
        raw = build_report_plan(**kwargs)
        resized = build_report_plan(**kwargs, fit_figures_to_page=True)
        orig_block = raw["sections"][0]["blocks"][-1]
        fit_block = resized["sections"][0]["blocks"][-1]
        self.assertEqual(orig_block["content_base64"], fit_block["content_base64"])
        self.assertEqual(orig_block["caption"], fit_block["caption"])
        self.assertEqual(orig_block["width"], 80000)
        self.assertLess(fit_block["width"], orig_block["width"])
        self.assertLess(fit_block["height"], orig_block["height"])

    def test_real_native_hwpx_picture_has_fitted_saved_geometry(self):
        payload = ("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0k"
                   "AAAAFElEQVR4nGMUscn7z8DAwMDEAAUAGa4BwYhFMToAAAAASUVORK5CYII=")
        requested = build_report_plan(
            title="너비 맞춤 검증", fit_figures_to_page=True,
            layout="science-lab",
            sections=[{"heading": "결과", "content": [{
                "type": "figure", "image_format": "png",
                "content_base64": payload, "width": 80000,
                "height": 40000, "caption": "합성 그림",
            }]}],
        )
        picture = requested["sections"][0]["blocks"][-1]
        self.assertLess(picture["width"], 80000)
        compiled = compile_rich_document_plan(requested)
        with tempfile.TemporaryDirectory(prefix="p426-fit-real-") as tmp:
            path = Path(tmp) / "figure.hwpx"
            receipt = compose_document_plan(path, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            figures = build_object_map(path)["pictures"]
            self.assertEqual(len(figures), 1)
            self.assertEqual(figures[0]["width"], picture["width"])
            self.assertEqual(figures[0]["height"], picture["height"])

    def test_wrong_fit_setting_and_dimensions_rejected(self):
        with self.assertRaisesRegex(ValueError, "FIT_INVALID"):
            build_report_plan(title="보고서", sections=[{"heading": "내용"}],
                              fit_figures_to_page="yes")
        with self.assertRaisesRegex(ValueError, "DIMENSIONS_INVALID"):
            fit_native_pictures_to_body([{"type": "picture", "width": 0}])

if __name__ == "__main__":
    unittest.main()
