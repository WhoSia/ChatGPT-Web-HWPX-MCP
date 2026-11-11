"""P4.27 R1: merged-anchor edits preserve unrelated native table state."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic,
    build_advanced_table_map,
)


def table_signature(table: dict) -> tuple:
    return (
        table["rows"], table["cols"], table["repeat_header"], table["page_break"],
        tuple((
            cell["row"], cell["col"], cell["row_span"], cell["col_span"],
            cell["text"], cell["width"], cell["height"],
            cell["border_fill_id_ref"], cell["header"], cell["vertical_alignment"],
        ) for cell in table["cells"]),
    )


class LosslessMergedTableEditingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p427-merged-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "original.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("Unrelated introductory paragraph")
        target = doc.add_table(rows=3, cols=3)
        for row in range(3):
            for col in range(3):
                target.set_cell_text(row, col, f"T{row}-{col}")
        target.merge_cells(0, 0, 0, 1)
        doc.add_paragraph("Unrelated post-table paragraph")
        other = doc.add_table(rows=2, cols=2)
        for row in range(2):
            for col in range(2):
                other.set_cell_text(row, col, f"Keep{row}-{col}")
        doc.save_to_path(str(self.path))
        doc.close()

    def edit(self, operations):
        return apply_advanced_table_edits_atomic(
            self.path, operations, expected_revision=2, current_revision=2
        )

    def test_merged_anchor_and_second_table_survive_native_header_edit(self):
        before = build_advanced_table_map(self.path)
        self.assertEqual(before["table_count"], 2)
        first, second = before["tables"]
        merged = [c for c in first["cells"] if c["col_span"] > 1]
        self.assertEqual(len(merged), 1)
        untouched_signature = table_signature(second)
        anchor_signature = (
            merged[0]["row"], merged[0]["col"], merged[0]["row_span"], merged[0]["col_span"],
            merged[0]["text"],
        )

        self.edit([{
            "op": "set_repeat_header", "table": first["locator"],
            "row": 0, "enabled": True,
        }])
        after = build_advanced_table_map(self.path)
        self.assertEqual(after["table_count"], 2)
        self.assertEqual(table_signature(after["tables"][1]), untouched_signature)
        updated_merged = next(c for c in after["tables"][0]["cells"]
                              if c["row"] == merged[0]["row"] and c["col"] == merged[0]["col"])
        self.assertEqual((
            updated_merged["row"], updated_merged["col"],
            updated_merged["row_span"], updated_merged["col_span"], updated_merged["text"]
        ), anchor_signature)
        self.assertTrue(after["tables"][0]["repeat_header"])

    def test_switching_repeat_header_row_removes_stale_native_header_flags(self):
        table = build_advanced_table_map(self.path)["tables"][0]
        self.edit([{
            "op": "set_repeat_header", "table": table["locator"],
            "row": 0, "enabled": True,
        }])
        first = build_advanced_table_map(self.path)["tables"][0]
        self.assertTrue(first["row_geometry"][0]["all_header"])

        self.edit([{
            "op": "set_repeat_header", "table": first["locator"],
            "row": 1, "enabled": True,
        }])
        second = build_advanced_table_map(self.path)["tables"][0]
        self.assertTrue(second["repeat_header"])
        self.assertFalse(second["row_geometry"][0]["all_header"])
        self.assertTrue(second["row_geometry"][1]["all_header"])

        self.edit([{
            "op": "set_repeat_header", "table": second["locator"],
            "row": 1, "enabled": False,
        }])
        disabled = build_advanced_table_map(self.path)["tables"][0]
        self.assertFalse(disabled["repeat_header"])
        self.assertFalse(any(row["all_header"] for row in disabled["row_geometry"]))

    def test_covered_cell_is_not_mutable_by_a_fabricated_locator(self):
        before = self.path.read_bytes()
        tables = build_advanced_table_map(self.path)["tables"]
        with self.assertRaisesRegex(ValueError, "Unknown cell locator"):
            self.edit([{
                "op": "set_cell_vertical_alignment",
                "table": tables[0]["locator"],
                "cell": "cell_covered_grid_slot_without_anchor",
                "alignment": "CENTER",
            }])
        self.assertEqual(hashlib.sha256(before).digest(),
                         hashlib.sha256(self.path.read_bytes()).digest())

    def test_stale_revision_rejected_without_touching_source(self):
        original = self.path.read_bytes()
        table = build_advanced_table_map(self.path)["tables"][0]
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            apply_advanced_table_edits_atomic(
                self.path,
                [{"op": "set_repeat_header", "table": table["locator"], "enabled": True}],
                expected_revision=1, current_revision=2
            )
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
