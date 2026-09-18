from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import server
from p2_document import apply_edits_atomic, apply_text_edits_atomic, build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map
from p23_richtext import apply_rich_formatting_atomic
from p24_inline import apply_inline_edits_atomic, build_inline_map


class P2DocumentTests(unittest.TestCase):
    def _document(self, directory: str) -> Path:
        path = Path(directory) / "p2.hwpx"
        server.materialize_hwpx(path, "alpha\nbeta\ngamma", "P2 title")
        return path

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_document_map_exposes_paragraph_locators_and_digests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            document_map = build_document_map(path)
            self.assertGreaterEqual(document_map["paragraph_count"], 4)
            self.assertEqual(len(document_map["semantic_sha256"]), 64)
            self.assertEqual(len(document_map["structure_sha256"]), 64)
            locators = [p["locator"] for p in document_map["paragraphs"]]
            self.assertEqual(len(locators), len(set(locators)))
            self.assertTrue(all(locator.startswith("p_") for locator in locators))

    def test_text_edit_preserves_locator_and_structure_for_intrinsic_id_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            target = next(p for p in before["paragraphs"] if p["text"] == "beta")
            result = apply_text_edits_atomic(
                path,
                [{"op": "replace_paragraph_text", "target": target["locator"], "text": "delta"}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_document_map(path)
            rebound = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            self.assertFalse(result["no_op"])
            self.assertEqual(rebound["text"], "delta")
            self.assertEqual(before["structure_sha256"], after["structure_sha256"])
            self.assertNotEqual(before["semantic_sha256"], after["semantic_sha256"])

    def test_insert_paragraph_returns_new_locator_and_changes_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            anchor = next(p for p in before["paragraphs"] if p["text"] == "beta")
            result = apply_edits_atomic(
                path,
                [{"op": "insert_paragraph_after", "target": anchor["locator"], "text": "inserted"}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_document_map(path)
            change = result["changes"][0]
            self.assertTrue(result["structure_changed"])
            self.assertEqual(after["paragraph_count"], before["paragraph_count"] + 1)
            self.assertIsNotNone(change["inserted_locator"])
            inserted = next(p for p in after["paragraphs"] if p["locator"] == change["inserted_locator"])
            self.assertEqual(inserted["text"], "inserted")

    def test_delete_paragraph_rebinding_marks_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            target = next(p for p in before["paragraphs"] if p["text"] == "beta")
            result = apply_edits_atomic(
                path,
                [{"op": "delete_paragraph", "target": target["locator"]}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_document_map(path)
            self.assertEqual(after["paragraph_count"], before["paragraph_count"] - 1)
            binding = next(
                b for b in result["locator_rebinding"]["bindings"]
                if b["before_locator"] == target["locator"]
            )
            self.assertEqual(binding["status"], "deleted")
            self.assertIsNone(binding["after_locator"])

    def test_move_paragraph_preserves_intrinsic_locator_and_changes_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            alpha = next(p for p in before["paragraphs"] if p["text"] == "alpha")
            gamma = next(p for p in before["paragraphs"] if p["text"] == "gamma")
            result = apply_edits_atomic(
                path,
                [{"op": "move_paragraph_after", "target": alpha["locator"], "anchor": gamma["locator"]}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_document_map(path)
            self.assertTrue(result["structure_changed"])
            moved = next(p for p in after["paragraphs"] if p["text"] == "alpha")
            self.assertEqual(moved["locator"], alpha["locator"])
            texts = [p["text"] for p in after["paragraphs"]]
            self.assertGreater(texts.index("alpha"), texts.index("gamma"))

    def test_formatting_map_and_run_format_change_are_semantic_structure_invariant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before_doc = build_document_map(path)
            before_fmt = build_formatting_map(path)
            target = next(p for p in before_doc["paragraphs"] if p["text"] == "beta")
            result = apply_formatting_atomic(
                path,
                [{"op": "set_run_format", "target": target["locator"], "format": {"bold": True}}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after_doc = build_document_map(path)
            after_fmt = build_formatting_map(path)
            self.assertFalse(result["semantic_changed"])
            self.assertFalse(result["structure_changed"])
            self.assertTrue(result["formatting_changed"])
            self.assertEqual(before_doc["semantic_sha256"], after_doc["semantic_sha256"])
            self.assertEqual(before_doc["structure_sha256"], after_doc["structure_sha256"])
            self.assertNotEqual(before_fmt["formatting_sha256"], after_fmt["formatting_sha256"])
            formatted = next(p for p in after_fmt["paragraphs"] if p["locator"] == target["locator"])
            self.assertTrue(any(run["style"] and run["style"].get("bold") for run in formatted["runs"] if run["text"]))

    def test_paragraph_format_change_is_resolved_and_text_preserving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            target = next(p for p in before["paragraphs"] if p["text"] == "alpha")
            result = apply_formatting_atomic(
                path,
                [{"op": "set_paragraph_format", "target": target["locator"], "format": {"alignment": "CENTER"}}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_formatting_map(path)
            formatted = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            self.assertFalse(result["semantic_changed"])
            self.assertFalse(result["structure_changed"])
            self.assertTrue(result["formatting_changed"])
            alignment = (formatted["paragraph_property"] or {}).get("alignment") or {}
            self.assertEqual(alignment.get("horizontal"), "CENTER")

    def test_p23_range_format_splits_only_selected_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before_doc = build_document_map(path)
            target = next(p for p in before_doc["paragraphs"] if p["text"] == "beta")
            result = apply_rich_formatting_atomic(
                path,
                [{
                    "op": "set_range_format",
                    "target": target["locator"],
                    "start": 1,
                    "end": 3,
                    "format": {"bold": True},
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_formatting_map(path)
            paragraph = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            text_runs = [run for run in paragraph["runs"] if run["text"]]
            self.assertEqual([run["text"] for run in text_runs], ["b", "et", "a"])
            self.assertEqual(paragraph["direct_text"], "beta")
            self.assertTrue(text_runs[1]["style"]["bold"])
            self.assertNotEqual(text_runs[0]["char_pr_id_ref"], text_runs[1]["char_pr_id_ref"])
            self.assertFalse(result["semantic_changed"])
            self.assertFalse(result["structure_changed"])
            self.assertTrue(result["formatting_changed"])

    def test_p23_copy_run_format_reuses_exact_char_property(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            alpha = next(p for p in before["paragraphs"] if p["text"] == "alpha")
            gamma = next(p for p in before["paragraphs"] if p["text"] == "gamma")
            apply_rich_formatting_atomic(
                path,
                [{"op": "set_run_format", "target": alpha["locator"], "format": {"italic": True}}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            source_map = build_formatting_map(path)
            source = next(p for p in source_map["paragraphs"] if p["locator"] == alpha["locator"])
            source_ref = next(run["char_pr_id_ref"] for run in source["runs"] if run["text"])
            apply_rich_formatting_atomic(
                path,
                [{
                    "op": "copy_run_format",
                    "source": alpha["locator"],
                    "source_run_index": 0,
                    "target": gamma["locator"],
                }],
                expected_revision=2,
                current_revision=2,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_formatting_map(path)
            copied = next(p for p in after["paragraphs"] if p["locator"] == gamma["locator"])
            copied_refs = {run["char_pr_id_ref"] for run in copied["runs"] if run["text"]}
            self.assertEqual(copied_refs, {source_ref})

    def test_p23_nested_paragraph_formatting_mutates_para_property(self) -> None:
        from hwpx import HwpxDocument

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested.hwpx"
            doc = HwpxDocument.new()
            table = doc.add_table(rows=1, cols=1)
            table.set_cell_text(0, 0, "nested")
            path.write_bytes(doc.to_bytes())
            doc.close()

            before_doc = build_document_map(path)
            target = next(
                p for p in before_doc["paragraphs"]
                if p["text"] == "nested" and p["container"] != "section-body"
            )
            result = apply_rich_formatting_atomic(
                path,
                [{
                    "op": "set_paragraph_format",
                    "target": target["locator"],
                    "format": {"alignment": "CENTER", "spacing_after_pt": 3},
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_formatting_map(path)
            formatted = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            alignment = (formatted["paragraph_property"] or {}).get("alignment") or {}
            self.assertEqual(alignment.get("horizontal"), "CENTER")
            self.assertFalse(result["semantic_changed"])
            self.assertFalse(result["structure_changed"])

    def test_p23_normalization_coalesces_equivalent_split_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            beta = next(p for p in before["paragraphs"] if p["text"] == "beta")
            apply_rich_formatting_atomic(
                path,
                [{
                    "op": "set_range_format",
                    "target": beta["locator"],
                    "start": 1,
                    "end": 3,
                    "format": {"bold": True},
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            split_map = build_formatting_map(path)
            split_para = next(p for p in split_map["paragraphs"] if p["locator"] == beta["locator"])
            base_ref = split_para["runs"][0]["char_pr_id_ref"]
            apply_rich_formatting_atomic(
                path,
                [{
                    "op": "copy_run_format",
                    "source": beta["locator"],
                    "source_run_index": 0,
                    "target": beta["locator"],
                    "start": 1,
                    "end": 3,
                }],
                expected_revision=2,
                current_revision=2,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            result = apply_rich_formatting_atomic(
                path,
                [{"op": "normalize_formatting", "target": beta["locator"]}],
                expected_revision=3,
                current_revision=3,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_formatting_map(path)
            normalized = next(p for p in after["paragraphs"] if p["locator"] == beta["locator"])
            text_runs = [run for run in normalized["runs"] if run["text"]]
            self.assertEqual([run["text"] for run in text_runs], ["beta"])
            self.assertEqual(text_runs[0]["char_pr_id_ref"], base_ref)
            self.assertGreaterEqual(result["normalization"]["merged_adjacent_runs"], 2)

    def test_p24_cross_run_inline_replacement_preserves_run_structure(self) -> None:
        from hwpx import HwpxDocument

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cross-run.hwpx"
            doc = HwpxDocument.new()
            paragraph = doc.add_paragraph("")
            paragraph.add_run("ab")
            paragraph.add_run("cd", bold=True)
            path.write_bytes(doc.to_bytes())
            doc.close()

            before_doc = build_document_map(path)
            target = next(p for p in before_doc["paragraphs"] if p["text"] == "abcd")
            before_inline = build_inline_map(path)
            receipt = before_inline["inline_structure_sha256"]
            result = apply_inline_edits_atomic(
                path,
                [{
                    "op": "replace_inline_text",
                    "target": target["locator"],
                    "start": 1,
                    "end": 3,
                    "text": "XY",
                    "expected_text": "bc",
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after_inline = build_inline_map(path)
            paragraph_after = next(
                p for p in after_inline["paragraphs"] if p["locator"] == target["locator"]
            )
            self.assertEqual(paragraph_after["inline_text"], "aXYd")
            self.assertEqual(after_inline["inline_structure_sha256"], receipt)
            self.assertTrue(result["inline_text_changed"])
            self.assertFalse(result["inline_structure_changed"])
            self.assertFalse(result["structure_changed"])

    def test_p24_hyperlink_display_text_edit_preserves_field_wrapper(self) -> None:
        from hwpx import HwpxDocument

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hyperlink.hwpx"
            doc = HwpxDocument.new()
            paragraph = doc.add_paragraph("before ")
            paragraph.add_hyperlink("https://example.com", "linked")
            paragraph.add_run(" after")
            path.write_bytes(doc.to_bytes())
            doc.close()

            before_doc = build_document_map(path)
            target = next(p for p in before_doc["paragraphs"] if "linked" in p["text"])
            inline = build_inline_map(path)
            mapped = next(p for p in inline["paragraphs"] if p["locator"] == target["locator"])
            field = next(item for item in mapped["fields"] if item["type"] == "HYPERLINK")
            self.assertEqual(mapped["inline_text"][field["start"]:field["end"]], "linked")
            structure_receipt = inline["inline_structure_sha256"]

            result = apply_inline_edits_atomic(
                path,
                [{
                    "op": "replace_inline_text",
                    "target": target["locator"],
                    "start": field["start"] + 1,
                    "end": field["end"] - 1,
                    "text": "INK",
                    "expected_text": "inke",
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_inline_map(path)
            mapped_after = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            after_field = next(item for item in mapped_after["fields"] if item["type"] == "HYPERLINK")
            self.assertEqual(mapped_after["inline_text"][after_field["start"]:after_field["end"]], "lINKd")
            self.assertEqual(after["inline_structure_sha256"], structure_receipt)
            self.assertFalse(result["inline_structure_changed"])

    def test_p24_single_run_date_field_cached_text_is_editable(self) -> None:
        from hwpx import HwpxDocument

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "date-field.hwpx"
            doc = HwpxDocument.new()
            paragraph = doc.add_paragraph("date: ")
            paragraph.add_date_field("2026년 9월 18일")
            path.write_bytes(doc.to_bytes())
            doc.close()

            doc_map = build_document_map(path)
            target = next(p for p in doc_map["paragraphs"] if "2026년" in p["text"])
            inline = build_inline_map(path)
            mapped = next(p for p in inline["paragraphs"] if p["locator"] == target["locator"])
            field = next(item for item in mapped["fields"] if item["type"] == "DATE")
            selected = mapped["inline_text"][field["start"]:field["end"]]
            self.assertEqual(selected, "2026년 9월 18일")

            apply_inline_edits_atomic(
                path,
                [{
                    "op": "replace_inline_text",
                    "target": target["locator"],
                    "start": field["start"],
                    "end": field["end"],
                    "text": "2026년 9월 19일",
                    "expected_text": selected,
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_inline_map(path)
            mapped_after = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            after_field = next(item for item in mapped_after["fields"] if item["type"] == "DATE")
            self.assertEqual(
                mapped_after["inline_text"][after_field["start"]:after_field["end"]],
                "2026년 9월 19일",
            )

    def test_p24_field_boundary_crossing_is_rejected_atomically(self) -> None:
        from hwpx import HwpxDocument

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "field-boundary.hwpx"
            doc = HwpxDocument.new()
            paragraph = doc.add_paragraph("A")
            paragraph.add_hyperlink("https://example.com", "BC")
            paragraph.add_run("D")
            path.write_bytes(doc.to_bytes())
            doc.close()

            target = next(p for p in build_document_map(path)["paragraphs"] if p["text"] == "ABCD")
            before_sha = self._sha(path)
            with self.assertRaisesRegex(ValueError, "field|inline structure|context"):
                apply_inline_edits_atomic(
                    path,
                    [{
                        "op": "replace_inline_text",
                        "target": target["locator"],
                        "start": 0,
                        "end": 2,
                        "text": "X",
                    }],
                    expected_revision=1,
                    current_revision=1,
                    validator=lambda candidate: server.validate_hwpx_package(candidate),
                )
            self.assertEqual(self._sha(path), before_sha)

    def test_p24_mixed_text_marker_is_preserved_and_special_atom_blocks_surgery(self) -> None:
        from hwpx import HwpxDocument

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed-inline.hwpx"
            doc = HwpxDocument.new()
            paragraph = doc.add_paragraph("abcd")
            paragraph.add_title_mark(in_toc=True)
            paragraph.add_run("x\ny", expand_special_characters=True)
            path.write_bytes(doc.to_bytes())
            doc.close()

            before = build_inline_map(path)
            mapped = next(p for p in before["paragraphs"] if p["inline_text"].startswith("abcd"))
            target = {"locator": mapped["locator"]}
            self.assertIn("\n", mapped["inline_text"])

            apply_inline_edits_atomic(
                path,
                [{
                    "op": "replace_inline_text",
                    "target": target["locator"],
                    "start": 0,
                    "end": 2,
                    "text": "AB",
                    "expected_text": "ab",
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_inline_map(path)
            self.assertEqual(before["inline_structure_sha256"], after["inline_structure_sha256"])

            mapped_after = next(p for p in after["paragraphs"] if p["locator"] == target["locator"])
            newline = mapped_after["inline_text"].index("\n")
            with self.assertRaisesRegex(ValueError, "structural/special"):
                apply_inline_edits_atomic(
                    path,
                    [{
                        "op": "replace_inline_text",
                        "target": target["locator"],
                        "start": newline - 1,
                        "end": newline + 1,
                        "text": "Q",
                    }],
                    expected_revision=2,
                    current_revision=2,
                )

    def test_stale_revision_rejects_without_byte_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            target = build_document_map(path)["paragraphs"][-1]
            before_sha = self._sha(path)
            with self.assertRaisesRegex(ValueError, "Stale revision"):
                apply_edits_atomic(
                    path,
                    [{"op": "delete_paragraph", "target": target["locator"]}],
                    expected_revision=1,
                    current_revision=2,
                )
            self.assertEqual(self._sha(path), before_sha)

    def test_invalid_operation_aborts_entire_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            target = build_document_map(path)["paragraphs"][-1]
            before_sha = self._sha(path)
            with self.assertRaisesRegex(ValueError, "Unknown paragraph locator"):
                apply_edits_atomic(
                    path,
                    [
                        {"op": "replace_paragraph_text", "target": target["locator"], "text": "would-change"},
                        {"op": "delete_paragraph", "target": "p_missing"},
                    ],
                    expected_revision=1,
                    current_revision=1,
                )
            self.assertEqual(self._sha(path), before_sha)

    def test_validator_failure_rolls_back_original_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            target = build_document_map(path)["paragraphs"][-1]
            before_sha = self._sha(path)

            def reject(_candidate: Path) -> dict:
                raise ValueError("synthetic validator rejection")

            with self.assertRaisesRegex(ValueError, "synthetic validator rejection"):
                apply_edits_atomic(
                    path,
                    [{"op": "insert_paragraph_after", "target": target["locator"], "text": "blocked"}],
                    expected_revision=1,
                    current_revision=1,
                    validator=reject,
                )
            self.assertEqual(self._sha(path), before_sha)


if __name__ == "__main__":
    unittest.main()
