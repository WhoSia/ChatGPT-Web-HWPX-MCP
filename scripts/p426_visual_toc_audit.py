"""Cross-check native TOC cached page numbers against observed rhwp SVG pages.

This is an independent-renderer diagnostic, NOT an automatic document
rewrite and not an assertion of Windows Hancom page-number parity.
"""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree


def _visual_lines(svg: bytes) -> list[str]:
    root = ElementTree.fromstring(svg)
    groups: dict[float, list[tuple[float, str]]] = {}
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "text":
            continue
        data = "".join(item.itertext())
        if not data.strip():
            continue
        try:
            x, y = float(item.get("x", "")), float(item.get("y", ""))
        except ValueError:
            continue
        groups.setdefault(round(y, 1), []).append((x, data))
    return [
        re.sub(r"\s+", "", "".join(text for _, text in sorted(group)))
        for _, group in sorted(groups.items())
    ]


def audit_toc_page_cache(
    svg_pages: list[bytes], headings: list[str],
) -> dict:
    if not isinstance(svg_pages, list) or not svg_pages:
        raise ValueError("TOC_VISUAL_PAGES_INVALID")
    if not isinstance(headings, list) or not headings or any(
        not isinstance(title, str) or not title.strip() for title in headings
    ):
        raise ValueError("TOC_EXPECTED_HEADINGS_INVALID")

    lines_by_page = [_visual_lines(svg) for svg in svg_pages]
    observed = []
    for number, title in enumerate(headings, 1):
        heading = f"{number}." + re.sub(r"\s+", "", title)
        located = [
            page_index + 1
            for page_index, lines in enumerate(lines_by_page)
            if heading in lines
        ]
        cached = []
        matcher = re.compile(re.escape(heading) + r"(\d+)")
        for line in lines_by_page[0]:
            match = matcher.fullmatch(line)
            if match:
                cached.append(int(match.group(1)))
        actual_page = located[0] if len(located) == 1 else None
        cached_page = cached[0] if len(cached) == 1 else None
        observed.append({
            "heading": title,
            "heading_index": number,
            "toc_cached_page": cached_page,
            "rendered_heading_page": actual_page,
            "mismatch": (
                cached_page != actual_page
                if cached_page is not None and actual_page is not None else None
            ),
        })

    mismatches = [item for item in observed if item["mismatch"] is True]
    unknown = [item for item in observed if item["mismatch"] is None]
    return {
        "authority": "RHWP_SVG_OBSERVATION_NOT_NATIVE_HANCOM_PAGINATION",
        "status": "INCOMPLETE" if unknown else (
            "STALE_TOC_PAGE_CACHE" if mismatches else "CONSISTENT_IN_THIS_RENDERER"
        ),
        "headings": observed,
        "mismatch_count": len(mismatches),
        "unresolved_heading_count": len(unknown),
        "automatically_repaired": False,
    }
