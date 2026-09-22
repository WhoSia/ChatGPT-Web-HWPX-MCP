from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from p325_drawing_layer import HP, _find_node, _mutate_section, build_drawing_layer_map
from p328_high_level_diagrams import build_high_level_diagram_map
from p329_diagram_lifecycle import (
    NODE_KINDS,
    _line_endpoints,
    _marker,
    _parse_marker,
    build_diagram_lifecycle_map,
)
from p326_drawing_style import build_drawing_style_map
from p330_diagram_design_system import (
    LAYOUT_POLICIES,
    THEMES,
    apply_diagram_design_system_atomic,
)

SCHEMA = "chatgpt-web-hwpx-mcp/brownfield-diagram/p3.32/v1"
AUTHORITY = "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY"
MAX_CANDIDATE_NODES = 32
MAX_CANDIDATE_EDGES = 64

DEFERRED = {
    "pixel_visual_recognition": (
        "EVIDENCE_GATE_CLOSED: P3.32 recognizes only HWPX-native drawing structure, labels, anchors, "
        "geometry and exact center-to-center static lines; no rendered-pixel or computer-vision inference."
    ),
    "occupied_name_carrier_override": (
        "EVIDENCE_GATE_CLOSED: an unmanaged shape with a non-empty hp:drawText@name is not auto-promoted "
        "because P3.29 ownership would overwrite pre-existing metadata."
    ),
    "cross_anchor_adoption": (
        "EVIDENCE_GATE_CLOSED: one promoted managed graph remains constrained to one paragraph anchor."
    ),
    "semantic_auto_repair": (
        "EVIDENCE_GATE_CLOSED: P3.32 may adopt observed relations and apply meaning-preserving layout/theme "
        "refactoring after promotion; it does not invent, delete or reinterpret graph relations."
    ),
    "smart_connector_binding": (
        "EVIDENCE_GATE_CLOSED: existing hp:connectLine/subjectIDRef smart bindings remain outside authority."
    ),
    "parallel_managed_edges": (
        "EVIDENCE_GATE_CLOSED: P3.29 still admits at most one managed static edge per ordered node pair."
    ),
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brownfield_diagram_contract() -> dict:
    return {
        "phase": "P3.32",
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "recognition_semantics": (
            "READ_ONLY_EVIDENCE_FIRST: recognition never writes ownership. Candidates are connected components "
            "of unmanaged top-level labeled shapes on one anchor whose native static lines terminate exactly at "
            "shape centers."
        ),
        "promotion_semantics": (
            "EXPLICIT_STALE_SAFE_ADOPTION: promotion writes only P3.29 hp:drawText@name identity carriers, "
            "preserves intrinsic id/instid and all visible label/style/geometry, and requires source/candidate hashes."
        ),
        "refactor_semantics": (
            "POST_PROMOTION_MEANING_PRESERVING_ONLY: legacy refactoring delegates only to P3.30 layout policy "
            "and theme materialization after managed identity/relation closure."
        ),
        "admitted_operations": [
            "recognize_existing_diagrams",
            "plan_diagram_adoption",
            "promote_diagram_candidate",
            "plan_legacy_diagram_refactor",
            "apply_legacy_diagram_refactor",
        ],
        "limits": {"nodes": MAX_CANDIDATE_NODES, "edges": MAX_CANDIDATE_EDGES},
        "deferred_operations": dict(DEFERRED),
    }


def _xywh(item: dict) -> tuple[int, int, int, int]:
    pos = item.get("position") or {}
    return (
        int(pos.get("horzOffset", 0) or 0),
        int(pos.get("vertOffset", 0) or 0),
        int(item.get("width", 0) or 0),
        int(item.get("height", 0) or 0),
    )


def _center(item: dict) -> tuple[int, int]:
    x, y, w, h = _xywh(item)
    return x + w // 2, y + h // 2


def _default_node_type(kind: str) -> str:
    if kind == "ellipse":
        return "terminator"
    if kind == "rect":
        return "process"
    return "node"


def _candidate_components(nodes: list[dict], edges: list[dict]) -> list[tuple[list[dict], list[dict]]]:
    by_locator = {node["locator"]: node for node in nodes}
    adjacency = {locator: set() for locator in by_locator}
    for edge in edges:
        a, b = edge["source_locator"], edge["target_locator"]
        if a in adjacency and b in adjacency:
            adjacency[a].add(b)
            adjacency[b].add(a)
    unseen = {loc for loc, links in adjacency.items() if links}
    result = []
    while unseen:
        root = sorted(unseen)[0]
        stack = [root]
        seen = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(sorted(adjacency[cur] - seen))
        unseen -= seen
        component_nodes = [by_locator[loc] for loc in sorted(seen)]
        component_edges = [
            edge for edge in edges
            if edge["source_locator"] in seen and edge["target_locator"] in seen
        ]
        result.append((component_nodes, component_edges))
    return result


def build_brownfield_diagram_map(path: Path) -> dict:
    drawing = build_drawing_layer_map(path)
    high = build_high_level_diagram_map(path)
    styles = build_drawing_style_map(path)
    managed = build_diagram_lifecycle_map(path)

    drawing_by_locator = {item["locator"]: item for item in drawing["objects"]}
    labeled = []
    for item in high["labeled_nodes"]:
        draw = item["draw_text"]
        marker = _parse_marker(draw.get("name"))
        base = drawing_by_locator.get(item["locator"])
        if base is None or marker is not None:
            continue
        labeled.append({
            "locator": item["locator"],
            "kind": item["kind"],
            "anchor_locator": item.get("anchor_locator"),
            "label": draw.get("text", ""),
            "name_carrier": draw.get("name", ""),
            "address_stability": base.get("address_stability"),
            "id": base.get("id"),
            "instid": base.get("instid"),
            "position": item.get("position"),
            "width": item.get("width"),
            "height": item.get("height"),
            "default_node_type": _default_node_type(item["kind"]),
        })

    by_anchor: dict[str, list[dict]] = {}
    for node in labeled:
        anchor = str(node.get("anchor_locator") or "")
        if anchor:
            by_anchor.setdefault(anchor, []).append(node)

    candidates = []
    for anchor, anchor_nodes in sorted(by_anchor.items()):
        centers: dict[tuple[int, int], list[str]] = {}
        node_by_locator = {n["locator"]: n for n in anchor_nodes}
        for node in anchor_nodes:
            centers.setdefault(_center(node), []).append(node["locator"])
        local_edges = []
        pair_counts: dict[tuple[str, str], int] = {}
        for obj in styles["objects"]:
            if obj.get("kind") != "line" or str(obj.get("anchor_locator") or "") != anchor:
                continue
            endpoints = _line_endpoints(styles, obj["locator"])
            if endpoints is None:
                continue
            a, b = endpoints
            if len(centers.get(a, [])) != 1 or len(centers.get(b, [])) != 1:
                continue
            source = centers[a][0]
            target = centers[b][0]
            if source == target:
                continue
            pair = (source, target)
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
            local_edges.append({
                "locator": obj["locator"],
                "source_locator": source,
                "target_locator": target,
                "binding": "EXACT_CENTER_STATIC_LINE",
            })

        for component_nodes, component_edges in _candidate_components(anchor_nodes, local_edges):
            if len(component_nodes) < 2 or not component_edges:
                continue
            locators = {n["locator"] for n in component_nodes}
            component_pair_counts = {
                pair: count for pair, count in pair_counts.items()
                if pair[0] in locators and pair[1] in locators
            }
            reasons = []
            if len(component_nodes) > MAX_CANDIDATE_NODES:
                reasons.append("NODE_LIMIT_EXCEEDED")
            if len(component_edges) > MAX_CANDIDATE_EDGES:
                reasons.append("EDGE_LIMIT_EXCEEDED")
            if any(len(centers[_center(node)]) != 1 for node in component_nodes):
                reasons.append("NODE_CENTER_COLLISION")
            if any(count > 1 for count in component_pair_counts.values()):
                reasons.append("PARALLEL_EDGE_AMBIGUITY")
            if any(node.get("address_stability") != "intrinsic-id" for node in component_nodes):
                reasons.append("REVISION_BOUND_NODE_LOCATOR")
            if any(str(node.get("name_carrier") or "") for node in component_nodes):
                reasons.append("NAME_CARRIER_OCCUPIED")
            seed = {
                "anchor": anchor,
                "nodes": [
                    {
                        "locator": n["locator"],
                        "kind": n["kind"],
                        "label": n["label"],
                        "id": n.get("id"),
                        "instid": n.get("instid"),
                        "center": _center(n),
                    }
                    for n in sorted(component_nodes, key=lambda x: x["locator"])
                ],
                "edges": [
                    {
                        "locator": e["locator"],
                        "source": e["source_locator"],
                        "target": e["target_locator"],
                    }
                    for e in sorted(component_edges, key=lambda x: (x["source_locator"], x["target_locator"], x["locator"]))
                ],
            }
            candidate_hash = _sha(seed)
            candidates.append({
                "candidate_id": "bf_" + candidate_hash[:16],
                "candidate_sha256": candidate_hash,
                "anchor_locator": anchor,
                "node_count": len(component_nodes),
                "edge_count": len(component_edges),
                "nodes": sorted(component_nodes, key=lambda x: x["locator"]),
                "edges": sorted(component_edges, key=lambda x: (x["source_locator"], x["target_locator"], x["locator"])),
                "promotable": not reasons,
                "hold_reasons": sorted(set(reasons)),
                "evidence": "NATIVE_STRUCTURE_PLUS_EXACT_CENTER_RELATIONS",
            })

    candidates.sort(key=lambda x: x["candidate_id"])
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "source_document_sha256": _file_sha(path),
        "unmanaged_labeled_node_count": len(labeled),
        "candidate_count": len(candidates),
        "promotable_candidate_count": sum(c["promotable"] for c in candidates),
        "candidates": candidates,
        "managed_diagram_count": managed["diagram_count"],
        "managed_diagrams": [
            {
                "diagram_id": d["diagram_id"],
                "node_count": d["node_count"],
                "edge_count": d["edge_count"],
                "anchor_locator": d["anchor_locator"],
            }
            for d in managed["diagrams"]
        ],
        "recognition_sha256": _sha([
            {
                "candidate_id": c["candidate_id"],
                "candidate_sha256": c["candidate_sha256"],
                "promotable": c["promotable"],
                "hold_reasons": c["hold_reasons"],
            }
            for c in candidates
        ]),
        "contract": brownfield_diagram_contract(),
    }


