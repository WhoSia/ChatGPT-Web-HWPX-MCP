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

from p28_tables import _save_document
from p29_objects import _resolve_paragraph
from p325_drawing_layer import HP, build_drawing_layer_map, _bounded_int
from p326_drawing_style import _color
from p327_diagram_composition import (
    _position_xy,
    _resolve_top,
    _set_xy,
    _size,
    _ensure_same_anchor,
    build_diagram_composition_map,
)

SCHEMA = "chatgpt-web-hwpx-mcp/high-level-diagram/p3.28/v1"
AUTHORITY = "STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY"

LABELABLE_KINDS = {"rect", "ellipse", "polygon"}
NODE_KINDS = {"process", "terminator", "decision", "data", "node"}
LAYOUTS = {"LEFT_TO_RIGHT", "TOP_DOWN"}
MAX_NODES = 32
MAX_EDGES = 64

DEFERRED = {
    "native_callout_shape": (
        "EVIDENCE_GATE_CLOSED: P3.28 callouts are labeled native shapes plus static pointer lines; "
        "no unmeasured Hancom callout/autoshape family is claimed."
    ),
    "smart_connector_routing": (
        "EVIDENCE_GATE_CLOSED: declarative plan edges compile to static line connectors and do not "
        "carry subjectIDRef binding or automatic rerouting."
    ),
    "rich_shape_text_runs": (
        "EVIDENCE_GATE_CLOSED: P3.28 owns plain shape-label text and margins; arbitrary mixed-run "
        "rich text inside hp:drawText remains outside this phase."
    ),
    "auto_page_avoidance": (
        "EVIDENCE_GATE_CLOSED: plan layout is deterministic HWPUNIT placement, not renderer-aware "
        "collision/page-break optimization."
    ),
}

