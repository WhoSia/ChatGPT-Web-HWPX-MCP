"""Compare observable layout signals in paired rhwp SVG pages."""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from hwpx_mcp.render.p426_rhwp_svg_preview import (
    RhwpPreviewUnavailable, render_svg_manifest, rhwp_capability,
)

SVG = "{http://www.w3.org/2000/svg}"
MAX_LAYOUT_PREVIEW_PAGES = 3


def _coordinate(value: str | None) -> float | None:
    try:
        number = float(value) if value is not None else math.nan
    except ValueError:
        return None
    return round(number, 2) if math.isfinite(number) else None


def _signals(data: bytes) -> tuple[tuple, dict, int]:
    root = ET.fromstring(data)
    if root.tag != SVG + "svg":
        raise ValueError("RHWP_LAYOUT_NOT_SVG")
    rules: dict[tuple[float, float], list[float]] = defaultdict(list)
    cell_bands: dict[ET.Element, set[float]] = defaultdict(set)
    stack = [(root, None)]
    while stack:
        node, cell = stack.pop()
        if node.tag == SVG + "defs":
            continue
        if node.tag == SVG + "g" and node.get("clip-path", "").startswith("url(#cell-clip-"):
            cell = node
        if node.tag == SVG + "text" and cell is not None and "".join(node.itertext()).strip():
            y = _coordinate(node.get("y"))
            if y is not None:
                cell_bands[cell].add(y)
        if node.tag == SVG + "line":
            x1, y1, x2, y2 = (_coordinate(node.get(k)) for k in ("x1", "y1", "x2", "y2"))
            if None not in (x1, y1, x2, y2) and y1 == y2 and x1 != x2:
                rules[min(x1, x2), max(x1, x2)].append(y1)
        stack.extend((child, cell) for child in node)
    canvas = tuple(root.get(k) for k in ("width", "height", "viewBox"))
    return canvas, rules, sum(map(len, cell_bands.values()))


def compare_rhwp_svg_layout(before: bytes, after: bytes) -> dict:
    """Measure renderer signals, using SVG user units and no text in the report."""
    old_canvas, old_rules, old_bands = _signals(before)
    new_canvas, new_rules, new_bands = _signals(after)
    removed = added = 0
    deltas = []
    for span in old_rules.keys() | new_rules.keys():
        old_y, new_y = old_rules.get(span, []), new_rules.get(span, [])
        old_count, new_count = Counter(old_y), Counter(new_y)
        removed += (old_count - new_count).total()
        added += (new_count - old_count).total()
        # Pair same-span rules by vertical order only when cardinality agrees.
        # This indicates observed displacement, without assigning a table ID.
        if len(old_y) == len(new_y):
            deltas.extend(round(b - a, 2) for a, b in zip(sorted(old_y), sorted(new_y)))
    canvas_changed = old_canvas != new_canvas
    changed = before != after
    return {
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "svg_changed": changed,
        "canvas_changed": canvas_changed,
        "cell_text_baseline_count": {"before": old_bands, "after": new_bands},
        "horizontal_rules": {
            "old_positions_absent": removed,
            "new_positions_added": added,
            "max_paired_vertical_delta_svg_units": max(deltas, key=lambda d: (abs(d), d), default=0),
        },
        "layout_signal_observed": canvas_changed or old_bands != new_bands or bool(removed or added),
    }


def preview_rhwp_layout(source: Path, candidate: Path, *, max_pages: int, start_page: int = 1) -> dict:
    """Compare the requested contiguous page range without returning documents or SVG bytes."""
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_LAYOUT_PREVIEW_PAGES:
        raise ValueError("P427_LAYOUT_PREVIEW_PAGE_LIMIT_INVALID")
    if type(start_page) is not int or start_page < 1:
        raise ValueError("P427_LAYOUT_PREVIEW_START_PAGE_INVALID")
    summary = {
        "status": "UNAVAILABLE",
        "engine": "RHWP_SVG_PREVIEW",
        "render_authority": "THIRD_PARTY_SVG_NOT_NATIVE_HANCOM",
        "requested_pages": max_pages,
        "start_page": start_page,
        "pages": [],
    }
    if not rhwp_capability()["available"]:
        return {**summary, "reason": "RHWP_BINARY_NOT_INSTALLED"}

    page_counts: dict[str, int] = {}
    with TemporaryDirectory(prefix="p427-layout-preview-") as tmp:
        try:
            for index in range(start_page - 1, start_page - 1 + max_pages):
                rendered = {}
                for label, path in (("before", source), ("after", candidate)):
                    output = Path(tmp) / f"{label}-{index}"
                    output.mkdir()
                    try:
                        manifest = render_svg_manifest(
                            path, output, profile="print", page_index=index,
                            max_pages=1, timeout_seconds=5,
                        )
                    except RhwpPreviewUnavailable as error:
                        if index == 0 or str(error) != "RHWP_RENDER_FAILED":
                            raise
                        # rhwp 0.8.7 exits without a manifest for missing pages.
                        # Read its page count through page zero before classifying the failure.
                        probe = Path(tmp) / f"{label}-page-count"
                        probe.mkdir()
                        first_page = render_svg_manifest(
                            path, probe, profile="print", page_index=0,
                            max_pages=1, timeout_seconds=5,
                        )
                        total = first_page["page_count"]
                        if type(total) is not int or not 1 <= total <= index:
                            raise
                        manifest = {"page_count": total, "pages": []}
                    total = manifest["page_count"]
                    pages = manifest["pages"]
                    if type(total) is not int or total < 1 or total != page_counts.get(label, total):
                        raise RuntimeError("RHWP_LAYOUT_PAGE_MANIFEST_INVALID")
                    page_counts[label] = total
                    if index >= total and not pages:
                        continue
                    if len(pages) != 1 or pages[0]["page"] != index or index >= total:
                        raise RuntimeError("RHWP_LAYOUT_PAGE_MANIFEST_INVALID")
                    rendered[label] = Path(pages[0]["path"]).read_bytes()
                if len(rendered) < 2:
                    summary["reason"] = "RHWP_LAYOUT_START_PAGE_OUTSIDE_COMMON_RANGE"
                    break
                summary["pages"].append({
                    "page": index + 1,
                    **compare_rhwp_svg_layout(rendered["before"], rendered["after"]),
                })
                if index + 1 >= min(page_counts.values()):
                    break
        except RhwpPreviewUnavailable as error:
            summary["reason"] = str(error)
        except (OSError, ValueError, RuntimeError, ET.ParseError):
            summary["reason"] = "RHWP_LAYOUT_OBSERVATION_FAILED"

    if len(page_counts) == 2:
        summary["page_count"] = page_counts
        summary["page_count_changed"] = page_counts["before"] != page_counts["after"]
        summary["all_pages_compared"] = (
            start_page == 1 and len(summary["pages"]) == max(page_counts.values())
        )
    if summary["pages"]:
        summary["svg_changed_pages"] = [
            row["page"] for row in summary["pages"] if row["svg_changed"]
        ]
        summary["layout_signal_pages"] = [
            row["page"] for row in summary["pages"] if row["layout_signal_observed"]
        ]
        summary["status"] = "PARTIAL" if "reason" in summary else "COMPARED"
    return summary