def _candidate(path: Path, candidate_id: str) -> tuple[dict, dict]:
    mapped = build_brownfield_diagram_map(path)
    found = next((c for c in mapped["candidates"] if c["candidate_id"] == str(candidate_id)), None)
    if found is None:
        raise ValueError(f"unknown brownfield diagram candidate: {candidate_id}")
    return mapped, found


def plan_diagram_adoption(
    path: Path,
    candidate_id: str,
    diagram_id: str,
    *,
    node_bindings: dict | None = None,
) -> dict:
    mapped, candidate = _candidate(path, candidate_id)
    if not candidate["promotable"]:
        raise ValueError(f"candidate is not promotable: {candidate['hold_reasons']}")
    if not str(diagram_id or ""):
        raise ValueError("diagram_id is required")
    node_bindings = node_bindings or {}
    if not isinstance(node_bindings, dict):
        raise ValueError("node_bindings must be an object")
    unknown = set(node_bindings) - {n["locator"] for n in candidate["nodes"]}
    if unknown:
        raise ValueError(f"node_bindings contains unknown locators: {sorted(unknown)}")

    bindings = []
    used_ids = set()
    for index, node in enumerate(candidate["nodes"], start=1):
        requested = node_bindings.get(node["locator"], {})
        if not isinstance(requested, dict):
            raise ValueError("each node binding must be an object")
        node_id = str(requested.get("node_id") or f"legacy-{index:02d}")
        node_type = str(requested.get("node_type") or node["default_node_type"]).lower()
        if node_type not in NODE_KINDS:
            raise ValueError(f"unsupported adopted node_type: {node_type}")
        if node_id in used_ids:
            raise ValueError(f"duplicate adopted node_id: {node_id}")
        used_ids.add(node_id)
        bindings.append({
            "locator": node["locator"],
            "node_id": node_id,
            "node_type": node_type,
            "label": node["label"],
            "source_id": node.get("id"),
            "source_instid": node.get("instid"),
        })

    plan_seed = {
        "source_document_sha256": mapped["source_document_sha256"],
        "recognition_sha256": mapped["recognition_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "candidate_id": candidate["candidate_id"],
        "diagram_id": str(diagram_id),
        "bindings": bindings,
        "relations": [
            {"source_locator": e["source_locator"], "target_locator": e["target_locator"]}
            for e in candidate["edges"]
        ],
    }
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "candidate_id": candidate["candidate_id"],
        "diagram_id": str(diagram_id),
        "source_document_sha256": mapped["source_document_sha256"],
        "source_recognition_sha256": mapped["recognition_sha256"],
        "source_candidate_sha256": candidate["candidate_sha256"],
        "bindings": bindings,
        "observed_relations": candidate["edges"],
        "adoption_plan_sha256": _sha(plan_seed),
        "mutation_scope": "HP_DRAWTEXT_NAME_ONLY",
    }


