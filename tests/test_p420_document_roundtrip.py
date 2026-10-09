"""P4.20 document production E2E: native package, edit, reopen, integrity."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from hwpx import HwpxDocument
from hwpx_mcp.document.p2_document import build_document_map, apply_text_edits_atomic
from hwpx_mcp.document.p22_formatting import build_formatting_map
from hwpx_mcp.document.p334r2_package_validation import validate_hwpx_package_light


class P420NativeDocumentRoundTrip(unittest.TestCase):
    def test_create_edit_reopen_validate_and_preserve_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "publication.hwpx"
            document = HwpxDocument.new()
            for paragraph in ("연구 보고서", "초록: 원문 검증", "실험 결과 및 논의", "출처 보존"):
                document.add_paragraph(paragraph)
            document.save_to_path(str(path))
            self.assertTrue(validate_hwpx_package_light(path)["valid"])
            initial = build_document_map(path)
            self.assertGreaterEqual(initial["paragraph_count"], 4)
            original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            target = next(p for p in initial["paragraphs"] if p["text"] == "실험 결과 및 논의")
            receipt = apply_text_edits_atomic(
                path,
                [{"op": "replace_paragraph_text", "target": target["locator"],
                  "text": "실험 결과, 관찰 및 한계"}],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: validate_hwpx_package_light(candidate)["valid"],
            )
            self.assertFalse(receipt["no_op"])
            self.assertTrue(validate_hwpx_package_light(path))
            self.assertNotEqual(original_hash, hashlib.sha256(path.read_bytes()).hexdigest())
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("Contents/section0.xml", archive.namelist())
            reopened = build_document_map(path)
            self.assertEqual(reopened["structure_sha256"], initial["structure_sha256"])
            self.assertNotEqual(reopened["semantic_sha256"], initial["semantic_sha256"])
            edited = next(p for p in reopened["paragraphs"] if p["locator"] == target["locator"])
            self.assertEqual(edited["text"], "실험 결과, 관찰 및 한계")
            self.assertIsInstance(build_formatting_map(path), dict)


if __name__ == "__main__":
    unittest.main()
