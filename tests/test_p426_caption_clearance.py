"""Reusable professional figure-caption clearance on native HWPX report plans."""
from __future__ import annotations

import unittest

from hwpx_mcp.interfaces.p425_report_presets import build_report_plan


class NativeCaptionClearanceTests(unittest.TestCase):
    def _build(self, clearance=0, existing=None):
        paragraph = {"type": "paragraph", "text": "캡션 아래 이어지는 본문"}
        if existing is not None:
            paragraph["paragraph_format"] = {"spacing_before_pt": existing}
        return build_report_plan(
            title="합성 보고서",
            caption_clearance_pt=clearance,
            sections=[{"heading": "결과", "content": [
                {"type": "figure", "image_format": "png",
                 "content_base64": "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGMUscn7z8DAwMDEAAUAGa4BwYhFMToAAAAASUVORK5CYII=",
                 "caption": "합성 그림", "width": 12000, "height": 6000},
                paragraph,
            ]}],
        )

    def test_opt_in_clearance_applies_to_next_paragraph_only(self):
        plan = self._build(clearance=14)
        blocks = plan["sections"][0]["blocks"]
        following = [b for b in blocks if b["type"] == "paragraph"][-1]
        self.assertEqual(following["paragraph_format"]["spacing_before_pt"], 14.0)

    def test_existing_larger_spacing_is_preserved(self):
        plan = self._build(clearance=12, existing=20)
        body = [b for b in plan["sections"][0]["blocks"] if b["type"] == "paragraph"][-1]
        self.assertEqual(body["paragraph_format"]["spacing_before_pt"], 20.0)

    def test_feature_defaults_to_off(self):
        plan = self._build()
        body = [b for b in plan["sections"][0]["blocks"] if b["type"] == "paragraph"][-1]
        self.assertNotIn("paragraph_format", body)

    def test_rejects_invalid_clearance(self):
        for invalid in (-1, 37, "14", True):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "CAPTION_CLEARANCE_INVALID"):
                self._build(clearance=invalid)


if __name__ == "__main__":
    unittest.main()