def _set_marker_name(path: Path, target: dict, marker: str) -> None:
    def mutate(root):
        node = _find_node(root, target)
        draw = node.find(f"{HP}drawText")
        if draw is None:
            raise ValueError("candidate node lost hp:drawText before promotion")
        existing = str(draw.get("name", "") or "")
        if existing:
            raise ValueError("candidate node hp:drawText@name became occupied")
        draw.set("name", marker)
    _mutate_section(path, target["section"], mutate)


def promote_diagram_candidate_atomic(
    path: Path,
    adoption_plan: dict,
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not isinstance(adoption_plan, dict):
        raise ValueError("adoption_plan must be an object")

    mapped = build_brownfield_diagram_map(path)
    if mapped["source_document_sha256"] != str(adoption_plan.get("source_document_sha256") or ""):
        raise ValueError("adoption plan source document hash is stale")
    if mapped["recognition_sha256"] != str(adoption_plan.get("source_recognition_sha256") or ""):
        raise ValueError("adoption plan recognition receipt is stale")
    candidate_id = str(adoption_plan.get("candidate_id") or "")
    candidate = next((c for c in mapped["candidates"] if c["candidate_id"] == candidate_id), None)
    if candidate is None:
        raise ValueError("adoption plan candidate is stale or no longer recognized")
    if candidate["candidate_sha256"] != str(adoption_plan.get("source_candidate_sha256") or ""):
        raise ValueError("adoption plan candidate receipt is stale")
    if not candidate["promotable"]:
        raise ValueError(f"candidate is no longer promotable: {candidate['hold_reasons']}")

    bindings = adoption_plan.get("bindings")
    if not isinstance(bindings, list) or len(bindings) != candidate["node_count"]:
        raise ValueError("adoption plan bindings no longer match candidate node count")
    by_locator = {n["locator"]: n for n in candidate["nodes"]}
    drawing = build_drawing_layer_map(path)
    targets = {item["locator"]: item for item in drawing["objects"]}
    if set(by_locator) != {str(item.get("locator") or "") for item in bindings}:
        raise ValueError("adoption plan locator set is stale")

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p332-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate_path = Path(tmp_name)
    candidate_path.write_bytes(path.read_bytes())
    validation = None
    try:
        for binding in bindings:
            locator = str(binding["locator"])
            target = targets.get(locator)
            if target is None:
                raise ValueError(f"candidate locator disappeared: {locator}")
            _set_marker_name(
                candidate_path,
                target,
                _marker(
                    str(adoption_plan["diagram_id"]),
                    str(binding["node_id"]),
                    str(binding["node_type"]),
                ),
            )
        lifecycle = build_diagram_lifecycle_map(candidate_path)
        promoted = next(
            (d for d in lifecycle["diagrams"] if d["diagram_id"] == str(adoption_plan["diagram_id"])),
            None,
        )
        if promoted is None:
            raise ValueError("promotion did not materialize one managed diagram")
        if promoted["node_count"] != candidate["node_count"] or promoted["edge_count"] != candidate["edge_count"]:
            raise ValueError("promotion changed or failed to recover observed graph cardinality")
        if validator is not None:
            validation = validator(candidate_path)
        os.replace(candidate_path, path)
    except Exception:
        try:
            candidate_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_id": str(adoption_plan["diagram_id"]),
        "candidate_id": candidate["candidate_id"],
        "node_count": promoted["node_count"],
        "edge_count": promoted["edge_count"],
        "identity_sha256": promoted["identity_sha256"],
        "relation_sha256": promoted["relation_sha256"],
        "source_object_identity_preserved": True,
        "visible_label_geometry_style_preserved_by_mutation_scope": True,
        "mutation_scope": "HP_DRAWTEXT_NAME_ONLY",
        "validation": validation,
    }


