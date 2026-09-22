from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from p330_diagram_design_system import (
    THEMES,
    LAYOUT_POLICIES,
    build_diagram_design_system_map,
    apply_diagram_design_system_atomic,
)

SCHEMA = "chatgpt-web-hwpx-mcp/diagram-quality-assurance/p3.31/v1"
AUTHORITY = "STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY"

PROFILES = {
    "baseline": {
        "require_nonempty_labels": True,
        "max_label_chars": 80,
        "require_weakly_connected": True,
        "require_acyclic": False,
        "require_single_source": False,
        "require_single_sink": False,
        "max_in_degree": 32,
        "max_out_degree": 32,
        "min_center_spacing": 0,
    },
    "flow": {
        "require_nonempty_labels": True,
        "max_label_chars": 64,
        "require_weakly_connected": True,
        "require_acyclic": True,
        "require_single_source": True,
        "require_single_sink": True,
        "max_in_degree": 8,
        "max_out_degree": 8,
        "min_center_spacing": 5000,
    },
    "presentation": {
        "require_nonempty_labels": True,
        "max_label_chars": 48,
        "require_weakly_connected": True,
        "require_acyclic": False,
        "require_single_source": False,
        "require_single_sink": False,
        "max_in_degree": 8,
        "max_out_degree": 8,
        "min_center_spacing": 6500,
    },
}

