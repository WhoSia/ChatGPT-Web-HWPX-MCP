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
from hwpx.oxml import ContainerMember

from p28_tables import _save_document
from p29_objects import _resolve_paragraph
from p325_drawing_layer import (
    HP,
    DRAWING_TAGS,
    build_drawing_layer_map,
    _bounded_int,
    _find_node,
    _mutate_section,
)
from p326_drawing_style import _author_shape

SCHEMA = "chatgpt-web-hwpx-mcp/diagram-composition/p3.27/v1"
AUTHORITY = "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY"

DEFERRED = {
    "insert_smart_connector": (
        "EVIDENCE_GATE_CLOSED: native hp:connectLine subjectIDRef/control-point transforms "
        "are not reconstructible from the available upstream real-document evidence."
    ),
    "scale_existing_group": (
        "EVIDENCE_GATE_CLOSED: P3.27 admits rigid group translation only; group scaling "
        "requires a dedicated native-render geometry batch."
    ),
}

MEMBER_KINDS = {"rect", "ellipse", "polygon"}
ALIGN_MODES = {
    "LEFT", "CENTER", "RIGHT",
    "TOP", "MIDDLE", "BOTTOM",
}
DISTRIBUTE_MODES = {"HORIZONTAL", "VERTICAL"}

BLOCK_PRESETS = {
    "two_nodes": [
        {"kind": "rect", "x": 0, "y": 0, "width": 7200, "height": 3600, "fill_color": "#EEF4FF"},
        {"kind": "rect", "x": 10800, "y": 0, "width": 7200, "height": 3600, "fill_color": "#EEF4FF"},
    ],
    "three_stage": [
        {"kind": "rect", "x": 0, "y": 0, "width": 6000, "height": 3200, "fill_color": "#F4F4F4"},
        {"kind": "rect", "x": 8500, "y": 0, "width": 6000, "height": 3200, "fill_color": "#F4F4F4"},
        {"kind": "rect", "x": 17000, "y": 0, "width": 6000, "height": 3200, "fill_color": "#F4F4F4"},
    ],
    "decision_cluster": [
        {"kind": "ellipse", "x": 0, "y": 4000, "width": 5200, "height": 3600, "fill_color": "#FFF6DD"},
        {"kind": "polygon", "x": 8000, "y": 3000, "points": [[0, 1800], [3000, 0], [6000, 1800], [3000, 3600]], "fill_color": "#FFF2CC"},
        {"kind": "rect", "x": 17000, "y": 0, "width": 6000, "height": 3200, "fill_color": "#EAF7EA"},
        {"kind": "rect", "x": 17000, "y": 6500, "width": 6000, "height": 3200, "fill_color": "#FCEAEA"},
    ],
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def diagram_composition_contract() -> dict:
    return {
        "phase": "P3.27",
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "ancestry": {
            "P3.25": "unified drawing inventory and anchored layout mutation",
            "P3.26": "dedicated native shape authoring and styling",
            "python-hwpx": "ContainerMember + add_container real-corpus-backed group authoring",
            "P3.27": "static connectors, group-local composition, alignment/distribution and reusable diagram blocks",
        },
        "connector_semantics": (
            "STATIC_LINE_CONNECTOR_ONLY: endpoints are materialized geometry; no subjectIDRef binding "
            "or automatic rerouting after node movement."
        ),
        "group_semantics": (
            "NEW_GROUP_FROM_LOCAL_MEMBERS + RIGID_TRANSLATION + P3.34-R3 bounded existing group/ungroup "
            "candidate for exactly two unrotated shared-anchor rect/ellipse objects; implementation-generated "
            "Hancom round-trip remains required before production promotion."
        ),
        "admitted_operations": [
            "insert_group",
            "insert_static_connector",
            "translate_group",
            "align_objects",
            "distribute_objects",
            "insert_diagram_block",
            "group_existing_objects",
            "ungroup_existing_objects",
        ],
        "member_families": sorted(MEMBER_KINDS),
        "block_presets": sorted(BLOCK_PRESETS),
        "deferred_operations": dict(DEFERRED),
    }


def _top_level_objects(path: Path) -> list[dict]:
    mapped = build_drawing_layer_map(path)
    return [
        item for item in mapped["objects"]
        if str(item.get("group_level") or "0") != "1"
    ]


def _resolve_top(path: Path, locator: object) -> dict:
    value = str(locator or "")
    found = next((item for item in _top_level_objects(path) if item["locator"] == value), None)
    if found is None:
        raise ValueError(f"Unknown top-level drawing locator: {value}")
    return found


def _position_xy(item: dict) -> tuple[int, int]:
    pos = item.get("position")
    if not isinstance(pos, dict):
        raise ValueError(f"drawing {item['locator']} has no hp:pos")
    if item.get("placement") != "floating":
        raise ValueError(f"drawing {item['locator']} must be floating for diagram composition")
    return int(pos.get("horzOffset", "0") or 0), int(pos.get("vertOffset", "0") or 0)


def _size(item: dict) -> tuple[int, int]:
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"drawing {item['locator']} has no positive geometry")
    return width, height


