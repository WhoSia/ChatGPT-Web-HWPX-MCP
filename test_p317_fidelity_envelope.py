from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p317_fidelity_envelope import (
    assess_edit_fidelity_envelope,
    production_fidelity_contract,
)
from p317_regression_corpus import materialize_p317_regression_corpus


class P317FidelityEnvelopeTests(unittest.TestCase):
    def test_contract_exposes_product_edit_classes(self):
        contract = production_fidelity_contract()
        names = {item["edit_class"] for item in contract["edit_classes"]}
        self.assertTrue({
            "text_content", "run_format", "paragraph_format", "table",
            "object_picture", "textbox", "equation", "page_section_geometry",
        }.issubset(names))

    def test_mixed_uncertified_plan_is_structural_only(self):
        result = assess_edit_fidelity_envelope([
            {"op": "set_range_format"},
            {"op": "create_table"},
            {"op": "insert_equation"},
        ])
        self.assertEqual(result["overall_authority_ceiling"], "STRUCTURAL_AUTHORITY_ONLY")
        self.assertTrue(result["native_render_check_required"])

    def test_unknown_operation_fails_open_to_review_not_exact(self):
        result = assess_edit_fidelity_envelope([{"op": "future_magic_edit"}])
        self.assertEqual(result["overall_authority_ceiling"], "UNCLASSIFIED_REQUIRES_REVIEW")
        self.assertTrue(result["native_render_check_required"])

    def test_inherited_page_geometry_is_version_indexed_boundary(self):
        result = assess_edit_fidelity_envelope([{"op": "set_page_margin"}])
        self.assertEqual(result["overall_authority_ceiling"], "VERSION_INDEXED_BOUNDARY")
        self.assertFalse(result["native_render_check_required"])

    def test_regression_corpus_materializes_real_hwpx_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = materialize_p317_regression_corpus(Path(tmp) / "p317")
            self.assertEqual(manifest["fixture_count"], 8)
            classes = {item["edit_class"] for item in manifest["fixtures"]}
            self.assertEqual(classes, {
                "text_content", "run_format", "paragraph_format", "table",
                "object_picture", "textbox", "page_section_geometry", "equation",
            })
            for item in manifest["fixtures"]:
                root = Path(tmp) / "p317" / item["fixture_id"]
                self.assertTrue((root / "source.hwpx").is_file())
                self.assertTrue((root / "target.hwpx").is_file())
                self.assertNotEqual(item["source_sha256"], item["target_sha256"])
            by_class = {item["edit_class"]: item for item in manifest["fixtures"]}
            self.assertIn("formatting_sha256", by_class["run_format"]["changed_runtime_dimensions"])
            self.assertIn("table_structure_sha256", by_class["table"]["changed_runtime_dimensions"])
            self.assertIn("object_structure_sha256", by_class["object_picture"]["changed_runtime_dimensions"])
            self.assertIn("page_geometry_sha256", by_class["page_section_geometry"]["changed_runtime_dimensions"])
            self.assertIn("equation_structure_sha256", by_class["equation"]["changed_runtime_dimensions"])


if __name__ == "__main__":
    unittest.main()
