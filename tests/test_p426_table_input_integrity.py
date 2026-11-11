"""P4.26: strict typed table mutations must not silently rewrite native HWPX."""
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


class NativeTableInputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p426-strict-tables-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "original.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("Stable user document")
        table = doc.add_table(rows=2, cols=2)
        for row in range(2):
            for col in range(2):
                table.set_cell_text(row, col, f"Cell {row}-{col}")
        doc.save_to_path(str(self.path))
        doc.close()
        self.table = build_advanced_table_map(self.path)["tables"][0]["locator"]

    def digest(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def mutate(self, operation):
        return apply_advanced_table_edits_atomic(
            self.path, [{"table": self.table, **operation}],
            expected_revision=3, current_revision=3,
        )

    def test_malformed_boolean_flags_rejected_without_original_changes(self):
        for operation in (
            {"op": "set_repeat_header", "row": 0, "enabled": "false"},
            {"op": "set_repeat_header", "row": 0, "enabled": 0},
            {"op": "set_row_properties", "row": 0, "header": "false"},
            {"op": "set_row_properties", "row": 0, "header": 1},
        ):
            with self.subTest(operation=operation):
                before = self.digest()
                with self.assertRaisesRegex(ValueError, "must be a boolean"):
                    self.mutate(operation)
                self.assertEqual(self.digest(), before)

    def test_bad_rows_and_heights_rejected_without_original_changes(self):
        for operation in (
            {"op": "set_repeat_header", "row": True},
            {"op": "set_row_properties", "row": "1", "header": True},
            {"op": "set_row_properties", "row": 0, "height": "1200"},
            {"op": "set_row_properties", "row": 0, "height": True},
            {"op": "set_row_properties", "row": 0, "height": 0},
        ):
            with self.subTest(operation=operation):
                before = self.digest()
                with self.assertRaises(ValueError):
                    self.mutate(operation)
                self.assertEqual(self.digest(), before)

    def test_actual_false_disables_repeat_header_after_reopen(self):
        self.mutate({"op": "set_repeat_header", "row": 0, "enabled": True})
        self.assertTrue(build_advanced_table_map(self.path)["tables"][0]["repeat_header"])
        self.mutate({"op": "set_repeat_header", "row": 0, "enabled": False})
        after = build_advanced_table_map(self.path)["tables"][0]
        self.assertFalse(after["repeat_header"])
        self.assertFalse(after["row_geometry"][0]["all_header"])

    def test_native_row_height_and_boolean_header_roundtrip(self):
        self.mutate({"op": "set_row_properties", "row": 1, "header": True, "height": 2500})
        after = build_advanced_table_map(self.path)["tables"][0]
        self.assertTrue(after["row_geometry"][1]["all_header"])
        self.assertEqual(after["row_geometry"][1]["heights"], [2500])


if __name__ == "__main__":
    unittest.main()
