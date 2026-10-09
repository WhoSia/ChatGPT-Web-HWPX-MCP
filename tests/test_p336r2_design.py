from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p23_richtext import apply_rich_formatting_atomic
from p321_document_composer import compose_document_plan
from p323_advanced_tables import build_advanced_table_map
from p336r2_design import (
    compile_design_plan,
    design_quality_contract,
    evaluate_generated_document,
    infer_presentation_roles,
    paragraph_features_from_hwpx,
)


class P336R2DesignTests(unittest.TestCase):
    def test_presentation_roles_use_formatting_not_prose_semantics(self):
        rows = [
            {"locator": "p0", "size_pt": 22, "bold_share": 1.0, "alignment": "CENTER", "container": "body"},
            {"locator": "p1", "size_pt": 11, "bold_share": 0.0, "alignment": "JUSTIFY", "container": "body"},
            {"locator": "p2", "size_pt": 14, "bold_share": 0.8, "alignment": "LEFT", "container": "body"},
            {"locator": "p3", "size_pt": 11, "bold_share": 0.0, "alignment": "JUSTIFY", "container": "body"},
        ]
        profile = infer_presentation_roles(rows)
        self.assertEqual(profile["hypotheses"][0]["presentation_role"], "TITLE")
        self.assertEqual(profile["hypotheses"][2]["presentation_role"], "HEADING")
        self.assertFalse(profile["content_semantics_used"])
        self.assertFalse(profile["recovery"]["applied"])
        self.assertEqual(
            profile["authority"],
            "PRESENTATION_ROLE_HYPOTHESIS_NOT_NATIVE_SEMANTIC_FACT",
        )

    def test_nested_title_recovers_only_when_primary_hierarchy_is_empty(self):
        rows = [
            {"locator": "p0", "size_pt": 11, "bold_share": 0.0, "alignment": "JUSTIFY", "container": "body"},
            {
                "locator": "p1", "size_pt": 18, "bold_share": 0.0, "alignment": "CENTER",
                "container": "subList", "nested_container": True, "in_table": True,
            },
            {
                "locator": "p2", "size_pt": 11, "bold_share": 1.0, "alignment": "CENTER",
                "container": "subList", "nested_container": True, "in_table": True,
            },
            {"locator": "p3", "size_pt": 11, "bold_share": 0.0, "alignment": "JUSTIFY", "container": "body"},
        ]
        profile = infer_presentation_roles(rows)
        self.assertEqual(profile["primary_hierarchy_count"], 0)
        self.assertTrue(profile["recovery"]["applied"])
        self.assertEqual(profile["recovery"]["strategy"], "EARLY_NESTED_SIZE_CENTER_TITLE")
        self.assertEqual(profile["hypotheses"][1]["presentation_role"], "TITLE")
        self.assertEqual(profile["final_hierarchy_count"], 1)

        existing = [
            {"locator": "a", "size_pt": 30, "bold_share": 1.0, "alignment": "CENTER", "container": "body"},
            {
                "locator": "b", "size_pt": 20, "bold_share": 1.0, "alignment": "CENTER",
                "container": "subList", "nested_container": True, "in_table": True,
            },
            {"locator": "c", "size_pt": 11, "bold_share": 0.0, "alignment": "JUSTIFY", "container": "body"},
        ]
        preserved = infer_presentation_roles(existing)
        self.assertGreater(preserved["primary_hierarchy_count"], 0)
        self.assertFalse(preserved["recovery"]["applied"])
        self.assertNotEqual(preserved["hypotheses"][1]["presentation_role"], "TITLE")

    def test_nested_bold_header_fallback_recovers_one_heading(self):
        rows = [
            {"locator": "p0", "size_pt": 11, "bold_share": 0.0, "alignment": "JUSTIFY", "container": "body"},
            {
                "locator": "p1", "size_pt": 11, "bold_share": 1.0, "alignment": "CENTER",
                "container": "subList", "nested_container": True, "in_table": True,
            },
            {
                "locator": "p2", "size_pt": 11, "bold_share": 1.0, "alignment": "CENTER",
                "container": "subList", "nested_container": True, "in_table": True,
            },
        ]
        profile = infer_presentation_roles(rows)
        self.assertEqual(profile["recovery"]["strategy"], "EARLY_NESTED_BOLD_CENTER_HEADER")
        self.assertEqual(profile["final_hierarchy_count"], 1)
        self.assertEqual(
            sum(item["presentation_role"] == "HEADING" for item in profile["hypotheses"]),
            1,
        )

    def test_polished_design_compiler_preserves_content_and_adds_table_policy(self):
        plan = {
            "preset": "default",
            "blocks": [
                {"id": "t", "type": "title", "text": "Quarterly Review"},
                {"id": "h", "type": "heading", "level": 1, "text": "Overview"},
                {"id": "p", "type": "paragraph", "text": "Body"},
                {
                    "id": "tbl",
                    "type": "table",
                    "rows": 3,
                    "cols": 2,
                    "first_row_header": True,
                    "cells": [["A", "B"], ["1", "2"], ["3", "4"]],
                },
            ],
        }
        compiled = compile_design_plan(plan, "POLISHED_REPORT")
        out = compiled["plan"]
        self.assertEqual(out["preset"], "polished-report")
        self.assertEqual(out["blocks"][0]["text"], plan["blocks"][0]["text"])
        table = out["blocks"][-1]["table_format"]
        self.assertTrue(table["repeat_header"])
        self.assertEqual(table["page_break"], "CELL")
        self.assertEqual(compiled["authority"], "EXPLICIT_HUMAN_DESIGN_TARGET")

    def test_composer_applies_table_finishing_and_benchmark_has_no_beauty_score(self):
        base = {
            "preset": "default",
            "blocks": [
                {"id": "title", "type": "title", "text": "Generated Quality Benchmark"},
                {"id": "heading", "type": "heading", "level": 1, "text": "Results"},
                {"id": "body", "type": "paragraph", "text": "A concise generated document."},
                {
                    "id": "table",
                    "type": "table",
                    "rows": 14,
                    "cols": 2,
                    "first_row_header": True,
                    "cells": [["Metric", "Value"]] + [[f"M{i}", str(i)] for i in range(13)],
                },
            ],
        }
        compiled = compile_design_plan(base, "POLISHED_REPORT")["plan"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "generated.hwpx"
            receipt = compose_document_plan(path, compiled)
            mapped = build_advanced_table_map(path)
            benchmark = evaluate_generated_document(path, "POLISHED_REPORT")

        self.assertEqual(receipt["preset"], "polished-report")
        self.assertEqual(mapped["table_count"], 1)
        self.assertTrue(mapped["tables"][0]["repeat_header"])
        self.assertEqual(mapped["tables"][0]["page_break"], "CELL")
        self.assertEqual(benchmark["mechanical_verdict"], "PASS")
        self.assertEqual(benchmark["aesthetic_verdict"], "NOT_ADJUDICATED")
        self.assertNotIn("score", benchmark)

    def test_real_generated_nested_title_recovery_for_both_design_modes(self):
        base = {
            "preset": "default",
            "blocks": [
                {"id": "body", "type": "paragraph", "text": "Body text"},
                {
                    "id": "table",
                    "type": "table",
                    "rows": 14,
                    "cols": 2,
                    "first_row_header": True,
                    "cells": [["Nested report title", ""]] + [[f"M{i}", str(i)] for i in range(13)],
                },
            ],
        }
        for mode in ("INSTITUTIONAL_COMPATIBILITY", "POLISHED_REPORT"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{mode.lower()}.hwpx"
                plan = compile_design_plan(base, mode)["plan"]
                compose_document_plan(path, plan)
                nested = next(item for item in paragraph_features_from_hwpx(path) if item["in_table"])
                apply_rich_formatting_atomic(
                    path,
                    [
                        {"op": "set_run_format", "target": nested["locator"], "format": {"size": 18}},
                        {"op": "set_paragraph_format", "target": nested["locator"], "format": {"alignment": "CENTER"}},
                    ],
                    expected_revision=1,
                    current_revision=1,
                    validator=None,
                )
                benchmark = evaluate_generated_document(path, mode)
                roles = benchmark["presentation_roles"]
                self.assertEqual(benchmark["mechanical_verdict"], "PASS")
                self.assertTrue(roles["recovery"]["applied"])
                self.assertEqual(roles["recovery"]["strategy"], "EARLY_NESTED_SIZE_CENTER_TITLE")
                self.assertGreaterEqual(roles["final_hierarchy_count"], 1)
                self.assertEqual(benchmark["aesthetic_verdict"], "NOT_ADJUDICATED")

    def test_contract_keeps_explicit_human_target_above_prevalence(self):
        contract = design_quality_contract()
        self.assertEqual(contract["authority_ladder"][-1], "EXPLICIT_HUMAN_DESIGN_TARGET")
        self.assertIn("cannot", contract["aesthetic_policy"].lower())
        self.assertIn("multi-container", contract["benchmark_policy"].lower())


if __name__ == "__main__":
    unittest.main()
