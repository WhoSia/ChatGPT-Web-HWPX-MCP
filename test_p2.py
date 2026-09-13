from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import server
from p2_document import apply_text_edits_atomic, build_document_map


class P2DocumentTests(unittest.TestCase):
    def _document(self, directory: str) -> Path:
        path = Path(directory) / "p2.hwpx"
        server.materialize_hwpx(path, "alpha\nbeta", "P2 title")
        return path

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_document_map_exposes_paragraph_locators_and_digests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            document_map = build_document_map(path)
            self.assertGreaterEqual(document_map["paragraph_count"], 3)
            self.assertEqual(len(document_map["semantic_sha256"]), 64)
            self.assertEqual(len(document_map["structure_sha256"]), 64)
            locators = [p["locator"] for p in document_map["paragraphs"]]
            self.assertEqual(len(locators), len(set(locators)))
            self.assertTrue(all(locator.startswith("p_") for locator in locators))

    def test_text_edit_preserves_locator_and_structure_for_intrinsic_id_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            before = build_document_map(path)
            target = before["paragraphs"][-1]
            result = apply_text_edits_atomic(
                path,
                [{"op": "replace_paragraph_text", "target": target["locator"], "text": "gamma"}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            after = build_document_map(path)
            self.assertFalse(result["no_op"])
            self.assertEqual(after["paragraphs"][-1]["locator"], target["locator"])
            self.assertEqual(after["paragraphs"][-1]["text"], "gamma")
            self.assertEqual(before["structure_sha256"], after["structure_sha256"])
            self.assertNotEqual(before["semantic_sha256"], after["semantic_sha256"])

    def test_stale_revision_rejects_without_byte_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._document(tmp)
            target = build_document_map(path)["paragraphs"][-1]
            before_sha = self._sha(path)
            with self.assertRaisesRegex(ValueError, "Stale revision"):
                apply_text_edits_atomic(
                    path,
                    [{"op": "replace_paragraph_text", "target": target["locator"], "text": "stale"}],
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
                apply_text_edits_atomic(
                    path,
                    [
                        {"op": "replace_paragraph_text", "target": target["locator"], "text": "would-change"},
                        {"op": "replace_paragraph_text", "target": "p_missing", "text": "boom"},
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
                apply_text_edits_atomic(
                    path,
                    [{"op": "replace_paragraph_text", "target": target["locator"], "text": "blocked"}],
                    expected_revision=1,
                    current_revision=1,
                    validator=reject,
                )
            self.assertEqual(self._sha(path), before_sha)


if __name__ == "__main__":
    unittest.main()
