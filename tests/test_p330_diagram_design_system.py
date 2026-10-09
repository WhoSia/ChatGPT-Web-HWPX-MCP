from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic
from p330_diagram_design_system import (
    apply_diagram_design_system_atomic,
    build_diagram_design_system_map,
    diagram_design_system_contract,
)


class DiagramDesignSystemTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "p330.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.30 anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.30 anchor")
        return path, anchor

    def _template(self, path: Path, anchor: str, diagram_id: str = "d1") -> None:
        apply_diagram_lifecycle_atomic(
            path,
            [{"op": "instantiate_template", "diagram_id": diagram_id, "anchor": anchor, "template": "decision_gate"}],
            expected_revision=1,
            current_revision=1,
        )

    def test_theme_preserves_identity_and_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._template(path, anchor)
            before = build_diagram_design_system_map(path)
            result = apply_diagram_design_system_atomic(
                path,
                [{"op": "apply_theme", "diagram_id": "d1", "theme": "classic"}],
                expected_revision=2,
                current_revision=2,
            )
            self.assertTrue(result["semantic_style_changed"])
            self.assertTrue(result["identity_preserved"])
            mapped = build_diagram_design_system_map(path)
            diagram = mapped["diagrams"][0]
            roles = {n["node_id"]: n["semantic_role"] for n in diagram["nodes"]}
            self.assertEqual(roles["decision"], "decision")
            branch_edges = [e for e in diagram["edges"] if e["source"] == "decision"]
            self.assertTrue(branch_edges)
            self.assertTrue(all(e["semantic_role"] == "branch" for e in branch_edges))

    def test_custom_node_and_edge_restyle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._template(path, anchor)
            apply_diagram_design_system_atomic(
                path,
                [
                    {"op": "restyle_node", "diagram_id": "d1", "node_id": "input", "style": {
                        "fill_color": "#DDEEFF", "stroke_color": "#112233", "stroke_width": 321,
                    }},
                    {"op": "restyle_edge", "diagram_id": "d1", "source": "input", "target": "decision", "style": {
                        "stroke_color": "#334455", "stroke_style": "DASH", "head_style": "ARROW",
                    }},
                ],
                expected_revision=2,
                current_revision=2,
            )
            mapped = build_diagram_design_system_map(path)["diagrams"][0]
            node = next(n for n in mapped["nodes"] if n["node_id"] == "input")
            edge = next(e for e in mapped["edges"] if e["source"] == "input" and e["target"] == "decision")
            self.assertEqual(node["effective_style"]["fill_color"], "#DDEEFF")
            self.assertEqual(node["effective_style"]["stroke_color"], "#112233")
            self.assertEqual(edge["effective_style"]["stroke_color"], "#334455")
            self.assertEqual(edge["effective_style"]["stroke_style"], "DASH")

    def test_layout_policy_and_parameterized_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            apply_diagram_design_system_atomic(
                path,
                [{
                    "op": "instantiate_styled_template",
                    "diagram_id": "styled",
                    "anchor": anchor,
                    "template": "linear_process",
                    "labels": {"start": "입력", "work": "검증", "end": "출력"},
                    "theme": "presentation",
                    "layout_policy": "compact",
                }],
                expected_revision=1,
                current_revision=1,
            )
            diagram = build_diagram_design_system_map(path)["diagrams"][0]
            labels = {n["node_id"]: n["label"] for n in diagram["nodes"]}
            self.assertEqual(labels["work"], "검증")
            xs = sorted(int(n["position"]["horzOffset"]) for n in diagram["nodes"])
            self.assertEqual(xs, [1000, 8600, 16200])

    def test_apply_design_system_and_fail_closed_private_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._template(path, anchor)
            apply_diagram_design_system_atomic(
                path,
                [{"op": "apply_design_system", "diagram_id": "d1", "theme": "mono", "layout_policy": "spacious"}],
                expected_revision=2,
                current_revision=2,
            )
            mapped = build_diagram_design_system_map(path)
            self.assertEqual(mapped["diagram_count"], 1)
            with self.assertRaisesRegex(ValueError, "EVIDENCE_GATE_CLOSED"):
                apply_diagram_design_system_atomic(
                    path,
                    [{"op": "persist_theme_name_in_private_xml"}],
                    expected_revision=3,
                    current_revision=3,
                )

    def test_contract(self):
        contract = diagram_design_system_contract()
        self.assertEqual(contract["phase"], "P3.30")
        self.assertEqual(contract["authority"], "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY")
        self.assertIn("classic", contract["themes"])
        self.assertIn("spacious", contract["layout_policies"])


if __name__ == "__main__":
    unittest.main()
