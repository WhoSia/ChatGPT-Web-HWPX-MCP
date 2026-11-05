"""Fast source-integrity gate for WSL/Hancom entrypoints.

Do not require Windows or activate COM; parse all Python entrypoints so an
accidental literal escaped newline cannot disable an entire release path.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "scripts/p423_wsl_hancom_pdf_bridge.py",
    "scripts/p424_wsl_hancom_preflight.py",
    "scripts/p424_competitor_benchmark.py",
    "hwpx_mcp/custody/p423_hancom_pdf.py",
    "hwpx_mcp/interfaces/p423_pdf_mcp.py",
)


class P424SourceIntegrityTests(unittest.TestCase):
    def test_all_native_and_benchmark_entrypoints_parse(self):
        for relative in SCRIPTS:
            with self.subTest(path=relative):
                path = ROOT / relative
                parsed = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
                self.assertIsInstance(parsed, ast.Module)

    def test_bridge_has_no_accidental_literal_backslash_n_in_subprocess_call(self):
        text = (ROOT / "scripts/p423_wsl_hancom_pdf_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("stdout=subprocess.DEVNULL,\\n", text)

    def test_p414_signed_agent_is_not_replaced_by_unsigned_wsl_smoke(self):
        bridge = (ROOT / "scripts/p423_wsl_hancom_pdf_bridge.py").read_text(encoding="utf-8")
        p414 = ROOT / "scripts/p414_windows_capture_agent.ps1"
        self.assertTrue(p414.is_file())
        self.assertIn("Not the production P4.14 signed-agent protocol", bridge)


if __name__ == "__main__":
    unittest.main()