NODE_DEFAULTS = {
    "process": {"kind": "rect", "width": 7200, "height": 3600, "fill_color": "#EEF4FF", "ratio": 0},
    "terminator": {"kind": "ellipse", "width": 7200, "height": 3600, "fill_color": "#EAF7EA"},
    "decision": {
        "kind": "polygon",
        "width": 7200,
        "height": 4200,
        "fill_color": "#FFF2CC",
        "points": [[0, 2100], [3600, 0], [7200, 2100], [3600, 4200]],
    },
    "data": {
        "kind": "polygon",
        "width": 7200,
        "height": 3600,
        "fill_color": "#F3EDFF",
        "points": [[1000, 0], [7200, 0], [6200, 3600], [0, 3600]],
    },
    "node": {"kind": "rect", "width": 7200, "height": 3600, "fill_color": "#F4F4F4", "ratio": 8},
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def high_level_diagram_contract() -> dict:
    return {
        "phase": "P3.28",
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "ancestry": {
            "P3.25": "drawing inventory + native hp:drawText read-back",
            "P3.26": "native shape authoring and styling",
            "P3.27": "static connectors + bounded composition",
            "python-hwpx": "real-corpus-backed HwpxOxmlShape.set_draw_text",
            "P3.28": "labeled nodes, callout composition, declarative plans and diagram macros",
        },
        "shape_text_semantics": (
            "NATIVE_HP_DRAWTEXT: one plain-text label with bounded textMargin and optional editable flag."
        ),
        "callout_semantics": (
            "COMPOSITE_CALLOUT: one labeled native node + one static pointer line; not a smart/native autoshape claim."
        ),
        "plan_semantics": (
            "DETERMINISTIC_LAYOUT_COMPILER: node ids resolve to newly authored floating shapes; edges compile "
            "after node materialization to static line geometry."
        ),
        "admitted_operations": [
            "set_shape_text",
            "remove_shape_text",
            "insert_labeled_node",
            "insert_callout",
            "insert_diagram_plan",
            "insert_flowchart",
            "insert_org_chart",
        ],
        "node_kinds": sorted(NODE_KINDS),
        "layouts": sorted(LAYOUTS),
        "limits": {"nodes": MAX_NODES, "edges": MAX_EDGES},
        "deferred_operations": dict(DEFERRED),
    }


def _draw_text_payload(node) -> dict | None:
    draw = node.find(f"{HP}drawText")
    if draw is None:
        return None
    margin = draw.find(f"{HP}textMargin")
    paragraphs = []
    for para in draw.iter(f"{HP}p"):
        paragraphs.append("".join((t.text or "") for t in para.iter(f"{HP}t")))
    return {
        "name": draw.get("name", ""),
        "editable": str(draw.get("editable", "0")).lower() in {"1", "true"},
        "last_width": draw.get("lastWidth"),
        "text_margin": None if margin is None else {
            side: int(margin.get(side, "0") or 0)
            for side in ("left", "right", "top", "bottom")
        },
        "paragraphs": paragraphs,
        "text": "\n".join(paragraphs),
    }


def build_high_level_diagram_map(path: Path) -> dict:
    composition = build_diagram_composition_map(path)
    base = build_drawing_layer_map(path)
    by_identity = {
        (item["section"], item["kind"], item.get("instid") or item.get("id")): item
        for item in base["objects"]
    }
    labeled = []
    with zipfile.ZipFile(path, "r") as archive:
        sections = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for section in sections:
            root = etree.fromstring(archive.read(section))
            for node in root.iter():
                kind = node.tag.rsplit("}", 1)[-1]
                if kind not in LABELABLE_KINDS:
                    continue
                identity = node.get("instid") or node.get("id")
                item = by_identity.get((section, kind, identity))
                if item is None or str(item.get("group_level") or "0") == "1":
                    continue
                draw = _draw_text_payload(node)
                if draw is None:
                    continue
                labeled.append({
                    "locator": item["locator"],
                    "kind": kind,
                    "anchor_locator": item.get("anchor_locator"),
                    "position": item.get("position"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "draw_text": draw,
                })
    label_seed = [
        {
            "locator": item["locator"],
            "kind": item["kind"],
            "text": item["draw_text"]["text"],
            "margin": item["draw_text"]["text_margin"],
            "editable": item["draw_text"]["editable"],
        }
        for item in labeled
    ]
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "labeled_node_count": len(labeled),
        "labeled_nodes": labeled,
        "shape_text_sha256": _sha(label_seed),
        "diagram_placement_sha256": composition["diagram_placement_sha256"],
        "group_topology_sha256": composition["group_topology_sha256"],
        "contract": high_level_diagram_contract(),
    }


def _find_shape_wrapper(paragraph, target: dict):
    identity = target.get("instid") or target.get("id")
    matches = [
        shape for shape in paragraph.shapes
        if shape.shape_type == target["kind"]
        and (shape.inst_id == identity if identity else True)
    ]
    if len(matches) != 1:
        raise ValueError("shape locator could not be rebound to one paragraph shape wrapper")
    return matches[0]


def _shape_text_margin(op: dict) -> dict[str, int]:
    margin = op.get("text_margin", 283)
    if isinstance(margin, dict):
        return {
            side: _bounded_int(margin.get(side, 283), f"text_margin_{side}", 0, 100000)
            for side in ("left", "right", "top", "bottom")
        }
    value = _bounded_int(margin, "text_margin", 0, 100000)
    return {side: value for side in ("left", "right", "top", "bottom")}


def _set_existing_shape_text(path: Path, op: dict, *, remove: bool = False) -> dict:
    target = _resolve_top(path, op.get("drawing"))
    if target["kind"] not in LABELABLE_KINDS:
        raise ValueError(f"shape text is admitted only for {sorted(LABELABLE_KINDS)}")
    if not target.get("anchor_locator"):
        raise ValueError("shape text mutation requires a stable paragraph anchor")
    doc = HwpxDocument.open(str(path))
    try:
        paragraph, _anchor = _resolve_paragraph(doc, path, target["anchor_locator"])
        shape = _find_shape_wrapper(paragraph, target)
        if remove:
            changed = shape.remove_draw_text()
            state = {"removed": bool(changed)}
        else:
            text = str(op.get("text", ""))
            if len(text) > 4000:
                raise ValueError("shape text exceeds the P3.28 4000-character bound")
            draw = shape.set_draw_text(
                text,
                name=str(op.get("name", ""))[:200],
                editable=bool(op.get("editable", False)),
                margin=_shape_text_margin(op),
                char_pr_id_ref=op.get("char_pr_id_ref"),
            )
            state = {
                "text": draw.text,
                "editable": draw.editable,
                "text_margin": draw.text_margin,
                "name": draw.name,
            }
        _save_document(doc, path, path)
    finally:
        doc.close()
    return {
        "op": "remove_shape_text" if remove else "set_shape_text",
        "drawing": target["locator"],
        "state": state,
    }


def _node_spec(op: dict) -> dict:
    node_type = str(op.get("node_type", "process")).lower()
    if node_type not in NODE_DEFAULTS:
        raise ValueError(f"unsupported node_type: {node_type}")
    spec = dict(NODE_DEFAULTS[node_type])
    for key in ("width", "height", "fill_color", "line_color", "line_width", "ratio", "points"):
        if key in op:
            spec[key] = op[key]
    return spec


def _insert_labeled_node(path: Path, op: dict) -> dict:
    anchor = str(op.get("anchor") or "")
    if not anchor:
        raise ValueError("insert_labeled_node requires anchor")
    label = str(op.get("text", ""))
    if len(label) > 4000:
        raise ValueError("node label exceeds the P3.28 4000-character bound")
    spec = _node_spec(op)
    kind = spec["kind"]
    width = _bounded_int(spec.get("width", 7200), "width", 1, 10_000_000)
    height = _bounded_int(spec.get("height", 3600), "height", 1, 10_000_000)
    before = {item["locator"] for item in build_drawing_layer_map(path)["objects"]}

    doc = HwpxDocument.open(str(path))
    try:
        paragraph, resolved_anchor = _resolve_paragraph(doc, path, anchor)
        common = {
            "line_color": _color(spec.get("line_color", "#000000"), "line_color"),
            "line_width": str(_bounded_int(spec.get("line_width", 283), "line_width", 1, 100000)),
            "fill_color": _color(spec.get("fill_color", "#F4F4F4"), "fill_color"),
            "treat_as_char": False,
        }
        if kind == "rect":
            shape = paragraph.add_rectangle(
                width,
                height,
                ratio=_bounded_int(spec.get("ratio", 0), "ratio", 0, 100),
                **common,
            )
        elif kind == "ellipse":
            shape = paragraph.add_ellipse(width, height, **common)
        elif kind == "polygon":
            points = spec.get("points")
            if not isinstance(points, list) or len(points) < 3:
                raise ValueError("polygon labeled node requires at least three points")
            parsed = [
                (
                    _bounded_int(pair[0], "point_x", -10_000_000, 10_000_000),
                    _bounded_int(pair[1], "point_y", -10_000_000, 10_000_000),
                )
                for pair in points
                if isinstance(pair, (list, tuple)) and len(pair) == 2
            ]
            if len(parsed) != len(points):
                raise ValueError("every polygon point must be [x,y]")
            shape = paragraph.add_polygon(parsed, **common)
        else:
            raise ValueError(f"unsupported labeled-node native family: {kind}")

        shape.set_draw_text(
            label,
            name=str(op.get("name", ""))[:200],
            editable=bool(op.get("editable", False)),
            margin=_shape_text_margin(op),
            char_pr_id_ref=op.get("char_pr_id_ref"),
        )
        shape.set_position(
            horizontal_offset=_bounded_int(op.get("horizontal_offset", 0), "horizontal_offset", 0, 10_000_000),
            vertical_offset=_bounded_int(op.get("vertical_offset", 0), "vertical_offset", 0, 10_000_000),
        )
        _save_document(doc, path, path)
    finally:
        doc.close()

    after = build_drawing_layer_map(path)
    created = [
        item for item in after["objects"]
        if item["locator"] not in before
        and item["kind"] == kind
        and str(item.get("group_level") or "0") != "1"
    ]
    if len(created) != 1:
        raise ValueError("labeled-node authoring did not yield one unique top-level shape")
    item = created[0]
    return {
        "op": "insert_labeled_node",
        "node_type": str(op.get("node_type", "process")).lower(),
        "created_node": item["locator"],
        "anchor": resolved_anchor["locator"],
        "label": label,
        "kind": kind,
    }


def _insert_pointer_line(
    path: Path,
    *,
    anchor: str,
    start: tuple[int, int],
    end: tuple[int, int],
    line_color: str,
    line_width: int,
) -> str:
    min_x = min(start[0], end[0])
    min_y = min(start[1], end[1])
    before = {item["locator"] for item in build_drawing_layer_map(path)["objects"]}
    doc = HwpxDocument.open(str(path))
    try:
        paragraph, _ = _resolve_paragraph(doc, path, anchor)
        shape = paragraph.add_line(
            start[0] - min_x,
            start[1] - min_y,
            end[0] - min_x,
            end[1] - min_y,
            line_color=_color(line_color, "line_color"),
            line_width=str(_bounded_int(line_width, "line_width", 1, 100000)),
            treat_as_char=False,
        )
        shape.set_position(horizontal_offset=min_x, vertical_offset=min_y)
        _save_document(doc, path, path)
    finally:
        doc.close()
    after = build_drawing_layer_map(path)
    created = [
        item for item in after["objects"]
        if item["locator"] not in before and item["kind"] == "line"
    ]
    if len(created) != 1:
        raise ValueError("pointer authoring did not yield one unique line")
    return created[0]["locator"]


def _insert_callout(path: Path, op: dict) -> dict:
    x = _bounded_int(op.get("horizontal_offset", 0), "horizontal_offset", 0, 10_000_000)
    y = _bounded_int(op.get("vertical_offset", 0), "vertical_offset", 0, 10_000_000)
    node_receipt = _insert_labeled_node(path, {
        **op,
        "op": "insert_labeled_node",
        "node_type": op.get("node_type", "process"),
        "horizontal_offset": x,
        "vertical_offset": y,
    })
    node = _resolve_top(path, node_receipt["created_node"])
    _ensure_same_anchor([node])
    w, h = _size(node)
    target_x = _bounded_int(op.get("target_x", x + w + 4000), "target_x", 0, 10_000_000)
    target_y = _bounded_int(op.get("target_y", y + h // 2), "target_y", 0, 10_000_000)
    start = (x + w // 2, y + h // 2)
    pointer = _insert_pointer_line(
        path,
        anchor=str(node["anchor_locator"]),
        start=start,
        end=(target_x, target_y),
        line_color=str(op.get("pointer_color", "#555555")),
        line_width=int(op.get("pointer_width", 283)),
    )
    return {
        "op": "insert_callout",
        "created_node": node_receipt["created_node"],
        "created_pointer": pointer,
        "binding": "STATIC_POINTER_GEOMETRY_ONLY",
        "target": {"x": target_x, "y": target_y},
    }


def _normalize_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("diagram plan must be an object")
    layout = str(plan.get("layout", "LEFT_TO_RIGHT")).upper()
    if layout not in LAYOUTS:
        raise ValueError(f"unsupported plan layout: {layout}")
    nodes = plan.get("nodes")
    edges = plan.get("edges", [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError(f"diagram plan requires 1..{MAX_NODES} nodes")
    if not isinstance(edges, list) or len(edges) > MAX_EDGES:
        raise ValueError(f"diagram plan allows at most {MAX_EDGES} edges")

    ids = []
    clean_nodes = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError("every plan node must be an object")
        node_id = str(node.get("id") or "")
        if not node_id or len(node_id) > 120:
            raise ValueError("every plan node requires a bounded non-empty id")
        if node_id in ids:
            raise ValueError(f"duplicate plan node id: {node_id}")
        ids.append(node_id)
        node_type = str(node.get("type", "process")).lower()
        if node_type not in NODE_KINDS:
            raise ValueError(f"unsupported plan node type: {node_type}")
        clean_nodes.append({
            **node,
            "id": node_id,
            "type": node_type,
            "label": str(node.get("label", node_id)),
            "_index": index,
        })

    id_set = set(ids)
    clean_edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("every plan edge must be an object")
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source not in id_set or target not in id_set:
            raise ValueError(f"edge references unknown node: {source}->{target}")
        if source == target:
            raise ValueError("self-loop edges are not admitted in P3.28")
        clean_edges.append({**edge, "from": source, "to": target})

    origin_x = _bounded_int(plan.get("origin_x", 1000), "origin_x", 0, 10_000_000)
    origin_y = _bounded_int(plan.get("origin_y", 1000), "origin_y", 0, 10_000_000)
    gap_x = _bounded_int(plan.get("gap_x", 10000), "gap_x", 1000, 1_000_000)
    gap_y = _bounded_int(plan.get("gap_y", 6500), "gap_y", 1000, 1_000_000)
    return {
        **plan,
        "layout": layout,
        "nodes": clean_nodes,
        "edges": clean_edges,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "gap_x": gap_x,
        "gap_y": gap_y,
    }


def validate_diagram_plan(plan: dict) -> dict:
    normalized = _normalize_plan(plan)
    return {
        "ok": True,
        "schema": SCHEMA,
        "layout": normalized["layout"],
        "node_count": len(normalized["nodes"]),
        "edge_count": len(normalized["edges"]),
        "node_ids": [node["id"] for node in normalized["nodes"]],
        "plan_sha256": _sha({
            "layout": normalized["layout"],
            "nodes": [
                {"id": n["id"], "type": n["type"], "label": n["label"]}
                for n in normalized["nodes"]
            ],
            "edges": [
                {"from": e["from"], "to": e["to"]}
                for e in normalized["edges"]
            ],
        }),
        "connector_semantics": "STATIC_GEOMETRY_ONLY",
    }


def _auto_positions(plan: dict) -> dict[str, tuple[int, int]]:
    layout = plan["layout"]
    positions = {}
    explicit = {
        node["id"]: (
            int(node["x"]),
            int(node["y"]),
        )
        for node in plan["nodes"]
        if "x" in node and "y" in node
    }
    for node in plan["nodes"]:
        if node["id"] in explicit:
            x, y = explicit[node["id"]]
            positions[node["id"]] = (
                _bounded_int(x, "node_x", 0, 10_000_000),
                _bounded_int(y, "node_y", 0, 10_000_000),
            )

    auto = [node for node in plan["nodes"] if node["id"] not in positions]
    for order, node in enumerate(auto):
        if layout == "LEFT_TO_RIGHT":
            x = plan["origin_x"] + order * plan["gap_x"]
            y = plan["origin_y"]
        else:
            x = plan["origin_x"]
            y = plan["origin_y"] + order * plan["gap_y"]
        positions[node["id"]] = (x, y)
    return positions


def _insert_diagram_plan(path: Path, op: dict) -> dict:
    anchor = str(op.get("anchor") or "")
    if not anchor:
        raise ValueError("insert_diagram_plan requires anchor")
    plan = _normalize_plan(op.get("plan"))
    positions = _auto_positions(plan)
    node_locators: dict[str, str] = {}
    node_receipts = []

    for node in plan["nodes"]:
        x, y = positions[node["id"]]
        receipt = _insert_labeled_node(path, {
            "op": "insert_labeled_node",
            "anchor": anchor,
            "node_type": node["type"],
            "text": node["label"],
            "horizontal_offset": x,
            "vertical_offset": y,
            "width": node.get("width", NODE_DEFAULTS[node["type"]].get("width", 7200)),
            "height": node.get("height", NODE_DEFAULTS[node["type"]].get("height", 3600)),
            "fill_color": node.get("fill_color", NODE_DEFAULTS[node["type"]].get("fill_color", "#F4F4F4")),
            "line_color": node.get("line_color", "#000000"),
            "line_width": node.get("line_width", 283),
            "text_margin": node.get("text_margin", 283),
            "editable": node.get("editable", False),
        })
        node_locators[node["id"]] = receipt["created_node"]
        node_receipts.append({"id": node["id"], **receipt})

    edge_receipts = []
    for edge in plan["edges"]:
        source = _resolve_top(path, node_locators[edge["from"]])
        target = _resolve_top(path, node_locators[edge["to"]])
        sx, sy = _position_xy(source)
        tx, ty = _position_xy(target)
        sw, sh = _size(source)
        tw, th = _size(target)
        created = _insert_pointer_line(
            path,
            anchor=anchor,
            start=(sx + sw // 2, sy + sh // 2),
            end=(tx + tw // 2, ty + th // 2),
            line_color=str(edge.get("line_color", "#444444")),
            line_width=int(edge.get("line_width", 283)),
        )
        edge_receipts.append({
            "from": edge["from"],
            "to": edge["to"],
            "created_connector": created,
            "binding": "STATIC_GEOMETRY_ONLY",
        })

    return {
        "op": "insert_diagram_plan",
        "layout": plan["layout"],
        "node_count": len(node_receipts),
        "edge_count": len(edge_receipts),
        "nodes": node_receipts,
        "edges": edge_receipts,
        "plan_receipt": validate_diagram_plan(plan),
    }


def _flowchart_plan(op: dict) -> dict:
    steps = op.get("steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= MAX_NODES:
        raise ValueError("insert_flowchart requires 2..32 steps")
    nodes = []
    for index, step in enumerate(steps):
        if isinstance(step, str):
            node_id = f"step-{index+1}"
            label = step
            node_type = "terminator" if index in {0, len(steps)-1} else "process"
        elif isinstance(step, dict):
            node_id = str(step.get("id") or f"step-{index+1}")
            label = str(step.get("label", node_id))
            node_type = str(step.get("type", "process")).lower()
        else:
            raise ValueError("flowchart steps must be strings or objects")
        nodes.append({"id": node_id, "label": label, "type": node_type})
    edges = [{"from": nodes[i]["id"], "to": nodes[i+1]["id"]} for i in range(len(nodes)-1)]
    extra = op.get("edges")
    if extra is not None:
        if not isinstance(extra, list):
            raise ValueError("flowchart edges override must be a list")
        edges = extra
    return {
        "layout": str(op.get("layout", "TOP_DOWN")).upper(),
        "nodes": nodes,
        "edges": edges,
        "origin_x": op.get("origin_x", 1000),
        "origin_y": op.get("origin_y", 1000),
        "gap_x": op.get("gap_x", 10000),
        "gap_y": op.get("gap_y", 6500),
    }


def _insert_flowchart(path: Path, op: dict) -> dict:
    receipt = _insert_diagram_plan(path, {
        "op": "insert_diagram_plan",
        "anchor": op.get("anchor"),
        "plan": _flowchart_plan(op),
    })
    return {"op": "insert_flowchart", **receipt}


def _flatten_org(node: dict, *, parent: str | None, depth: int, order: list[int], out_nodes: list, out_edges: list):
    if not isinstance(node, dict):
        raise ValueError("org-chart nodes must be objects")
    node_id = str(node.get("id") or "")
    if not node_id:
        raise ValueError("every org-chart node requires id")
    label = str(node.get("label", node_id))
    rank = order[0]
    order[0] += 1
    out_nodes.append({
        "id": node_id,
        "label": label,
        "type": str(node.get("type", "node")).lower(),
        "_depth": depth,
        "_rank": rank,
    })
    if parent is not None:
        out_edges.append({"from": parent, "to": node_id})
    children = node.get("children", [])
    if not isinstance(children, list):
        raise ValueError("org-chart children must be a list")
    for child in children:
        _flatten_org(child, parent=node_id, depth=depth+1, order=order, out_nodes=out_nodes, out_edges=out_edges)


def _org_chart_plan(op: dict) -> dict:
    root = op.get("root")
    nodes: list[dict] = []
    edges: list[dict] = []
    _flatten_org(root, parent=None, depth=0, order=[0], out_nodes=nodes, out_edges=edges)
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ValueError("org chart exceeds P3.28 size bounds")

    origin_x = _bounded_int(op.get("origin_x", 1000), "origin_x", 0, 10_000_000)
    origin_y = _bounded_int(op.get("origin_y", 1000), "origin_y", 0, 10_000_000)
    gap_x = _bounded_int(op.get("gap_x", 9000), "gap_x", 1000, 1_000_000)
    gap_y = _bounded_int(op.get("gap_y", 6500), "gap_y", 1000, 1_000_000)

    levels: dict[int, list[dict]] = {}
    for node in nodes:
        levels.setdefault(int(node["_depth"]), []).append(node)
    positioned = []
    for depth in sorted(levels):
        level = levels[depth]
        total = len(level)
        for index, node in enumerate(level):
            positioned.append({
                "id": node["id"],
                "label": node["label"],
                "type": node["type"],
                "x": origin_x + index * gap_x,
                "y": origin_y + depth * gap_y,
            })
    return {"layout": "TOP_DOWN", "nodes": positioned, "edges": edges}


def _insert_org_chart(path: Path, op: dict) -> dict:
    receipt = _insert_diagram_plan(path, {
        "op": "insert_diagram_plan",
        "anchor": op.get("anchor"),
        "plan": _org_chart_plan(op),
    })
    return {"op": "insert_org_chart", **receipt}


def _apply_one(path: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED:
        raise ValueError(DEFERRED[name])
    if name == "set_shape_text":
        return _set_existing_shape_text(path, op, remove=False)
    if name == "remove_shape_text":
        return _set_existing_shape_text(path, op, remove=True)
    if name == "insert_labeled_node":
        return _insert_labeled_node(path, op)
    if name == "insert_callout":
        return _insert_callout(path, op)
    if name == "insert_diagram_plan":
        return _insert_diagram_plan(path, op)
    if name == "insert_flowchart":
        return _insert_flowchart(path, op)
    if name == "insert_org_chart":
        return _insert_org_chart(path, op)
    raise ValueError(f"Unsupported P3.28 operation: {name}")


def apply_high_level_diagrams_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 32:
        raise ValueError("P3.28 transaction requires 1..32 high-level operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each P3.28 operation must be an object")

    before = build_high_level_diagram_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p328-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_high_level_diagram_map(candidate)
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
            "labeled_node_count": before["labeled_node_count"],
            "shape_text_sha256": before["shape_text_sha256"],
            "diagram_placement_sha256": before["diagram_placement_sha256"],
        },
        "after": {
            "labeled_node_count": after["labeled_node_count"],
            "shape_text_sha256": after["shape_text_sha256"],
            "diagram_placement_sha256": after["diagram_placement_sha256"],
        },
        "shape_text_changed": before["shape_text_sha256"] != after["shape_text_sha256"],
        "diagram_placement_changed": before["diagram_placement_sha256"] != after["diagram_placement_sha256"],
        "operation_count": len(operations),
        "receipts": receipts,
        "validation": validation,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
