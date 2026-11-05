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
        with self.assertRaisesRegex(ValueError, "alignment separators"):
            build_piecewise_script([{"expression": "x&y", "condition": "x>0"}])
    def test_rejects_row_separator_in_user_condition(self):
        with self.assertRaisesRegex(ValueError, "alignment separators"):
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
            build_piecewise_script([{"expression": r"\\notarealcommand", "condition": "x>0"}])

if __name__ == "__main__":
    unittest.main()
