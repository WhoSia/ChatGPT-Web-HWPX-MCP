from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import (
    apply_diagram_lifecycle_atomic,
    build_diagram_lifecycle_map,
    diagram_lifecycle_contract,
)


class DiagramLifecycleTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "p329.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.29 anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(x["locator"] for x in mapped["paragraphs"] if x.get("text") == "P3.29 anchor")
        return path, anchor

    def _create(self, path: Path, anchor: str):
        return apply_diagram_lifecycle_atomic(
            path,
            [{
                "op": "create_diagram",
                "diagram_id": "main",
                "anchor": anchor,
                "plan": {
                    "layout": "LEFT_TO_RIGHT",
                    "nodes": [
                        {"id": "start", "type": "terminator", "label": "Start"},
                        {"id": "work", "type": "process", "label": "Work"},
                        {"id": "end", "type": "terminator", "label": "End"},
                    ],
                    "edges": [
                        {"from": "start", "to": "work"},
                        {"from": "work", "to": "end"},
                    ],
                },
            }],
            expected_revision=1,
            current_revision=1,
        )

    def test_identity_survives_reopen_and_relations_reconstruct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._create(path, anchor)
            reopened = build_diagram_lifecycle_map(path)
            self.assertEqual(reopened["diagram_count"], 1)
            d = reopened["diagrams"][0]
            self.assertEqual([n["node_id"] for n in d["nodes"]], ["end", "start", "work"])
            self.assertEqual({e["edge_id"] for e in d["edges"]}, {"start->work", "work->end"})
            self.assertTrue(all(n["node_type"] in {"process", "terminator"} for n in d["nodes"]))

    def test_patch_node_rebuilds_incident_static_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._create(path, anchor)
            before = build_diagram_lifecycle_map(path)["diagrams"][0]
            old_edges = {e["locator"] for e in before["edges"]}
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "patch_node", "diagram_id": "main", "node_id": "work", "label": "Review", "x": 18000, "width": 9000}],
                expected_revision=2,
                current_revision=2,
            )
            after = build_diagram_lifecycle_map(path)["diagrams"][0]
            work = next(n for n in after["nodes"] if n["node_id"] == "work")
            self.assertEqual(work["label"], "Review")
            self.assertEqual(work["position"]["horzOffset"], "18000")
            self.assertEqual(int(work["width"]), 9000)
            self.assertEqual({e["edge_id"] for e in after["edges"]}, {"start->work", "work->end"})
            self.assertTrue(old_edges.isdisjoint({e["locator"] for e in after["edges"]}))

    def test_add_remove_edge_and_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._create(path, anchor)
            apply_diagram_lifecycle_atomic(
                path,
                [
                    {"op": "add_node", "diagram_id": "main", "node_id": "audit", "node_type": "decision", "label": "Audit?", "x": 12000, "y": 9000},
                    {"op": "add_edge", "diagram_id": "main", "source": "work", "target": "audit"},
                ],
                expected_revision=2,
                current_revision=2,
            )
            d = build_diagram_lifecycle_map(path)["diagrams"][0]
            self.assertIn("audit", {n["node_id"] for n in d["nodes"]})
            self.assertIn("work->audit", {e["edge_id"] for e in d["edges"]})
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "remove_node", "diagram_id": "main", "node_id": "audit"}],
                expected_revision=3,
                current_revision=3,
            )
            d = build_diagram_lifecycle_map(path)["diagrams"][0]
            self.assertNotIn("audit", {n["node_id"] for n in d["nodes"]})
            self.assertNotIn("work->audit", {e["edge_id"] for e in d["edges"]})

    def test_relayout_and_move_subgraph_preserve_semantic_relations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._create(path, anchor)
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "relayout_diagram", "diagram_id": "main", "layout": "TOP_DOWN", "order": ["start", "work", "end"], "origin_x": 3000, "origin_y": 2000, "gap_y": 7000}],
                expected_revision=2,
                current_revision=2,
            )
            d = build_diagram_lifecycle_map(path)["diagrams"][0]
            pos = {n["node_id"]: (int(n["position"]["horzOffset"]), int(n["position"]["vertOffset"])) for n in d["nodes"]}
            self.assertEqual(pos["start"], (3000, 2000))
            self.assertEqual(pos["work"], (3000, 9000))
            self.assertEqual(pos["end"], (3000, 16000))
            self.assertEqual({e["edge_id"] for e in d["edges"]}, {"start->work", "work->end"})
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "move_subgraph", "diagram_id": "main", "node_ids": ["work", "end"], "dx": 5000, "dy": 1000}],
                expected_revision=3,
                current_revision=3,
            )
            d = build_diagram_lifecycle_map(path)["diagrams"][0]
            self.assertEqual({e["edge_id"] for e in d["edges"]}, {"start->work", "work->end"})

    def test_template_clone_and_remove_subgraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "instantiate_template", "diagram_id": "tpl", "template": "linear_process", "anchor": anchor}],
                expected_revision=1,
                current_revision=1,
            )
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "clone_subgraph", "diagram_id": "tpl", "node_ids": ["start", "work"], "new_prefix": "copy", "dx": 0, "dy": 9000}],
                expected_revision=2,
                current_revision=2,
            )
            d = build_diagram_lifecycle_map(path)["diagrams"][0]
            self.assertIn("copy-start", {n["node_id"] for n in d["nodes"]})
            self.assertIn("copy-work", {n["node_id"] for n in d["nodes"]})
            self.assertIn("copy-start->copy-work", {e["edge_id"] for e in d["edges"]})
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "remove_subgraph", "diagram_id": "tpl", "node_ids": ["copy-start", "copy-work"]}],
                expected_revision=3,
                current_revision=3,
            )
            d = build_diagram_lifecycle_map(path)["diagrams"][0]
            self.assertNotIn("copy-start", {n["node_id"] for n in d["nodes"]})

    def test_polygon_resize_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_diagram_lifecycle_atomic(
                path,
                [{
                    "op": "create_diagram",
                    "diagram_id": "poly",
                    "anchor": anchor,
                    "plan": {"nodes": [{"id": "d", "type": "decision", "label": "D"}], "edges": []},
                }],
                expected_revision=1,
                current_revision=1,
            )
            with self.assertRaisesRegex(ValueError, "polygon resize"):
                apply_diagram_lifecycle_atomic(
                    path,
                    [{"op": "patch_node", "diagram_id": "poly", "node_id": "d", "width": 9000}],
                    expected_revision=2,
                    current_revision=2,
                )

    def test_contract(self):
        c = diagram_lifecycle_contract()
        self.assertEqual(c["phase"], "P3.29")
        self.assertIn("linear_process", c["templates"])
        self.assertIn("smart_connector_binding", c["deferred_operations"])
        self.assertIn("polygon_bbox_resize", c["deferred_operations"])
        self.assertEqual(c["limits"], {"nodes": 32, "edges": 64})


if __name__ == "__main__":
    unittest.main()
