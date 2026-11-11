"""Native editable math plus cross-renderer visible equation-caption fallback."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p2_document import build_document_map


def report(mode: str = "native"):
    return build_report_plan(
        title="수식 표시 품질",
        number_captions=True,
        equation_caption_mode=mode,
        sections=[{"heading": "수식", "content": [
            {"type": "equation", "latex": "V=IR", "caption": "옴의 법칙"},
            {"type": "equation", "latex": r"\frac{V}{I}=R", "caption": "저항의 정의"},
        ]}],
    )


class EquationCaptionExperienceTests(unittest.TestCase):
    def test_default_keeps_actual_native_caption_object(self):
        blocks = report()["sections"][0]["blocks"]
        equations = [b for b in blocks if b["type"] == "equation"]
        self.assertEqual([b.get("caption") for b in equations],
                         ["식 1. 옴의 법칙", "식 2. 저항의 정의"])
        self.assertFalse(any(b.get("_p426_caption_for") for b in blocks))

    def test_explicit_fallback_uses_visible_paragraphs_no_duplicate_native_caption(self):
        blocks = report("visible-paragraph")["sections"][0]["blocks"]
        equations = [b for b in blocks if b["type"] == "equation"]
        captions = [b for b in blocks if b.get("_p426_caption_for") is not None]
        self.assertEqual(len(equations), 2)
        self.assertEqual(len(captions), 2)
        self.assertTrue(all("caption" not in b for b in equations))
        self.assertEqual([b["text"] for b in captions],
                         ["식 1. 옴의 법칙", "식 2. 저항의 정의"])
        self.assertTrue(all(b["paragraph_format"]["keep_with_next"] for b in equations))

    def test_native_hwpx_keeps_two_editable_equations_and_visible_caption_text(self):
        compiled = compile_rich_document_plan(report("visible-paragraph"))
        with tempfile.TemporaryDirectory(prefix="p426-visible-equations-") as tmp:
            p = Path(tmp) / "equations.hwpx"
            receipt = compose_document_plan(p, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            equations = build_equation_map(p)["equations"]
            paragraphs = build_document_map(p)["paragraphs"]
            self.assertEqual(len(equations), 2)
            joined = "\n".join(str(q.get("text") or "") for q in paragraphs)
            self.assertIn("식 1. 옴의 법칙", joined)
            self.assertIn("식 2. 저항의 정의", joined)

    def test_rejects_ambiguous_caption_modes(self):
        with self.assertRaisesRegex(ValueError, "CAPTION_MODE_INVALID"):
            report("both")


if __name__ == "__main__":
    unittest.main()
