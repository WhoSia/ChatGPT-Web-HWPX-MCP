from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from lxml import etree
from hwpx import HwpxDocument

from p2_document import build_document_map
from p28_tables import _save_document
from p29_objects import _resolve_paragraph
from p325_drawing_layer import (
    HP,
    DRAWING_TAGS,
    build_drawing_layer_map,
    drawing_layer_contract,
    _find_node,
    _mutate_section,
    _bounded_int,
)

HC_URI = "http://www.hancom.co.kr/hwpml/2011/core"
HC = f"{{{HC_URI}}}"
SCHEMA = "chatgpt-web-hwpx-mcp/drawing-style/p3.26/v1"

AUTHORABLE_KINDS = {"line", "ellipse", "polygon", "arc"}
STYLEABLE_KINDS = {"line", "rect", "ellipse", "polygon", "arc"}
LINE_STYLES = {
    "SOLID", "DASH", "DOT", "DASH_DOT", "DASH_DOT_DOT",
    "LONG_DASH", "CIRCLE", "DOUBLE_SLIM", "SLIM_THICK", "THICK_SLIM",
    "SLIM_THICK_SLIM",
}
END_CAPS = {"FLAT", "ROUND"}
ARROW_STYLES = {
    "NORMAL", "ARROW", "SPEAR", "CONCAVE_ARROW", "EMPTY_DIAMOND",
    "EMPTY_CIRCLE", "EMPTY_BOX", "FILLED_DIAMOND", "FILLED_CIRCLE",
    "FILLED_BOX",
}
ARROW_SIZES = {
    "SMALL_SMALL", "SMALL_MEDIUM", "SMALL_LARGE",
    "MEDIUM_SMALL", "MEDIUM_MEDIUM", "MEDIUM_LARGE",
    "LARGE_SMALL", "LARGE_MEDIUM", "LARGE_LARGE",
}
SHADOW_TYPES = {"NONE", "DROP", "CONTINUOUS"}
ARC_TYPES = {"NORMAL", "PIE", "CHORD"}
ARC_CORNERS = {"TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"}

DEFERRED = {
    "insert_curve": "EVIDENCE_GATE_CLOSED: curve bbox depends on Hancom spline fitting not yet reconstructed.",
    "insert_connect_line": "EVIDENCE_GATE_CLOSED: smart connector geometry depends on subjectIDRef and nontrivial transforms.",
    "gradient_fill": "EVIDENCE_GATE_CLOSED: P3.26 admits solid winBrush fill only for production styling.",
    "pattern_fill": "EVIDENCE_GATE_CLOSED: hatch/pattern production semantics require a dedicated render batch.",
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _color(value: object, name: str) -> str:
    text = str(value or "").upper()
    if len(text) != 7 or not text.startswith("#") or any(ch not in "0123456789ABCDEF" for ch in text[1:]):
        raise ValueError(f"{name} must be #RRGGBB")
    return text


def _alpha(value: object, name: str = "alpha") -> int:
    return _bounded_int(value, name, 0, 255)


def _line_width(value: object) -> str:
    width = _bounded_int(value, "line_width", 1, 100000)
    return str(width)


def drawing_style_contract() -> dict:
    return {
        "phase": "P3.26",
        "schema": SCHEMA,
        "authority": "STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "ancestry": {
            "P3.25": "unified drawing-object map, layout and bounded geometry mutation",
            "python-hwpx": "dedicated add_line/add_ellipse/add_polygon/add_arc helpers; upstream Hancom render evidence",
            "P3.26": "production authoring + stroke/fill/arrowhead/shadow/transparency + shape geometry read-back",
        },
        "admitted_authoring": sorted(AUTHORABLE_KINDS),
        "styleable_families": sorted(STYLEABLE_KINDS),
        "admitted_operations": [
            "insert_line", "insert_ellipse", "insert_polygon", "insert_arc",
            "set_shape_stroke", "set_shape_fill", "clear_shape_fill",
            "set_shape_shadow", "set_shape_arrowheads",
        ],
        "deferred_operations": dict(DEFERRED),
    }


