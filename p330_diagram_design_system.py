from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from p326_drawing_style import (
    build_drawing_style_map,
    _resolve_style_target,
    _mutate_style,
    _set_stroke,
    _set_fill,
    _set_arrowheads,
)
from p329_diagram_lifecycle import (
    TEMPLATES as LIFECYCLE_TEMPLATES,
    build_diagram_lifecycle_map,
    _diagram,
    _node,
    _create,
    _edge_pairs,
    _remove_edges,
    _insert_edge,
)
from p327_diagram_composition import _resolve_top, _set_xy

SCHEMA = "chatgpt-web-hwpx-mcp/diagram-design-system/p3.30/v1"
AUTHORITY = "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY"

DEFERRED = {
    "rich_shape_text_typography": (
        "EVIDENCE_GATE_CLOSED: P3.30 styles native shape stroke/fill/edge geometry only; "
        "mixed-run hp:drawText typography needs dedicated evidence."
    ),
    "renderer_aware_collision_layout": (
        "EVIDENCE_GATE_CLOSED: layout policies are deterministic HWPUNIT spacing presets, "
        "not Hancom-render collision solving."
    ),
    "persist_theme_name_in_private_xml": (
        "EVIDENCE_GATE_CLOSED: P3.30 does not create a sidecar/private XML theme registry."
    ),
    "smart_connector_style_binding": (
        "EVIDENCE_GATE_CLOSED: edge styles apply to P3.29 reconstructed static relations, "
        "not hp:connectLine bindings."
    ),
}

LAYOUT_POLICIES = {
    "compact": {"gap_x": 7600, "gap_y": 5000},
    "standard": {"gap_x": 10000, "gap_y": 6500},
    "spacious": {"gap_x": 14000, "gap_y": 9000},
}

THEMES = {
    "classic": {
        "nodes": {
            "process": {"fill_color": "#F3F6FA", "stroke_color": "#34495E", "stroke_width": 283},
            "terminator": {"fill_color": "#E8F3FF", "stroke_color": "#2F6690", "stroke_width": 283},
            "decision": {"fill_color": "#FFF2CC", "stroke_color": "#A66E00", "stroke_width": 283},
            "data": {"fill_color": "#E8F5E9", "stroke_color": "#3B7D44", "stroke_width": 283},
            "node": {"fill_color": "#F2F2F2", "stroke_color": "#555555", "stroke_width": 283},
        },
        "edges": {
            "flow": {"stroke_color": "#555555", "stroke_width": 200, "stroke_style": "SOLID", "head_style": "ARROW"},
            "branch": {"stroke_color": "#A66E00", "stroke_width": 240, "stroke_style": "SOLID", "head_style": "ARROW"},
        },
    },
    "mono": {
        "nodes": {
            "process": {"fill_color": "#FFFFFF", "stroke_color": "#333333", "stroke_width": 240},
            "terminator": {"fill_color": "#F2F2F2", "stroke_color": "#333333", "stroke_width": 240},
            "decision": {"fill_color": "#E6E6E6", "stroke_color": "#222222", "stroke_width": 283},
            "data": {"fill_color": "#FAFAFA", "stroke_color": "#555555", "stroke_width": 240},
            "node": {"fill_color": "#F5F5F5", "stroke_color": "#444444", "stroke_width": 240},
        },
        "edges": {
            "flow": {"stroke_color": "#555555", "stroke_width": 180, "stroke_style": "SOLID", "head_style": "ARROW"},
            "branch": {"stroke_color": "#222222", "stroke_width": 220, "stroke_style": "DASH", "head_style": "ARROW"},
        },
    },
    "presentation": {
        "nodes": {
            "process": {"fill_color": "#EAF2FF", "stroke_color": "#2457A6", "stroke_width": 320},
            "terminator": {"fill_color": "#DDF7F0", "stroke_color": "#087F5B", "stroke_width": 320},
            "decision": {"fill_color": "#FFF0D6", "stroke_color": "#D97706", "stroke_width": 340},
            "data": {"fill_color": "#F0E8FF", "stroke_color": "#6D3CC1", "stroke_width": 320},
            "node": {"fill_color": "#EEF2F7", "stroke_color": "#425466", "stroke_width": 300},
        },
        "edges": {
            "flow": {"stroke_color": "#425466", "stroke_width": 240, "stroke_style": "SOLID", "head_style": "ARROW"},
            "branch": {"stroke_color": "#D97706", "stroke_width": 280, "stroke_style": "DASH", "head_style": "ARROW"},
        },
    },
}

