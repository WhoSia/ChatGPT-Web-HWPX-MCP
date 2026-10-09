from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from hwpx_mcp.document.p325_drawing_layer import build_drawing_layer_map

PHASE = "P4.9"
SCHEMA = "chatgpt-web-hwpx-mcp/visual-conformance/p4.9/v1"

ISSUE_ZERO_AREA = "ZERO_AREA_GEOMETRY"
ISSUE_NEGATIVE_OFFSET = "NEGATIVE_GEOMETRY_OFFSET"
ISSUE_VISUAL_GROUP_INCOMPLETE = "VISUAL_GROUP_INCOMPLETE"
ISSUE_LABEL_TARGET_MISSING = "LABEL_TARGET_MISSING"
ISSUE_VALUE_TARGET_MISSING = "VALUE_TARGET_MISSING"
ISSUE_DEGENERATE_KPI_CONTAINER = "DEGENERATE_KPI_CONTAINER"
ISSUE_KPI_CHILD_OUTSIDE_CONTAINER = "KPI_CHILD_OUTSIDE_CONTAINER"
ISSUE_MATERIALIZED_OBJECT_MISSING = "MATERIALIZED_OBJECT_MISSING"
ISSUE_MATERIALIZED_WRONG_KIND = "MATERIALIZED_WRONG_KIND"
ISSUE_MATERIALIZED_DEGENERATE = "MATERIALIZED_DEGENERATE_GEOMETRY"
ISSUE_MATERIALIZED_TEXT_MISMATCH = "MATERIALIZED_TEXT_MISMATCH"
ISSUE_UNEXPECTED_ROTATION = "UNEXPECTED_ROTATION"
ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER = "VISUAL_CHILD_OUTSIDE_CONTAINER"


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _finite_nonnegative(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0


def _positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _issue(code: str, component_id: str, detail: str, **extra: Any) -> dict:
    return {
        "code": code,
        "component_id": component_id,
        "detail": detail,
        **extra,
    }


def certify_bar_chart(plan: dict) -> dict:
    cid = str(plan.get("component_id") or "")
    width = int(plan.get("width") or 0)
    height = int(plan.get("height") or 0)
    rows = list(plan.get("rows") or [])
    issues: list[dict] = []
    groups: list[dict] = []

    if not _positive(width) or not _positive(height):
        issues.append(_issue(ISSUE_ZERO_AREA, cid, "chart width/height must be positive"))

    for row in rows:
        label = str(row.get("label") or "").strip()
        value = row.get("value")
        x = row.get("x")
        y = row.get("y")
        label_x = row.get("label_x")
        value_x = row.get("value_x")
        bar_width = row.get("bar_width")
        bar_height = row.get("bar_height")
        index = int(row.get("index") or 0)

        if not label:
            issues.append(_issue(ISSUE_LABEL_TARGET_MISSING, cid, "bar row has no label", row_index=index))
        if value is None:
            issues.append(_issue(ISSUE_VALUE_TARGET_MISSING, cid, "bar row has no value", row_index=index))
        if not _positive(bar_width) or not _positive(bar_height):
            issues.append(_issue(ISSUE_ZERO_AREA, cid, "bar geometry must be positive", row_index=index))
        for name, coordinate in {
            "x": x,
            "y": y,
            "label_x": label_x,
            "value_x": value_x,
        }.items():
            if not _finite_nonnegative(coordinate):
                issues.append(
                    _issue(
                        ISSUE_NEGATIVE_OFFSET,
                        cid,
                        f"{name} must be finite and non-negative",
                        row_index=index,
                        field=name,
                    )
                )

        expected_children = {
            "shape": _positive(bar_width) and _positive(bar_height),
            "label": bool(label),
            "value": value is not None,
        }

        label_width = max(2400, int(x or 0) - 400)
        text_height = int(bar_height or 0) + 900
        shape_right = int(x or 0) + int(bar_width or 0)
        label_right = int(label_x or 0) + label_width
        value_right = int(value_x or 0) + 5200
        shape_bottom = int(y or 0) + int(bar_height or 0)
        text_top = int(y or 0) - 250
        text_bottom = text_top + text_height
        container_bottom = int(plan.get("top_offset") or 0) + height
        if max(shape_right, label_right, value_right) > width or max(shape_bottom, text_bottom) > container_bottom:
            issues.append(
                _issue(
                    ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER,
                    cid,
                    "bar row child geometry exceeds declared visual container",
                    row_index=index,
                    chart_width=width,
                    chart_bottom=container_bottom,
                    child_right=max(shape_right, label_right, value_right),
                    child_bottom=max(shape_bottom, text_bottom),
                )
            )
        if not all(expected_children.values()):
            issues.append(
                _issue(
                    ISSUE_VISUAL_GROUP_INCOMPLETE,
                    cid,
                    "bar semantic group requires shape+label+value",
                    row_index=index,
                    children=expected_children,
                )
            )

        groups.append(
            {
                "group_id": f"{cid}:bar:{index}",
                "semantic_role": "bar_row",
                "row_index": index,
                "label": label,
                "value": value,
                "children": ["shape", "label", "value"],
                "bounds": {
                    "shape": [int(x or 0), int(y or 0), int(bar_width or 0), int(bar_height or 0)],
                    "label": [int(label_x or 0), int(y or 0)],
                    "value": [int(value_x or 0), int(y or 0)],
                },
            }
        )

    if not rows:
        issues.append(_issue(ISSUE_VISUAL_GROUP_INCOMPLETE, cid, "bar chart has no semantic rows"))

    certificate = {
        "phase": PHASE,
        "schema": SCHEMA,
        "component_id": cid,
        "type": "bar_chart",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "semantic_groups": groups,
        "expected_group_count": len(rows),
        "actual_group_count": len(groups),
    }
    certificate["certificate_sha256"] = _sha(certificate)
    return certificate


def certify_kpi_strip(plan: dict) -> dict:
    cid = str(plan.get("component_id") or "")
    width = int(plan.get("width") or 0)
    height = int(plan.get("height") or 0)
    items = list(plan.get("items") or [])
    issues: list[dict] = []

    if not _positive(width) or not _positive(height):
        issues.append(_issue(ISSUE_DEGENERATE_KPI_CONTAINER, cid, "KPI width/height must be positive"))

    gap = 700
    box_width = 0
    if items:
        box_width = max(4200, int((width - gap * (len(items) - 1)) / len(items)))
    total_width = box_width * len(items) + gap * max(0, len(items) - 1)

    if items and total_width > width:
        issues.append(
            _issue(
                ISSUE_KPI_CHILD_OUTSIDE_CONTAINER,
                cid,
                "KPI child boxes exceed declared strip width",
                strip_width=width,
                child_extent=total_width,
            )
        )

    groups = []
    for item in items:
        index = int(item.get("index") or 0)
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label:
            issues.append(_issue(ISSUE_LABEL_TARGET_MISSING, cid, "KPI item label missing", item_index=index))
        if not value:
            issues.append(_issue(ISSUE_VALUE_TARGET_MISSING, cid, "KPI item value missing", item_index=index))
        if not label or not value:
            issues.append(
                _issue(
                    ISSUE_VISUAL_GROUP_INCOMPLETE,
                    cid,
                    "KPI semantic group requires container+label+value",
                    item_index=index,
                )
            )
        x = index * (box_width + gap)
        value_height = max(1800, min(2800, height // 2 - 300))
        label_height = max(1500, min(2400, height // 2 - 400))
        value_bottom = 500 + value_height
        label_bottom = max(2600, height // 2) + label_height
        if max(value_bottom, label_bottom) > height:
            issues.append(
                _issue(
                    ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER,
                    cid,
                    "KPI label/value geometry exceeds card height",
                    item_index=index,
                    card_height=height,
                    child_bottom=max(value_bottom, label_bottom),
                )
            )
        groups.append(
            {
                "group_id": f"{cid}:kpi:{index}",
                "semantic_role": "kpi_card",
                "item_index": index,
                "label": label,
                "value": value,
                "children": ["container", "label", "value"],
                "bounds": [x, int(plan.get("top_offset") or 0), box_width, height],
            }
        )

    if not items:
        issues.append(_issue(ISSUE_VISUAL_GROUP_INCOMPLETE, cid, "KPI strip has no semantic items"))

    certificate = {
        "phase": PHASE,
        "schema": SCHEMA,
        "component_id": cid,
        "type": "kpi_strip",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "semantic_groups": groups,
        "strip_bounds": [0, int(plan.get("top_offset") or 0), width, height],
        "expected_group_count": len(items),
        "actual_group_count": len(groups),
    }
    certificate["certificate_sha256"] = _sha(certificate)
    return certificate


def certify_visual_plan(plan: dict) -> dict:
    kind = str(plan.get("type") or "")
    if kind == "bar_chart":
        return certify_bar_chart(plan)
    if kind == "kpi_strip":
        return certify_kpi_strip(plan)
    raise ValueError(f"unsupported visual plan type for P4.9 certificate: {kind}")


def certify_visual_plans(plans: list[dict]) -> dict:
    certificates = [certify_visual_plan(plan) for plan in plans]
    issues = [issue for cert in certificates for issue in cert["issues"]]
    result = {
        "phase": PHASE,
        "schema": SCHEMA,
        "status": "PASS" if not issues else "FAIL",
        "certificate_count": len(certificates),
        "certificates": certificates,
        "issues": issues,
        "authority": "STATIC_GEOMETRY_AND_SEMANTIC_GROUP_CERTIFICATE_NOT_NATIVE_RENDER_AUTHORITY",
    }
    result["visual_certificate_sha256"] = _sha(result)
    return result


def _find_materialized_object(mapped: dict, *, locator: str | None = None, shape_id: str | None = None) -> dict | None:
    objects = list(mapped.get("objects") or [])
    if locator:
        found = next((item for item in objects if str(item.get("locator") or "") == str(locator)), None)
        if found is not None:
            return found
    if shape_id:
        found = next(
            (
                item for item in objects
                if str(item.get("id") or item.get("instid") or "") == str(shape_id)
            ),
            None,
        )
        if found is not None:
            return found
    return None


def _audit_rect_object(
    component_id: str,
    role: str,
    obj: dict | None,
    issues: list[dict],
    *,
    expected_text: str | None = None,
) -> dict:
    if obj is None:
        issues.append(
            _issue(
                ISSUE_MATERIALIZED_OBJECT_MISSING,
                component_id,
                f"materialized object missing for {role}",
                role=role,
            )
        )
        return {"role": role, "status": "MISSING"}

    evidence = {
        "role": role,
        "status": "PASS",
        "locator": obj.get("locator"),
        "kind": obj.get("kind"),
        "width": obj.get("width"),
        "height": obj.get("height"),
        "position": obj.get("position"),
        "rotation": obj.get("rotation"),
        "text": obj.get("text"),
    }
    if obj.get("kind") != "rect":
        issues.append(
            _issue(
                ISSUE_MATERIALIZED_WRONG_KIND,
                component_id,
                f"{role} materialized as {obj.get('kind')}, expected rect",
                role=role,
                locator=obj.get("locator"),
            )
        )
        evidence["status"] = "FAIL"
    if not _positive(obj.get("width")) or not _positive(obj.get("height")):
        issues.append(
            _issue(
                ISSUE_MATERIALIZED_DEGENERATE,
                component_id,
                f"{role} width/height must remain positive after materialization",
                role=role,
                locator=obj.get("locator"),
                width=obj.get("width"),
                height=obj.get("height"),
            )
        )
        evidence["status"] = "FAIL"

    rotation = obj.get("rotation") or {}
    angle = int(rotation.get("angle", "0") or 0) if isinstance(rotation, dict) else 0
    if angle != 0:
        issues.append(
            _issue(
                ISSUE_UNEXPECTED_ROTATION,
                component_id,
                f"{role} unexpectedly rotated",
                role=role,
                locator=obj.get("locator"),
                angle=angle,
            )
        )
        evidence["status"] = "FAIL"

    if expected_text is not None:
        actual = str(obj.get("text") or "")
        if expected_text not in actual:
            issues.append(
                _issue(
                    ISSUE_MATERIALIZED_TEXT_MISMATCH,
                    component_id,
                    f"{role} text does not preserve semantic payload",
                    role=role,
                    locator=obj.get("locator"),
                    expected_text=expected_text,
                    actual_text=actual,
                )
            )
            evidence["status"] = "FAIL"
    return evidence


def audit_materialized_visuals(path: Path, receipts: list[dict]) -> dict:
    mapped = build_drawing_layer_map(path)
    issues: list[dict] = []
    components = []

    for component in receipts:
        cid = str(component.get("component_id") or "")
        kind = str(component.get("type") or "")
        group_evidence = []
        if kind == "bar_chart":
            for row in component.get("receipts") or []:
                bar_info = row.get("bar") or {}
                bar = _find_materialized_object(mapped, locator=str(bar_info.get("locator") or ""))
                label_info = row.get("label_box") or {}
                value_info = row.get("value_box") or {}
                label = _find_materialized_object(mapped, shape_id=str(label_info.get("shape_id") or ""))
                value = _find_materialized_object(mapped, shape_id=str(value_info.get("shape_id") or ""))
                group_evidence.append({
                    "semantic_group_id": row.get("semantic_group_id"),
                    "objects": [
                        _audit_rect_object(cid, "shape", bar, issues),
                        _audit_rect_object(cid, "label", label, issues, expected_text=str(row.get("label") or "")),
                        _audit_rect_object(cid, "value", value, issues, expected_text=f"{row.get('value'):g}"),
                    ],
                })
        elif kind == "kpi_strip":
            for item in component.get("receipts") or []:
                container_info = item.get("container") or {}
                container = _find_materialized_object(mapped, locator=str(container_info.get("locator") or ""))
                label_info = item.get("label_box") or {}
                value_info = item.get("value_box") or {}
                label = _find_materialized_object(mapped, shape_id=str(label_info.get("shape_id") or ""))
                value = _find_materialized_object(mapped, shape_id=str(value_info.get("shape_id") or ""))
                group_evidence.append({
                    "semantic_group_id": item.get("semantic_group_id"),
                    "objects": [
                        _audit_rect_object(cid, "container", container, issues),
                        _audit_rect_object(cid, "label", label, issues, expected_text=str(item.get("label") or "")),
                        _audit_rect_object(cid, "value", value, issues, expected_text=str(item.get("value") or "")),
                    ],
                })
        else:
            issues.append(_issue(ISSUE_VISUAL_GROUP_INCOMPLETE, cid, f"unsupported materialized visual type: {kind}"))

        components.append({
            "component_id": cid,
            "type": kind,
            "semantic_groups": group_evidence,
        })

    result = {
        "phase": PHASE,
        "schema": SCHEMA,
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "components": components,
        "drawing_count": mapped.get("drawing_count"),
        "drawing_structure_sha256": mapped.get("drawing_structure_sha256"),
        "drawing_geometry_sha256": mapped.get("drawing_geometry_sha256"),
        "authority": "POST_MATERIALIZATION_STRUCTURAL_AUDIT_NOT_NATIVE_RENDER_AUTHORITY",
    }
    result["materialized_visual_audit_sha256"] = _sha(result)
    return result
