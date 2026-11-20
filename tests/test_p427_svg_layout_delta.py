from __future__ import annotations

import unittest

from hwpx_mcp.render.p427_svg_layout_delta import compare_rhwp_svg_layout


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
