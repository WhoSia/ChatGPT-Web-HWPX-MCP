from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from p312_render_harness import validate_capture
from p340_feedback_loop import diagnose_document_with_render

SCHEMA = "chatgpt-web-hwpx-mcp/p3.41/page-composition/v1"
PPM = 1_000_000

_THRESHOLDS: dict[str, dict[str, int]] = {
    "POLISHED_REPORT": {
        "max_lines": 52,
        "max_vertical_span_ppm": 900_000,
        "max_line_area_ppm": 190_000,
        "max_internal_gap_ppm": 210_000,
        "max_balance_delta_ppm": 520_000,
    },
    "RESEARCH_BRIEF": {
        "max_lines": 48,
        "max_vertical_span_ppm": 885_000,
        "max_line_area_ppm": 180_000,
        "max_internal_gap_ppm": 190_000,
        "max_balance_delta_ppm": 500_000,
    },
    "INSTITUTIONAL_REPORT": {
        "max_lines": 54,
        "max_vertical_span_ppm": 905_000,
        "max_line_area_ppm": 200_000,
        "max_internal_gap_ppm": 220_000,
        "max_balance_delta_ppm": 540_000,
    },
    "ACADEMIC_REPORT": {
        "max_lines": 58,
        "max_vertical_span_ppm": 920_000,
        "max_line_area_ppm": 220_000,
        "max_internal_gap_ppm": 230_000,
        "max_balance_delta_ppm": 560_000,
    },
    "FORM": {
        "max_lines": 60,
        "max_vertical_span_ppm": 930_000,
        "max_line_area_ppm": 240_000,
        "max_internal_gap_ppm": 260_000,
        "max_balance_delta_ppm": 620_000,
    },
}

_SEVERITY = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _ppm(numerator: int | float, denominator: int | float) -> int:
    denominator = float(denominator)
    if denominator <= 0:
        return 0
    return int((float(numerator) * PPM / denominator) + 0.5)


def _thresholds(archetype: str) -> dict[str, int]:
    key = str(archetype or "POLISHED_REPORT").strip().upper()
    if key not in _THRESHOLDS:
        raise ValueError(f"unsupported composition archetype: {archetype}")
    return dict(_THRESHOLDS[key])


def page_composition_contract() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "P3.41",
        "purpose": "PAGE_LEVEL_COMPOSITION_GRAMMAR_WITHOUT_BEAUTY_SCORING",
        "inherits": [
            "P3.39_DESIGN_CONSTITUTION",
            "P3.40_RENDER_DIAGNOSE_REPAIR_RERENDER",
        ],
        "primitive_metrics": [
            "line_count",
            "vertical_span_ppm",
            "line_area_ppm",
            "largest_internal_gap_ppm",
            "top_bottom_balance_delta_ppm",
            "top_margin_ppm",
            "bottom_margin_ppm",
        ],
        "finding_families": [
            "PAGE_COMPOSITION_OVERFULL",
            "PAGE_RHYTHM_LARGE_WHITESPACE_BAND",
            "PAGE_TOP_HEAVY_COMPOSITION",
            "PAGE_BOTTOM_HEAVY_COMPOSITION",
            "PAGE_BOUNDARY_SINGLE_LINE_PARAGRAPH",
            "DOCUMENT_PAGE_DENSITY_VARIANCE_HIGH",
        ],
        "policy_boundary": "AGENT_PLAN_ONLY_UNTIL_LOCATOR_TO_PAGE_BREAK_MUTATION_IS_PROVEN",
        "polyglot": {
            "python": "capture normalization, research diagnostics, benchmark orchestration",
            "rust": "deterministic page-geometry decision kernel",
            "typescript": "product/client contract and threshold schema",
            "powershell": "Windows Hancom world-contact bridge",
            "rule": "POLYGLOT_BY_COMPARATIVE_ADVANTAGE_NOT_LANGUAGE_COUNT",
        },
        "archetype_thresholds": _THRESHOLDS,
        "non_claims": [
            "No scalar beauty score.",
            "No page-break mutation from raster evidence alone.",
            "Whitespace signals are review evidence and may be intentional.",
            "Static composition policy is not native-render improvement authority.",
        ],
    }


