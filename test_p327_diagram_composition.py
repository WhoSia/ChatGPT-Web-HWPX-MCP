from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p326_drawing_style import apply_drawing_style_atomic
from p327_diagram_composition import (
    apply_diagram_composition_atomic,
    build_diagram_composition_map,
    diagram_composition_contract,
)


class DiagramCompositionTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "diagram.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("diagram anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "diagram anchor")
        return path, anchor

    def _three_shapes(self, path: Path, anchor: str) -> list[str]:
        apply_drawing_style_atomic(
            path,
            [
                {"op": "insert_ellipse", "anchor": anchor, "width": 4000, "height": 3000, "treat_as_char": False},
                {"op": "insert_ellipse", "anchor": anchor, "width": 4000, "height": 3000, "treat_as_char": False},
                {"op": "insert_ellipse", "anchor": anchor, "width": 4000, "height": 3000, "treat_as_char": False},
            ],
            expected_revision=1,
            current_revision=1,
        )
        mapped = build_diagram_composition_map(path)
        locs = [item["locator"] for item in mapped["top_level_objects"] if item["kind"] == "ellipse"]
        self.assertEqual(len(locs), 3)
        apply_diagram_composition_atomic(
            path,
            [
                {"op": "align_objects", "drawings": locs, "mode": "TOP"},
            ],
            expected_revision=2,
            current_revision=2,
        )
        # Give the three objects distinct x positions.
        from p325_drawing_layer import _mutate_section, _find_node, HP
        refreshed = build_diagram_composition_map(path)
        for index, locator in enumerate(locs):
            item = next(x for x in refreshed["top_level_objects"] if x["locator"] == locator)
            def mutate(root, item=item, index=index):
                node = _find_node(root, item)
                pos = node.find(f"{HP}pos")
                pos.set("horzOffset", str(index * 8000))
                pos.set("vertOffset", "1000")
            _mutate_section(path, item["section"], mutate)
        return locs

    def test_group_authoring_and_rigid_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            result = apply_diagram_composition_atomic(
                path,
                [{
                    "op": "insert_group",
                    "anchor": anchor,
                    "horizontal_offset": 1200,
                    "vertical_offset": 900,
                    "members": [
                        {"kind": "rect", "x": 0, "y": 0, "width": 5000, "height": 3000},
                        {"kind": "ellipse", "x": 7000, "y": 0, "width": 4000, "height": 3000},
                    ],
                }],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(result["group_topology_changed"])
            mapped = build_diagram_composition_map(path)
            self.assertEqual(mapped["group_count"], 1)
            group = mapped["groups"][0]
            self.assertEqual(len(group["members"]), 2)
            self.assertEqual(group["position"]["horzOffset"], "1200")
            apply_diagram_composition_atomic(
                path,
                [{"op": "translate_group", "group": group["locator"], "dx": 500, "dy": 300}],
                expected_revision=2,
                current_revision=2,
            )
            moved = build_diagram_composition_map(path)["groups"][0]
            self.assertEqual(moved["position"]["horzOffset"], "1700")
            self.assertEqual(moved["position"]["vertOffset"], "1200")

    def test_align_distribute_and_static_connector(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            locs = self._three_shapes(path, anchor)
            apply_diagram_composition_atomic(
                path,
                [{"op": "distribute_objects", "drawings": locs, "mode": "HORIZONTAL"}],
                expected_revision=3,
                current_revision=3,
            )
            mapped = build_diagram_composition_map(path)
            xs = []
            for locator in locs:
                item = next(x for x in mapped["top_level_objects"] if x["locator"] == locator)
                xs.append(int(item["position"]["horzOffset"]))
            self.assertEqual(xs, [0, 8000, 16000])
            apply_diagram_composition_atomic(
                path,
                [{"op": "insert_static_connector", "source": locs[0], "target": locs[2]}],
                expected_revision=4,
                current_revision=4,
            )
            final = build_diagram_composition_map(path)
            self.assertGreaterEqual(sum(1 for x in final["top_level_objects"] if x["kind"] == "line"), 1)

    def test_reusable_block_and_fail_closed_smart_connector(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_diagram_composition_atomic(
                path,
                [{"op": "insert_diagram_block", "preset": "three_stage", "anchor": anchor}],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_diagram_composition_map(path)
            self.assertEqual(mapped["group_count"], 1)
            self.assertEqual(len(mapped["groups"][0]["members"]), 3)
            with self.assertRaisesRegex(ValueError, "EVIDENCE_GATE_CLOSED"):
                apply_diagram_composition_atomic(
                    path,
                    [{"op": "insert_smart_connector"}],
                    expected_revision=2,
                    current_revision=2,
                )

    def test_contract(self):
        contract = diagram_composition_contract()
        self.assertEqual(contract["phase"], "P3.27")
        self.assertEqual(contract["authority"], "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY")
        self.assertIn("insert_smart_connector", contract["deferred_operations"])
        self.assertIn("three_stage", contract["block_presets"])


if __name__ == "__main__":
    unittest.main()
