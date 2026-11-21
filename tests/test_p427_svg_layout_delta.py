from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx_mcp.render.p426_rhwp_svg_preview import RhwpPreviewUnavailable
from hwpx_mcp.render.p427_svg_layout_delta import compare_rhwp_svg_layout, preview_rhwp_layout


def page(text: str, *, wrapped: bool = False, y: int = 45) -> bytes:
    second = '<text y="31">long</text>' if wrapped else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 100">'
        '<defs><line x1="0" y1="1" x2="100" y2="1"/></defs>'
        f'<g clip-path="url(#cell-clip-1)"><text x="1" y="20">{text}</text>'
        f'<text x="2" y="20">.</text>{second}</g>'
        f'<line x1="10" y1="{y}" x2="110" y2="{y}"/>'
        '<line x1="10" y1="1" x2="10" y2="99"/></svg>'
    ).encode()


class SvgLayoutDeltaTests(unittest.TestCase):
    def test_changed_glyphs_do_not_imply_layout_movement(self):
        result = compare_rhwp_svg_layout(page("before"), page("after"))
        self.assertTrue(result["svg_changed"])
        self.assertFalse(result["layout_signal_observed"])
        self.assertEqual(result["cell_text_baseline_count"], {"before": 1, "after": 1})

    def test_wrap_and_horizontal_rule_movement_are_visible(self):
        result = compare_rhwp_svg_layout(page("before"), page("after", wrapped=True, y=57))
        self.assertTrue(result["layout_signal_observed"])
        self.assertEqual(result["cell_text_baseline_count"], {"before": 1, "after": 2})
        self.assertEqual(result["horizontal_rules"], {
            "old_positions_absent": 1, "new_positions_added": 1,
            "max_paired_vertical_delta_svg_units": 12,
        })

    @patch("hwpx_mcp.render.p427_svg_layout_delta.rhwp_capability", return_value={"available": False})
    def test_missing_renderer_reports_unavailable(self, _capability):
        result = preview_rhwp_layout(Path("before.hwpx"), Path("after.hwpx"), max_pages=1)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "RHWP_BINARY_NOT_INSTALLED")
        self.assertEqual(result["pages"], [])
        self.assertNotIn("layout_signal_pages", result)

    @patch("hwpx_mcp.render.p427_svg_layout_delta.rhwp_capability", return_value={"available": True})
    @patch("hwpx_mcp.render.p427_svg_layout_delta.render_svg_manifest")
    def test_compares_common_pages_and_retains_page_count_change(self, render, _capability):
        def emit(path, output, *, page_index, **_options):
            rendered = output / "observed.svg"
            rendered.write_bytes(page(path.stem))
            return {"page_count": 1 if path.stem == "before" else 2,
                    "pages": [{"page": page_index, "path": str(rendered)}]}
        render.side_effect = emit
        result = preview_rhwp_layout(Path("before.hwpx"), Path("after.hwpx"), max_pages=3)
        self.assertEqual(result["status"], "COMPARED")
        self.assertTrue(result["page_count_changed"])
        self.assertFalse(result["all_pages_compared"])
        self.assertEqual([row["page"] for row in result["pages"]], [1])
        self.assertEqual(render.call_count, 2)

    @patch("hwpx_mcp.render.p427_svg_layout_delta.rhwp_capability", return_value={"available": True})
    @patch("hwpx_mcp.render.p427_svg_layout_delta.render_svg_manifest")
    def test_selects_later_pages_and_reports_missing_pairs(self, render, _capability):
        def emit(path, output, *, page_index, **_options):
            total = 5 if path.stem == "before" else 4
            if page_index >= total:
                raise RhwpPreviewUnavailable("RHWP_RENDER_FAILED")
            rendered = output / "observed.svg"
            rendered.write_bytes(page(path.stem, wrapped=path.stem == "after" and page_index == 3))
            return {"page_count": total, "pages": [{"page": page_index, "path": str(rendered)}]}

        render.side_effect = emit
        before, after = Path("before.hwpx"), Path("after.hwpx")
        result = preview_rhwp_layout(before, after, start_page=3, max_pages=3)
        self.assertEqual([row["page"] for row in result["pages"]], [3, 4])
        self.assertEqual([call.kwargs["page_index"] for call in render.call_args_list], [2, 2, 3, 3])
        self.assertFalse(result["all_pages_compared"])
        self.assertEqual(result["svg_changed_pages"], [3, 4])
        self.assertEqual(result["layout_signal_pages"], [4])

        result = preview_rhwp_layout(before, after, start_page=5, max_pages=1)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "RHWP_LAYOUT_START_PAGE_OUTSIDE_COMMON_RANGE")
        self.assertEqual(result["page_count"], {"before": 5, "after": 4})
        self.assertEqual(result["pages"], [])
        self.assertNotIn("layout_signal_pages", result)

    def test_rejects_invalid_one_based_start_page(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "START_PAGE_INVALID"):
                    preview_rhwp_layout(Path("before.hwpx"), Path("after.hwpx"),
                                        start_page=value, max_pages=1)
