"""P4.24 WSL -> native Hangul PDF handoff regression suite.

Mock the OS interop transport but execute the *real bridge* Python module:
this catches syntax and receipt logic regressions before Windows acceptance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p423_wsl_hancom_pdf_bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("p424_wsl_bridge_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("Cannot load WSL bridge")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class P424WSLNativePdfBridgeTests(unittest.TestCase):
    def test_bridge_is_valid_executable_python(self):
        # importlib executes source: a stray 'if ( or ...' must fail this test
        self.assertTrue(callable(load_bridge().export_wsl_native_pdf))

    def test_non_wsl_is_explicitly_unavailable(self):
        bridge = load_bridge()
        with patch.object(bridge, "on_wsl", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "WSL_ENVIRONMENT_REQUIRED"):
                bridge.export_wsl_native_pdf(Path("source.hwpx"), Path("source.pdf"))

    def test_rejects_existing_pdf_before_invoking_interop(self):
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as root:
            src, out = Path(root) / "source.hwpx", Path(root) / "out.pdf"
            src.write_bytes(b"PK" + b"0" * 300)
            out.write_bytes(b"preexisting-output")
            with patch.object(bridge, "on_wsl", return_value=True), patch.object(
                bridge, "_approved_windows_mount", side_effect=lambda p: p
            ), patch.object(bridge, "_windows_path", return_value=r"C:\test\x"), patch.object(
                bridge.subprocess, "run"
            ) as runner:
                with self.assertRaisesRegex(ValueError, "Use a new"):
                    bridge.export_wsl_native_pdf(src, out)
                runner.assert_not_called()
            self.assertEqual(out.read_bytes(), b"preexisting-output")

    def test_valid_receipt_is_checked_against_original_and_pdf(self):
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as root:
            src, out = Path(root) / "source.hwpx", Path(root) / "out.pdf"
            original = b"PK" + b"equation-test" * 20
            pdf = b"%PDF-1.7\n" + b"native-pdf-mock" * 10
            src.write_bytes(original)
            def execute(command, **kwargs):
                out.write_bytes(pdf)
                receipt = out.with_suffix(".pdf.receipt.json")
                receipt.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "engine": "HANCOM_HWP_EXE_COM",
                    "input_sha256": hashlib.sha256(original).hexdigest(),
                    "output_sha256": hashlib.sha256(pdf).hexdigest(),
                    "hancom_product_version": "simulated-only",
                }), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")
            with patch.object(bridge, "on_wsl", return_value=True), patch.object(
                bridge, "_approved_windows_mount", side_effect=lambda p: p
            ), patch.object(bridge, "_windows_path", return_value=r"C:\test\x"), patch.object(
                bridge.subprocess, "run", side_effect=execute
            ):
                result = bridge.export_wsl_native_pdf(src, out)
            self.assertEqual(result["status"], "PDF_CREATED_UNREVIEWED")
            self.assertEqual(result["pdf_sha256"], hashlib.sha256(pdf).hexdigest())
            self.assertEqual(result["native_visual_acceptance"], "NOT_ADJUDICATED")

    def test_mismatched_receipt_fails_closed(self):
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as root:
            src, out = Path(root) / "source.hwpx", Path(root) / "out.pdf"
            src.write_bytes(b"PK" + b"original" * 20)
            def execute(command, **kwargs):
                out.write_bytes(b"%PDF-1.7\n" + b"mock" * 50)
                receipt = out.with_suffix(".pdf.receipt.json")
                receipt.write_text(json.dumps({
                    "status": "PDF_CREATED_UNREVIEWED",
                    "engine": "HANCOM_HWP_EXE_COM",
                    "input_sha256": "0" * 64,
                    "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                }), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")
            with patch.object(bridge, "on_wsl", return_value=True), patch.object(
                bridge, "_approved_windows_mount", side_effect=lambda p: p
            ), patch.object(bridge, "_windows_path", return_value=r"C:\test\x"), patch.object(
                bridge.subprocess, "run", side_effect=execute
            ):
                with self.assertRaisesRegex(RuntimeError, "MISMATCH"):
                    bridge.export_wsl_native_pdf(src, out)


if __name__ == "__main__":
    unittest.main()