def _primitive_from_page(page: dict) -> dict:
    width = int(page["width_px"])
    height = int(page["height_px"])
    lines = list(page.get("line_boxes") or [])
    if not lines:
        return {
            "page_index": int(page["page_index"]),
            "width_px": width,
            "height_px": height,
            "line_count": 0,
            "left_px": 0,
            "right_px": 0,
            "top_px": 0,
            "bottom_px": 0,
            "line_area_px2": 0,
            "largest_internal_gap_px": height,
            "top_area_px2": 0,
            "bottom_area_px2": 0,
            "paragraph_line_counts": {},
            "first_paragraph_locator": "",
            "last_paragraph_locator": "",
            "raster_sha256": str(page.get("raster_sha256") or ""),
        }

    ordered = sorted(lines, key=lambda x: (float(x["y"]), float(x["x"])))
    left = int(round(min(float(x["x"]) for x in ordered)))
    right = int(round(max(float(x["x"]) + float(x["width"]) for x in ordered)))
    top = int(round(min(float(x["y"]) for x in ordered)))
    bottom = int(round(max(float(x["y"]) + float(x["height"]) for x in ordered)))
    line_area = int(round(sum(float(x["width"]) * float(x["height"]) for x in ordered)))

    largest_gap = 0
    for current, nxt in zip(ordered, ordered[1:]):
        current_bottom = float(current["y"]) + float(current["height"])
        gap = max(0.0, float(nxt["y"]) - current_bottom)
        largest_gap = max(largest_gap, int(round(gap)))

    top_area = 0
    bottom_area = 0
    counts: dict[str, int] = {}
    for line in ordered:
        area = int(round(float(line["width"]) * float(line["height"])))
        center_y = float(line["y"]) + float(line["height"]) / 2.0
        if center_y < height / 2.0:
            top_area += area
        else:
            bottom_area += area
        locator = str(line.get("paragraph_locator") or "")
        if locator:
            counts[locator] = counts.get(locator, 0) + 1

    first_locator = str(ordered[0].get("paragraph_locator") or "")
    last_locator = str(ordered[-1].get("paragraph_locator") or "")
    return {
        "page_index": int(page["page_index"]),
        "width_px": width,
        "height_px": height,
        "line_count": len(ordered),
        "left_px": left,
        "right_px": right,
        "top_px": top,
        "bottom_px": bottom,
        "line_area_px2": line_area,
        "largest_internal_gap_px": largest_gap,
        "top_area_px2": top_area,
        "bottom_area_px2": bottom_area,
        "paragraph_line_counts": counts,
        "first_paragraph_locator": first_locator,
        "last_paragraph_locator": last_locator,
        "raster_sha256": str(page.get("raster_sha256") or ""),
    }


