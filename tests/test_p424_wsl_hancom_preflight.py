"""P4.24 WSL readiness check is read-only and independent of Windows COM."""
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import zipfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.p424_wsl_hancom_preflight import inspect_wsl_hancom_preflight


class P424WslPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "source.hwpx"
        self.destination = root / "output.pdf"
        self.script = root / "p423_hancom_native_pdf.ps1"
        with zipfile.ZipFile(self.source, "w") as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("Contents/content.hpf", "synthetic not a real HWPX")
            zf.writestr("Contents/header.xml", "<header/>")
        self.script.write_text("# synthetic fixture only\n", encoding="utf-8")

    def _check(self):
        with patch("scripts.p424_wsl_hancom_preflight.on_wsl", return_value=True), patch(
            "scripts.p424_wsl_hancom_preflight._approved_windows_mount",
            side_effect=lambda path: Path(path).resolve(),
        ), patch(
            "scripts.p424_wsl_hancom_preflight.shutil.which",
            return_value="/usr/bin/fixture-only",
        ):
            return inspect_wsl_hancom_preflight(
                self.source, self.destination, repository_script=self.script
            )

    def test_readiness_does_not_claim_hancom_execution_or_visual_pass(self):
        result = self._check()
        self.assertEqual(result["status"], "READY_FOR_MANUAL_SMOKE")
        self.assertFalse(result["powershell_or_com_executed"])
        self.assertFalse(result["hancom_installation_verified"])
        self.assertFalse(result["native_render_verified"])
        self.assertFalse(self.destination.exists())

    def test_wrong_input_header_is_rejected_before_render(self):
        self.source.write_bytes(b"NOTZIP" + b"0" * 200)
        self.assertIn("SOURCE_ZIP_HEADER_INVALID", self._check()["issues"])

    def test_fake_zip_magic_without_directory_is_rejected(self):
        self.source.write_bytes(bytes((80, 75, 3, 4)) + b"0" * 200)
        self.assertIn("SOURCE_ZIP_DIRECTORY_INVALID", self._check()["issues"])

    def test_existing_receipt_blocks_reusing_output(self):
        self.destination.with_suffix(".pdf.receipt.json").write_text("{}")
        self.assertIn("RECEIPT_PATH_ALREADY_USED", self._check()["issues"])

    def test_existing_pdf_blocks_overwrite(self):
        self.destination.write_bytes(b"%PDF-1.7")
        self.assertIn("DESTINATION_MUST_BE_NEW_PDF", self._check()["issues"])

    def test_missing_windows_interop_commands_blocks_ready(self):
        with patch("scripts.p424_wsl_hancom_preflight.on_wsl", return_value=True), patch(
            "scripts.p424_wsl_hancom_preflight._approved_windows_mount",
            side_effect=lambda path: Path(path).resolve(),
        ), patch(
            "scripts.p424_wsl_hancom_preflight.shutil.which",
            return_value=None,
        ):
            result = inspect_wsl_hancom_preflight(
                self.source, self.destination, repository_script=self.script
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("COMMAND_UNAVAILABLE_POWERSHELL_EXE", result["issues"])

    def test_readonly_cli_runs_directly_without_package_import_errors(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "p424_wsl_hancom_preflight.py"
        result = subprocess.run(
            [sys.executable, str(script), str(self.source), str(self.destination)],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["powershell_or_com_executed"])

    def test_not_wsl_never_reports_ready(self):
        with patch("scripts.p424_wsl_hancom_preflight.on_wsl", return_value=False), patch(
            "scripts.p424_wsl_hancom_preflight._approved_windows_mount",
            side_effect=lambda path: Path(path).resolve(),
        ), patch(
            "scripts.p424_wsl_hancom_preflight.shutil.which",
            return_value="/usr/bin/fixture-only",
        ):
            result = inspect_wsl_hancom_preflight(
                self.source, self.destination, repository_script=self.script
            )
        self.assertIn("WSL_KERNEL_REQUIRED", result["issues"])


if __name__ == "__main__":
    unittest.main()
