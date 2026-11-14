"""P4.26 named layout design system and P3.38 style-profile pass-through."""
from __future__ import annotations

import unittest

from hwpx_mcp.orchestration.p426_layout_tokens import (
    PROFILES, compile_layout_tokens, normalize_layout_tokens,
)
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan


class P426LayoutTokenTests(unittest.TestCase):
    def test_three_native_visual_profiles(self):
        self.assertEqual(set(PROFILES), {
            "science-lab", "academic-journal", "institutional-clean",
        })
        for name in PROFILES:
            with self.subTest(name=name):
                compiled = compile_layout_tokens(name)
                self.assertEqual(len(compiled["tokens_sha256"]), 64)
                self.assertEqual(compiled["tokens"]["name"], name)
                self.assertGreater(compiled["geometry"]["content_width_mm"], 140)

    def test_repeatable_digest_and_controlled_override(self):
        first = compile_layout_tokens({
            "base": "science-lab",
            "typography": {"body_line_percent": 160},
            "page": {"margins_mm": [24, 22, 20, 20]},
        })
        second = compile_layout_tokens({
            "page": {"margins_mm": [24, 22, 20, 20]},
            "typography": {"body_line_percent": 160},
            "base": "science-lab",
        })
        self.assertEqual(first["tokens_sha256"], second["tokens_sha256"])
        self.assertEqual(first["style_profile"], second["style_profile"])
        self.assertEqual(first["geometry"]["content_width_mm"], 164)
        self.assertEqual(first["style_profile"]["roles"]["body"]["paragraph"]["line_spacing_percent"], 160)

    def test_report_frontend_propagates_layout_tokens_to_rich_compiler(self):
        from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
        plan = build_report_plan(
            title="회로 분석", layout={"base": "science-lab",
                                     "typography": {"body_line_percent": 160}},
            sections=[{"heading": "이론", "content": [
                {"type": "paragraph", "text": "정확한 조판 입력"},
            ]}],
        )
        compiled = compile_rich_document_plan(plan)
        self.assertEqual(
            compiled["plan"]["style_profile"]["roles"]["body"]["paragraph"]["line_spacing_percent"],
            160,
        )
        self.assertEqual(compiled["plan"]["style_profile"]["name"], "science-lab")

    def test_preview_and_create_share_one_layout_profile(self):
        from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
        params = dict(title="반복 가능한 결과",
                      sections=[{"heading": "연구", "paragraphs": ["측정 과정"]}],
                      layout="academic-journal")
        p1 = compile_rich_document_plan(build_report_plan(**params))
        p2 = compile_rich_document_plan(build_report_plan(**params))
        self.assertEqual(p1["plan_sha256"], p2["plan_sha256"])
        self.assertEqual(p1["plan"]["style_profile"],
                         compile_layout_tokens("academic-journal")["style_profile"])

    def test_fail_unusable_page_geometry(self):
        with self.assertRaisesRegex(ValueError, "BODY_GEOMETRY"):
            normalize_layout_tokens({"page": {"margins_mm": [60, 60, 60, 60]}})

    def test_disallow_unrecognized_css_like_tokens(self):
        with self.assertRaisesRegex(ValueError, "OVERRIDES"):
            normalize_layout_tokens({"typography": {"drop_shadow": "blue"}})

    def test_forged_fonts_and_unsupported_paper_rejected(self):
        with self.assertRaisesRegex(ValueError, "FONT_INVALID"):
            normalize_layout_tokens({"typography": {"korean_font": ""}})
        with self.assertRaisesRegex(ValueError, "PAPER_NOT_SUPPORTED"):
            normalize_layout_tokens({"page": {"paper": "US-Letter"}})

    def test_compiler_keeps_the_actual_native_style_profile(self):
        compiled = compile_layout_tokens("academic-journal")
        requested = {
            "preset": "academic-report",
            "style_profile": compiled["style_profile"],
            "sections": [{"blocks": [
                {"type": "title", "text": "실험 결과"},
                {"type": "paragraph", "text": "문단 간격 적용"},
            ]}],
        }
        actual = compile_rich_document_plan(requested)
        self.assertEqual(
            actual["plan"]["style_profile"], compiled["style_profile"]
        )
        self.assertIsNotNone(actual["plan_sha256"])
        self.assertEqual(actual["plan"]["blocks"][1]["text"], "문단 간격 적용")


if __name__ == "__main__":
    unittest.main()