def analyze_page_primitive(primitive: dict, archetype: str = "POLISHED_REPORT") -> dict:
    t = _thresholds(archetype)
    width = int(primitive["width_px"])
    height = int(primitive["height_px"])
    line_count = int(primitive["line_count"])
    left = int(primitive["left_px"])
    right = int(primitive["right_px"])
    top = int(primitive["top_px"])
    bottom = int(primitive["bottom_px"])
    line_area = int(primitive["line_area_px2"])
    largest_gap = int(primitive["largest_internal_gap_px"])
    top_area = int(primitive["top_area_px2"])
    bottom_area = int(primitive["bottom_area_px2"])

    vertical_span = max(0, bottom - top)
    total_half_area = top_area + bottom_area
    metrics = {
        "line_count": line_count,
        "top_margin_ppm": _ppm(top, height) if line_count else PPM,
        "bottom_margin_ppm": _ppm(max(0, height - bottom), height) if line_count else PPM,
        "left_margin_ppm": _ppm(left, width) if line_count else PPM,
        "right_margin_ppm": _ppm(max(0, width - right), width) if line_count else PPM,
        "vertical_span_ppm": _ppm(vertical_span, height) if line_count else 0,
        "line_area_ppm": _ppm(line_area, width * height) if line_count else 0,
        "largest_internal_gap_ppm": _ppm(largest_gap, height) if line_count else PPM,
        "top_bottom_balance_delta_ppm": (
            _ppm(abs(top_area - bottom_area), total_half_area) if total_half_area else 0
        ),
    }

    findings: list[dict] = []
    overfull = (
        line_count >= t["max_lines"]
        or metrics["vertical_span_ppm"] >= t["max_vertical_span_ppm"]
        or metrics["line_area_ppm"] >= t["max_line_area_ppm"]
    )
    if overfull:
        severe = (
            line_count >= t["max_lines"] + 10
            or metrics["vertical_span_ppm"] >= t["max_vertical_span_ppm"] + 50_000
            or metrics["line_area_ppm"] >= t["max_line_area_ppm"] + 60_000
        )
        findings.append({
            "code": "PAGE_COMPOSITION_OVERFULL",
            "severity": "HIGH" if severe else "MEDIUM",
            "principle": "DENSITY_BUDGET",
        })

    if line_count >= 8 and metrics["largest_internal_gap_ppm"] >= t["max_internal_gap_ppm"]:
        findings.append({
            "code": "PAGE_RHYTHM_LARGE_WHITESPACE_BAND",
            "severity": "LOW",
            "principle": "READING_GEOMETRY",
        })

    if (
        line_count >= 8
        and metrics["vertical_span_ppm"] >= 500_000
        and metrics["top_bottom_balance_delta_ppm"] >= t["max_balance_delta_ppm"]
    ):
        code = "PAGE_TOP_HEAVY_COMPOSITION" if top_area > bottom_area else "PAGE_BOTTOM_HEAVY_COMPOSITION"
        findings.append({
            "code": code,
            "severity": "LOW",
            "principle": "NARRATIVE_VISUAL_AGREEMENT",
        })

    return {
        "metrics": metrics,
        "findings": findings,
        "finding_codes": [x["code"] for x in findings],
    }


def _renderer_authority(renderer: dict | None, normalized: dict) -> tuple[str, bool]:
    renderer = dict(renderer or {})
    raster_hashes = [str(p.get("raster_sha256") or "") for p in normalized.get("pages", [])]
    valid = bool(
        renderer.get("hancom_native")
        and str(renderer.get("executable_sha256") or "").strip()
        and int(renderer.get("dpi") or 0) > 0
        and raster_hashes
        and all(len(x) == 64 for x in raster_hashes)
    )
    return ("HANCOM_NATIVE_RENDER_EVIDENCE" if valid else "EXTERNAL_RENDER_OBSERVATION", valid)


