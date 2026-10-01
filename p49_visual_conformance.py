from __future__ import annotations

import hashlib
import json
import math
from typing import Any

PHASE = "P4.9"
SCHEMA = "chatgpt-web-hwpx-mcp/visual-conformance/p4.9/v1"

ISSUE_ZERO_AREA = "ZERO_AREA_GEOMETRY"
ISSUE_NEGATIVE_OFFSET = "NEGATIVE_GEOMETRY_OFFSET"
ISSUE_VISUAL_GROUP_INCOMPLETE = "VISUAL_GROUP_INCOMPLETE"
ISSUE_LABEL_TARGET_MISSING = "LABEL_TARGET_MISSING"
ISSUE_VALUE_TARGET_MISSING = "VALUE_TARGET_MISSING"
ISSUE_DEGENERATE_KPI_CONTAINER = "DEGENERATE_KPI_CONTAINER"
ISSUE_KPI_CHILD_OUTSIDE_CONTAINER = "KPI_CHILD_OUTSIDE_CONTAINER"


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
