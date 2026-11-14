"""Rendering quality: actual equation labels must appear on pages."""
from __future__ import annotations

import unittest
from scripts.p426_visual_equation_caption_audit import audit_visible_equation_captions


def svg(*lines: str) -> bytes:
    content = "".join(
        f'<text x="20" y="{100+i*22}">{text}</text>'
        for i,text in enumerate(lines)
    )
    return ('<svg xmlns="http://www.w3.org/2000/svg">' + content + '</svg>').encode()


class EquationCaptionVisualAcceptanceTests(unittest.TestCase):
    def test_two_visible_labels(self):
        r=audit_visible_equation_captions(
            [svg("식 1. 옴의 법칙", "식 2. 저항의 정의")],
            ["식 1. 옴의 법칙", "식 2. 저항의 정의"],
        )
        self.assertEqual(r["status"], "ALL_VISIBLE")
        self.assertEqual(r["captions"][0]["rendered_pages"], [1])

    def test_missing_label_is_detected(self):
        r=audit_visible_equation_captions(
            [svg("식 1. 옴의 법칙")],
            ["식 1. 옴의 법칙", "식 2. 저항의 정의"],
        )
        self.assertEqual(r["status"], "MISSING_OR_AMBIGUOUS")

    def test_duplicate_caption_is_not_accepted(self):
        r=audit_visible_equation_captions(
            [svg("식 1. 옴의 법칙"), svg("식 1. 옴의 법칙")],
            ["식 1. 옴의 법칙"],
        )
        self.assertEqual(r["status"], "MISSING_OR_AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