def _ensure_same_anchor(items: list[dict]) -> str:
    anchors = {str(item.get("anchor_locator") or "") for item in items}
    if len(anchors) != 1 or "" in anchors:
        raise ValueError("diagram operation requires drawings with one shared paragraph anchor")
    return next(iter(anchors))


def _set_xy(path: Path, item: dict, x: int, y: int) -> dict:
    x = _bounded_int(x, "horizontal_offset", 0, 10_000_000)
    y = _bounded_int(y, "vertical_offset", 0, 10_000_000)
    def mutate(root):
        node = _find_node(root, item)
        pos = node.find(f"{HP}pos")
        if pos is None or str(pos.get("treatAsChar", "")).lower() not in {"0", "false"}:
            raise ValueError("diagram positioning requires a floating object")
        pos.set("horzOffset", str(x))
        pos.set("vertOffset", str(y))
        return dict(pos.attrib)
    state = _mutate_section(path, item["section"], mutate)
    return {"drawing": item["locator"], "x": x, "y": y, "position": state}


def _member_from_spec(spec: dict) -> ContainerMember:
    kind = str(spec.get("kind") or "").lower()
    if kind not in MEMBER_KINDS:
        raise ValueError(f"unsupported group member family: {kind}")
    x = _bounded_int(spec.get("x", 0), "member_x", -10_000_000, 10_000_000)
    y = _bounded_int(spec.get("y", 0), "member_y", -10_000_000, 10_000_000)
    line_color = str(spec.get("line_color", "#000000")).upper()
    line_width = str(_bounded_int(spec.get("line_width", 283), "line_width", 1, 100000))
    fill = spec.get("fill_color")
    fill_color = None if fill is None else str(fill).upper()
    if kind == "rect":
        return ContainerMember.rect(
            x, y,
            _bounded_int(spec.get("width", 7200), "member_width", 1, 10_000_000),
            _bounded_int(spec.get("height", 3600), "member_height", 1, 10_000_000),
            ratio=_bounded_int(spec.get("ratio", 0), "ratio", 0, 100),
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
        )
    if kind == "ellipse":
        return ContainerMember.ellipse(
            x, y,
            _bounded_int(spec.get("width", 7200), "member_width", 1, 10_000_000),
            _bounded_int(spec.get("height", 3600), "member_height", 1, 10_000_000),
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
        )
    points = spec.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("polygon group member requires at least 3 coordinate pairs")
    parsed = []
    for pair in points:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("polygon member points must be [x,y] pairs")
        parsed.append((
            _bounded_int(pair[0], "point_x", -10_000_000, 10_000_000),
            _bounded_int(pair[1], "point_y", -10_000_000, 10_000_000),
        ))
    return ContainerMember.polygon(
        x, y, parsed,
        line_color=line_color,
        line_width=line_width,
        fill_color=fill_color,
    )


def _insert_group(path: Path, op: dict) -> dict:
    specs = op.get("members")
    if not isinstance(specs, list) or not specs or len(specs) > 32:
        raise ValueError("insert_group requires 1..32 member specs")
    before = {item["locator"] for item in _top_level_objects(path)}
    doc = HwpxDocument.open(str(path))
    try:
        paragraph, anchor = _resolve_paragraph(doc, path, op.get("anchor"))
        members = [_member_from_spec(spec) for spec in specs]
        paragraph.add_container(
            members,
            treat_as_char=bool(op.get("treat_as_char", False)),
        )
        _save_document(doc, path, path)
    finally:
        doc.close()
    created = [
        item for item in _top_level_objects(path)
        if item["locator"] not in before and item["kind"] == "container"
    ]
    if len(created) != 1:
        raise ValueError("insert_group did not yield one uniquely identifiable container")
    group = created[0]
    if not bool(op.get("treat_as_char", False)):
        x = _bounded_int(op.get("horizontal_offset", 0), "horizontal_offset", 0, 10_000_000)
        y = _bounded_int(op.get("vertical_offset", 0), "vertical_offset", 0, 10_000_000)
        _set_xy(path, group, x, y)
        group = _resolve_top(path, group["locator"])
    return {
        "op": "insert_group",
        "created_group": group["locator"],
        "anchor": anchor["locator"],
        "member_count": len(specs),
    }


