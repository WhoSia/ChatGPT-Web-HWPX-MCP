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

if __name__ == "__main__":
    unittest.main()
