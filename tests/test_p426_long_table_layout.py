"""P4.26 long native table break policy and repeated header acceptance.

This asserts persisted HWPX table properties, not renderer page count.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p323_advanced_tables import build_advanced_table_map


class NativeLongTableTests(unittest.TestCase):
    @staticmethod
    def _rows(count: int) -> list[list[str]]:
        return [["회차", "측정값", "설명"]] + [
            [str(i), f"{i * 0.125:.3f}", f"합성 측정 기록 {i}"]
            for i in range(1, count)
        ]

    def test_real_long_table_persists_cell_break_and_repeated_header(self):
        rows = self._rows(80)
        requested = build_report_plan(
            title="장기 실험 데이터",
            layout="academic-journal",
            sections=[{"heading": "연속 측정", "content": [
                {"type": "paragraph", "text": "80행 측정 데이터"},
                {"type": "table", "caption": "연속 측정 표",
                 "first_row_header": True,
                 "table_format": {
                     "page_break": "CELL", "repeat_header": True,
                     "border_color": "#345C79",
                 },
                 "cells": rows},
            ]}],
        )
        compiled = compile_rich_document_plan(requested)
        with tempfile.TemporaryDirectory(prefix="p426-long-table-") as tmp:
            out = Path(tmp) / "long_table.hwpx"
            receipt = compose_document_plan(out, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            tables = build_advanced_table_map(out)["tables"]
            self.assertEqual(len(tables), 1)
            table = tables[0]
            self.assertEqual(table["rows"], 80)
            self.assertEqual(table["page_break"], "CELL")
            self.assertTrue(table["repeat_header"])
            self.assertTrue(table["row_geometry"][0]["all_header"])
            self.assertEqual(len(table["cells"]), 80 * 3)

    def test_native_table_policy_precedence_is_explicit(self):
        request = build_report_plan(
            title="표 정책",
            sections=[{"heading": "검토", "tables": [{
                "cells": [["열 A", "열 B"], ["첫째", "둘째"]],
                "width": 32000,
                "first_row_header": True,
                "table_format": {
                    "page_break": "TABLE", "repeat_header": False,
                    "border_color": "ABCDEF",
                },
            }]}],
        )
        table = request["sections"][0]["blocks"][-1]
        self.assertEqual(table["width"], 32000)
        self.assertEqual(table["table_format"], {
            "page_break": "TABLE", "repeat_header": False,
            "border_color": "#ABCDEF",
        })

    def test_invalid_table_layout_fails_before_creating_a_document(self):
        cases = [
            {"width": -1},
            {"table_format": {"page_break": "WRONG"}},
            {"table_format": {"repeat_header": "yes"}},
            {"table_format": {"border_color": "not-a-color"}},
            {"table_format": {"hidden_native_field": 7}},
        ]
        for extras in cases:
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                build_report_plan(
                    title="잘못된 표",
                    sections=[{"heading": "결과", "tables": [{
                        "cells": [["제목"], ["본문"]], **extras,
                    }]}],
                )


if __name__ == "__main__":
    unittest.main()
