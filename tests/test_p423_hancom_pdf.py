"""P4.23 Hancom native PDF conversion: fail-closed without Windows/COM."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import subprocess

from hwpx_mcp.custody.p423_hancom_pdf import (
    native_pdf_capability, export_native_hwp_pdf, HancomPdfUnavailable,
)


class P423HancomPdfTests(unittest.TestCase):
    def test_capability_names_actual_hancom_engine(self):
        cap = native_pdf_capability()
        self.assertEqual(cap["engine"], "HANCOM_HWP_EXE_COM")
        self.assertEqual(cap["native_pdf_visual_adjudication"], "SEPARATE_REQUIRED")

    def test_linux_does_not_claim_hancom_pdf(self):
        with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=False):
            with self.assertRaises(HancomPdfUnavailable):
                export_native_hwp_pdf("input.hwpx", "out.pdf")

    def test_export_refuses_bad_input_extension_without_invoking_powershell(self):
        with tempfile.TemporaryDirectory() as folder:
            input_file = Path(folder) / "sample.txt"
            input_file.write_text("not an HWPX", encoding="utf-8")
            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run"
            ) as execute:
                with self.assertRaisesRegex(ValueError, "source must be"):
                    export_native_hwp_pdf(input_file, Path(folder) / "out.pdf")
                execute.assert_not_called()

    def test_timeout_never_claims_pdf_created(self):
        from hwpx_mcp.custody.p423_hancom_pdf import HancomPdfConversionError
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"0" * 200)
            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="powershell.exe", timeout=180),
            ):
                with self.assertRaisesRegex(HancomPdfConversionError, "TIMED_OUT"):
                    export_native_hwp_pdf(source, dest)
            self.assertFalse(dest.exists())

    def test_valid_mocked_native_export_receipt_and_pdf_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"1" * 200)
            payload = b"%PDF-1.7\n" + b"dummy-test-only" * 12

            def native_process(argv, **kwargs):
                receipt_file = Path(argv[argv.index("-ReceiptPath") + 1])
                output_file = Path(argv[argv.index("-OutputPath") + 1])
                output_file.write_bytes(payload)
                receipt_file.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "engine": "HANCOM_HWP_EXE_COM",
                    "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "output_sha256": hashlib.sha256(payload).hexdigest(),
                    "output_bytes": len(payload),
                }))
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run", side_effect=native_process
            ):
                receipt = export_native_hwp_pdf(source, dest)
            self.assertEqual(receipt["status"], "PDF_CREATED_UNREVIEWED")
            self.assertEqual(receipt["pdf_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(dest.read_bytes(), payload)
            self.assertEqual(receipt["native_visual_acceptance"] if "native_visual_acceptance" in receipt else "NOT_ADJUDICATED", "NOT_ADJUDICATED")

    def test_invalid_worker_receipt_is_rejected_and_output_removed(self):
        from hwpx_mcp.custody.p423_hancom_pdf import HancomPdfConversionError
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"1" * 200)

            def corrupt_worker(argv, **kwargs):
                dest.write_bytes(b"%PDF-1.7\\n" + b"0" * 100)
                receipt_file = Path(argv[argv.index("-ReceiptPath") + 1])
                receipt_file.write_text("{invalid JSON", encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run", side_effect=corrupt_worker
            ):
                with self.assertRaisesRegex(HancomPdfConversionError, "RECEIPT_MISMATCH"):
                    export_native_hwp_pdf(source, dest)
            self.assertFalse(dest.exists())

    def test_non_utf8_receipt_fails_closed(self):
        from hwpx_mcp.custody.p423_hancom_pdf import HancomPdfConversionError
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"1" * 200)

            def invalid_utf8_worker(argv, **kwargs):
                dest.write_bytes(b"%PDF-1.7\\n" + b"1" * 100)
                receipt_file = Path(argv[argv.index("-ReceiptPath") + 1])
                receipt_file.write_bytes(b"\\xff\\xfe\\xff")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run", side_effect=invalid_utf8_worker
            ):
                with self.assertRaisesRegex(HancomPdfConversionError, "RECEIPT_MISMATCH"):
                    export_native_hwp_pdf(source, dest)
            self.assertFalse(dest.exists())

    def test_native_worker_cannot_publish_pdf_if_source_changes(self):
        from hwpx_mcp.custody.p423_hancom_pdf import HancomPdfConversionError
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"1" * 200)
            payload = b"%PDF-1.7\\n" + b"0" * 100

            def mutating_worker(argv, **kwargs):
                initial_sha = hashlib.sha256(source.read_bytes()).hexdigest()
                dest.write_bytes(payload)
                receipt_file = Path(argv[argv.index("-ReceiptPath") + 1])
                receipt_file.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "engine": "HANCOM_HWP_EXE_COM",
                    "input_sha256": initial_sha,
                    "output_sha256": hashlib.sha256(payload).hexdigest(),
                    "output_bytes": len(payload),
                }), encoding="utf-8")
                source.write_bytes(b"PK" + b"2" * 200)
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run", side_effect=mutating_worker
            ):
                with self.assertRaisesRegex(HancomPdfConversionError, "RECEIPT_MISMATCH"):
                    export_native_hwp_pdf(source, dest)
            self.assertFalse(dest.exists())

    def test_non_pdf_payload_with_consistent_receipt_fails_closed(self):
        from hwpx_mcp.custody.p423_hancom_pdf import HancomPdfConversionError
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"1" * 200)
            payload = b"NOT-A-PDF" + b"x" * 100

            def fake_worker(argv, **kwargs):
                dest.write_bytes(payload)
                receipt_path = Path(argv[argv.index("-ReceiptPath") + 1])
                receipt_path.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "engine": "HANCOM_HWP_EXE_COM",
                    "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "output_sha256": hashlib.sha256(payload).hexdigest(),
                    "output_bytes": len(payload),
                }), encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run", side_effect=fake_worker
            ):
                with self.assertRaisesRegex(HancomPdfConversionError, "RECEIPT_MISMATCH"):
                    export_native_hwp_pdf(source, dest)
            self.assertFalse(dest.exists())

    def test_preexisting_pdf_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            dest = Path(tmp) / "out.pdf"
            source.write_bytes(b"PK" + b"1" * 200)
            dest.write_bytes(b"existing pdf")
            with patch("hwpx_mcp.custody.p423_hancom_pdf.is_windows_hancom_host", return_value=True), patch(
                "hwpx_mcp.custody.p423_hancom_pdf.subprocess.run"
            ) as run:
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    export_native_hwp_pdf(source, dest)
                run.assert_not_called()
            self.assertEqual(dest.read_bytes(), b"existing pdf")

    def test_native_powershell_never_quits_unowned_hangul(self):
        from hwpx_mcp.custody import p423_hancom_pdf
        script = Path(p423_hancom_pdf.__file__).resolve().parents[2] / "scripts" / "p423_hancom_native_pdf.ps1"
        body = script.read_text(encoding="utf-8")
        self.assertIn("HANCOM_COM_PROCESS_NOT_JOB_OWNED", body)
        self.assertIn("if ($ownedHwp -and $null -ne $jobHwpPid)", body)
        self.assertIn("HANCOM_EXECUTABLE_IDENTITY_UNAVAILABLE", body)
        self.assertIn("hancom_executable_sha256", body)
        self.assertNotIn("Stop-Process -Name Hwp", body)


if __name__ == "__main__":
    unittest.main()
