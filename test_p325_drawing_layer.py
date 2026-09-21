from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p325_drawing_layer import (
    apply_drawing_layer_atomic,
    build_drawing_layer_map,
    drawing_layer_contract,
)


class DrawingLayerTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "drawing.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("drawing anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(
            item["locator"] for item in mapped["paragraphs"]
            if item.get("text") == "drawing anchor"
        )
        return path, anchor

    def test_textbox_layout_geometry_rotation_flip_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            first = apply_drawing_layer_atomic(
                path,
                [{
                    "op": "insert_textbox",
                    "anchor": anchor,
                    "text": "hello drawing",
                    "width": 9000,
                    "height": 4500,
                    "treat_as_char": False,
                    "horizontal_offset": 1200,
                    "vertical_offset": 800,
                    "z_order": 7,
                }],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(first["drawing_structure_changed"])
            mapped = build_drawing_layer_map(path)
            self.assertEqual(mapped["drawing_count"], 1)
            box = mapped["objects"][0]
            self.assertEqual(box["kind"], "rect")
            self.assertTrue(box["has_textbox"])
            self.assertEqual(box["text"], "hello drawing")
            self.assertEqual(box["z_order"], 7)

            second = apply_drawing_layer_atomic(
                path,
                [
                    {
                        "op": "set_drawing_layout",
                        "drawing": box["locator"],
                        "text_wrap": "IN_FRONT_OF_TEXT",
                        "z_order": 11,
                        "horizontal_offset": 2200,
                        "vertical_offset": 1600,
                        "horz_rel_to": "PAPER",
                        "vert_rel_to": "PAPER",
                    },
                    {
                        "op": "resize_drawing_object",
                        "drawing": box["locator"],
                        "width": 10000,
                        "height": 5000,
                    },
                    {
                        "op": "rotate_drawing_object",
                        "drawing": box["locator"],
                        "angle": 15,
                    },
                    {
                        "op": "flip_drawing_object",
                        "drawing": box["locator"],
                        "horizontal": True,
                        "vertical": False,
                    },
                ],
                expected_revision=2,
                current_revision=2,
            )
            self.assertTrue(second["drawing_geometry_changed"])
            reopened = build_drawing_layer_map(path)
            item = reopened["objects"][0]
            self.assertEqual((item["width"], item["height"]), (10000, 5000))
            self.assertEqual(item["text_wrap"], "IN_FRONT_OF_TEXT")
            self.assertEqual(item["z_order"], 11)
            self.assertEqual(item["position"]["horzOffset"], "2200")
            self.assertEqual(item["position"]["vertOffset"], "1600")
            self.assertEqual(item["rotation"]["angle"], "15")
            self.assertEqual(item["flip"]["horizontal"], "1")

    def test_rectangle_authoring_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_drawing_layer_atomic(
                path,
                [{
                    "op": "insert_rectangle",
                    "anchor": anchor,
                    "width": 7200,
                    "height": 3600,
                    "treat_as_char": False,
                }],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_drawing_layer_map(path)
            self.assertEqual(mapped["drawing_count"], 1)
            rect = mapped["objects"][0]
            self.assertEqual(rect["kind"], "rect")
            self.assertFalse(rect["has_textbox"])
            apply_drawing_layer_atomic(
                path,
                [{"op": "remove_drawing_object", "drawing": rect["locator"]}],
                expected_revision=2,
                current_revision=2,
            )
            self.assertEqual(build_drawing_layer_map(path)["drawing_count"], 0)

    def test_grouping_and_generic_shape_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _anchor = self._fixture(Path(tmp))
            for op in ("group_objects", "ungroup_objects", "insert_generic_shape"):
                with self.assertRaisesRegex(ValueError, "EVIDENCE_GATE_CLOSED"):
                    apply_drawing_layer_atomic(
                        path,
                        [{"op": op}],
                        expected_revision=1,
                        current_revision=1,
                    )

    def test_stale_revision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, "Stale revision"):
                apply_drawing_layer_atomic(
                    path,
                    [{"op": "insert_textbox", "anchor": anchor, "text": "x"}],
                    expected_revision=1,
                    current_revision=2,
                )

    def test_contract_authority(self):
        contract = drawing_layer_contract()
        self.assertEqual(contract["phase"], "P3.25")
        self.assertEqual(contract["authority"], "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY")
        self.assertIn("group_objects", contract["deferred_operations"])
        self.assertEqual(contract["admitted_authoring"], ["insert_textbox", "insert_rectangle"])


if __name__ == "__main__":
    unittest.main()
