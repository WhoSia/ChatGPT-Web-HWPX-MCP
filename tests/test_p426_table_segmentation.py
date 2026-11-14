"""P4.26 renderer-driven response: optional native segmented long tables."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.orchestration.p426_table_pagination import segment_native_long_tables
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p323_advanced_tables import build_advanced_table_map


class P426TableSegmentationTests(unittest.TestCase):
    @staticmethod
    def _rows():
        return [["인덱스", "값", "내용"]] + [
            [str(i), str(i * 0.2), "장기 측정값"]
            for i in range(1, 80)
        ]

    def test_exact_data_preservation_and_logical_table_identity(self):
        grid = self._rows()
        source = [{
            "type": "table", "id": "measurements",
            "rows": 80, "cols": 3,
            "caption": "장기 측정 표",
            "first_row_header": True,
            "cells": grid,
            "table_format": {"page_break": "CELL", "repeat_header": True},
        }]
        segmented = segment_native_long_tables(source, max_rows_per_segment=20)
        self.assertEqual(segmented["segmented_table_count"], 1)
        self.assertEqual(segmented["segment_summaries"][0]["generated_segments"], 5)
        tables = [b for b in segmented["blocks"] if b["type"] == "table"]
        self.assertEqual(len(tables), 5)
        self.assertEqual([b["rows"] for b in tables], [20, 20, 20, 20, 4])
        self.assertEqual(sum(b["rows"] - 1 for b in tables), 79)
        self.assertEqual([b for t in tables for b in t["cells"][1:]], grid[1:])
        self.assertTrue(all(t["cells"][0] == grid[0] for t in tables))
        self.assertTrue(all(t["first_row_header"] for t in tables))
        self.assertTrue(all(t["table_format"]["repeat_header"] for t in tables))
        self.assertEqual(len([b for b in segmented["blocks"] if b["type"] == "page_break"]), 5)
        self.assertEqual([t["id"] for t in tables],
                         ["measurements"] + [f"measurements_segment_{i}" for i in range(2, 6)])
        self.assertEqual(source[0]["rows"], 80)
        self.assertEqual(len(source[0]["cells"]), 80)

    def test_numbering_uses_one_logical_table_caption(self):
        grid = self._rows()
        plan = build_report_plan(
            title="분할 표", segment_long_tables=True,
            table_segment_rows=20, number_captions=True,
            sections=[{"heading": "결과", "content": [
                {"type": "table", "id": "measurements",
                 "first_row_header": True, "caption": "연속 측정",
                 "cells": grid},
                {"type": "table", "first_row_header": True,
                 "caption": "별도 표", "cells": [["a"], ["b"]]},
            ]}],
        )
        tables = [b for b in plan["sections"][0]["blocks"] if b["type"] == "table"]
        self.assertEqual(len(tables), 6)
        self.assertEqual([b["caption"] for b in tables],
                         ["표 1. 연속 측정"] +
                         ["표 1. 연속 측정 (계속)"] * 4 +
                         ["표 2. 별도 표"])

    def test_real_hwpx_contains_five_native_tables_instead_of_clipped_one(self):
        plan = build_report_plan(
            title="분할 품질 검증", layout="science-lab",
            segment_long_tables=True, table_segment_rows=20,
            sections=[{"heading": "결과", "content": [{
                "type": "table", "caption": "장기 측정",
                "first_row_header": True, "cells": self._rows(),
            }]}],
        )
        compiled = compile_rich_document_plan(plan)
        self.assertEqual(compiled["block_counts"]["table"], 5)
        self.assertEqual(compiled["block_counts"]["page_break"], 5)
        with tempfile.TemporaryDirectory(prefix="p426-segmented-tables-") as tmp:
            target = Path(tmp) / "segmented.hwpx"
            result = compose_document_plan(target, compiled["plan"])
            self.assertTrue(result["atomic_commit"])
            found = build_advanced_table_map(target)["tables"]
            self.assertEqual(len(found), 5)
            self.assertEqual(sum(table["rows"] - 1 for table in found), 79)
            self.assertTrue(all(t["repeat_header"] and t["page_break"] == "CELL"
                                for t in found))

    def test_refuses_headerless_table_and_invalid_chunk_budget(self):
        with self.assertRaisesRegex(ValueError, "REQUIRES_HEADER"):
            segment_native_long_tables([{
                "type": "table", "rows": 80, "cols": 1,
                "cells": [[str(i)] for i in range(80)],
            }])
        with self.assertRaisesRegex(ValueError, "ROWS_INVALID"):
            segment_native_long_tables([], max_rows_per_segment=4)


if __name__ == "__main__":
    unittest.main()