def _group_member_map(root, container) -> list[dict]:
    result = []
    for child in container:
        kind = child.tag.rsplit("}", 1)[-1]
        if kind not in DRAWING_TAGS or str(child.get("groupLevel") or "0") != "1":
            continue
        offset = child.find(f"{HP}offset")
        org = child.find(f"{HP}orgSz")
        result.append({
            "kind": kind,
            "id": child.get("id"),
            "instid": child.get("instid"),
            "offset": None if offset is None else dict(sorted(offset.attrib.items())),
            "org_size": None if org is None else dict(sorted(org.attrib.items())),
            "group_level": child.get("groupLevel"),
        })
    return result


def build_diagram_composition_map(path: Path) -> dict:
    base = build_drawing_layer_map(path)
    top = [
        item for item in base["objects"]
        if str(item.get("group_level") or "0") != "1"
    ]
    top_ids = {
        (item["section"], item["kind"], item.get("instid") or item.get("id")): item
        for item in top
    }
    groups = []
    with zipfile.ZipFile(path, "r") as archive:
        sections = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for section in sections:
            root = etree.fromstring(archive.read(section))
            for container in root.iter(f"{HP}container"):
                if str(container.get("groupLevel") or "0") == "1":
                    continue
                base_item = top_ids.get((section, "container", container.get("instid") or container.get("id")))
                if base_item is None:
                    continue
                groups.append({
                    "locator": base_item["locator"],
                    "anchor_locator": base_item.get("anchor_locator"),
                    "position": base_item.get("position"),
                    "width": base_item.get("width"),
                    "height": base_item.get("height"),
                    "members": _group_member_map(root, container),
                })
    placement_seed = [
        {
            "locator": item["locator"],
            "anchor": item.get("anchor_locator"),
            "kind": item["kind"],
            "width": item.get("width"),
            "height": item.get("height"),
            "position": item.get("position"),
        }
        for item in top
    ]
    group_seed = [
        {
            "locator": group["locator"],
            "position": group["position"],
            "width": group["width"],
            "height": group["height"],
            "members": group["members"],
        }
        for group in groups
    ]
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "top_level_count": len(top),
        "top_level_objects": top,
        "group_count": len(groups),
        "groups": groups,
        "diagram_placement_sha256": _sha(placement_seed),
        "group_topology_sha256": _sha(group_seed),
        "contract": diagram_composition_contract(),
    }


