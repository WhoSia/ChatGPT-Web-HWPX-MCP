from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p323_advanced_tables import (
    advanced_table_contract,
    apply_advanced_table_edits_atomic,
    build_advanced_table_map,
)


class P323AdvancedTablesTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        path = root / "advanced-tables.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.23 advanced table fixture")
        table = doc.add_table(rows=3, cols=3)
        for r in range(3):
            for c in range(3):
                table.set_cell_text(r, c, f"R{r}C{c}")
        doc.save_to_path(str(path))
        doc.close()
        return path

    def test_repeat_header_row_height_and_vertical_alignment_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            before = build_advanced_table_map(path)
            table = before["tables"][0]
            target_cell = next(c["locator"] for c in table["cells"] if c["row"] == 1 and c["col"] == 1)

            result = apply_advanced_table_edits_atomic(
                path,
                [
                    {"op": "set_repeat_header", "table": table["locator"], "row": 0, "enabled": True},
                    {"op": "set_row_properties", "table": table["locator"], "row": 1, "height": 2400},
                    {
                        "op": "set_cell_vertical_alignment",
                        "table": table["locator"],
                        "cell": target_cell,
                        "alignment": "BOTTOM",
                    },
                    {"op": "set_table_page_break", "table": table["locator"], "mode": "TABLE"},
                ],
                expected_revision=4,
                current_revision=4,
            )
            self.assertTrue(result["advanced_table_layout_changed"])

            reopened = HwpxDocument.open(str(path))
            reopened.close()
            after = build_advanced_table_map(path)
            mapped = after["tables"][0]
            self.assertTrue(mapped["repeat_header"])
            self.assertEqual(mapped["page_break"], "TABLE")
            self.assertTrue(mapped["row_geometry"][0]["all_header"])
            self.assertEqual(mapped["row_geometry"][1]["heights"], [2400])
            cell = next(c for c in mapped["cells"] if c["row"] == 1 and c["col"] == 1)
            self.assertEqual(cell["vertical_alignment"], "BOTTOM")

    def test_column_insert_remains_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            table = build_advanced_table_map(path)["tables"][0]
            with self.assertRaisesRegex(ValueError, "SUPERSEDED_BY_P3.34_R1"):
                apply_advanced_table_edits_atomic(
                    path,
                    [{"op": "insert_column_by_clone", "table": table["locator"], "ref_col": 0}],
                    expected_revision=1,
                    current_revision=1,
                )

    def test_bounded_count_one_column_insert_is_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            before = build_advanced_table_map(path)
            table = before["tables"][0]
            anchor = next(c["locator"] for c in table["cells"] if c["row"] == 1 and c["col"] == 1)
            result = apply_advanced_table_edits_atomic(
                path,
                [{
                    "op": "insert_column_native_bounded",
                    "table": table["locator"],
                    "cell": anchor,
                    "direction": "LEFT",
                    "count": 1,
                }],
                expected_revision=3,
                current_revision=3,
            )
            self.assertTrue(result["table_structure_changed"])
            self.assertEqual(result["transcripts"][0]["authority"], "COUNT1_LEFT_RIGHT_NATIVE_COLUMN_INSERTION")
            after = build_advanced_table_map(path)["tables"][0]
            self.assertEqual(after["cols"], 4)
            inserted = next(c for c in after["cells"] if c["row"] == 1 and c["col"] == 1)
            self.assertEqual(inserted["text"], "")

            with self.assertRaisesRegex(ValueError, "exactly count=1"):
                apply_advanced_table_edits_atomic(
                    path,
                    [{
                        "op": "insert_column_native_bounded",
                        "table": after["locator"],
                        "cell": next(c["locator"] for c in after["cells"] if c["row"] == 1 and c["col"] == 2),
                        "direction": "RIGHT",
                        "count": 2,
                    }],
                    expected_revision=4,
                    current_revision=4,
                )

    def test_stale_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            table = build_advanced_table_map(path)["tables"][0]
            with self.assertRaisesRegex(ValueError, "Stale revision"):
                apply_advanced_table_edits_atomic(
                    path,
                    [{"op": "set_repeat_header", "table": table["locator"], "row": 0}],
                    expected_revision=1,
                    current_revision=2,
                )

    def test_contract_declares_structural_authority(self):
        contract = advanced_table_contract()
        self.assertEqual(contract["phase"], "P3.23")
        self.assertEqual(contract["authority"], "STRUCTURAL_AUTHORITY_ONLY")
        self.assertIn("insert_column_by_clone", contract["deferred_operations"])


if __name__ == "__main__":
    unittest.main()
