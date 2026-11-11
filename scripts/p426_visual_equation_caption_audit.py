"""Evidence that equation labels actually appear in rendered SVG pages.

This is a displayability audit; a separate native HWPX equation-map
roundtrip verifies that the equations themselves remain editable.
"""
from __future__ import annotations

import re
from scripts.p426_visual_toc_audit import _visual_lines


def audit_visible_equation_captions(
    svg_pages: list[bytes], captions: list[str],
) -> dict:
    if not svg_pages or any(not isinstance(page, bytes) for page in svg_pages):
        raise ValueError("EQUATION_CAPTION_SVG_INVALID")
    if not captions or any(not isinstance(c, str) or not c.strip() for c in captions):
        raise ValueError("EQUATION_CAPTIONS_INVALID")
    observed = []
    for page_num, page in enumerate(svg_pages, 1):
        observed.extend((page_num, line) for line in _visual_lines(page))
    items = []
    for caption in captions:
        target = re.sub(r"\s+", "", caption)
        locations = [i for i, line in observed if line == target]
        items.append({
            "caption": caption, "rendered_pages": locations,
            "unique": len(locations) == 1,
        })
    return {
        "status": "ALL_VISIBLE" if all(row["unique"] for row in items)
        else "MISSING_OR_AMBIGUOUS",
        "captions": items,
        "authority": "OBSERVED_RHWP_SVG_TEXT_NOT_HANCOM_RENDERING",
        "math_editability_verified_here": False,
    }