PARAMETERIZED_TEMPLATES = {
    "linear_process",
    "decision_gate",
    "org_triad",
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def diagram_design_system_contract() -> dict:
    return {
        "phase": "P3.30",
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "theme_semantics": (
            "MATERIALIZED_NATIVE_STYLE: theme names are operation-level presets; persistent node identity "
            "comes from P3.29 and the resulting fill/stroke/arrow attributes remain in HWPX bytes."
        ),
        "semantic_roles": {
            "node": ["process", "terminator", "decision", "data", "node"],
            "edge": ["flow", "branch"],
            "edge_role_rule": "branch iff source node type is decision; otherwise flow",
        },
        "themes": sorted(THEMES),
        "layout_policies": sorted(LAYOUT_POLICIES),
        "parameterized_templates": sorted(PARAMETERIZED_TEMPLATES),
        "admitted_operations": [
            "apply_theme",
            "restyle_node",
            "restyle_edge",
            "apply_layout_policy",
            "instantiate_styled_template",
            "apply_design_system",
        ],
        "deferred_operations": dict(DEFERRED),
    }


def _style_index(path: Path) -> dict[str, dict]:
    return {item["locator"]: item for item in build_drawing_style_map(path)["styles"]}


def _node_role(node: dict) -> str:
    role = str(node.get("node_type") or "")
    if role not in {"process", "terminator", "decision", "data", "node"}:
        raise ValueError(f"unsupported semantic node role: {role}")
    return role


def _edge_role(diagram: dict, edge: dict) -> str:
    source = next(n for n in diagram["nodes"] if n["node_id"] == edge["source"])
    return "branch" if source["node_type"] == "decision" else "flow"


def _normalized_style(style: dict) -> dict:
    line = style.get("line_shape") or {}
    fill = style.get("fill") or {}
    return {
        "stroke_color": line.get("color"),
        "stroke_width": line.get("width"),
        "stroke_style": line.get("style"),
        "head_style": line.get("headStyle"),
        "fill_color": fill.get("faceColor"),
        "fill_alpha": fill.get("alpha"),
    }


def build_diagram_design_system_map(path: Path) -> dict:
    lifecycle = build_diagram_lifecycle_map(path)
    styles = _style_index(path)
    diagrams = []
    for diagram in lifecycle["diagrams"]:
        nodes = []
        for node in diagram["nodes"]:
            style = styles.get(node["locator"])
            nodes.append({
                **node,
                "semantic_role": _node_role(node),
                "effective_style": None if style is None else _normalized_style(style),
            })
        edges = []
        for edge in diagram["edges"]:
            style = styles.get(edge["locator"])
            edges.append({
                **edge,
                "semantic_role": _edge_role(diagram, edge),
                "effective_style": None if style is None else _normalized_style(style),
            })
        diagrams.append({
            **diagram,
            "nodes": nodes,
            "edges": edges,
        })
    style_seed = [
        {
            "diagram_id": d["diagram_id"],
            "nodes": [
                {"node_id": n["node_id"], "role": n["semantic_role"], "style": n["effective_style"]}
                for n in d["nodes"]
            ],
            "edges": [
                {"edge_id": e["edge_id"], "role": e["semantic_role"], "style": e["effective_style"]}
                for e in d["edges"]
            ],
        }
        for d in diagrams
    ]
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_count": len(diagrams),
        "diagrams": diagrams,
        "semantic_style_sha256": _sha(style_seed),
        "diagram_identity_sha256": lifecycle["diagram_identity_sha256"],
        "diagram_relation_sha256": lifecycle["diagram_relation_sha256"],
        "contract": diagram_design_system_contract(),
    }


def _apply_native_style(path: Path, locator: str, spec: dict, *, edge: bool) -> dict:
    target = _resolve_style_target(path, locator)
    receipts = []
    stroke_op = {}
    if "stroke_color" in spec:
        stroke_op["color"] = spec["stroke_color"]
    if "stroke_width" in spec:
        stroke_op["width"] = spec["stroke_width"]
    if "stroke_style" in spec:
        stroke_op["style"] = spec["stroke_style"]
    if "stroke_alpha" in spec:
        stroke_op["alpha"] = spec["stroke_alpha"]
    if stroke_op:
        receipts.append({
            "stroke": _mutate_style(path, target, lambda node: _set_stroke(node, stroke_op))
        })
    if not edge and "fill_color" in spec:
        fill_op = {"color": spec["fill_color"]}
        if "fill_alpha" in spec:
            fill_op["alpha"] = spec["fill_alpha"]
        receipts.append({
            "fill": _mutate_style(path, target, lambda node: _set_fill(node, fill_op))
        })
    if edge and "head_style" in spec:
        arrow_op = {
            "head_style": spec["head_style"],
            "head_fill": bool(spec.get("head_fill", True)),
        }
        if "head_size" in spec:
            arrow_op["head_size"] = spec["head_size"]
        receipts.append({
            "arrow": _mutate_style(path, target, lambda node: _set_arrowheads(node, arrow_op))
        })
    return {"drawing": locator, "receipts": receipts}


