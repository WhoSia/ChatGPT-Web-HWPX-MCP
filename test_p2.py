from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import server
from p2_document import apply_edits_atomic, apply_text_edits_atomic, build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map


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
