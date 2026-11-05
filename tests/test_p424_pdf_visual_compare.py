"""Synthetic page-level visual regression tests, no user PDF in public CI."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p424_pdf_visual_compare.py"


def load_script():
    spec = importlib.util.spec_from_file_location("p424_pdf_visual_compare", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class P424PdfVisualCompareTests(unittest.TestCase):
    def test_invalid_dpi_rejected_before_optional_dependency(self):
        with self.assertRaisesRegex(ValueError, "dpi"):
            load_script().compare_pdf_pages(Path("a.pdf"), Path("b.pdf"), dpi=20)

    def test_invalid_threshold_rejected(self):
        with self.assertRaisesRegex(ValueError, "threshold"):
            load_script().compare_pdf_pages(
                Path("a.pdf"), Path("b.pdf"), pixel_delta_threshold=-1
            )


@unittest.skipUnless(importlib.util.find_spec("fitz"), "PyMuPDF optional developer dependency")
class P424PdfVisualRealRasterTests(unittest.TestCase):
    def make_pdf(self, path: Path, *, text: str, pages: int = 1):
        import fitz
        with fitz.open() as doc:
            for _ in range(pages):
                page = doc.new_page(width=595, height=842)
                if text:
                    page.insert_text((70, 100), text)
            doc.save(path)

    def test_identical_pdf_reports_zero_changed_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "before.pdf"
            self.make_pdf(baseline, text="One")
            report = load_script().compare_pdf_pages(baseline, baseline, dpi=72)
            self.assertEqual(report["pages"][0]["fraction_changed_pixels"], 0)
            self.assertEqual(report["baseline_pages"], 1)
            self.assertEqual(report["visual_acceptance"], "REQUIRES_HUMAN_PAGE_REVIEW")

    def test_changed_text_is_not_marked_as_visual_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, candidate = Path(tmp) / "before.pdf", Path(tmp) / "after.pdf"
            self.make_pdf(baseline, text="One")
            self.make_pdf(candidate, text="Two")
            report = load_script().compare_pdf_pages(baseline, candidate, dpi=72)
            self.assertGreater(report["pages"][0]["fraction_changed_pixels"], 0)
            self.assertFalse(report["native_hancom_render_verified"])

    def test_added_page_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, candidate = Path(tmp) / "before.pdf", Path(tmp) / "after.pdf"
            self.make_pdf(baseline, text="Same", pages=1)
            self.make_pdf(candidate, text="Same", pages=2)
            report = load_script().compare_pdf_pages(baseline, candidate, dpi=72)
            self.assertEqual(report["pages"][1]["status"], "MISSING_PAGE")


if __name__ == "__main__":
    unittest.main()