def _theme(name: object) -> tuple[str, dict]:
    key = str(name or "classic").lower()
    if key not in THEMES:
        raise ValueError(f"unknown diagram theme: {key}")
    return key, THEMES[key]


def _apply_theme(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    theme_name, theme = _theme(op.get("theme"))
    nodes = []
    for node in diagram["nodes"]:
        role = _node_role(node)
        nodes.append({
            "node_id": node["node_id"],
            "role": role,
            **_apply_native_style(path, node["locator"], theme["nodes"][role], edge=False),
        })
    current = _diagram(path, diagram["diagram_id"])
    edges = []
    for edge in current["edges"]:
        role = _edge_role(current, edge)
        edges.append({
            "edge_id": edge["edge_id"],
            "role": role,
            **_apply_native_style(path, edge["locator"], theme["edges"][role], edge=True),
        })
    return {"op": "apply_theme", "diagram_id": diagram["diagram_id"], "theme": theme_name, "nodes": nodes, "edges": edges}


def _restyle_node(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    node = _node(diagram, op.get("node_id"))
    spec = op.get("style")
    if not isinstance(spec, dict) or not spec:
        raise ValueError("restyle_node requires a non-empty style object")
    allowed = {"fill_color", "fill_alpha", "stroke_color", "stroke_width", "stroke_style", "stroke_alpha"}
    extra = set(spec) - allowed
    if extra:
        raise ValueError(f"unsupported node style tokens: {sorted(extra)}")
    return {
        "op": "restyle_node",
        "diagram_id": diagram["diagram_id"],
        "node_id": node["node_id"],
        **_apply_native_style(path, node["locator"], spec, edge=False),
    }


def _restyle_edge(path: Path, op: dict) -> dict:
    diagram = _diagram(path, op.get("diagram_id"))
    source, target = str(op.get("source") or ""), str(op.get("target") or "")
    edge = next((e for e in diagram["edges"] if e["source"] == source and e["target"] == target), None)
    if edge is None:
        raise ValueError(f"unknown managed edge: {source}->{target}")
    spec = op.get("style")
    if not isinstance(spec, dict) or not spec:
        raise ValueError("restyle_edge requires a non-empty style object")
    allowed = {"stroke_color", "stroke_width", "stroke_style", "stroke_alpha", "head_style", "head_size", "head_fill"}
    extra = set(spec) - allowed
    if extra:
        raise ValueError(f"unsupported edge style tokens: {sorted(extra)}")
    return {
        "op": "restyle_edge",
        "diagram_id": diagram["diagram_id"],
        "edge_id": edge["edge_id"],
        **_apply_native_style(path, edge["locator"], spec, edge=True),
    }


def _apply_layout_policy(path: Path, op: dict) -> dict:
    name = str(op.get("policy") or "standard").lower()
    if name not in LAYOUT_POLICIES:
        raise ValueError(f"unknown layout policy: {name}")
    policy = LAYOUT_POLICIES[name]
    diagram = _diagram(path, op.get("diagram_id"))
    layout = str(op.get("layout", "LEFT_TO_RIGHT")).upper()
    if layout not in {"LEFT_TO_RIGHT", "TOP_DOWN"}:
        raise ValueError(f"unsupported layout: {layout}")
    origin_x = int(op.get("origin_x", 1000))
    origin_y = int(op.get("origin_y", 1000))
    gap_x = int(op.get("gap_x", policy["gap_x"]))
    gap_y = int(op.get("gap_y", policy["gap_y"]))
    order = op.get("order") or [n["node_id"] for n in diagram["nodes"]]
    if sorted(order) != sorted(n["node_id"] for n in diagram["nodes"]):
        raise ValueError("layout-policy order must contain every managed node exactly once")

    pairs = _edge_pairs(diagram)
    initial_nodes = {node["node_id"]: node for node in diagram["nodes"]}
    _remove_edges(path, diagram)

    # P3.29 reconstructs identity from exact centers and therefore fails closed
    # on even transient center collisions. Stage every node at a unique remote
    # coordinate before assigning final policy coordinates.
    for index, node_id in enumerate(order):
        target = _resolve_top(path, initial_nodes[node_id]["locator"])
        _set_xy(path, target, 8_000_000 + index * 20_000, 8_000_000)

    for index, node_id in enumerate(order):
        target = _resolve_top(path, initial_nodes[node_id]["locator"])
        x = origin_x + (index * gap_x if layout == "LEFT_TO_RIGHT" else 0)
        y = origin_y + (index * gap_y if layout == "TOP_DOWN" else 0)
        _set_xy(path, target, x, y)

    rebuilt = []
    for source, target in pairs:
        rebuilt.append(_insert_edge(path, diagram["diagram_id"], source, target))
    return {
        "op": "apply_layout_policy",
        "policy": name,
        "layout": layout,
        "order": order,
        "rebuilt_edges": rebuilt,
        "collision_safe_staging": True,
    }


def _instantiate_styled_template(path: Path, op: dict) -> dict:
    template = str(op.get("template") or "")
    if template not in PARAMETERIZED_TEMPLATES:
        raise ValueError(f"unknown parameterized template: {template}")
    plan = json.loads(json.dumps(LIFECYCLE_TEMPLATES[template]))
    labels = op.get("labels", {})
    if not isinstance(labels, dict):
        raise ValueError("template labels must be an object")
    known = {node["id"] for node in plan["nodes"]}
    unknown = set(labels) - known
    if unknown:
        raise ValueError(f"unknown template label ids: {sorted(unknown)}")
    for node in plan["nodes"]:
        if node["id"] in labels:
            node["label"] = str(labels[node["id"]])
    policy_name = str(op.get("layout_policy", "standard")).lower()
    if policy_name not in LAYOUT_POLICIES:
        raise ValueError(f"unknown layout policy: {policy_name}")
    policy = LAYOUT_POLICIES[policy_name]
    plan["layout"] = str(op.get("layout", plan.get("layout", "LEFT_TO_RIGHT"))).upper()
    plan["origin_x"] = int(op.get("origin_x", 1000))
    plan["origin_y"] = int(op.get("origin_y", 1000))
    plan["gap_x"] = int(op.get("gap_x", policy["gap_x"]))
    plan["gap_y"] = int(op.get("gap_y", policy["gap_y"]))
    created = _create(path, {
        "op": "create_diagram",
        "diagram_id": op.get("diagram_id"),
        "anchor": op.get("anchor"),
        "plan": plan,
    })
    themed = _apply_theme(path, {"diagram_id": created["diagram_id"], "theme": op.get("theme", "classic")})
    return {
        "op": "instantiate_styled_template",
        "template": template,
        "layout_policy": policy_name,
        "created": created,
        "themed": themed,
    }


def _apply_design_system(path: Path, op: dict) -> dict:
    layout = _apply_layout_policy(path, {
        "diagram_id": op.get("diagram_id"),
        "policy": op.get("layout_policy", "standard"),
        "layout": op.get("layout", "LEFT_TO_RIGHT"),
        "origin_x": op.get("origin_x", 1000),
        "origin_y": op.get("origin_y", 1000),
        "order": op.get("order"),
    })
    theme = _apply_theme(path, {
        "diagram_id": op.get("diagram_id"),
        "theme": op.get("theme", "classic"),
    })
    return {"op": "apply_design_system", "layout": layout, "theme": theme}


def _apply_one(path: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED:
        raise ValueError(DEFERRED[name])
    if name == "apply_theme":
        return _apply_theme(path, op)
    if name == "restyle_node":
        return _restyle_node(path, op)
    if name == "restyle_edge":
        return _restyle_edge(path, op)
    if name == "apply_layout_policy":
        return _apply_layout_policy(path, op)
    if name == "instantiate_styled_template":
        return _instantiate_styled_template(path, op)
    if name == "apply_design_system":
        return _apply_design_system(path, op)
    raise ValueError(f"Unsupported P3.30 operation: {name}")


def apply_diagram_design_system_atomic(
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
        raise ValueError("P3.30 transaction requires 1..32 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each P3.30 operation must be an object")

    before = build_diagram_design_system_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p330-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_diagram_design_system_map(candidate)
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
            "semantic_style_sha256": before["semantic_style_sha256"],
            "diagram_identity_sha256": before["diagram_identity_sha256"],
            "diagram_relation_sha256": before["diagram_relation_sha256"],
        },
        "after": {
            "semantic_style_sha256": after["semantic_style_sha256"],
            "diagram_identity_sha256": after["diagram_identity_sha256"],
            "diagram_relation_sha256": after["diagram_relation_sha256"],
        },
        "semantic_style_changed": before["semantic_style_sha256"] != after["semantic_style_sha256"],
        "identity_preserved": before["diagram_identity_sha256"] == after["diagram_identity_sha256"],
        "operation_count": len(operations),
        "receipts": receipts,
        "validation": validation,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
