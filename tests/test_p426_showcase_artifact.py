"""Executable acceptance of the user-downloadable P4.26 synthetic report."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.p426_generate_native_showcase import (
    create_showcase, make_synthetic_curve_png,
)


class NativeShowcaseArtifactTests(unittest.TestCase):
    def test_chart_png_signature_and_geometry(self):
        png = make_synthetic_curve_png()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 1000)

    def test_showcase_creates_real_readable_native_hwpx_with_manifest(self):
        with tempfile.TemporaryDirectory(prefix="p426-showcase-accept-") as tmp:
            folder = Path(tmp)
            report = create_showcase(folder)
            self.assertEqual(report["native_tables"], 3)
            self.assertEqual(report["native_segment_rows"], [28, 28, 26])
            self.assertEqual(report["table_cells"], 246)
            self.assertEqual(report["long_table_mode"], "NATIVE_SEGMENTED_WITH_PAGE_BREAKS")
            self.assertEqual(report["table_rows"], 80)
            self.assertEqual(report["target_max_rows_per_segment"], 28)
            self.assertEqual(report["native_pictures"], 1)
            self.assertEqual(report["native_equations"], 2)
            self.assertEqual(report["native_footnotes"], 1)
            self.assertGreaterEqual(report["native_crossrefs"], 1)
            self.assertFalse(report["windows_hancom_render_verified"])
            self.assertFalse(report["chatgpt_host_delivery_verified"])
            doc = folder / report["filename"]
            self.assertTrue(doc.exists())
            self.assertTrue(doc.read_bytes().startswith(b"PK"))
            stored = json.loads((folder / "P426_생성검증_manifest.json").read_text("utf-8"))
            self.assertEqual(stored, report)

    def test_36_row_budget_keeps_exact_79_data_records(self):
        with tempfile.TemporaryDirectory(prefix="p426-showcase-36-") as tmp:
            result = create_showcase(Path(tmp), table_segment_rows=36)
            self.assertEqual(result["native_tables"], 3)
            self.assertEqual(result["native_segment_rows"], [36, 36, 10])
            self.assertEqual(result["table_cells"], 246)
            self.assertEqual(result["table_rows"], 80)
            self.assertEqual(result["target_max_rows_per_segment"], 36)
            self.assertIn("36행분할", result["filename"])

    def test_showcase_refuses_overwriting_a_report_without_authorization(self):
        with tempfile.TemporaryDirectory(prefix="p426-showcase-overwrite-") as tmp:
            output = Path(tmp)
            create_showcase(output)
            with self.assertRaises(FileExistsError):
                create_showcase(output)


if __name__ == "__main__":
    unittest.main()
