"""P4.24 native Windows worker boundary regressions (mocked COM transport).

The actual Hancom.exe native visual acceptance is separate and must not be
inferred from these tests.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx_mcp.custody.p423_hancom_pdf import (
    export_native_hwp_pdf,
    HancomPdfConversionError,
)


class NativePdfWorkerCustodyTests(unittest.TestCase):
    def _run(self, *, change_source=False, bad_size=False):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / "source.hwpx", Path(tmp) / "native.pdf"
            original = b"PK" + b"equations" * 50
            pdf = b"%PDF-1.7\\n" + b"mock-native" * 30
            source.write_bytes(original)

            def powershell(cmd, **kwargs):
                self.assertNotIn("text", kwargs, "PowerShell console must stay raw bytes")
                self.assertNotIn("encoding", kwargs)
                output = Path(cmd[cmd.index("-OutputPath") + 1])
                receipt_path = Path(cmd[cmd.index("-ReceiptPath") + 1])
                output.write_bytes(pdf)
                receipt_path.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "engine": "HANCOM_HWP_EXE_COM",
                    "input_sha256": hashlib.sha256(original).hexdigest(),
                    "output_sha256": hashlib.sha256(pdf).hexdigest(),
                    "output_bytes": len(pdf) + (1 if bad_size else 0),
                }), encoding="utf-8")
                if change_source:
                    source.write_bytes(original + b"mutation")
                return subprocess.CompletedProcess(cmd, 0, "한컴 상태".encode("cp949"), b"")

            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run", side_effect=powershell
            ):
                if change_source or bad_size:
                    with self.assertRaisesRegex(HancomPdfConversionError, "RECEIPT_MISMATCH"):
                        export_native_hwp_pdf(source, destination)
                    self.assertFalse(destination.exists(), "Untrusted output must not remain publishable")
                else:
                    result = export_native_hwp_pdf(source, destination)
                    self.assertEqual(result["pdf_sha256"], hashlib.sha256(pdf).hexdigest())
                    self.assertEqual(destination.read_bytes(), pdf)

    def test_cp949_diagnostics_do_not_mask_valid_receipt(self):
        self._run()

    def test_source_mutation_fails_closed(self):
        self._run(change_source=True)

    def test_output_byte_count_mismatch_fails_closed(self):
        self._run(bad_size=True)


if __name__ == "__main__":
    unittest.main()