DEFERRED = {
    "pixel_level_overlap": (
        "EVIDENCE_GATE_CLOSED: P3.31 checks native object bounding boxes only; "
        "rendered glyph/pixel overlap requires Hancom-native capture."
    ),
    "color_contrast_accessibility": (
        "EVIDENCE_GATE_CLOSED: P3.31 does not infer rendered text/background contrast "
        "from incomplete shape-text run styling."
    ),
    "font_legibility": (
        "EVIDENCE_GATE_CLOSED: font rendering and legibility require native-render evidence."
    ),
    "aesthetic_quality_score": (
        "EVIDENCE_GATE_CLOSED: P3.31 does not assign subjective visual-quality scores."
    ),
    "semantic_graph_repair": (
        "EVIDENCE_GATE_CLOSED: automatic node/edge addition or deletion can change meaning; "
        "P3.31 reports such findings but does not auto-repair them."
    ),
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def diagram_quality_assurance_contract() -> dict:
    return {
        "phase": "P3.31",
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "profiles": sorted(PROFILES),
        "checks": [
            "label_presence",
            "label_length",
            "weak_connectivity",
            "acyclicity",
            "source_sink_cardinality",
            "degree_bounds",
            "theme_token_conformance",
            "native_bbox_overlap",
            "minimum_center_spacing",
        ],
        "finding_levels": ["ERROR", "WARN"],
        "repair_semantics": (
            "SAFE_STRUCTURAL_ONLY: executable repairs are restricted to P3.30 theme "
            "materialization and collision-safe layout policy application. Semantic graph "
            "changes are advisory only."
        ),
        "admitted_operations": [
            "validate_diagram",
            "plan_diagram_repairs",
            "apply_diagram_repairs",
        ],
        "deferred_operations": dict(DEFERRED),
    }


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _xywh(node: dict) -> tuple[int, int, int, int]:
    position = node.get("position") or {}
    x = _int(position.get("horzOffset"))
    y = _int(position.get("vertOffset"))
    return x, y, _int(node.get("width")), _int(node.get("height"))


def _center(node: dict) -> tuple[int, int]:
    x, y, w, h = _xywh(node)
    return x + w // 2, y + h // 2


def _overlap(a: dict, b: dict) -> bool:
    ax, ay, aw, ah = _xywh(a)
    bx, by, bw, bh = _xywh(b)
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _distance_sq(a: dict, b: dict) -> int:
    ax, ay = _center(a)
    bx, by = _center(b)
    return (ax - bx) ** 2 + (ay - by) ** 2


def _graph(diagram: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    ids = {node["node_id"] for node in diagram["nodes"]}
    outgoing = {nid: set() for nid in ids}
    incoming = {nid: set() for nid in ids}
    for edge in diagram["edges"]:
        source, target = edge["source"], edge["target"]
        if source in ids and target in ids:
            outgoing[source].add(target)
            incoming[target].add(source)
    return outgoing, incoming


def _weak_components(diagram: dict) -> list[list[str]]:
    outgoing, incoming = _graph(diagram)
    unseen = set(outgoing)
    components: list[list[str]] = []
    while unseen:
        root = sorted(unseen)[0]
        stack = [root]
        seen = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(sorted((outgoing[current] | incoming[current]) - seen))
        components.append(sorted(seen))
        unseen -= seen
    return components


def _has_cycle(diagram: dict) -> bool:
    outgoing, _incoming = _graph(diagram)
    state = {node: 0 for node in outgoing}

    def visit(node: str) -> bool:
        if state[node] == 1:
            return True
        if state[node] == 2:
            return False
        state[node] = 1
        for nxt in sorted(outgoing[node]):
            if visit(nxt):
                return True
        state[node] = 2
        return False

    return any(visit(node) for node in sorted(outgoing) if state[node] == 0)


def _style_matches(actual: dict | None, expected: dict) -> list[dict]:
    actual = actual or {}
    mismatches = []
    mapping = {
        "fill_color": "fill_color",
        "stroke_color": "stroke_color",
        "stroke_width": "stroke_width",
        "stroke_style": "stroke_style",
        "head_style": "head_style",
    }
    for token, key in mapping.items():
        if token not in expected:
            continue
        observed = actual.get(key)
        target = expected[token]
        if str(observed) != str(target):
            mismatches.append({"token": token, "expected": target, "observed": observed})
    return mismatches


def _merged_constraints(profile: object, constraints: dict | None) -> tuple[str, dict]:
    name = str(profile or "baseline").lower()
    if name not in PROFILES:
        raise ValueError(f"unknown QA profile: {name}")
    merged = dict(PROFILES[name])
    constraints = constraints or {}
    if not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    allowed = set(merged)
    extra = set(constraints) - allowed
    if extra:
        raise ValueError(f"unsupported graph/readability constraints: {sorted(extra)}")
    merged.update(constraints)
    for key in ("max_label_chars", "max_in_degree", "max_out_degree", "min_center_spacing"):
        merged[key] = int(merged[key])
        if merged[key] < 0:
            raise ValueError(f"{key} must be non-negative")
    return name, merged


def _finding(level: str, code: str, message: str, **evidence: Any) -> dict:
    return {
        "level": level,
        "code": code,
        "message": message,
        "evidence": evidence,
    }


def validate_diagram_quality(
    path: Path,
    diagram_id: str,
    *,
    profile: str = "baseline",
    constraints: dict | None = None,
    expected_theme: str | None = None,
) -> dict:
    design = build_diagram_design_system_map(path)
    diagram = next((d for d in design["diagrams"] if d["diagram_id"] == str(diagram_id)), None)
    if diagram is None:
        raise ValueError(f"unknown managed diagram: {diagram_id}")
    profile_name, rules = _merged_constraints(profile, constraints)
    if expected_theme is not None:
        expected_theme = str(expected_theme).lower()
        if expected_theme not in THEMES:
            raise ValueError(f"unknown expected_theme: {expected_theme}")

    findings = []
    outgoing, incoming = _graph(diagram)

    if rules["require_nonempty_labels"]:
        for node in diagram["nodes"]:
            if not str(node.get("label") or "").strip():
                findings.append(_finding(
                    "ERROR", "EMPTY_LABEL", "Managed node has no non-whitespace label.",
                    node_id=node["node_id"],
                ))
    for node in diagram["nodes"]:
        chars = len(str(node.get("label") or ""))
        if rules["max_label_chars"] and chars > rules["max_label_chars"]:
            findings.append(_finding(
                "WARN", "LABEL_TOO_LONG", "Managed node label exceeds the structural length budget.",
                node_id=node["node_id"], characters=chars, maximum=rules["max_label_chars"],
            ))

    components = _weak_components(diagram)
    if rules["require_weakly_connected"] and len(components) > 1:
        findings.append(_finding(
            "ERROR", "DISCONNECTED_GRAPH", "Managed diagram has more than one weakly connected component.",
            components=components,
        ))

    isolated = [
        node for node in sorted(outgoing)
        if not outgoing[node] and not incoming[node] and len(outgoing) > 1
    ]
    for node_id in isolated:
        findings.append(_finding(
            "WARN", "ISOLATED_NODE", "Managed node has no incoming or outgoing managed relation.",
            node_id=node_id,
        ))

    cycle = _has_cycle(diagram)
    if rules["require_acyclic"] and cycle:
        findings.append(_finding(
            "ERROR", "CYCLE_PRESENT", "QA profile requires an acyclic managed graph.",
        ))

    sources = sorted(node for node in outgoing if not incoming[node])
    sinks = sorted(node for node in outgoing if not outgoing[node])
    if rules["require_single_source"] and len(sources) != 1:
        findings.append(_finding(
            "ERROR", "SOURCE_CARDINALITY", "QA profile requires exactly one source node.",
            sources=sources, count=len(sources),
        ))
    if rules["require_single_sink"] and len(sinks) != 1:
        findings.append(_finding(
            "ERROR", "SINK_CARDINALITY", "QA profile requires exactly one sink node.",
            sinks=sinks, count=len(sinks),
        ))

    for node_id in sorted(outgoing):
        if len(incoming[node_id]) > rules["max_in_degree"]:
            findings.append(_finding(
                "ERROR", "MAX_IN_DEGREE", "Managed node exceeds configured incoming-degree bound.",
                node_id=node_id, observed=len(incoming[node_id]), maximum=rules["max_in_degree"],
            ))
        if len(outgoing[node_id]) > rules["max_out_degree"]:
            findings.append(_finding(
                "ERROR", "MAX_OUT_DEGREE", "Managed node exceeds configured outgoing-degree bound.",
                node_id=node_id, observed=len(outgoing[node_id]), maximum=rules["max_out_degree"],
            ))

    nodes = sorted(diagram["nodes"], key=lambda x: x["node_id"])
    for i, left in enumerate(nodes):
        for right in nodes[i + 1:]:
            if _overlap(left, right):
                findings.append(_finding(
                    "ERROR", "NATIVE_BBOX_OVERLAP", "Two managed node native bounding boxes overlap.",
                    left=left["node_id"], right=right["node_id"],
                ))
            spacing = rules["min_center_spacing"]
            if spacing > 0 and _distance_sq(left, right) < spacing ** 2:
                findings.append(_finding(
                    "WARN", "CENTER_SPACING_BELOW_MINIMUM", "Managed node centers are closer than the configured structural spacing.",
                    left=left["node_id"], right=right["node_id"], minimum=spacing,
                ))

    if expected_theme is not None:
        theme = THEMES[expected_theme]
        for node in diagram["nodes"]:
            role = node["semantic_role"]
            mismatches = _style_matches(node.get("effective_style"), theme["nodes"][role])
            if mismatches:
                findings.append(_finding(
                    "WARN", "NODE_THEME_MISMATCH", "Managed node native style differs from expected theme tokens.",
                    node_id=node["node_id"], role=role, theme=expected_theme, mismatches=mismatches,
                ))
        for edge in diagram["edges"]:
            role = edge["semantic_role"]
            mismatches = _style_matches(edge.get("effective_style"), theme["edges"][role])
            if mismatches:
                findings.append(_finding(
                    "WARN", "EDGE_THEME_MISMATCH", "Managed edge native style differs from expected theme tokens.",
                    edge_id=edge["edge_id"], role=role, theme=expected_theme, mismatches=mismatches,
                ))

    findings.sort(key=lambda x: (0 if x["level"] == "ERROR" else 1, x["code"], json.dumps(x["evidence"], sort_keys=True)))
    errors = sum(x["level"] == "ERROR" for x in findings)
    warnings = sum(x["level"] == "WARN" for x in findings)
    seed = {
        "diagram_id": diagram["diagram_id"],
        "profile": profile_name,
        "constraints": rules,
        "expected_theme": expected_theme,
        "findings": findings,
        "identity": design["diagram_identity_sha256"],
        "relations": design["diagram_relation_sha256"],
        "style": design["semantic_style_sha256"],
    }
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_id": diagram["diagram_id"],
        "profile": profile_name,
        "constraints": rules,
        "expected_theme": expected_theme,
        "passed": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "finding_count": len(findings),
        "findings": findings,
        "graph_summary": {
            "node_count": diagram["node_count"],
            "edge_count": diagram["edge_count"],
            "sources": sources,
            "sinks": sinks,
            "weak_component_count": len(components),
            "has_cycle": cycle,
        },
        "qa_sha256": _sha(seed),
        "diagram_identity_sha256": design["diagram_identity_sha256"],
        "diagram_relation_sha256": design["diagram_relation_sha256"],
        "semantic_style_sha256": design["semantic_style_sha256"],
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


def build_diagram_quality_map(
    path: Path,
    *,
    profile: str = "baseline",
    constraints: dict | None = None,
    expected_theme: str | None = None,
) -> dict:
    design = build_diagram_design_system_map(path)
    reports = [
        validate_diagram_quality(
            path,
            diagram["diagram_id"],
            profile=profile,
            constraints=constraints,
            expected_theme=expected_theme,
        )
        for diagram in design["diagrams"]
    ]
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_count": len(reports),
        "passed": all(report["passed"] for report in reports),
        "error_count": sum(report["error_count"] for report in reports),
        "warning_count": sum(report["warning_count"] for report in reports),
        "reports": reports,
        "quality_sha256": _sha([report["qa_sha256"] for report in reports]),
        "contract": diagram_quality_assurance_contract(),
    }


def plan_diagram_repairs(
    path: Path,
    diagram_id: str,
    *,
    profile: str = "baseline",
    constraints: dict | None = None,
    expected_theme: str | None = None,
    repair_theme: str | None = None,
    repair_layout_policy: str | None = None,
    layout: str = "LEFT_TO_RIGHT",
) -> dict:
    report = validate_diagram_quality(
        path,
        diagram_id,
        profile=profile,
        constraints=constraints,
        expected_theme=expected_theme,
    )
    operations = []
    reasons = []
    codes = {finding["code"] for finding in report["findings"]}

    theme_name = str(repair_theme or expected_theme or "").lower()
    if theme_name:
        if theme_name not in THEMES:
            raise ValueError(f"unknown repair_theme: {theme_name}")
        if {"NODE_THEME_MISMATCH", "EDGE_THEME_MISMATCH"} & codes:
            operations.append({"op": "apply_theme", "diagram_id": diagram_id, "theme": theme_name})
            reasons.append("materialize expected semantic-role theme tokens")

    if repair_layout_policy is not None:
        policy = str(repair_layout_policy).lower()
        if policy not in LAYOUT_POLICIES:
            raise ValueError(f"unknown repair_layout_policy: {policy}")
        if {"NATIVE_BBOX_OVERLAP", "CENTER_SPACING_BELOW_MINIMUM"} & codes:
            operations.append({
                "op": "apply_layout_policy",
                "diagram_id": diagram_id,
                "policy": policy,
                "layout": str(layout).upper(),
            })
            reasons.append("apply collision-safe deterministic spacing policy")

    advisory = [
        finding for finding in report["findings"]
        if finding["code"] not in {
            "NODE_THEME_MISMATCH",
            "EDGE_THEME_MISMATCH",
            "NATIVE_BBOX_OVERLAP",
            "CENTER_SPACING_BELOW_MINIMUM",
        }
    ]
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "diagram_id": diagram_id,
        "source_qa_sha256": report["qa_sha256"],
        "operation_count": len(operations),
        "operations": operations,
        "reasons": reasons,
        "advisory_findings": advisory,
        "fully_auto_repairable": bool(report["findings"]) and not advisory,
        "no_op": not operations,
        "repair_plan_sha256": _sha({
            "diagram_id": diagram_id,
            "source": report["qa_sha256"],
            "operations": operations,
            "advisory": advisory,
        }),
    }


