"""P4.26 opted-in spacing normalization and real native equation authoring."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.equations.p426_latex_compatibility import normalize_equation_latex
from hwpx_mcp.interfaces.p426_equation_experience import describe_equation
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p210_equations import build_equation_map


class P426EquationCompatibilityTests(unittest.TestCase):
    def test_strict_does_not_modify_input(self):
        raw = r"\int_0^1 x^2\,dx"
        result = normalize_equation_latex(raw)
        self.assertEqual(result["normalized_latex"], raw)
        self.assertEqual(result["removed_spacing_commands"], [])
        with self.assertRaisesRegex(ValueError, "LATEX_TO_EQEDIT_UNSUPPORTED"):
            describe_equation(raw, policy="strict")

    def test_opt_in_portable_drops_only_spacing_commands(self):
        raw = r"\int_0^1 x^2\,dx"
        info = describe_equation(raw, policy="portable")
        self.assertTrue(info["eqedit_script"])
        self.assertEqual(info["compatibility"]["removed_spacing_commands"], [r"\,"])
        self.assertTrue(info["compatibility"]["spacing_adjusted"])
        self.assertFalse(info["compatibility"]["visual_spacing_preserved"])
        self.assertIn(r"\int", info["normalized_latex"])

    def test_structural_macros_remain_unchanged(self):
        raw = r"\frac{a}{b}+\sqrt{c}\quad d"
        info = normalize_equation_latex(raw, "portable")
        self.assertIn(r"\frac{a}{b}", info["normalized_latex"])
        self.assertIn(r"\sqrt{c}", info["normalized_latex"])
        self.assertEqual(info["removed_spacing_commands"], [r"\quad"])

    def test_unsupported_math_does_not_silently_change(self):
        raw = r"\unsupportedCommand{x}"
        info = normalize_equation_latex(raw, "portable")
        self.assertEqual(info["normalized_latex"], raw)
        with self.assertRaises(Exception):
            describe_equation(raw, policy="portable")

    def test_native_report_portable_equation_survives_roundtrip(self):
        plan = build_report_plan(title="적분식", sections=[{
            "heading": "이론",
            "content": [
                {"type": "equation", "latex": r"\int_0^1 x^2\,dx",
                 "policy": "portable", "caption": "정적분"},
            ],
        }])
        equation = plan["sections"][0]["blocks"][-1]
        self.assertEqual(equation["type"], "equation")
        self.assertEqual(equation["spacing_normalization"], [r"\,"])
        compiled = compile_rich_document_plan(plan)
        with tempfile.TemporaryDirectory(prefix="p426-portable-math-") as tmp:
            path = Path(tmp) / "math.hwpx"
            receipt = compose_document_plan(path, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            saved = build_equation_map(path)
            self.assertEqual(saved["equation_count"], 1)
            self.assertTrue(saved["equations"][0]["script"].strip())


if __name__ == "__main__":
    unittest.main()
