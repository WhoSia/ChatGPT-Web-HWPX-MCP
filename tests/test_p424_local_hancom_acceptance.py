"""End-to-end local acceptance orchestration tests with mocked Windows transport."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from p424_local_hancom_acceptance import run_local_acceptance


class P424LocalHancomAcceptanceTests(unittest.TestCase):
    def test_single_command_creates_pdf_and_reviewable_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "input.hwpx", root / "output"
            source.write_bytes(b"PK" + b"source" * 30)
            output.mkdir()
            payload = b"%PDF-1.7\n" + b"native-mocked-output" * 10
            def convert(path, pdf_path):
                pdf_path.write_bytes(payload)
                return {
                    "status": "PDF_CREATED_UNREVIEWED",
                    "pdf_sha256": hashlib.sha256(payload).hexdigest(),
                    "hancom_product_version": "TEST_ONLY",
                }
            with patch("p424_local_hancom_acceptance.export_wsl_native_pdf", side_effect=convert):
                result = run_local_acceptance(source, output)
            self.assertTrue(result["native_pdf_created"])
            self.assertFalse(result["production_approved"])
            self.assertEqual(result["visual_acceptance"], "REQUIRES_HUMAN_PAGE_REVIEW")
            self.assertIsNone(result["pdf_page_diff"])
            saved = json.loads((output / "input.p424-acceptance.json").read_text())
            self.assertEqual(saved["native_pdf_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertNotIn("source_bytes", saved)

    def test_pdf_baseline_comparison_is_integrated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, baseline, output = root / "a.hwpx", root / "gold.pdf", root / "out"
            source.write_bytes(b"PK" + b"A" * 150)
            baseline.write_bytes(b"%PDF-old")
            output.mkdir()
            payload = b"%PDF-new-result"
            def convert(path, dest):
                dest.write_bytes(payload)
                return {"pdf_sha256": hashlib.sha256(payload).hexdigest()}
            with patch("p424_local_hancom_acceptance.export_wsl_native_pdf", side_effect=convert), patch(
                "p424_local_hancom_acceptance.compare_pdf_pages",
                return_value={"pages": [{"page": 1, "fraction_changed_pixels": 0.02}]},
            ) as compare:
                result = run_local_acceptance(source, output, baseline_pdf=baseline)
            compare.assert_called_once()
            self.assertEqual(result["pdf_page_diff"]["pages"][0]["page"], 1)

    def test_failure_never_reports_successful_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.hwpx", root / "output"
            source.write_bytes(b"PK" + b"file" * 50)
            output.mkdir()
            with patch("p424_local_hancom_acceptance.export_wsl_native_pdf", side_effect=RuntimeError("HANCOM_FAILED")):
                with self.assertRaisesRegex(RuntimeError, "HANCOM_FAILED"):
                    run_local_acceptance(source, output)
            self.assertFalse((output / "source.p424-acceptance.json").exists())

    def test_existing_result_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.hwpx", root / "output"
            source.write_bytes(b"PK" + b"file" * 50)
            output.mkdir()
            pdf = output / "source.native-hancom.pdf"
            pdf.write_bytes(b"keep original")
            with patch("p424_local_hancom_acceptance.export_wsl_native_pdf") as convert:
                with self.assertRaises(FileExistsError):
                    run_local_acceptance(source, output)
                convert.assert_not_called()
            self.assertEqual(pdf.read_bytes(), b"keep original")


if __name__ == "__main__":
    unittest.main()
