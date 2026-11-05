"""Product acceptance tests for declarative native EqEdit cases authoring."""
import unittest

from hwpx_mcp.document.p423_piecewise_authoring import build_piecewise_script


class P423PiecewiseAuthoringTests(unittest.TestCase):
    def test_two_rows_use_structural_alignment(self):
        result = build_piecewise_script([
            {"expression": "x", "condition": "x>0"},
            {"expression": "0", "condition": "x\\leq0"},
        ])
        self.assertEqual(result.script, "cases {x & x > 0 # 0 & x leq 0}")
        self.assertEqual(result.row_count, 2)

    def test_no_conditions_single_column(self):
        result = build_piecewise_script([{"expression": "x"}, {"expression": "0"}])
        self.assertEqual(result.script, "cases {x # 0}")
        self.assertFalse(result.has_conditions)
    def test_optional_gap_is_explicit_only(self):
        result = build_piecewise_script([{"expression": "x", "condition": "x>0"}], condition_gap=2)
        self.assertEqual(result.script, "cases {x & ~~x > 0}")
    def test_rejects_ampersand_in_user_expression(self):
        with self.assertRaises(ValueError):
            build_piecewise_script([{"expression": "x&y", "condition": "x>0"}])
    def test_rejects_row_separator_in_user_condition(self):
        with self.assertRaisesRegex(ValueError, "unsupported character"):
            build_piecewise_script([{"expression": "x", "condition": "x#0"}])
    def test_rejects_mixed_condition_columns(self):
        with self.assertRaisesRegex(ValueError, "consistently"):
            build_piecewise_script([{"expression": "x", "condition": "x>0"}, {"expression": "0"}])
    def test_rejects_floating_spacing_value(self):
        with self.assertRaisesRegex(ValueError, "condition_gap"):
            build_piecewise_script([{"expression": "x", "condition": "x>0"}], condition_gap=1.5)
    def test_rejects_gap_without_conditions(self):
        with self.assertRaisesRegex(ValueError, "condition_gap"):
            build_piecewise_script([{"expression": "x"}], condition_gap=1)
    def test_rejects_unsupported_latex(self):
        with self.assertRaises(Exception):
            build_piecewise_script([{"expression": r"\notarealcommand", "condition": "x>0"}])

    def test_nested_matrix_does_not_fake_case_condition(self):
        result = build_piecewise_script([
            {"expression": r"\begin{matrix}a&b\\c&d\end{matrix}"},
            {"expression": "0"},
        ])
        self.assertFalse(result.has_conditions)
        self.assertTrue(result.script.startswith("cases {matrix {"))

    def test_plain_korean_conditions_compile_to_upright_text(self):
        result = build_piecewise_script([
            {"expression": "1", "condition_text": "양수"},
            {"expression": "0", "condition_text": "그 외"},
        ])
        self.assertTrue(result.has_conditions)
        self.assertIn('rm "양수" it', result.script)

    def test_plain_text_cannot_inject_eqedit_grid(self):
        with self.assertRaisesRegex(ValueError, "control characters"):
            build_piecewise_script([{"expression": "x", "condition_text": "x & y"}])

    def test_explicit_and_plain_conditions_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "cannot combine"):
            build_piecewise_script([{"expression": "x", "condition": "x>0", "condition_text": "양수"}])

    def test_mixed_plain_text_and_latex_conditions(self):
        result = build_piecewise_script([
            {"expression": "x", "condition": "x>0"},
            {"expression": "0", "condition_text": "그 외"},
        ])
        self.assertEqual(result.row_count, 2)
        self.assertTrue(result.has_conditions)

if __name__ == "__main__":
    unittest.main()