def diagnose_page_composition(
    capture: dict,
    *,
    renderer: dict | None = None,
    archetype: str = "POLISHED_REPORT",
) -> dict:
    normalized = validate_capture(capture)
    authority, world_contact = _renderer_authority(renderer, normalized)
    primitives = [_primitive_from_page(page) for page in normalized["pages"]]
    page_metrics: list[dict] = []
    findings: list[dict] = []

    for primitive in primitives:
        decision = analyze_page_primitive(primitive, archetype)
        page_index = int(primitive["page_index"])
        metric = {
            "page_index": page_index,
            "raster_sha256": primitive.get("raster_sha256"),
            **decision["metrics"],
        }
        page_metrics.append(metric)
        for finding in decision["findings"]:
            findings.append({
                **finding,
                "scope": f"PAGE_{page_index + 1}",
                "evidence": metric,
                "recommendation": {
                    "PAGE_COMPOSITION_OVERFULL": "Rebudget blocks or page breaks before shrinking type.",
                    "PAGE_RHYTHM_LARGE_WHITESPACE_BAND": "Review section/block spacing and intentional page-break placement.",
                    "PAGE_TOP_HEAVY_COMPOSITION": "Review whether the page transition leaves an unnecessarily weak lower half.",
                    "PAGE_BOTTOM_HEAVY_COMPOSITION": "Review whether preceding content or a section break should move earlier.",
                }[finding["code"]],
            })

    for left, right in zip(primitives, primitives[1:]):
        locator = str(left.get("last_paragraph_locator") or "")
        if not locator or locator != str(right.get("first_paragraph_locator") or ""):
            continue
        left_count = int((left.get("paragraph_line_counts") or {}).get(locator, 0))
        right_count = int((right.get("paragraph_line_counts") or {}).get(locator, 0))
        if min(left_count, right_count) <= 1:
            findings.append({
                "code": "PAGE_BOUNDARY_SINGLE_LINE_PARAGRAPH",
                "severity": "MEDIUM",
                "scope": f"PAGE_{int(left['page_index']) + 1}_TO_{int(right['page_index']) + 1}",
                "principle": "READING_GEOMETRY",
                "evidence": {
                    "paragraph_locator": locator,
                    "lines_before_break": left_count,
                    "lines_after_break": right_count,
                },
                "recommendation": "Review keep-with-next/keep-together or local repagination; do not mutate from raster evidence alone.",
            })

    densities = [m["line_area_ppm"] for m in page_metrics if m["line_area_ppm"] > 0]
    if len(densities) >= 3:
        med = int(statistics.median(densities))
        maximum = max(densities)
        if med > 0 and maximum * 100 >= med * 175:
            findings.append({
                "code": "DOCUMENT_PAGE_DENSITY_VARIANCE_HIGH",
                "severity": "LOW",
                "scope": "DOCUMENT",
                "principle": "DENSITY_BUDGET",
                "evidence": {"median_line_area_ppm": med, "max_line_area_ppm": maximum},
                "recommendation": "Review whether one page is carrying disproportionate information density relative to the document.",
            })

    max_severity = max((_SEVERITY[x["severity"]] for x in findings), default=0)
    verdict = "REVIEW_REQUIRED" if max_severity >= _SEVERITY["HIGH"] else ("PASS_WITH_WARNINGS" if findings else "PASS")
    result = {
        "schema": SCHEMA,
        "phase": "P3.41",
        "archetype": str(archetype).upper(),
        "authority": authority,
        "world_contact_valid": world_contact,
        "capture_sha256": normalized["capture_sha256"],
        "page_count": normalized["page_count"],
        "page_metrics": page_metrics,
        "findings": findings,
        "finding_count": len(findings),
        "verdict": verdict,
    }
    result["composition_diagnostic_sha256"] = _sha(result)
    return result


def diagnose_document_page_composition(
    path: Path | str,
    *,
    capture: dict,
    renderer: dict | None = None,
    archetype: str = "POLISHED_REPORT",
    mode: str = "POLISHED_REPORT",
    human_feedback: list[dict] | None = None,
) -> dict:
    base = diagnose_document_with_render(
        Path(path),
        mode=mode,
        capture=capture,
        renderer=renderer,
        human_feedback=human_feedback,
    )
    composition = diagnose_page_composition(capture, renderer=renderer, archetype=archetype)
    merged = list(base.get("findings") or [])
    seen = {(str(x.get("code")), str(x.get("scope"))) for x in merged}
    for finding in composition["findings"]:
        key = (str(finding.get("code")), str(finding.get("scope")))
        if key not in seen:
            merged.append(finding)
            seen.add(key)

    result = {
        **base,
        "schema": "chatgpt-web-hwpx-mcp/p3.41/document-page-composition-diagnostic/v1",
        "phase": "P3.41",
        "p340_diagnostic_sha256": base.get("diagnostic_sha256"),
        "page_composition": composition,
        "findings": merged,
        "finding_count": len(merged),
    }
    if composition["verdict"] == "REVIEW_REQUIRED":
        result["verdict"] = "REVIEW_REQUIRED"
    elif merged and result.get("verdict") == "PASS":
        result["verdict"] = "PASS_WITH_WARNINGS"
    result["summary"] = {
        **dict(result.get("summary") or {}),
        "page_composition_verdict": composition["verdict"],
        "page_composition_finding_count": composition["finding_count"],
    }
    result["diagnostic_sha256"] = _sha({k: v for k, v in result.items() if k != "diagnostic_sha256"})
    return result


