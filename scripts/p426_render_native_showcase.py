#!/usr/bin/env python3
"""Render a real synthetic HWPX with an independently installed rhwp CLI.

Uses the optional P4.26 SVG adapter, retaining the page files and a JSON
record of observed renderer metrics. Does not generate Hancom-native PDF.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hwpx_mcp.render.p426_rhwp_svg_preview import render_svg_manifest


def create_svg_previews(
    source: Path, output: Path, *,
    executable: str = "rhwp", pages: int = 2,
) -> dict:
    if type(pages) is not int or not 1 <= pages <= 10:
        raise ValueError("RENDER_EXAMPLE_PAGE_COUNT_INVALID")
    source = Path(source)
    output = Path(output)
    if not source.is_file():
        raise FileNotFoundError("SYNTHETIC_HWPX_NOT_FOUND")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("RENDER_OUTPUT_NOT_EMPTY")
    observed = []
    first_page_total = None
    for index in range(pages):
        target = output / f"page-{index}"
        target.mkdir()
        result = render_svg_manifest(
            source, target, executable=executable,
            page_index=index, max_pages=1, profile="print",
        )
        if first_page_total is None:
            first_page_total = result["page_count"]
            if type(first_page_total) is int and first_page_total > 0:
                # Stop before asking for a page beyond the total.
                pages = min(pages, first_page_total)
        if len(result["pages"]) != 1:
            raise AssertionError("RHWP_EXAMPLE_PAGE_RENDER_COUNT_MISMATCH")
        observed.append({
            "requested_page_index": index,
            "renderer_reported_page_count": result["page_count"],
            **result["pages"][0],
        })
        if type(first_page_total) is int and index + 1 >= first_page_total:
            break

    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p426/rhwp-real-render/v1",
        "engine": "RHWP_SVG_PREVIEW",
        "renderer_build_required": True,
        "native_hancom_pdf": False,
        "actual_cli_invoked": True,
        "page_count_reported": first_page_total,
        "svg_pages": observed,
        "total_overflow_cell_lines": sum(
            x["overflow_cell_lines"] or 0 for x in observed
        ),
        "authority": "INDEPENDENT_RHWP_RENDERER_NOT_HANCOM_COMPATIBILITY_ORACLE",
        "visual_review_required": True,
    }
    (output / "p426_rhwp_render_observation.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--executable", default="rhwp")
    parser.add_argument("--pages", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(
        create_svg_previews(
            args.source, args.output_dir,
            executable=args.executable, pages=args.pages,
        ),
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
