from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p328_high_level_diagrams import (
    apply_high_level_diagrams_atomic,
    build_high_level_diagram_map,
    high_level_diagram_contract,
    validate_diagram_plan,
)


class HighLevelDiagramTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "p328.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.28 anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.28 anchor")
        return path, anchor

    def test_labeled_node_and_relabel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            first = apply_high_level_diagrams_atomic(
                path,
                [{
                    "op": "insert_labeled_node",
                    "anchor": anchor,
                    "node_type": "decision",
                    "text": "검토?",
                    "horizontal_offset": 1200,
                    "vertical_offset": 900,
                }],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(first["shape_text_changed"])
            mapped = build_high_level_diagram_map(path)
            self.assertEqual(mapped["labeled_node_count"], 1)
            node = mapped["labeled_nodes"][0]
            self.assertEqual(node["draw_text"]["text"], "검토?")
            apply_high_level_diagrams_atomic(
                path,
                [{"op": "set_shape_text", "drawing": node["locator"], "text": "승인?"}],
                expected_revision=2,
                current_revision=2,
            )
            changed = build_high_level_diagram_map(path)["labeled_nodes"][0]
            self.assertEqual(changed["draw_text"]["text"], "승인?")

    def test_callout_composition(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            result = apply_high_level_diagrams_atomic(
                path,
                [{
                    "op": "insert_callout",
                    "anchor": anchor,
                    "text": "주의",
                    "horizontal_offset": 1000,
                    "vertical_offset": 1000,
                    "target_x": 14000,
                    "target_y": 7000,
                }],
                expected_revision=1,
                current_revision=1,
            )
            receipt = result["receipts"][0]
            self.assertEqual(receipt["binding"], "STATIC_POINTER_GEOMETRY_ONLY")
            self.assertTrue(receipt["created_node"])
            self.assertTrue(receipt["created_pointer"])

    def test_declarative_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            plan = {
                "layout": "LEFT_TO_RIGHT",
                "nodes": [
                    {"id": "start", "type": "terminator", "label": "시작"},
                    {"id": "work", "type": "process", "label": "처리"},
                    {"id": "end", "type": "terminator", "label": "끝"},
                ],
                "edges": [
                    {"from": "start", "to": "work"},
                    {"from": "work", "to": "end"},
                ],
            }
            verdict = validate_diagram_plan(plan)
            self.assertEqual(verdict["node_count"], 3)
            result = apply_high_level_diagrams_atomic(
                path,
                [{"op": "insert_diagram_plan", "anchor": anchor, "plan": plan}],
                expected_revision=1,
                current_revision=1,
            )
            receipt = result["receipts"][0]
            self.assertEqual(receipt["node_count"], 3)
            self.assertEqual(receipt["edge_count"], 2)
            self.assertEqual(build_high_level_diagram_map(path)["labeled_node_count"], 3)

    def test_flowchart_and_org_chart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            flow = apply_high_level_diagrams_atomic(
                path,
                [{
                    "op": "insert_flowchart",
                    "anchor": anchor,
                    "steps": [
                        {"id": "s", "label": "시작", "type": "terminator"},
                        {"id": "p", "label": "처리", "type": "process"},
                        {"id": "d", "label": "확인", "type": "decision"},
                        {"id": "e", "label": "종료", "type": "terminator"},
                    ],
                }],
                expected_revision=1,
                current_revision=1,
            )
            self.assertEqual(flow["receipts"][0]["node_count"], 4)

            org = apply_high_level_diagrams_atomic(
                path,
                [{
                    "op": "insert_org_chart",
                    "anchor": anchor,
                    "origin_x": 40000,
                    "root": {
                        "id": "ceo",
                        "label": "대표",
                        "children": [
                            {"id": "rnd", "label": "연구"},
                            {"id": "ops", "label": "운영"},
                        ],
                    },
                }],
                expected_revision=2,
                current_revision=2,
            )
            self.assertEqual(org["receipts"][0]["node_count"], 3)

    def test_invalid_plan_and_contract(self):
        with self.assertRaisesRegex(ValueError, "unknown node"):
            validate_diagram_plan({
                "nodes": [{"id": "a", "label": "A"}],
                "edges": [{"from": "a", "to": "missing"}],
            })
        contract = high_level_diagram_contract()
        self.assertEqual(contract["phase"], "P3.28")
        self.assertIn("smart_connector_routing", contract["deferred_operations"])


if __name__ == "__main__":
    unittest.main()