def plan_legacy_diagram_refactor(
    path: Path,
    diagram_id: str,
    *,
    layout_policy: str = "",
    layout: str = "LEFT_TO_RIGHT",
    theme: str = "",
) -> dict:
    lifecycle = build_diagram_lifecycle_map(path)
    diagram = next((d for d in lifecycle["diagrams"] if d["diagram_id"] == str(diagram_id)), None)
    if diagram is None:
        raise ValueError(f"unknown managed diagram: {diagram_id}")
    operations = []
    if layout_policy:
        policy = str(layout_policy).lower()
        if policy not in LAYOUT_POLICIES:
            raise ValueError(f"unknown layout policy: {policy}")
        operations.append({
            "op": "apply_layout_policy",
            "diagram_id": str(diagram_id),
            "policy": policy,
            "layout": str(layout).upper(),
        })
    if theme:
        theme_name = str(theme).lower()
        if theme_name not in THEMES:
            raise ValueError(f"unknown diagram theme: {theme_name}")
        operations.append({"op": "apply_theme", "diagram_id": str(diagram_id), "theme": theme_name})
    if not operations:
        raise ValueError("refactor plan requires layout_policy and/or theme")
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_id": str(diagram_id),
        "source_identity_sha256": diagram["identity_sha256"],
        "source_relation_sha256": diagram["relation_sha256"],
        "operations": operations,
        "refactor_plan_sha256": _sha({
            "diagram_id": str(diagram_id),
            "identity": diagram["identity_sha256"],
            "relations": diagram["relation_sha256"],
            "operations": operations,
        }),
        "semantic_relation_mutation": False,
    }


