"""Exercise checked batch edits on a reusable equation-heavy report fixture."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.custody.p427_structured_edit_preservation import (
    apply_bounded_table_edits_with_preservation_atomic,
    preview_preserved_table_batch,
)
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p323_advanced_tables import build_advanced_table_map
from scripts.p426_generate_native_showcase import create_showcase


class ReportEditAcceptanceTests(unittest.TestCase):
    def test_edits_in_two_table_segments_preserve_equations_and_other_cells(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixture = create_showcase(directory)
            path = directory / fixture["filename"]
            original = path.read_bytes()
            equations = build_equation_map(path)["equations"]
            self.assertEqual(len(equations), 2)
            before = build_advanced_table_map(path)["tables"]
            self.assertEqual(len(before), 3)

            operations = []
            targets = {}
            for table, replacement in zip((before[0], before[-1]), ("11.125", "39.625")):
                cell = next(c for c in table["cells"] if (c["row"], c["col"]) == (1, 0))
                targets[cell["locator"]] = (cell["text"], replacement)
                operations.append({
                    "op": "set_cell_text", "table": table["locator"],
                    "cell": cell["locator"], "text": replacement,
                })

            preview = preview_preserved_table_batch(path, operations, revision=1)
            self.assertEqual(path.read_bytes(), original)
            saved = apply_bounded_table_edits_with_preservation_atomic(
                path, operations, expected_revision=1, current_revision=1,
            )
            self.assertEqual(preview["changes"], saved["changes"])
            self.assertEqual(len(saved["changes"]), 2)
            self.assertEqual(preview["candidate_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            for change in saved["changes"]:
                self.assertEqual((change["before"], change["after"]), targets[change["cell"]])

            self.assertEqual(build_equation_map(path)["equations"], equations)
            after = build_advanced_table_map(path)["tables"]
            self.assertEqual(len(after), len(before))
            for old, new in zip(before, after, strict=True):
                self.assertEqual((old["rows"], old["cols"]), (new["rows"], new["cols"]))
                self.assertEqual(old["repeat_header"], new["repeat_header"])
                for old_cell, new_cell in zip(old["cells"], new["cells"], strict=True):
                    expected_text = targets.get(old_cell["locator"], (None, old_cell["text"]))[1]
                    self.assertEqual(new_cell["text"], expected_text)
