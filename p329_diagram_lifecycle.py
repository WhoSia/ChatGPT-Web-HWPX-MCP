from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

from p325_drawing_layer import (
    build_drawing_layer_map,
    _find_node,
    _mutate_section,
    _resize_node,
)
from p326_drawing_style import build_drawing_style_map
from p327_diagram_composition import _position_xy, _set_xy, _size, _resolve_top
from p328_high_level_diagrams import (
    NODE_DEFAULTS,
    NODE_KINDS,
    _insert_labeled_node,
    _insert_pointer_line,
    _normalize_plan,
    _set_existing_shape_text,
    build_high_level_diagram_map,
)

SCHEMA = "chatgpt-web-hwpx-mcp/diagram-lifecycle/p3.29/v1"
AUTHORITY = "STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY"
IDENTITY_PREFIX = "p329"
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,48}$")
LAYOUTS = {"LEFT_TO_RIGHT", "TOP_DOWN"}
MAX_MANAGED_NODES = 48
MAX_MANAGED_EDGES = 96

DEFERRED = {
    "smart_connector_binding": (
        "EVIDENCE_GATE_CLOSED: P3.29 reconstructs managed edges from exact static line geometry and "
        "regenerates them after node geometry changes; it does not claim hp:connectLine binding."
    ),
    "parallel_managed_edges": (
        "EVIDENCE_GATE_CLOSED: one managed static edge per ordered source->target pair; parallel-edge "
        "identity would require a separate durable edge carrier."
    ),
    "cross_anchor_subgraph": (
        "EVIDENCE_GATE_CLOSED: one managed diagram is constrained to one paragraph anchor."
    ),
    "renderer_aware_autolayout": (
        "EVIDENCE_GATE_CLOSED: relayout is deterministic HWPUNIT placement, not Hancom-render collision solving."
    ),
}

