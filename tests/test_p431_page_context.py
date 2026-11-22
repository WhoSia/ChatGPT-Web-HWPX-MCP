import unittest
from hwpx_mcp.render.p431_page_context import page_paragraph_candidates


def paragraph(index, text):
    return dict(locator=f"p_{index}", section_index=0, paragraph_index=index,
                container="section-body", text=text, text_sha256="a" * 64)


class PageContextTests(unittest.TestCase):
    def test_split_svg_text_and_duplicate_source_remain_candidates(self):
        paragraphs = [paragraph(0, "abcdefgh ijkl"), paragraph(1, "abcdefgh ijkl"),
                      paragraph(2, "next page content")]
        result = page_paragraph_candidates(
            b"<svg><defs><text>next page content</text></defs>"
            b"<text>abc<tspan>defgh</tspan></text><text>ijkl</text></svg>", paragraphs, limit=1)
        self.assertEqual(result["candidate_count"], 2)
        self.assertTrue(result["truncated"])
        self.assertFalse(result["candidates"][0]["source_text_unique"])
        self.assertFalse(result["complete_page_mapping"])

    def test_partial_paragraph_and_image_only_page_do_not_invent_mapping(self):
        paragraphs = [paragraph(0, "a paragraph spans several pages")]
        result = page_paragraph_candidates(b"<svg><text>a paragraph</text></svg>", paragraphs)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(page_paragraph_candidates(b"<svg><image/></svg>", paragraphs)["candidate_count"], 0)

    def test_continuation_covers_every_matching_paragraph_once(self):
        paragraphs = [paragraph(i, "repeated heading") for i in range(27)]
        svg = b"<svg><text>repeated heading</text></svg>"
        first = page_paragraph_candidates(svg, paragraphs)
        second = page_paragraph_candidates(svg, paragraphs, offset=first["next_candidate_offset"])
        self.assertEqual(len(first["candidates"]), 20)
        self.assertEqual(len(second["candidates"]), 7)
        self.assertIsNone(second["next_candidate_offset"])
        self.assertFalse(second["truncated"])
        self.assertEqual(len({p["locator"] for p in first["candidates"] + second["candidates"]}), 27)
