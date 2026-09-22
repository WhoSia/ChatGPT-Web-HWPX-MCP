from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic
from p330_diagram_design_system import apply_diagram_design_system_atomic
from p331_diagram_quality_assurance import (
    apply_diagram_repairs_atomic,
    build_diagram_quality_map,
    diagram_quality_assurance_contract,
    plan_diagram_repairs,
    validate_diagram_quality,
)


class DiagramQualityAssuranceTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> tuple[Path, str]:
        path = directory / "p331.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.31 anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.31 anchor")
        return path, anchor

    def _linear(self, path: Path, anchor: str, diagram_id: str = "qa") -> None:
        apply_diagram_lifecycle_atomic(
            path,
            [{"op": "instantiate_template", "diagram_id": diagram_id, "anchor": anchor, "template": "linear_process"}],
            expected_revision=1,
            current_revision=1,
        )

    def test_flow_profile_passes_styled_linear_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._linear(path, anchor)
            apply_diagram_design_system_atomic(
                path,
                [{"op": "apply_design_system", "diagram_id": "qa", "theme": "presentation", "layout_policy": "standard"}],
                expected_revision=2,
                current_revision=2,
            )
            report = validate_diagram_quality(path, "qa", profile="flow", expected_theme="presentation")
            self.assertTrue(report["passed"])
            self.assertEqual(report["error_count"], 0)
            self.assertEqual(report["warning_count"], 0)
            self.assertEqual(report["graph_summary"]["sources"], ["start"])
            self.assertEqual(report["graph_summary"]["sinks"], ["end"])

    def test_detects_disconnect_cycle_degree_and_label_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._linear(path, anchor)
            apply_diagram_lifecycle_atomic(
                path,
                [
                    {"op": "add_node", "diagram_id": "qa", "node_id": "isolated", "node_type": "process", "label": "   ", "x": 50000, "y": 1000},
                    {"op": "add_edge", "diagram_id": "qa", "source": "end", "target": "start"},
                ],
                expected_revision=2,
                current_revision=2,
            )
            report = validate_diagram_quality(
                path, "qa", profile="flow", constraints={"max_out_degree": 1}
            )
            codes = {x["code"] for x in report["findings"]}
            self.assertFalse(report["passed"])
            self.assertIn("EMPTY_LABEL", codes)
            self.assertIn("DISCONNECTED_GRAPH", codes)
            self.assertIn("ISOLATED_NODE", codes)
            self.assertIn("CYCLE_PRESENT", codes)

    def test_theme_mismatch_and_safe_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._linear(path, anchor)
            before = validate_diagram_quality(path, "qa", expected_theme="presentation")
            self.assertIn("NODE_THEME_MISMATCH", {x["code"] for x in before["findings"]})
            plan = plan_diagram_repairs(
                path, "qa", expected_theme="presentation", repair_theme="presentation"
            )
            self.assertEqual(plan["operation_count"], 1)
            apply_diagram_repairs_atomic(
                path,
                plan,
                expected_revision=2,
                current_revision=2,
            )
            after = validate_diagram_quality(path, "qa", expected_theme="presentation")
            self.assertNotIn("NODE_THEME_MISMATCH", {x["code"] for x in after["findings"]})
            self.assertNotIn("EDGE_THEME_MISMATCH", {x["code"] for x in after["findings"]})

    def test_overlap_detected_and_layout_repair_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._linear(path, anchor)
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "patch_node", "diagram_id": "qa", "node_id": "work", "x": 5000, "y": 1000}],
                expected_revision=2,
                current_revision=2,
            )
            report = validate_diagram_quality(path, "qa", profile="baseline")
            self.assertIn("NATIVE_BBOX_OVERLAP", {x["code"] for x in report["findings"]})
            plan = plan_diagram_repairs(
                path, "qa", repair_layout_policy="standard", layout="LEFT_TO_RIGHT"
            )
            self.assertEqual(plan["operations"][0]["op"], "apply_layout_policy")

    def test_quality_map_and_deferred_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._fixture(Path(tmp))
            self._linear(path, anchor)
            mapped = build_diagram_quality_map(path)
            self.assertEqual(mapped["diagram_count"], 1)
            self.assertTrue(mapped["quality_sha256"])
            contract = diagram_quality_assurance_contract()
            self.assertEqual(contract["phase"], "P3.31")
            self.assertIn("color_contrast_accessibility", contract["deferred_operations"])


if __name__ == "__main__":
    unittest.main()
