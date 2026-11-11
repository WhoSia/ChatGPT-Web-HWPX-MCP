"""Visual caption paragraph clearance using real SVG baseline positions."""
from __future__ import annotations

import unittest

from scripts.p426_visual_spacing_audit import audit_caption_to_body_gap


def example_svg(caption_y: float, body_y: float) -> bytes:
    return f'''<svg xmlns="http://www.w3.org/2000/svg">
      <text x="5" y="{caption_y}">그림 1. 전압과 전류의 합성 선형 관계</text>
      <text x="5" y="{body_y}">아래 표는 긴 표의 분할과 반복 머리글 기능 검증을 위해</text>
    </svg>'''.encode("utf-8")


class SvgClearanceTests(unittest.TestCase):
    caption = "그림 1. 전압과 전류의 합성 선형 관계"
    body = "아래 표는 긴 표의 분할과"

    def test_detects_baselines_too_close(self):
        result = audit_caption_to_body_gap(
            [example_svg(508.57, 515.15)], self.caption, self.body
        )
        self.assertEqual(result["status"], "GAP_BELOW_THRESHOLD")
        self.assertAlmostEqual(result["baseline_gap"], 6.58)

    def test_accepts_spaced_caption_and_body(self):
        result = audit_caption_to_body_gap(
            [example_svg(508.57, 537.15)], self.caption, self.body
        )
        self.assertEqual(result["status"], "BASELINE_CLEARANCE_ACCEPTED")
        self.assertGreater(result["baseline_gap"], 16)

    def test_rejects_ambiguous_occurrences(self):
        svg = example_svg(508.57, 537.15)
        result = audit_caption_to_body_gap(
            [svg, svg], self.caption, self.body
        )
        self.assertEqual(result["status"], "AMBIGUOUS_OR_MISSING_TEXT")

    def test_rejects_invalid_inputs(self):
        with self.assertRaisesRegex(ValueError, "CAPTION_AUDIT_GAP_INVALID"):
            audit_caption_to_body_gap(
                [example_svg(10, 30)], self.caption, self.body,
                minimum_baseline_gap=-5,
            )


if __name__ == "__main__":
    unittest.main()
