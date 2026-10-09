"""Portable native capture packs must import relocated HWPX implementations."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import capture_runtime


class PortableCaptureRuntimeTests(unittest.TestCase):
    def test_preserves_package_tree_and_imports_from_isolated_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "capture_runtime.py").write_text("# fixture\n", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts" / "probe.py").write_text("from hwpx_mcp.document.sample import value\n", encoding="utf-8")
            module_dir = root / "hwpx_mcp" / "document"
            module_dir.mkdir(parents=True)
            (root / "hwpx_mcp" / "__init__.py").write_text("", encoding="utf-8")
            (module_dir / "__init__.py").write_text("", encoding="utf-8")
            (module_dir / "sample.py").write_text("value = 42\n", encoding="utf-8")
            for name in ("requirements.txt", "requirements-capture.txt", "requirements-dev.txt"):
                (root / name).write_text("# fixture\n", encoding="utf-8")
            pack = root / "pack"
            pack.mkdir()

            with patch.object(capture_runtime, "__file__", str(root / "capture_runtime.py")):
                receipt = capture_runtime.attach_capture_runtime(pack)

            manifest_path = pack / "runtime-manifest.json"
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(receipt, json.loads(manifest_path.read_text(encoding="utf-8")))
            packaged_module = pack / "runtime" / "hwpx_mcp" / "document" / "sample.py"
            self.assertTrue(packaged_module.is_file())
            row = next(r for r in receipt["files"] if r["path"] == "hwpx_mcp/document/sample.py")
            self.assertEqual(row["sha256"], hashlib.sha256(packaged_module.read_bytes()).hexdigest())
            self.assertEqual(len({r["path"] for r in receipt["files"]}), len(receipt["files"]))

            proc = subprocess.run(
                [sys.executable, "-c", "from hwpx_mcp.document.sample import value; assert value == 42"],
                cwd=pack / "runtime",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