def _style_payload(node) -> dict:
    line = node.find(f"{HP}lineShape")
    fill = node.find(f"{HC}fillBrush")
    win = None if fill is None else fill.find(f"{HC}winBrush")
    shadow = node.find(f"{HP}shadow")
    points = []
    for child in node:
        local = child.tag.rsplit("}", 1)[-1]
        if local in {"startPt", "endPt", "pt", "pt0", "pt1", "pt2", "pt3", "center", "ax1", "ax2", "start1", "end1", "start2", "end2"}:
            points.append({"kind": local, **dict(sorted(child.attrib.items()))})
    return {
        "line_shape": None if line is None else dict(sorted(line.attrib.items())),
        "fill": None if win is None else dict(sorted(win.attrib.items())),
        "shadow": None if shadow is None else dict(sorted(shadow.attrib.items())),
        "shape_attributes": dict(sorted(node.attrib.items())),
        "geometry_points": points,
    }


def build_drawing_style_map(path: Path) -> dict:
    base = build_drawing_layer_map(path)
    by_identity = {
        (item["section"], item["kind"], item.get("instid") or item.get("id")): item
        for item in base["objects"]
    }
    styles = []
    with zipfile.ZipFile(path, "r") as archive:
        sections = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for section in sections:
            root = etree.fromstring(archive.read(section))
            for node in root.iter():
                kind = node.tag.rsplit("}", 1)[-1]
                if kind not in DRAWING_TAGS:
                    continue
                identity = node.get("instid") or node.get("id")
                base_item = by_identity.get((section, kind, identity))
                if base_item is None:
                    continue
                payload = {
                    "locator": base_item["locator"],
                    "kind": kind,
                    "section": section,
                    "anchor_locator": base_item.get("anchor_locator"),
                    **_style_payload(node),
                }
                styles.append(payload)
    style_seed = [
        {
            "locator": item["locator"],
            "line_shape": item["line_shape"],
            "fill": item["fill"],
            "shadow": item["shadow"],
        }
        for item in styles
    ]
    geometry_seed = [
        {
            "locator": item["locator"],
            "shape_attributes": item["shape_attributes"],
            "geometry_points": item["geometry_points"],
        }
        for item in styles
    ]
    return {
        **base,
        "style_schema": SCHEMA,
        "styles": styles,
        "drawing_style_sha256": _sha(style_seed),
        "shape_geometry_sha256": _sha(geometry_seed),
        "style_contract": drawing_style_contract(),
    }


def _created_locator(before: dict, after: dict, kind: str) -> str:
    old = {item["locator"] for item in before["objects"]}
    created = [item for item in after["objects"] if item["locator"] not in old and item["kind"] == kind]
    if len(created) != 1:
        raise ValueError(f"{kind} authoring did not yield one uniquely identifiable object")
    return created[0]["locator"]


