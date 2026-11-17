"""Saved HWPX checks for the preserved table batch boundary."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument
from hwpx_mcp.custody.p427_structured_edit_preservation import (
    MAX_PRESERVED_TABLE_BATCH,
    apply_bounded_table_edits_with_preservation_atomic,
    preview_preserved_table_batch,
    preserved_table_batch_plan_sha256,
)
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic, build_advanced_table_map,
)

from test_p427_nested_table_in_cell import make_nested_fixture, raw_nested_table_count


class PreservedTableBatchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="p427-batch-test-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "original.hwpx"
        make_nested_fixture(self.path)
        self.original = self.path.read_bytes()
        host, self.child = build_advanced_table_map(self.path)["tables"]
        self.peer = {
            "op": "set_cell_text", "table": host["locator"],
            "cell": host["cells"][1]["locator"], "text": "변경한 이웃 셀",
        }
        self.phrase = {
            "op": "replace_cell_phrase", "table": self.child["locator"],
            "cell": self.child["cells"][0]["locator"], "paragraph_index": 0,
            "old_text": "Inner", "new_text": "Reviewed",
        }

    def batch(self, operations, validator=None):
        return apply_bounded_table_edits_with_preservation_atomic(
            self.path, operations, expected_revision=2, current_revision=2,
            candidate_validator=validator,
        )

    def assert_unchanged(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_mixed_operations_preserve_nested_table_and_validate_final_bytes_once(self):
        validated = []

        def validate(candidate):
            validated.append(candidate.read_bytes())
            return {"sha256": hashlib.sha256(validated[-1]).hexdigest()}

        page_break = {"op": "set_table_page_break", "table": self.child["locator"], "mode": "TABLE"}
        result = self.batch([self.peer, self.phrase, page_break], validate)
        self.assertEqual(result["operation_count"], 3)
        self.assertEqual(validated, [self.path.read_bytes()])
        self.assertEqual(result["committed_sha256"], result["package_validation"]["sha256"])
        self.assertEqual(result["mutation_footprint"]["observed"]["changed_parts"],
                         [self.child["section_path"]])
        self.assertEqual(raw_nested_table_count(self.path), 1)
        host, child = build_advanced_table_map(self.path)["tables"]
        self.assertEqual(host["cells"][1]["text"], "변경한 이웃 셀")
        self.assertTrue(child["cells"][0]["text"].startswith("Reviewed"))
        self.assertEqual(child["page_break"], "TABLE")

    def test_later_invalid_operation_leaves_source_and_cleans_candidate(self):
        invalid = {**self.phrase, "old_text": "absent"}
        with self.assertRaisesRegex(ValueError, "P427_BATCH_OPERATION_FAILED:1"):
            self.batch([self.peer, invalid])
        self.assert_unchanged()

    def test_final_validation_cannot_rewrite_an_earlier_edited_cell(self):
        def rewrite_prior_edit(candidate):
            apply_advanced_table_edits_atomic(
                candidate, [{**self.peer, "text": "Undeclared change"}],
                expected_revision=2, current_revision=2,
            )

        with self.assertRaisesRegex(ValueError, "P427_BATCH_OPERATION_FAILED:1.*SEMANTIC_DRIFT"):
            self.batch([self.peer, self.phrase], rewrite_prior_edit)
        self.assert_unchanged()

    def test_rejects_oversized_empty_and_repeated_targets(self):
        for operations, error in (
            ([], "SIZE_INVALID"),
            ([self.peer] * (MAX_PRESERVED_TABLE_BATCH + 1), "SIZE_INVALID"),
            ([self.peer, {**self.peer, "text": "또 변경"}], "TARGET_REPEATED:1"),
        ):
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, error):
                    self.batch(operations)
                self.assert_unchanged()

    def test_preview_reports_actual_checked_changes_without_replacing_source(self):
        mode = {"op": "set_table_page_break", "table": self.child["locator"], "mode": "TABLE"}
        result = preview_preserved_table_batch(self.path, [self.phrase, mode], revision=2)
        first, second = result["changes"]
        self.assertIn("Inner", first["before"])
        self.assertIn("Reviewed", first["after"])
        self.assertEqual(first["paragraph_index"], 0)
        self.assertEqual(second["after"], "TABLE")
        self.assertEqual(result["changed_sections"], [self.child["section_path"]])
        self.assertEqual(result["preservation_grade"], "TARGETED_PARTS_ONLY")
        self.assert_unchanged()

    def test_preview_bounds_cell_text_and_refuses_failed_operations(self):
        large = {**self.peer, "text": "값" * 500}
        change = preview_preserved_table_batch(self.path, [large], revision=2)["changes"][0]
        self.assertEqual(change["after"], "값" * 240)
        self.assertTrue(change["text_truncated"])
        with self.assertRaisesRegex(ValueError, "P427_BATCH_OPERATION_FAILED:1"):
            preview_preserved_table_batch(
                self.path, [self.peer, {**self.phrase, "old_text": "absent"}], revision=2,
            )
        self.assert_unchanged()

    def test_host_and_child_phrases_preview_and_commit_in_one_batch(self):
        outer, inner = build_advanced_table_map(self.path)["tables"]
        host = {
            "op": "replace_cell_phrase", "table": outer["locator"],
            "cell": outer["cells"][0]["locator"], "paragraph_index": 0,
            "old_text": "Outer host", "new_text": "수정한 바깥 설명",
        }
        for operations in ([host, self.phrase], [self.phrase, host]):
            with self.subTest(order=[op["table"] for op in operations]):
                self.path.write_bytes(self.original)
                preview = preview_preserved_table_batch(self.path, operations, revision=2)
                self.assert_unchanged()
                self.assertEqual(preview["operation_count"], 2)
                proposed = {change["table"]: change["after"] for change in preview["changes"]}
                self.assertEqual(proposed[outer["locator"]], host["new_text"])
                self.assertTrue(proposed[inner["locator"]].startswith("Reviewed"))
                result = self.batch(operations)
                self.assertEqual(result["operation_count"], 2)
                edited_outer, edited_inner = build_advanced_table_map(self.path)["tables"]
                self.assertEqual(edited_outer["cells"][0]["text"], proposed[outer["locator"]])
                self.assertEqual(edited_inner["cells"][0]["text"], proposed[inner["locator"]])
                self.assertEqual(edited_inner["cells"][1:], inner["cells"][1:])
                self.assertEqual(raw_nested_table_count(self.path), 1)

    def test_plan_fingerprint_binds_order_document_revision_and_source(self):
        operations = [self.peer, self.phrase]
        args = ("doc_a", 2, "a" * 64, operations)
        fingerprint = preserved_table_batch_plan_sha256(*args)
        reordered_keys = [dict(reversed(list(op.items()))) for op in operations]
        self.assertEqual(fingerprint, preserved_table_batch_plan_sha256(*args[:3], reordered_keys))
        for changed in (
            ("doc_b", *args[1:]),
            (args[0], 3, *args[2:]),
            (*args[:2], "b" * 64, operations),
            (*args[:3], list(reversed(operations))),
            (*args[:3], [{**self.peer, "text": "다른 값"}, self.phrase]),
        ):
            self.assertNotEqual(fingerprint, preserved_table_batch_plan_sha256(*changed))

    def test_aggregates_footprint_for_two_sections(self):
        with HwpxDocument.new() as document:
            first = document.add_table(1, 1)
            first.set_cell_text(0, 0, "First")
            second = document.add_table(1, 1, section=document.add_section())
            second.set_cell_text(0, 0, "Second")
            document.save_to_path(str(self.path))
        tables = build_advanced_table_map(self.path)["tables"]
        sections = {table["section_path"] for table in tables}
        self.assertEqual(len(sections), 2)
        result = self.batch([
            {"op": "set_cell_text", "table": table["locator"],
             "cell": table["cells"][0]["locator"], "text": f"Changed {index}"}
            for index, table in enumerate(tables)
        ])
        self.assertEqual(set(result["mutation_footprint"]["observed"]["changed_parts"]), sections)
