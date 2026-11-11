"""P4.26 mock external rhwp CLI: output belongs to a temporary owned folder."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx_mcp.render import p426_rhwp_svg_preview as preview


class RhwpPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic.hwpx"
        self.source.write_bytes(b"synthetic zip fixtures only")
        self.output = self.root / "svg-pages"
        self.output.mkdir()

    def test_binary_absent_fails_explicitly(self):
        with patch.object(preview.shutil, "which", return_value=None):
            self.assertFalse(preview.rhwp_capability()["available"])
            with self.assertRaisesRegex(preview.RhwpPreviewUnavailable, "NOT_INSTALLED"):
                preview.render_svg_manifest(self.source, self.output)

    def test_svg_manifest_roundtrip(self):
        def fake_command(args, **kwargs):
            self.assertEqual(args[1], "export-svg")
            self.assertIn("--json", args)
            generated = self.output / "page-0.svg"
            generated.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
            manifest = {
                "schemaVersion": "1.0", "format": "svg",
                "pageCount": 1, "renderedCount": 1,
                "pages": [{
                    "page": 0, "path": str(generated),
                    "bytes": generated.stat().st_size,
                    "overflowCellLines": 0,
                }],
            }
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(manifest).encode(), stderr=b"")
        with patch.object(preview.shutil, "which", return_value="/usr/bin/rhwp"), patch.object(preview.subprocess, "run", side_effect=fake_command):
            result = preview.render_svg_manifest(self.source, self.output)
        self.assertEqual(result["rendered_count"], 1)
        self.assertEqual(result["pages"][0]["sha256"], preview.hashlib.sha256(
            (self.output / "page-0.svg").read_bytes()).hexdigest())
        self.assertEqual(result["render_authority"], "THIRD_PARTY_SVG_NOT_NATIVE_HANCOM")

    def test_non_empty_output_refused(self):
        (self.output / "existing.txt").write_text("do not replace")
        with self.assertRaisesRegex(ValueError, "OUTPUT_DIR_MUST_BE_EMPTY"):
            preview.render_svg_manifest(self.source, self.output)

    def test_external_svg_path_rejected(self):
        outside = self.root / "outside.svg"
        outside.write_text("<svg></svg>")
        manifest = {
            "format": "svg", "pageCount": 1,
            "pages": [{"page": 0, "path": str(outside)}],
        }
        with patch.object(preview.shutil, "which", return_value="/usr/bin/rhwp"), patch.object(
            preview.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(manifest).encode(), stderr=b""),
        ):
            with self.assertRaisesRegex(RuntimeError, "UNEXPECTED_SVG_PATH"):
                preview.render_svg_manifest(self.source, self.output)

    def test_mocked_cli_failure_is_not_a_preview(self):
        with patch.object(preview.shutil, "which", return_value="/usr/bin/rhwp"), patch.object(
            preview.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 2, stdout=b"", stderr=b"failed"),
        ):
            with self.assertRaisesRegex(preview.RhwpPreviewUnavailable, "RENDER_FAILED"):
                preview.render_svg_manifest(self.source, self.output)


if __name__ == "__main__":
    unittest.main()
