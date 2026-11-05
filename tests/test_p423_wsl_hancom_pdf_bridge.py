"""WSL bridge must refuse generic Linux and non-Windows-mounted paths."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.p423_wsl_hancom_pdf_bridge import (
    _approved_windows_mount, export_wsl_native_pdf,
)


class P423WslHancomBridgeTests(unittest.TestCase):
    def test_generic_linux_is_not_native_hancom(self):
        with patch("scripts.p423_wsl_hancom_pdf_bridge.on_wsl", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "WSL_ENVIRONMENT_REQUIRED"):
                export_wsl_native_pdf(Path("/tmp/input.hwpx"), Path("/tmp/output.pdf"))

    def test_local_linux_temp_dir_cannot_be_passed_to_windows_hangul(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Windows-mounted"):
                _approved_windows_mount(Path(folder) / "untrusted.hwpx")

    def test_invalid_timeout_is_rejected_before_file_mutation(self):
        with patch("scripts.p423_wsl_hancom_pdf_bridge.on_wsl", return_value=True):
            with self.assertRaisesRegex(ValueError, "timeout_seconds"):
                export_wsl_native_pdf(Path("/mnt/c/test.hwpx"), Path("/mnt/c/result.pdf"), timeout_seconds=5)

    def test_mocked_windows_hancom_result_requires_pdf_receipt_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.hwpx"
            destination = Path(folder) / "result.pdf"
            source.write_bytes(b"PK" + b"source" * 50)
            payload = b"%PDF-1.7\\n" + b"mock-pdf" * 40

            def emulate_windows_runner(argv, **kwargs):
                destination.write_bytes(payload)
                receipt = destination.with_suffix(".pdf.receipt.json")
                receipt.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "output_sha256": hashlib.sha256(payload).hexdigest(),
                    "hancom_page_count": 4,
                }), encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch("scripts.p423_wsl_hancom_pdf_bridge.on_wsl", return_value=True), patch(
                "scripts.p423_wsl_hancom_pdf_bridge._approved_windows_mount",
                side_effect=lambda path: Path(path).resolve(),
            ), patch(
                "scripts.p423_wsl_hancom_pdf_bridge._windows_path",
                return_value=r"C:\\test\\source.hwpx",
            ), patch(
                "scripts.p423_wsl_hancom_pdf_bridge.subprocess.run",
                side_effect=emulate_windows_runner,
            ):
                result = export_wsl_native_pdf(source, destination)

            self.assertEqual(result["pdf_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(result["status"], "PDF_CREATED_UNREVIEWED")
            self.assertEqual(result["native_visual_acceptance"], "NOT_ADJUDICATED")
            self.assertEqual(result["hancom_page_count"], 4)


if __name__ == "__main__":
    unittest.main()