def _author_shape(path: Path, op: dict) -> dict:
    name = str(op["op"])
    kind = name.removeprefix("insert_")
    before = build_drawing_layer_map(path)
    doc = HwpxDocument.open(str(path))
    try:
        paragraph, target = _resolve_paragraph(doc, path, op.get("anchor"))
        common = {
            "line_color": _color(op.get("line_color", "#000000"), "line_color"),
            "line_width": _line_width(op.get("line_width", 283)),
            "treat_as_char": bool(op.get("treat_as_char", False)),
        }
        if kind == "line":
            paragraph.add_line(
                _bounded_int(op.get("start_x", 0), "start_x", -10_000_000, 10_000_000),
                _bounded_int(op.get("start_y", 0), "start_y", -10_000_000, 10_000_000),
                _bounded_int(op.get("end_x", 14400), "end_x", -10_000_000, 10_000_000),
                _bounded_int(op.get("end_y", 0), "end_y", -10_000_000, 10_000_000),
                **common,
            )
        elif kind == "ellipse":
            paragraph.add_ellipse(
                _bounded_int(op.get("width", 14400), "width", 1, 10_000_000),
                _bounded_int(op.get("height", 7200), "height", 1, 10_000_000),
                fill_color=None if op.get("fill_color") is None else _color(op["fill_color"], "fill_color"),
                **common,
            )
        elif kind == "polygon":
            points = op.get("points")
            if not isinstance(points, list) or len(points) < 3:
                raise ValueError("insert_polygon requires points=[[x,y], ...] with at least 3 points in HWPUNIT")
            parsed = [
                (
                    _bounded_int(pair[0], "point_x", -10_000_000, 10_000_000),
                    _bounded_int(pair[1], "point_y", -10_000_000, 10_000_000),
                )
                for pair in points
                if isinstance(pair, (list, tuple)) and len(pair) == 2
            ]
            if len(parsed) != len(points):
                raise ValueError("every polygon point must be a 2-item coordinate pair")
            paragraph.add_polygon(
                parsed,
                fill_color=None if op.get("fill_color") is None else _color(op["fill_color"], "fill_color"),
                **common,
            )
        elif kind == "arc":
            corner = str(op.get("corner", "TOP_LEFT")).upper()
            arc_type = str(op.get("arc_type", "NORMAL")).upper()
            if corner not in ARC_CORNERS or arc_type not in ARC_TYPES:
                raise ValueError("invalid arc corner or arc_type")
            paragraph.add_arc(
                _bounded_int(op.get("width", 14400), "width", 1, 10_000_000),
                _bounded_int(op.get("height", 14400), "height", 1, 10_000_000),
                corner=corner,
                arc_type=arc_type,
                fill_color=None if op.get("fill_color") is None else _color(op["fill_color"], "fill_color"),
                **common,
            )
        else:
            raise ValueError(f"unsupported shape authoring family: {kind}")
        _save_document(doc, path, path)
    finally:
        doc.close()
    after = build_drawing_layer_map(path)
    return {
        "op": name,
        "kind": kind,
        "created_drawing": _created_locator(before, after, kind),
        "anchor": target["locator"],
    }


def _resolve_style_target(path: Path, locator: object) -> dict:
    mapped = build_drawing_style_map(path)
    value = str(locator or "")
    found = next((item for item in mapped["styles"] if item["locator"] == value), None)
    if found is None:
        raise ValueError(f"Unknown drawing locator: {value}")
    if found["kind"] not in STYLEABLE_KINDS:
        raise ValueError(f"shape styling is not admitted for family {found['kind']}")
    return found


def _mutate_style(path: Path, target: dict, mutator: Callable[[Any], dict | None]) -> dict | None:
    def apply(root):
        base = next(
            item for item in build_drawing_layer_map(path)["objects"]
            if item["locator"] == target["locator"]
        )
        node = _find_node(root, base)
        return mutator(node)
    return _mutate_section(path, target["section"], apply)


def _set_stroke(node, op: dict) -> dict:
    line = node.find(f"{HP}lineShape")
    if line is None:
        raise ValueError("shape has no lineShape")
    if "color" in op:
        line.set("color", _color(op["color"], "stroke color"))
    if "width" in op:
        line.set("width", _line_width(op["width"]))
    if "style" in op:
        style = str(op["style"]).upper()
        if style not in LINE_STYLES:
            raise ValueError(f"unsupported line style: {style}")
        line.set("style", style)
    if "end_cap" in op:
        cap = str(op["end_cap"]).upper()
        if cap not in END_CAPS:
            raise ValueError(f"unsupported end cap: {cap}")
        line.set("endCap", cap)
    if "alpha" in op:
        line.set("alpha", str(_alpha(op["alpha"])))
    return dict(sorted(line.attrib.items()))


def _set_fill(node, op: dict) -> dict:
    color = _color(op.get("color"), "fill color")
    fill = node.find(f"{HC}fillBrush")
    if fill is None:
        fill = etree.Element(f"{HC}fillBrush")
        line = node.find(f"{HP}lineShape")
        shadow = node.find(f"{HP}shadow")
        if shadow is not None:
            node.insert(node.index(shadow), fill)
        elif line is not None:
            node.insert(node.index(line) + 1, fill)
        else:
            node.append(fill)
    win = fill.find(f"{HC}winBrush")
    if win is None:
        win = etree.SubElement(fill, f"{HC}winBrush")
    win.set("faceColor", color)
    win.set("hatchColor", _color(op.get("hatch_color", "#FFFFFF"), "hatch_color"))
    if "alpha" in op:
        win.set("alpha", str(_alpha(op["alpha"])))
    return dict(sorted(win.attrib.items()))


