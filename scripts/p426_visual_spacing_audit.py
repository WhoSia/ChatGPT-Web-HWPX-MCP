"""Measure actual SVG text baseline clearances near report captions.

Reports what the independent rhwp renderer drew; it is not a native
Hancom metric or proof of physical glyph bounding-box separation.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree


def _lines(svg: bytes) -> list[dict]:
    root = ElementTree.fromstring(svg)
    grouped: dict[float, list[tuple[float, str]]] = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "text":
            continue
        try:
            x = float(node.get("x", ""))
            y = float(node.get("y", ""))
        except ValueError:
            continue
        value = "".join(node.itertext())
        if value.strip():
            grouped.setdefault(round(y, 2), []).append((x, value))
    return [
        {"baseline_y": y, "text": re.sub(
            r"\\s+", "", "".join(text for _, text in sorted(parts))
        )}
        for y, parts in sorted(grouped.items())
    ]


def audit_caption_to_body_gap(
    svg_pages: list[bytes], caption: str, body_prefix: str,
    *, minimum_baseline_gap: float = 16.0,
) -> dict:
    if not svg_pages or not all(isinstance(x, bytes) for x in svg_pages):
        raise ValueError("CAPTION_AUDIT_SVG_INVALID")
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError("CAPTION_AUDIT_TITLE_INVALID")
    if not isinstance(body_prefix, str) or not body_prefix.strip():
        raise ValueError("CAPTION_AUDIT_BODY_INVALID")
    if type(minimum_baseline_gap) not in (int, float) or not 1 <= minimum_baseline_gap <= 100:
        raise ValueError("CAPTION_AUDIT_GAP_INVALID")
    title_key = re.sub(r"\\s+", "", caption)
    body_key = re.sub(r"\\s+", "", body_prefix)
    title_positions = []
    body_positions = []
    for page_index, payload in enumerate(svg_pages):
        for line in _lines(payload):
            if title_key in line["text"]:
                title_positions.append((page_index, line["baseline_y"]))
            if body_key in line["text"]:
                body_positions.append((page_index, line["baseline_y"]))
    if len(title_positions) != 1 or len(body_positions) != 1:
        return {
            "status": "AMBIGUOUS_OR_MISSING_TEXT",
            "caption_matches": len(title_positions),
            "body_matches": len(body_positions),
            "authority": "ACTUAL_RHWP_SVG_BASELINES_NOT_NATIVE_HANCOM",
        }
    caption_page, caption_y = title_positions[0]
    body_page, body_y = body_positions[0]
    gap = round(body_y - caption_y, 2) if caption_page == body_page else None
    return {
        "status": (
            "DIFFERENT_PAGES" if gap is None else
            "GAP_BELOW_THRESHOLD" if gap < minimum_baseline_gap else
            "BASELINE_CLEARANCE_ACCEPTED"
        ),
        "caption_page": caption_page + 1,
        "body_page": body_page + 1,
        "caption_baseline_y": caption_y,
        "body_baseline_y": body_y,
        "baseline_gap": gap,
        "minimum_baseline_gap": minimum_baseline_gap,
        "authority": "ACTUAL_RHWP_SVG_BASELINES_NOT_NATIVE_HANCOM",
    }
