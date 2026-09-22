from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p326_drawing_style import (
    apply_drawing_style_atomic,
    build_drawing_style_map,
    drawing_style_contract,
)


class DrawingStyleTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "shape.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("shape anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "shape anchor")
        return path, anchor

    def test_author_four_shape_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            result = apply_drawing_style_atomic(
                path,
                [
                    {"op":"insert_line","anchor":anchor,"start_x":0,"start_y":0,"end_x":9000,"end_y":3000},
                    {"op":"insert_ellipse","anchor":anchor,"width":8000,"height":5000,"fill_color":"#DDEEFF"},
                    {"op":"insert_polygon","anchor":anchor,"points":[[0,0],[8000,0],[4000,6000]],"fill_color":"#FFF0CC"},
                    {"op":"insert_arc","anchor":anchor,"width":6000,"height":6000,"corner":"TOP_LEFT","arc_type":"PIE","fill_color":"#E8DDFF"},
                ],
                expected_revision=1,current_revision=1,
            )
            self.assertTrue(result["drawing_structure_changed"])
            mapped = build_drawing_style_map(path)
            self.assertEqual(mapped["drawing_count"], 4)
            self.assertEqual(mapped["family_counts"]["line"], 1)
            self.assertEqual(mapped["family_counts"]["ellipse"], 1)
            self.assertEqual(mapped["family_counts"]["polygon"], 1)
            self.assertEqual(mapped["family_counts"]["arc"], 1)

    def test_stroke_fill_shadow_arrowheads_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_drawing_style_atomic(
                path,
                [{"op":"insert_line","anchor":anchor,"start_x":0,"start_y":0,"end_x":9000,"end_y":3000}],
                expected_revision=1,current_revision=1,
            )
            line = build_drawing_style_map(path)["objects"][0]
            apply_drawing_style_atomic(
                path,
                [
                    {"op":"set_shape_stroke","drawing":line["locator"],"color":"#224466","width":420,"style":"DASH","alpha":35,"end_cap":"ROUND"},
                    {"op":"set_shape_arrowheads","drawing":line["locator"],"head_style":"ARROW","tail_style":"FILLED_CIRCLE","head_size":"MEDIUM_MEDIUM","tail_size":"SMALL_SMALL"},
                    {"op":"set_shape_shadow","drawing":line["locator"],"type":"DROP","color":"#808080","offset_x":300,"offset_y":400,"alpha":70},
                ],
                expected_revision=2,current_revision=2,
            )
            style = build_drawing_style_map(path)["styles"][0]
            self.assertEqual(style["line_shape"]["color"], "#224466")
            self.assertEqual(style["line_shape"]["style"], "DASH")
            self.assertEqual(style["line_shape"]["headStyle"], "ARROW")
            self.assertEqual(style["line_shape"]["tailStyle"], "FILLED_CIRCLE")
            self.assertEqual(style["shadow"]["type"], "DROP")
            self.assertEqual(style["shadow"]["alpha"], "70")

    def test_fill_add_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_drawing_style_atomic(
                path,
                [{"op":"insert_ellipse","anchor":anchor,"width":7000,"height":4000}],
                expected_revision=1,current_revision=1,
            )
            ellipse = build_drawing_style_map(path)["objects"][0]
            apply_drawing_style_atomic(
                path,
                [{"op":"set_shape_fill","drawing":ellipse["locator"],"color":"#AABBCC","alpha":40}],
                expected_revision=2,current_revision=2,
            )
            self.assertEqual(build_drawing_style_map(path)["styles"][0]["fill"]["faceColor"], "#AABBCC")
            apply_drawing_style_atomic(
                path,
                [{"op":"clear_shape_fill","drawing":ellipse["locator"]}],
                expected_revision=3,current_revision=3,
            )
            self.assertIsNone(build_drawing_style_map(path)["styles"][0]["fill"])

    def test_deferred_families_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._fixture(Path(tmp))
            for name in ("insert_curve","insert_connect_line","gradient_fill","pattern_fill"):
                with self.assertRaisesRegex(ValueError,"EVIDENCE_GATE_CLOSED"):
                    apply_drawing_style_atomic(path,[{"op":name}],expected_revision=1,current_revision=1)

    def test_contract(self):
        c=drawing_style_contract()
        self.assertEqual(c["phase"],"P3.26")
        self.assertEqual(c["authority"],"STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY")
        self.assertEqual(c["admitted_authoring"],["arc","ellipse","line","polygon"])


if __name__=="__main__":
    unittest.main()