def _clear_fill(node) -> dict:
    fill = node.find(f"{HC}fillBrush")
    if fill is not None:
        node.remove(fill)
    return {"cleared": True}


def _set_shadow(node, op: dict) -> dict:
    shadow = node.find(f"{HP}shadow")
    if shadow is None:
        raise ValueError("shape has no shadow element")
    kind = str(op.get("type", "NONE")).upper()
    if kind not in SHADOW_TYPES:
        raise ValueError(f"unsupported shadow type: {kind}")
    shadow.set("type", kind)
    if "color" in op:
        shadow.set("color", _color(op["color"], "shadow color"))
    if "offset_x" in op:
        shadow.set("offsetX", str(_bounded_int(op["offset_x"], "offset_x", -10_000_000, 10_000_000)))
    if "offset_y" in op:
        shadow.set("offsetY", str(_bounded_int(op["offset_y"], "offset_y", -10_000_000, 10_000_000)))
    if "alpha" in op:
        shadow.set("alpha", str(_alpha(op["alpha"])))
    return dict(sorted(shadow.attrib.items()))


def _set_arrowheads(node, op: dict) -> dict:
    line = node.find(f"{HP}lineShape")
    if line is None:
        raise ValueError("shape has no lineShape")
    for field, attr in (("head_style", "headStyle"), ("tail_style", "tailStyle")):
        if field in op:
            value = str(op[field]).upper()
            if value not in ARROW_STYLES:
                raise ValueError(f"unsupported arrow style: {value}")
            line.set(attr, value)
    for field, attr in (("head_size", "headSz"), ("tail_size", "tailSz")):
        if field in op:
            value = str(op[field]).upper()
            if value not in ARROW_SIZES:
                raise ValueError(f"unsupported arrow size: {value}")
            line.set(attr, value)
    if "head_fill" in op:
        line.set("headfill", "1" if bool(op["head_fill"]) else "0")
    if "tail_fill" in op:
        line.set("tailfill", "1" if bool(op["tail_fill"]) else "0")
    return dict(sorted(line.attrib.items()))


def _apply_one(path: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED:
        raise ValueError(DEFERRED[name])
    if name in {"insert_line", "insert_ellipse", "insert_polygon", "insert_arc"}:
        return _author_shape(path, op)

    target = _resolve_style_target(path, op.get("drawing"))
    if name == "set_shape_stroke":
        state = _mutate_style(path, target, lambda node: _set_stroke(node, op))
    elif name == "set_shape_fill":
        if target["kind"] == "line":
            raise ValueError("line fill is not admitted")
        state = _mutate_style(path, target, lambda node: _set_fill(node, op))
    elif name == "clear_shape_fill":
        state = _mutate_style(path, target, _clear_fill)
    elif name == "set_shape_shadow":
        state = _mutate_style(path, target, lambda node: _set_shadow(node, op))
    elif name == "set_shape_arrowheads":
        state = _mutate_style(path, target, lambda node: _set_arrowheads(node, op))
    else:
        raise ValueError(f"Unsupported P3.26 operation: {name}")
    return {"op": name, "drawing": target["locator"], "state": state}


def apply_drawing_style_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 64:
        raise ValueError("P3.26 transaction requires 1..64 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each P3.26 operation must be an object")

    before = build_drawing_style_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p326-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_drawing_style_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "before": {
            "drawing_count": before["drawing_count"],
            "drawing_style_sha256": before["drawing_style_sha256"],
            "shape_geometry_sha256": before["shape_geometry_sha256"],
        },
        "after": {
            "drawing_count": after["drawing_count"],
            "drawing_style_sha256": after["drawing_style_sha256"],
            "shape_geometry_sha256": after["shape_geometry_sha256"],
        },
        "drawing_style_changed": before["drawing_style_sha256"] != after["drawing_style_sha256"],
        "shape_geometry_changed": before["shape_geometry_sha256"] != after["shape_geometry_sha256"],
        "drawing_structure_changed": before["drawing_structure_sha256"] != after["drawing_structure_sha256"],
        "operation_count": len(operations),
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