def plan_render_guided_layout_policy(diagnostic: dict) -> dict:
    composition = dict(diagnostic.get("page_composition") or diagnostic)
    actions: list[dict] = []
    mapping = {
        "PAGE_COMPOSITION_OVERFULL": "REBALANCE_PAGE_DENSITY",
        "PAGE_RHYTHM_LARGE_WHITESPACE_BAND": "REVIEW_SECTION_OR_BLOCK_SPACING",
        "PAGE_TOP_HEAVY_COMPOSITION": "REVIEW_PAGE_BREAK_OR_BLOCK_ORDER",
        "PAGE_BOTTOM_HEAVY_COMPOSITION": "REVIEW_PAGE_BREAK_OR_BLOCK_ORDER",
        "PAGE_BOUNDARY_SINGLE_LINE_PARAGRAPH": "REVIEW_KEEP_TOGETHER_OR_REPAGINATION",
        "DOCUMENT_PAGE_DENSITY_VARIANCE_HIGH": "NORMALIZE_CROSS_PAGE_DENSITY",
    }
    seen: set[tuple[str, str]] = set()
    for finding in composition.get("findings") or []:
        code = str(finding.get("code") or "")
        action = mapping.get(code)
        if not action:
            continue
        key = (action, str(finding.get("scope") or ""))
        if key in seen:
            continue
        seen.add(key)
        actions.append({
            "action": action,
            "status": "AGENT_PLAN",
            "scope": key[1],
            "reason": code,
            "evidence": finding.get("evidence"),
            "mutation_authority": "NOT_GRANTED_FROM_PAGE_RASTER_ALONE",
        })

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.41/render-guided-layout-policy/v1",
        "phase": "P3.41",
        "action_count": len(actions),
        "actions": actions,
        "executable_count": 0,
        "agent_plan_count": len(actions),
        "authority": "RENDER_GUIDED_LAYOUT_POLICY_NOT_AUTOMATIC_PAGE_MUTATION_AUTHORITY",
    }
    result["layout_policy_sha256"] = _sha(result)
    return result


def compare_page_composition_diagnostics(before: dict, after: dict) -> dict:
    def keys(value: dict) -> set[tuple[str, str]]:
        return {
            (str(x.get("code") or ""), str(x.get("scope") or ""))
            for x in (value.get("findings") or [])
        }

    before_comp = dict(before.get("page_composition") or before)
    after_comp = dict(after.get("page_composition") or after)
    before_keys = keys(before_comp)
    after_keys = keys(after_comp)
    both_native = (
        before_comp.get("authority") == "HANCOM_NATIVE_RENDER_EVIDENCE"
        and after_comp.get("authority") == "HANCOM_NATIVE_RENDER_EVIDENCE"
    )
    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.41/page-composition-comparison/v1",
        "phase": "P3.41",
        "resolved": [{"code": c, "scope": s} for c, s in sorted(before_keys - after_keys)],
        "introduced": [{"code": c, "scope": s} for c, s in sorted(after_keys - before_keys)],
        "persistent": [{"code": c, "scope": s} for c, s in sorted(before_keys & after_keys)],
        "native_before_after_available": both_native,
        "capture_changed": before_comp.get("capture_sha256") != after_comp.get("capture_sha256"),
        "authority": (
            "NATIVE_HANCOM_BEFORE_AFTER_PAGE_COMPOSITION"
            if both_native
            else "COMPOSITION_COMPARISON_WITHOUT_JOINT_NATIVE_AUTHORITY"
        ),
    }
    result["comparison_sha256"] = _sha(result)
    return result