def _insert_static_connector(path: Path, op: dict) -> dict:
    source = _resolve_top(path, op.get("source"))
    target = _resolve_top(path, op.get("target"))
    anchor = _ensure_same_anchor([source, target])
    sx, sy = _position_xy(source)
    tx, ty = _position_xy(target)
    sw, sh = _size(source)
    tw, th = _size(target)
    start = (sx + sw // 2, sy + sh // 2)
    end = (tx + tw // 2, ty + th // 2)
    min_x = min(start[0], end[0])
    min_y = min(start[1], end[1])
    receipt = _author_shape(path, {
        "op": "insert_line",
        "anchor": anchor,
        "start_x": start[0] - min_x,
        "start_y": start[1] - min_y,
        "end_x": end[0] - min_x,
        "end_y": end[1] - min_y,
        "line_color": op.get("line_color", "#000000"),
        "line_width": op.get("line_width", 283),
        "treat_as_char": False,
    })
    line = _resolve_top(path, receipt["created_drawing"])
    _set_xy(path, line, min_x, min_y)
    return {
        "op": "insert_static_connector",
        "created_connector": line["locator"],
        "source": source["locator"],
        "target": target["locator"],
        "binding": "STATIC_GEOMETRY_ONLY",
        "reroutes_after_node_move": False,
    }


def _align(path: Path, op: dict) -> dict:
    locators = op.get("drawings")
    if not isinstance(locators, list) or len(locators) < 2 or len(locators) > 32:
        raise ValueError("align_objects requires 2..32 drawing locators")
    items = [_resolve_top(path, locator) for locator in locators]
    _ensure_same_anchor(items)
    mode = str(op.get("mode") or "").upper()
    if mode not in ALIGN_MODES:
        raise ValueError(f"unsupported alignment mode: {mode}")
    boxes = []
    for item in items:
        x, y = _position_xy(item)
        w, h = _size(item)
        boxes.append((item, x, y, w, h))
    left = min(x for _, x, _, _, _ in boxes)
    right = max(x + w for _, x, _, w, _ in boxes)
    top = min(y for _, _, y, _, _ in boxes)
    bottom = max(y + h for _, _, y, _, h in boxes)
    receipts = []
    for item, x, y, w, h in boxes:
        nx, ny = x, y
        if mode == "LEFT":
            nx = left
        elif mode == "CENTER":
            nx = (left + right - w) // 2
        elif mode == "RIGHT":
            nx = right - w
        elif mode == "TOP":
            ny = top
        elif mode == "MIDDLE":
            ny = (top + bottom - h) // 2
        elif mode == "BOTTOM":
            ny = bottom - h
        receipts.append(_set_xy(path, item, nx, ny))
    return {"op": "align_objects", "mode": mode, "receipts": receipts}


def _distribute(path: Path, op: dict) -> dict:
    locators = op.get("drawings")
    if not isinstance(locators, list) or len(locators) < 3 or len(locators) > 32:
        raise ValueError("distribute_objects requires 3..32 drawing locators")
    items = [_resolve_top(path, locator) for locator in locators]
    _ensure_same_anchor(items)
    mode = str(op.get("mode") or "").upper()
    if mode not in DISTRIBUTE_MODES:
        raise ValueError(f"unsupported distribution mode: {mode}")
    boxes = []
    for item in items:
        x, y = _position_xy(item)
        w, h = _size(item)
        boxes.append((item, x, y, w, h))
    if mode == "HORIZONTAL":
        boxes.sort(key=lambda row: row[1] + row[3] / 2)
        centers = [x + w / 2 for _, x, _, w, _ in boxes]
        first, last = centers[0], centers[-1]
        step = (last - first) / (len(boxes) - 1)
        receipts = []
        for index, (item, x, y, w, h) in enumerate(boxes):
            center = first + step * index
            receipts.append(_set_xy(path, item, round(center - w / 2), y))
    else:
        boxes.sort(key=lambda row: row[2] + row[4] / 2)
        centers = [y + h / 2 for _, _, y, _, h in boxes]
        first, last = centers[0], centers[-1]
        step = (last - first) / (len(boxes) - 1)
        receipts = []
        for index, (item, x, y, w, h) in enumerate(boxes):
            center = first + step * index
            receipts.append(_set_xy(path, item, x, round(center - h / 2)))
    return {"op": "distribute_objects", "mode": mode, "receipts": receipts}


def _translate_group(path: Path, op: dict) -> dict:
    group = _resolve_top(path, op.get("group"))
    if group["kind"] != "container":
        raise ValueError("translate_group requires a top-level container")
    x, y = _position_xy(group)
    dx = _bounded_int(op.get("dx", 0), "dx", -10_000_000, 10_000_000)
    dy = _bounded_int(op.get("dy", 0), "dy", -10_000_000, 10_000_000)
    nx, ny = x + dx, y + dy
    if nx < 0 or ny < 0:
        raise ValueError("group translation would create a negative floating offset")
    return {"op": "translate_group", **_set_xy(path, group, nx, ny)}


def _insert_block(path: Path, op: dict) -> dict:
    preset = str(op.get("preset") or "").lower()
    if preset not in BLOCK_PRESETS:
        raise ValueError(f"unknown diagram block preset: {preset}")
    receipt = _insert_group(path, {
        "op": "insert_group",
        "anchor": op.get("anchor"),
        "members": BLOCK_PRESETS[preset],
        "treat_as_char": bool(op.get("treat_as_char", False)),
        "horizontal_offset": op.get("horizontal_offset", 0),
        "vertical_offset": op.get("vertical_offset", 0),
    })
    return {"op": "insert_diagram_block", "preset": preset, **receipt}


def _apply_one(path: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED:
        raise ValueError(DEFERRED[name])
    if name == "insert_group":
        return _insert_group(path, op)
    if name == "group_existing_objects":
        from p334r3_existing_group import group_existing_objects
        return group_existing_objects(path, op.get("drawings"))
    if name == "ungroup_existing_objects":
        from p334r3_existing_group import ungroup_existing_objects
        return ungroup_existing_objects(path, op.get("group"))
    if name == "insert_static_connector":
        return _insert_static_connector(path, op)
    if name == "translate_group":
        return _translate_group(path, op)
    if name == "align_objects":
        return _align(path, op)
    if name == "distribute_objects":
        return _distribute(path, op)
    if name == "insert_diagram_block":
        return _insert_block(path, op)
    raise ValueError(f"Unsupported P3.27 operation: {name}")


def apply_diagram_composition_atomic(
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
        raise ValueError("P3.27 transaction requires 1..64 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each P3.27 operation must be an object")

    before = build_diagram_composition_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p327-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_diagram_composition_map(candidate)
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
            "top_level_count": before["top_level_count"],
            "group_count": before["group_count"],
            "diagram_placement_sha256": before["diagram_placement_sha256"],
            "group_topology_sha256": before["group_topology_sha256"],
        },
        "after": {
            "top_level_count": after["top_level_count"],
            "group_count": after["group_count"],
            "diagram_placement_sha256": after["diagram_placement_sha256"],
            "group_topology_sha256": after["group_topology_sha256"],
        },
        "diagram_placement_changed": before["diagram_placement_sha256"] != after["diagram_placement_sha256"],
        "group_topology_changed": before["group_topology_sha256"] != after["group_topology_sha256"],
        "operation_count": len(operations),
        "receipts": receipts,
        "validation": validation,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
