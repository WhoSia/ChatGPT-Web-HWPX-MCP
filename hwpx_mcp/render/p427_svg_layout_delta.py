"""Compare observable layout signals in paired rhwp SVG pages."""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from xml.etree import ElementTree as ET

SVG = "{http://www.w3.org/2000/svg}"


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