def apply_diagram_repairs_atomic(
    path: Path,
    repair_plan: dict,
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not isinstance(repair_plan, dict):
        raise ValueError("repair_plan must be an object")
    operations = repair_plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("repair_plan has no executable operations")
    if len(operations) > 16:
        raise ValueError("P3.31 repair plan exceeds 16 operations")
    allowed = {"apply_theme", "apply_layout_policy"}
    if any(str(op.get("op")) not in allowed for op in operations if isinstance(op, dict)):
        raise ValueError("P3.31 repair plan contains a non-safe operation")

    diagram_id = str(repair_plan.get("diagram_id") or operations[0].get("diagram_id") or "")
    if not diagram_id:
        raise ValueError("repair_plan requires diagram_id")
    source_hash = str(repair_plan.get("source_qa_sha256") or "")
    if source_hash:
        baseline = validate_diagram_quality(
            path,
            diagram_id,
            profile=str(repair_plan.get("profile", "baseline")),
            constraints=repair_plan.get("constraints"),
            expected_theme=repair_plan.get("expected_theme"),
        )
        if baseline["qa_sha256"] != source_hash:
            raise ValueError("repair_plan source QA receipt is stale")

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p331-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    validation = None
    try:
        transaction = apply_diagram_design_system_atomic(
            candidate,
            operations,
            expected_revision=current_revision,
            current_revision=current_revision,
            validator=validator,
        )
        if validator is not None:
            validation = transaction["validation"]
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "operation_count": len(operations),
        "operations": operations,
        "design_system_diff": transaction,
        "validation": validation,
        "authority": AUTHORITY,
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