def apply_legacy_diagram_refactor_atomic(
    path: Path,
    refactor_plan: dict,
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if not isinstance(refactor_plan, dict):
        raise ValueError("refactor_plan must be an object")
    diagram_id = str(refactor_plan.get("diagram_id") or "")
    lifecycle = build_diagram_lifecycle_map(path)
    diagram = next((d for d in lifecycle["diagrams"] if d["diagram_id"] == diagram_id), None)
    if diagram is None:
        raise ValueError(f"unknown managed diagram: {diagram_id}")
    if diagram["identity_sha256"] != str(refactor_plan.get("source_identity_sha256") or ""):
        raise ValueError("refactor plan source identity is stale")
    if diagram["relation_sha256"] != str(refactor_plan.get("source_relation_sha256") or ""):
        raise ValueError("refactor plan source relations are stale")
    operations = refactor_plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("refactor plan has no operations")
    allowed = {"apply_layout_policy", "apply_theme"}
    if any(not isinstance(op, dict) or str(op.get("op")) not in allowed for op in operations):
        raise ValueError("P3.32 refactor plan contains a non-meaning-preserving operation")

    transaction = apply_diagram_design_system_atomic(
        path,
        operations,
        expected_revision=expected_revision,
        current_revision=current_revision,
        validator=validator,
    )
    after = build_diagram_lifecycle_map(path)
    final = next(d for d in after["diagrams"] if d["diagram_id"] == diagram_id)
    if final["relation_sha256"] != diagram["relation_sha256"]:
        raise ValueError("legacy refactor changed managed semantic relations")
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_id": diagram_id,
        "operation_count": len(operations),
        "operations": operations,
        "design_system_diff": transaction,
        "relation_preserved": True,
        "relation_sha256": final["relation_sha256"],
        "identity_sha256": final["identity_sha256"],
        "validation": transaction.get("validation"),
    }
