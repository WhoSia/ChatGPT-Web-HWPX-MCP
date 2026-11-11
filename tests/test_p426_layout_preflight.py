"""P4.26 layout preflight: diagnostic geometry, not speculative rendering."""
from __future__ import annotations

import unittest
from hwpx_mcp.orchestration.p426_layout_preflight import assess_native_layout

class NativeLayoutPreflightTests(unittest.TestCase):
    def test_image_wider_than_a4_body_reports_review(self):
        result = assess_native_layout({"blocks": [
            {"id": "fig1", "type": "picture", "width": 60_000},
        ]}, "science-lab")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["issues"][0]["code"], "OBJECT_EXCEEDS_BODY_WIDTH")
        self.assertEqual(result["authority"], "STATIC_PREVIEW_ONLY_NOT_HANCOM_RENDER")

    def test_in_body_picture_has_no_width_warning(self):
        result = assess_native_layout({"blocks": [
            {"type": "picture", "width": 12_000},
        ]}, "academic-journal")
        self.assertEqual(result["status"], "NO_STATIC_WIDTH_FLAGS")
        self.assertEqual(result["issues"], [])

    def test_large_table_asks_for_layout_review(self):
        result = assess_native_layout({"sections": [
            {"blocks": [{"type": "table", "rows": 5, "cols": 12}]},
        ]})
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["issues"][0]["code"], "MANY_TABLE_COLUMNS")

    def test_long_table_with_cell_split_and_header_has_no_policy_warnings(self):
        result = assess_native_layout({"blocks": [{
            "type": "table", "rows": 80, "cols": 3,
            "first_row_header": True,
            "table_format": {"page_break": "CELL", "repeat_header": True},
        }]}, "science-lab")
        self.assertEqual(result["status"], "NO_STATIC_WIDTH_FLAGS")
        self.assertFalse(result["issues"])

    def test_long_table_with_no_split_and_header_reports_two_specific_risks(self):
        result = assess_native_layout({"blocks": [{
            "type": "table", "rows": 80, "cols": 3,
            "table_format": {"page_break": "TABLE", "repeat_header": False},
        }]}, "science-lab")
        codes = {issue["code"] for issue in result["issues"]}
        self.assertEqual(codes, {
            "LONG_TABLE_WITHOUT_CELL_SPLIT",
            "LONG_TABLE_WITHOUT_REPEATED_HEADER",
        })
        self.assertEqual(result["authority"], "STATIC_PREVIEW_ONLY_NOT_HANCOM_RENDER")

    def test_short_table_does_not_trigger_long_table_review(self):
        result = assess_native_layout({"blocks": [{
            "type": "table", "rows": 3, "cols": 2,
            "table_format": {"page_break": "TABLE", "repeat_header": False},
        }]})
        self.assertEqual(result["issues"], [])

    def test_invalid_native_object_width(self):
        result = assess_native_layout({"blocks": [
            {"type": "equation", "width": -1},
        ]})
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["issues"][0]["code"], "NATIVE_WIDTH_INVALID")

    def test_rejects_invalid_plan(self):
        with self.assertRaisesRegex(ValueError, "LAYOUT_PLAN_INVALID"):
            assess_native_layout("not a plan")

if __name__ == "__main__":
    unittest.main()
