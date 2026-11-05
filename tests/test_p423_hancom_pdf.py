"""P4.23 Hancom native PDF conversion: fail-closed without Windows/COM."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx_mcp.custody.p423_hancom_pdf import (
    native_pdf_capability, export_native_hwp_pdf, HancomPdfUnavailable,
)


class P423HancomPdfTests(unittest.TestCase):
    def test_capability_names_actual_hancom_engine(self):
        cap = native_pdf_capability()
        self.assertEqual(cap["engine"], "HANCOM_HWP_EXE_COM")
        self.assertEqual(cap["native_pdf_visual_adjudication"], "SEPARATE_REQUIRED")

    def test_linux_does_not_claim_hancom_pdf(self):
        with patch("hwpx_mcp.custody.p423_hancom_pdf.os.name", "posix"):
            with self.assertRaises(HancomPdfUnavailable):
                export_native_hwp_pdf("input.hwpx", "out.pdf")

    def test_export_refuses_bad_input_extension_without_invoking_powershell(self):
        with tempfile.TemporaryDirectory() as folder:
            input_file = Path(folder) / "sample.txt"
            input_file.write_text("not an HWPX", encoding="utf-8")
            with patch("hwpx_mcp.custody.p423_hancom_pdf.os.name", "nt"), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run"
            ) as execute:
                with self.assertRaisesRegex(ValueError, "source must be"):
                    export_native_hwp_pdf(input_file, Path(folder) / "out.pdf")
                execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
