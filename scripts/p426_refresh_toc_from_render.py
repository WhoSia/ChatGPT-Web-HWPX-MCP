#!/usr/bin/env python3
"""Apply actual rendered SVG page evidence to *cached* native HWPX TOC.

The original source is preserved. This produces a second HWPX revision
which MUST be rendered again before its page number quality is accepted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hwpx_mcp.render.p426_toc_cache_refresh import (
    discover_native_toc_headings, refresh_native_toc_cache_from_svg,
)
from scripts.p426_visual_toc_audit import audit_toc_page_cache

SHOWCASE_HEADINGS = (
    "연구 배경", "이론적 분석", "합성 실험 결과", "결론 및 한계"
)


def load_complete_svg_pages(render_root: Path) -> list[bytes]:
    render_root = Path(render_root)
    manifest = json.loads(
        (render_root / "p426_rhwp_render_observation.json").read_text(encoding="utf-8")
    )
    entries = manifest.get("svg_pages")
    count = manifest.get("page_count_reported")
    if not isinstance(entries, list) or not entries or type(count) is not int:
        raise ValueError("TOC_RENDER_MANIFEST_INVALID")
    if len(entries) != count or [
        entry.get("requested_page_index") for entry in entries
    ] != list(range(count)):
        raise ValueError("TOC_PARTIAL_OR_OUT_OF_ORDER_RENDER_INVALID")
    pages = []
    for entry in entries:
        rel = entry.get("relative_svg_path")
        if not isinstance(rel, str):
            raise ValueError("TOC_SVG_RELATIVE_PATH_INVALID")
        path = (render_root / rel).resolve()
        if not path.is_relative_to(render_root.resolve()):
            raise ValueError("TOC_SVG_PATH_ESCAPE")
        data = path.read_bytes()
        if not data or len(data) > 4 * 1024 * 1024:
            raise ValueError("TOC_SVG_DATA_INVALID")
        pages.append(data)
    return pages


def refresh_from_render(
    source: Path, render_root: Path, destination: Path,
    headings: list[str] | None = None,
) -> dict:
    selected = discover_native_toc_headings(source) if headings is None else headings
    pages = load_complete_svg_pages(render_root)
    before = audit_toc_page_cache(pages, selected)
    result = refresh_native_toc_cache_from_svg(source, destination, pages, selected)
    return {
        **result,
        "source_render_toc_audit": before,
        "rendered_pages_inspected": len(pages),
        "next_step": "RERENDER_REFERSHED_HWPX_AND_REPEAT_TOC_AUDIT",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--render-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    args = parser.parse_args()
    result = refresh_from_render(args.source, args.render_root, args.output)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
