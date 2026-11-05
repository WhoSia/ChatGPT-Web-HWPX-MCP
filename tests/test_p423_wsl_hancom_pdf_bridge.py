"""WSL bridge must refuse generic Linux and non-Windows-mounted paths."""
from __future__ import annotations

from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