TEMPLATES = {
    "linear_process": {
        "layout": "LEFT_TO_RIGHT",
        "nodes": [
            {"id": "start", "type": "terminator", "label": "Start"},
            {"id": "work", "type": "process", "label": "Work"},
            {"id": "end", "type": "terminator", "label": "End"},
        ],
        "edges": [{"from": "start", "to": "work"}, {"from": "work", "to": "end"}],
    },
    "decision_gate": {
        "layout": "LEFT_TO_RIGHT",
        "nodes": [
            {"id": "input", "type": "process", "label": "Input"},
            {"id": "decision", "type": "decision", "label": "Decision"},
            {"id": "accept", "type": "process", "label": "Accept"},
            {"id": "reject", "type": "process", "label": "Reject"},
        ],
        "edges": [
            {"from": "input", "to": "decision"},
            {"from": "decision", "to": "accept"},
            {"from": "decision", "to": "reject"},
        ],
    },
    "org_triad": {
        "layout": "TOP_DOWN",
        "nodes": [
            {"id": "lead", "type": "node", "label": "Lead", "x": 11000, "y": 1000},
            {"id": "left", "type": "node", "label": "Left", "x": 1000, "y": 8000},
            {"id": "right", "type": "node", "label": "Right", "x": 21000, "y": 8000},
        ],
        "edges": [{"from": "lead", "to": "left"}, {"from": "lead", "to": "right"}],
    },
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _id(value: object, name: str) -> str:
    text = str(value or "")
    if not ID_RE.fullmatch(text):
        raise ValueError(f"{name} must match {ID_RE.pattern}")
    return text


def _marker(diagram_id: str, node_id: str, node_type: str) -> str:
    return f"{IDENTITY_PREFIX}|{_id(diagram_id, 'diagram_id')}|{_id(node_id, 'node_id')}|{node_type}"


def _parse_marker(value: object) -> dict | None:
    text = str(value or "")
    parts = text.split("|")
    if len(parts) != 4 or parts[0] != IDENTITY_PREFIX:
        return None
    diagram_id, node_id, node_type = parts[1:]
    if not ID_RE.fullmatch(diagram_id) or not ID_RE.fullmatch(node_id) or node_type not in NODE_KINDS:
        return None
    return {"diagram_id": diagram_id, "node_id": node_id, "node_type": node_type}


def diagram_lifecycle_contract() -> dict:
    return {
        "phase": "P3.29",
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "identity_semantics": (
            "NATIVE_DRAWTEXT_NAME_CARRIER: P3.29-owned nodes persist diagram_id/node_id/node_type in "
            "hp:drawText@name while visible label text remains independent."
        ),
        "edge_semantics": (
            "STATIC_RELATION_RECONSTRUCTION: managed edges are exact center-to-center native lines; "
            "source/target identity is reconstructed from current geometry and edges are regenerated "
            "after managed node geometry changes."
        ),
        "admitted_operations": [
            "create_diagram", "instantiate_template", "patch_node", "add_node", "remove_node",
            "add_edge", "remove_edge", "relayout_diagram", "move_subgraph",
            "clone_subgraph", "remove_subgraph",
        ],
        "templates": sorted(TEMPLATES),
        "layouts": sorted(LAYOUTS),
        "limits": {"nodes": MAX_MANAGED_NODES, "edges": MAX_MANAGED_EDGES},
        "deferred_operations": dict(DEFERRED),
    }


def _line_endpoints(style_map: dict, locator: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    style = next((x for x in style_map["styles"] if x["locator"] == locator and x["kind"] == "line"), None)
    base = next((x for x in style_map["objects"] if x["locator"] == locator), None)
    if style is None or base is None:
        return None
    try:
        ox, oy = _position_xy(base)
    except ValueError:
        return None
    pts = {p["kind"]: p for p in style.get("geometry_points", [])}
    start = pts.get("startPt")
    end = pts.get("endPt")
    if start is None or end is None:
        return None
    try:
        return (
            (ox + int(start.get("x", 0)), oy + int(start.get("y", 0))),
            (ox + int(end.get("x", 0)), oy + int(end.get("y", 0))),
        )
    except (TypeError, ValueError):
        return None


def build_diagram_lifecycle_map(path: Path) -> dict:
    high = build_high_level_diagram_map(path)
    styles = build_drawing_style_map(path)
    diagrams: dict[str, dict] = {}
    locator_to_node: dict[str, dict] = {}

    for item in high["labeled_nodes"]:
        identity = _parse_marker(item["draw_text"].get("name"))
        if identity is None:
            continue
        diagram_id = identity["diagram_id"]
        node = {
            **identity,
            "locator": item["locator"],
            "kind": item["kind"],
            "label": item["draw_text"]["text"],
            "anchor_locator": item.get("anchor_locator"),
            "position": item.get("position"),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        diagrams.setdefault(diagram_id, {"diagram_id": diagram_id, "nodes": [], "edges": []})["nodes"].append(node)
        locator_to_node[item["locator"]] = node

    for diagram in diagrams.values():
        diagram["nodes"].sort(key=lambda x: x["node_id"])
        ids = [n["node_id"] for n in diagram["nodes"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate managed node identity in diagram {diagram['diagram_id']}")
        anchors = {str(n.get("anchor_locator") or "") for n in diagram["nodes"]}
        if len(anchors) != 1 or "" in anchors:
            raise ValueError(f"managed diagram {diagram['diagram_id']} crosses paragraph anchors")
        diagram["anchor_locator"] = next(iter(anchors))
        centers: dict[tuple[int, int], str] = {}
        for node in diagram["nodes"]:
            item = _resolve_top(path, node["locator"])
            x, y = _position_xy(item)
            w, h = _size(item)
            center = (x + w // 2, y + h // 2)
            if center in centers:
                raise ValueError("managed node centers collide; edge identity would be ambiguous")
            centers[center] = node["node_id"]

        for obj in styles["objects"]:
            if obj["kind"] != "line" or str(obj.get("anchor_locator") or "") != diagram["anchor_locator"]:
                continue
            endpoints = _line_endpoints(styles, obj["locator"])
            if endpoints is None:
                continue
            a, b = endpoints
            if a not in centers or b not in centers or centers[a] == centers[b]:
                continue
            source, target = centers[a], centers[b]
            pair = f"{source}->{target}"
            if any(edge["edge_id"] == pair for edge in diagram["edges"]):
                raise ValueError(f"parallel managed edges are not admitted: {pair}")
            diagram["edges"].append({
                "edge_id": pair,
                "source": source,
                "target": target,
                "locator": obj["locator"],
                "binding": "STATIC_GEOMETRY_RECONSTRUCTED",
            })
        diagram["edges"].sort(key=lambda x: x["edge_id"])
        diagram["node_count"] = len(diagram["nodes"])
        diagram["edge_count"] = len(diagram["edges"])
        diagram["identity_sha256"] = _sha([
            {"id": n["node_id"], "type": n["node_type"], "locator": n["locator"]}
            for n in diagram["nodes"]
        ])
        diagram["relation_sha256"] = _sha([
            {"source": e["source"], "target": e["target"]} for e in diagram["edges"]
        ])

    ordered = [diagrams[key] for key in sorted(diagrams)]
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_count": len(ordered),
        "diagrams": ordered,
        "managed_node_count": sum(x["node_count"] for x in ordered),
        "managed_edge_count": sum(x["edge_count"] for x in ordered),
        "diagram_identity_sha256": _sha([
            {"diagram_id": d["diagram_id"], "identity": d["identity_sha256"]} for d in ordered
        ]),
        "diagram_relation_sha256": _sha([
            {"diagram_id": d["diagram_id"], "relation": d["relation_sha256"]} for d in ordered
        ]),
        "contract": diagram_lifecycle_contract(),
    }


def _diagram(path: Path, diagram_id: object) -> dict:
    did = _id(diagram_id, "diagram_id")
    found = next((x for x in build_diagram_lifecycle_map(path)["diagrams"] if x["diagram_id"] == did), None)
    if found is None:
        raise ValueError(f"unknown managed diagram: {did}")
    return found


def _node(diagram: dict, node_id: object) -> dict:
    nid = _id(node_id, "node_id")
    found = next((x for x in diagram["nodes"] if x["node_id"] == nid), None)
    if found is None:
        raise ValueError(f"unknown managed node: {nid}")
    return found


def _remove_locator(path: Path, locator: str) -> dict:
    target = _resolve_top(path, locator)
    def mutate(root):
        node = _find_node(root, target)
        parent = node.getparent()
        if parent is None:
            raise ValueError("drawing object has no mutable parent")
        parent.remove(node)
        grand = parent.getparent()
        if grand is not None and parent.tag.rsplit("}", 1)[-1] == "run" and len(parent) == 0:
            grand.remove(parent)
    _mutate_section(path, target["section"], mutate)
    return {"removed": locator, "kind": target["kind"]}


def _edge_pairs(diagram: dict) -> list[tuple[str, str]]:
    return [(e["source"], e["target"]) for e in diagram["edges"]]


def _remove_edges(path: Path, diagram: dict) -> None:
    for edge in list(diagram["edges"]):
        _remove_locator(path, edge["locator"])


def _insert_edge(path: Path, diagram_id: str, source_id: str, target_id: str) -> dict:
    diagram = _diagram(path, diagram_id)
    source = _node(diagram, source_id)
    target = _node(diagram, target_id)
    if source_id == target_id:
        raise ValueError("self-loop managed edges are not admitted")
    if any(e["source"] == source_id and e["target"] == target_id for e in diagram["edges"]):
        raise ValueError(f"managed edge already exists: {source_id}->{target_id}")
    s = _resolve_top(path, source["locator"])
    t = _resolve_top(path, target["locator"])
    sx, sy = _position_xy(s)
    tx, ty = _position_xy(t)
    sw, sh = _size(s)
    tw, th = _size(t)
    locator = _insert_pointer_line(
        path,
        anchor=diagram["anchor_locator"],
        start=(sx + sw // 2, sy + sh // 2),
        end=(tx + tw // 2, ty + th // 2),
        line_color="#444444",
        line_width=283,
    )
    return {"edge_id": f"{source_id}->{target_id}", "locator": locator}


def _rebuild_edges(path: Path, diagram_id: str, pairs: list[tuple[str, str]]) -> list[dict]:
    current = _diagram(path, diagram_id)
    _remove_edges(path, current)
    receipts = []
    for source, target in pairs:
        receipts.append(_insert_edge(path, diagram_id, source, target))
    return receipts


def _create(path: Path, op: dict) -> dict:
    diagram_id = _id(op.get("diagram_id"), "diagram_id")
    if any(x["diagram_id"] == diagram_id for x in build_diagram_lifecycle_map(path)["diagrams"]):
        raise ValueError(f"managed diagram already exists: {diagram_id}")
    plan = _normalize_plan(op.get("plan"))
    if len(plan["nodes"]) > MAX_MANAGED_NODES or len(plan["edges"]) > MAX_MANAGED_EDGES:
        raise ValueError("managed diagram exceeds P3.29 bounds")
    anchor = str(op.get("anchor") or "")
    if not anchor:
        raise ValueError("create_diagram requires anchor")
    node_locators: dict[str, str] = {}
    positions = {}
    auto_order = 0
    for node in plan["nodes"]:
        if "x" in node and "y" in node:
            x, y = int(node["x"]), int(node["y"])
        elif plan["layout"] == "LEFT_TO_RIGHT":
            x, y = plan["origin_x"] + auto_order * plan["gap_x"], plan["origin_y"]
            auto_order += 1
        else:
            x, y = plan["origin_x"], plan["origin_y"] + auto_order * plan["gap_y"]
            auto_order += 1
        positions[node["id"]] = (x, y)
        receipt = _insert_labeled_node(path, {
            "anchor": anchor,
            "node_type": node["type"],
            "text": node["label"],
            "name": _marker(diagram_id, node["id"], node["type"]),
            "horizontal_offset": x,
            "vertical_offset": y,
            "width": node.get("width", NODE_DEFAULTS[node["type"]].get("width", 7200)),
            "height": node.get("height", NODE_DEFAULTS[node["type"]].get("height", 3600)),
            "fill_color": node.get("fill_color", NODE_DEFAULTS[node["type"]].get("fill_color", "#F4F4F4")),
            "line_color": node.get("line_color", "#000000"),
            "line_width": node.get("line_width", 283),
        })
        node_locators[node["id"]] = receipt["created_node"]
    edges = []
    for edge in plan["edges"]:
        edges.append(_insert_edge(path, diagram_id, edge["from"], edge["to"]))
    return {
        "op": "create_diagram",
        "diagram_id": diagram_id,
        "node_count": len(node_locators),
        "edge_count": len(edges),
        "node_locators": node_locators,
        "edges": edges,
    }


def _instantiate_template(path: Path, op: dict) -> dict:
    name = str(op.get("template") or "")
    if name not in TEMPLATES:
        raise ValueError(f"unknown diagram template: {name}")
    plan = json.loads(json.dumps(TEMPLATES[name]))
    for key in ("origin_x", "origin_y", "gap_x", "gap_y", "layout"):
        if key in op:
            plan[key] = op[key]
    receipt = _create(path, {**op, "op": "create_diagram", "plan": plan})
    return {"op": "instantiate_template", "template": name, **receipt}


def _patch_node(path: Path, op: dict) -> dict:
    diagram_id = _id(op.get("diagram_id"), "diagram_id")
    diagram = _diagram(path, diagram_id)
    node = _node(diagram, op.get("node_id"))
    pairs = _edge_pairs(diagram)
    target = _resolve_top(path, node["locator"])

    if "label" in op:
        _set_existing_shape_text(path, {
            "drawing": node["locator"],
            "text": str(op["label"]),
            "name": _marker(diagram_id, node["node_id"], node["node_type"]),
            "text_margin": op.get("text_margin", 283),
        })
        diagram = _diagram(path, diagram_id)
        node = _node(diagram, node["node_id"])
        target = _resolve_top(path, node["locator"])

    if "x" in op or "y" in op:
        x, y = _position_xy(target)
        _set_xy(path, target, int(op.get("x", x)), int(op.get("y", y)))
        diagram = _diagram(path, diagram_id)
        node = _node(diagram, node["node_id"])
        target = _resolve_top(path, node["locator"])

    if "width" in op or "height" in op:
        w, h = _size(target)
        width, height = int(op.get("width", w)), int(op.get("height", h))
        def mutate(root):
            _resize_node(_find_node(root, target), width, height)
        _mutate_section(path, target["section"], mutate)

    rebuilt = _rebuild_edges(path, diagram_id, pairs) if pairs else []
    return {"op": "patch_node", "diagram_id": diagram_id, "node_id": node["node_id"], "rebuilt_edges": rebuilt}


def _add_node(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    if diagram["node_count"] >= MAX_MANAGED_NODES:
        raise ValueError("managed node limit reached")
    node_id = _id(op.get("node_id"), "node_id")
    if any(x["node_id"] == node_id for x in diagram["nodes"]):
        raise ValueError(f"managed node already exists: {node_id}")
    node_type = str(op.get("node_type", "process")).lower()
    if node_type not in NODE_KINDS:
        raise ValueError(f"unsupported node_type: {node_type}")
    receipt = _insert_labeled_node(path, {
        "anchor": diagram["anchor_locator"],
        "node_type": node_type,
        "text": str(op.get("label", node_id)),
        "name": _marker(diagram["diagram_id"], node_id, node_type),
        "horizontal_offset": int(op.get("x", 1000)),
        "vertical_offset": int(op.get("y", 1000)),
        "width": op.get("width", NODE_DEFAULTS[node_type].get("width", 7200)),
        "height": op.get("height", NODE_DEFAULTS[node_type].get("height", 3600)),
        "fill_color": op.get("fill_color", NODE_DEFAULTS[node_type].get("fill_color", "#F4F4F4")),
    })
    return {"op": "add_node", "diagram_id": diagram["diagram_id"], "node_id": node_id, **receipt}


def _remove_node(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    node = _node(diagram, op.get("node_id"))
    incident = [e for e in diagram["edges"] if node["node_id"] in {e["source"], e["target"]}]
    for edge in incident:
        _remove_locator(path, edge["locator"])
    _remove_locator(path, node["locator"])
    return {"op": "remove_node", "node_id": node["node_id"], "removed_edges": [e["edge_id"] for e in incident]}


def _add_edge(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    if diagram["edge_count"] >= MAX_MANAGED_EDGES:
        raise ValueError("managed edge limit reached")
    source = _id(op.get("source"), "source")
    target = _id(op.get("target"), "target")
    return {"op": "add_edge", **_insert_edge(path, diagram["diagram_id"], source, target)}


def _remove_edge(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    source = _id(op.get("source"), "source")
    target = _id(op.get("target"), "target")
    edge = next((e for e in diagram["edges"] if e["source"] == source and e["target"] == target), None)
    if edge is None:
        raise ValueError(f"unknown managed edge: {source}->{target}")
    _remove_locator(path, edge["locator"])
    return {"op": "remove_edge", "edge_id": edge["edge_id"]}


def _relayout(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    layout = str(op.get("layout", "LEFT_TO_RIGHT")).upper()
    if layout not in LAYOUTS:
        raise ValueError(f"unsupported layout: {layout}")
    origin_x = int(op.get("origin_x", 1000))
    origin_y = int(op.get("origin_y", 1000))
    gap_x = int(op.get("gap_x", 10000))
    gap_y = int(op.get("gap_y", 6500))
    order = op.get("order") or [n["node_id"] for n in diagram["nodes"]]
    if sorted(order) != sorted(n["node_id"] for n in diagram["nodes"]):
        raise ValueError("relayout order must contain every managed node exactly once")
    pairs = _edge_pairs(diagram)
    for index, node_id in enumerate(order):
        current = _diagram(path, diagram["diagram_id"])
        node = _node(current, node_id)
        target = _resolve_top(path, node["locator"])
        x = origin_x + (index * gap_x if layout == "LEFT_TO_RIGHT" else 0)
        y = origin_y + (index * gap_y if layout == "TOP_DOWN" else 0)
        _set_xy(path, target, x, y)
    rebuilt = _rebuild_edges(path, diagram["diagram_id"], pairs) if pairs else []
    return {"op": "relayout_diagram", "layout": layout, "order": order, "rebuilt_edges": rebuilt}


def _move_subgraph(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    node_ids = [_id(x, "node_id") for x in op.get("node_ids", [])]
    if not node_ids or len(node_ids) != len(set(node_ids)):
        raise ValueError("move_subgraph requires unique non-empty node_ids")
    pairs = _edge_pairs(diagram)
    dx, dy = int(op.get("dx", 0)), int(op.get("dy", 0))
    moved = []
    for node_id in node_ids:
        current = _diagram(path, diagram["diagram_id"])
        node = _node(current, node_id)
        target = _resolve_top(path, node["locator"])
        x, y = _position_xy(target)
        _set_xy(path, target, x + dx, y + dy)
        moved.append(node_id)
    rebuilt = _rebuild_edges(path, diagram["diagram_id"], pairs) if pairs else []
    return {"op": "move_subgraph", "node_ids": moved, "dx": dx, "dy": dy, "rebuilt_edges": rebuilt}


def _clone_subgraph(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    selected = [_id(x, "node_id") for x in op.get("node_ids", [])]
    prefix = _id(op.get("new_prefix", "copy"), "new_prefix")
    if not selected:
        raise ValueError("clone_subgraph requires node_ids")
    dx, dy = int(op.get("dx", 12000)), int(op.get("dy", 0))
    mapping = {}
    for node_id in selected:
        node = _node(diagram, node_id)
        new_id = _id(f"{prefix}-{node_id}", "cloned_node_id")
        if any(x["node_id"] == new_id for x in diagram["nodes"]) or new_id in mapping.values():
            raise ValueError(f"cloned node id already exists: {new_id}")
        target = _resolve_top(path, node["locator"])
        x, y = _position_xy(target)
        w, h = _size(target)
        _add_node(path, {
            "diagram_id": diagram["diagram_id"], "node_id": new_id, "node_type": node["node_type"],
            "label": node["label"], "x": x + dx, "y": y + dy, "width": w, "height": h,
        })
        mapping[node_id] = new_id
    internal = [
        (e["source"], e["target"]) for e in diagram["edges"]
        if e["source"] in mapping and e["target"] in mapping
    ]
    for source, target in internal:
        _insert_edge(path, diagram["diagram_id"], mapping[source], mapping[target])
    return {"op": "clone_subgraph", "mapping": mapping, "cloned_edges": [f"{mapping[s]}->{mapping[t]}" for s, t in internal]}


def _remove_subgraph(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    selected = {_id(x, "node_id") for x in op.get("node_ids", [])}
    if not selected:
        raise ValueError("remove_subgraph requires node_ids")
    missing = selected - {n["node_id"] for n in diagram["nodes"]}
    if missing:
        raise ValueError(f"unknown managed nodes: {sorted(missing)}")
    edges = [e for e in diagram["edges"] if e["source"] in selected or e["target"] in selected]
    for edge in edges:
        _remove_locator(path, edge["locator"])
    for node_id in sorted(selected):
        current = _diagram(path, diagram["diagram_id"])
        _remove_locator(path, _node(current, node_id)["locator"])
    return {"op": "remove_subgraph", "node_ids": sorted(selected), "removed_edges": [e["edge_id"] for e in edges]}


def _apply_one(path: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED:
        raise ValueError(DEFERRED[name])
    if name == "create_diagram":
        return _create(path, op)
    if name == "instantiate_template":
        return _instantiate_template(path, op)
    if name == "patch_node":
        return _patch_node(path, op)
    if name == "add_node":
        return _add_node(path, op)
    if name == "remove_node":
        return _remove_node(path, op)
    if name == "add_edge":
        return _add_edge(path, op)
    if name == "remove_edge":
        return _remove_edge(path, op)
    if name == "relayout_diagram":
        return _relayout(path, op)
    if name == "move_subgraph":
        return _move_subgraph(path, op)
    if name == "clone_subgraph":
        return _clone_subgraph(path, op)
    if name == "remove_subgraph":
        return _remove_subgraph(path, op)
    raise ValueError(f"Unsupported P3.29 operation: {name}")


def apply_diagram_lifecycle_atomic(
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
        raise ValueError("P3.29 transaction requires 1..32 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each P3.29 operation must be an object")

    before = build_diagram_lifecycle_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p329-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_diagram_lifecycle_map(candidate)
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
            "diagram_count": before["diagram_count"],
            "managed_node_count": before["managed_node_count"],
            "managed_edge_count": before["managed_edge_count"],
            "diagram_identity_sha256": before["diagram_identity_sha256"],
            "diagram_relation_sha256": before["diagram_relation_sha256"],
        },
        "after": {
            "diagram_count": after["diagram_count"],
            "managed_node_count": after["managed_node_count"],
            "managed_edge_count": after["managed_edge_count"],
            "diagram_identity_sha256": after["diagram_identity_sha256"],
            "diagram_relation_sha256": after["diagram_relation_sha256"],
        },
        "operation_count": len(operations),
        "receipts": receipts,
        "validation": validation,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
