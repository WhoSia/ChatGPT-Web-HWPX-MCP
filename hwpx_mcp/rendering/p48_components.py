from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from hwpx_mcp.rendering.p46_native_authoring import audit_equation_latex

PHASE = "P4.8"
PRODUCT = "0.34.0-p4.8"
SCHEMA = "chatgpt-web-hwpx-mcp/components/p4.8/v1"

ARCHETYPES = {
    "TECHNICAL_NOTE": {"preset": "polished-report", "heading_level": 1},
    "RESEARCH_REPORT": {"preset": "polished-report", "heading_level": 1},
    "POLICY_BRIEF": {"preset": "institutional-report", "heading_level": 1},
    "LAB_REPORT": {"preset": "polished-report", "heading_level": 1},
    "STUDY_GUIDE": {"preset": "default", "heading_level": 1},
}

SUPPORTED_COMPONENTS = {
    "paragraph", "definition", "theorem", "lemma", "proof", "equation",
    "equation_reference", "data_table", "bar_chart", "kpi_strip", "image",
    "callout", "page_break",
}

UNSUPPORTED_CHART_TYPES = {"line_chart", "scatter_chart", "pie_chart", "area_chart"}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def component_authoring_contract() -> dict:
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": SCHEMA,
        "archetypes": sorted(ARCHETYPES),
        "components": sorted(SUPPORTED_COMPONENTS),
        "chart_support": {
            "native_structural": ["bar_chart", "kpi_strip"],
            "typed_hold": sorted(UNSUPPORTED_CHART_TYPES),
            "bar_backend": [
                "P4.9 bounded insert_rectangle",
                "P3.25 insert_textbox label/value overlays",
                "P4.9 preflight + post-materialization visual certificates",
            ],
            "authority": "STRUCTURAL_NATIVE_CHART_COMPOSITION_NOT_NATIVE_HANCOM_CHART_OBJECT",
        },
        "semantic_math": {
            "components": ["definition", "theorem", "lemma", "proof", "equation", "equation_reference"],
            "equation_backend": "P4.6 VERIFIED_LATEX_TO_EQEDIT_ONLY",
            "reference_semantics": "STABLE_COMPILER_LABEL_PLUS_BOOKMARK_NOT_DYNAMIC_EQUATION_NUMBER_FIELD",
            "p47_frontier_inherited": "NO_P4.7_PENDING_EQEDIT_CANDIDATE_IS_USED",
        },
        "atomicity": "PRIVATE_COMPONENT_COMPILATION_AND_NATIVE_POSTPROCESSING_BEFORE_ONE_REVISION_1_COMMIT",
        "principles": [
            "SEMANTIC_COMPONENT_BEFORE_RAW_FORMATTING",
            "REUSE_VERIFIED_NATIVE_PRIMITIVES",
            "UNSUPPORTED_VISUAL_PRIMITIVE_FAILS_CLOSED",
            "NO_P4.7_EQEDIT_HOLD_BYPASS",
            "ONE_SHOT_AUTHORING_STAYS_ONE_DURABLE_REVISION",
        ],
    }


def _component_id(raw: dict, section_index: int, component_index: int) -> str:
    value = str(raw.get("id") or f"s{section_index+1}_c{component_index+1}").strip()
    if not value or len(value) > 80:
        raise ValueError("component id must be 1..80 characters")
    return value


def _math_heading(kind: str, title: str, number: int | None) -> str:
    names = {"definition": "정의", "theorem": "정리", "lemma": "보조정리"}
    base = names[kind]
    if number is not None:
        base += f" {number}"
    return f"{base}. {title}" if title else base


def _normalize_series(raw: dict) -> list[dict]:
    values = raw.get("data")
    if not isinstance(values, list) or not 1 <= len(values) <= 12:
        raise ValueError("bar_chart.data must contain 1..12 items")
    rows = []
    seen = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError("bar_chart data items must be objects")
        label = str(item.get("label") or "").strip()
        if not label or label in seen:
            raise ValueError("bar_chart labels must be non-empty and unique")
        seen.add(label)
        value = float(item.get("value"))
        if not math.isfinite(value) or value < 0:
            raise ValueError("bar_chart values must be finite and non-negative")
        rows.append({"label": label, "value": value, "index": index})
    return rows


def _compile_bar_chart(cid: str, raw: dict, caption_block_id: str) -> dict:
    rows = _normalize_series(raw)
    maximum = max((row["value"] for row in rows), default=0.0)
    width = int(raw.get("width", 32000))
    height = int(raw.get("height", max(9000, len(rows) * 3600)))
    if not 12000 <= width <= 80000:
        raise ValueError("bar_chart width must be 12000..80000 HWPUNIT")
    if not 6000 <= height <= 80000:
        raise ValueError("bar_chart height must be 6000..80000 HWPUNIT")
    color = str(raw.get("color") or "#4F81BD").upper()
    if len(color) != 7 or not color.startswith("#") or any(ch not in "0123456789ABCDEF" for ch in color[1:]):
        raise ValueError("bar_chart color must be #RRGGBB")
    label_width = min(9000, max(4500, width // 4))
    value_width = 6500
    bar_area = max(4000, width - label_width - value_width - 1200)
    row_height = max(1800, height // len(rows))
    bar_height = max(900, int(row_height * 0.5))
    top_offset = 1800
    chart_rows = []
    for row in rows:
        ratio = 0.0 if maximum <= 0 else row["value"] / maximum
        bar_width = max(240, int(bar_area * ratio)) if row["value"] > 0 else 240
        y = top_offset + row["index"] * row_height
        chart_rows.append({
            **row,
            "bar_width": bar_width,
            "bar_height": bar_height,
            "x": label_width,
            "y": y,
            "label_x": 0,
            "value_x": label_width + bar_width + 300,
        })
    return {
        "component_id": cid,
        "type": "bar_chart",
        "anchor_block_id": caption_block_id,
        "title": str(raw.get("title") or ""),
        "color": color,
        "width": width,
        "height": height,
        "top_offset": top_offset,
        "reserved_spacing_pt": max(72, int((height + top_offset) / 100) + 8),
        "rows": chart_rows,
        "authority": "P4.9_BOUNDED_RECTANGLE_PLUS_TEXTBOX_WITH_VISUAL_CERTIFICATION",
    }


def _compile_kpi_strip(cid: str, raw: dict, anchor_block_id: str) -> dict:
    items = raw.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 6:
        raise ValueError("kpi_strip.items must contain 1..6 items")
    out = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("kpi item must be an object")
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value:
            raise ValueError("kpi label and value are required")
        out.append({"index": index, "label": label, "value": value})
    return {
        "component_id": cid,
        "type": "kpi_strip",
        "anchor_block_id": anchor_block_id,
        "items": out,
        "width": int(raw.get("width", 36000)),
        "height": int(raw.get("height", 7200)),
        "top_offset": 1600,
        "reserved_spacing_pt": max(72, int((int(raw.get("height", 7200)) + 1600) / 100) + 8),
        "authority": "P4.9_BOUNDED_KPI_CONTAINER_PLUS_INDEPENDENT_TEXTBOXES",
    }


def compile_document_components(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")
    archetype = str(spec.get("archetype") or "TECHNICAL_NOTE").upper()
    if archetype not in ARCHETYPES:
        raise ValueError(f"unsupported archetype: {archetype}")
    sections = spec.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 24:
        raise ValueError("spec.sections must contain 1..24 sections")

    title = str(spec.get("title") or "").strip()
    rich_sections = []
    chart_plans = []
    blockers = []
    component_map = []
    equation_labels: dict[str, str] = {}
    theorem_counter = 0
    lemma_counter = 0
    definition_counter = 0
    equation_counter = 0
    used_ids = set()

    # First pass assigns stable semantic labels independent of surface order changes.
    for si, section in enumerate(sections):
        components = section.get("components") if isinstance(section, dict) else None
        if not isinstance(components, list):
            raise ValueError("each section.components must be a list")
        for ci, raw in enumerate(components):
            if not isinstance(raw, dict):
                raise ValueError("components must be objects")
            cid = _component_id(raw, si, ci)
            if cid in used_ids:
                raise ValueError(f"duplicate component id: {cid}")
            used_ids.add(cid)
            kind = str(raw.get("type") or "").strip().lower()
            if kind == "equation":
                equation_counter += 1
                label = str(raw.get("label") or cid)
                if label in equation_labels:
                    raise ValueError(f"duplicate equation label: {label}")
                equation_labels[label] = str(raw.get("number") or equation_counter)

    equation_counter = 0
    for si, section in enumerate(sections):
        heading = str(section.get("heading") or "").strip()
        blocks = []
        if heading:
            blocks.append({"id": f"s{si+1}_heading", "type": "heading", "level": 1, "text": heading})
        for ci, raw in enumerate(section.get("components") or []):
            cid = _component_id(raw, si, ci)
            kind = str(raw.get("type") or "").strip().lower()
            if kind in UNSUPPORTED_CHART_TYPES:
                blockers.append({
                    "component_id": cid,
                    "type": kind,
                    "reason": "UNSUPPORTED_CHART_PRIMITIVE",
                    "repair_options": ["data_table", "bar_chart", "user_supplied_image"],
                })
                component_map.append({"component_id": cid, "type": kind, "status": "BLOCKED"})
                continue
            if kind not in SUPPORTED_COMPONENTS:
                raise ValueError(f"unsupported component type: {kind}")

            emitted = []
            if kind == "paragraph":
                emitted.append({"id": cid, "type": "paragraph", "text": str(raw.get("text") or "")})

            elif kind in {"definition", "theorem", "lemma"}:
                if kind == "definition":
                    definition_counter += 1; number = definition_counter
                elif kind == "theorem":
                    theorem_counter += 1; number = theorem_counter
                else:
                    lemma_counter += 1; number = lemma_counter
                heading_id = f"{cid}_heading"
                emitted.extend([
                    {
                        "id": heading_id,
                        "type": "paragraph",
                        "text": _math_heading(kind, str(raw.get("title") or "").strip(), number),
                        "bookmark": f"p48-{cid}",
                        "run_format": {"bold": True},
                        "paragraph_format": {"keep_with_next": True, "spacing_before_pt": 6, "spacing_after_pt": 2},
                    },
                    {"id": cid, "type": "paragraph", "text": str(raw.get("text") or "")},
                ])

            elif kind == "proof":
                emitted.extend([
                    {
                        "id": f"{cid}_heading", "type": "paragraph", "text": str(raw.get("heading") or "증명"),
                        "run_format": {"bold": True}, "paragraph_format": {"keep_with_next": True},
                    },
                    {
                        "id": cid, "type": "paragraph",
                        "text": str(raw.get("text") or "") + ("" if str(raw.get("text") or "").rstrip().endswith("□") else "  □"),
                    },
                ])

            elif kind == "equation":
                equation_counter += 1
                latex = str(raw.get("latex") or "").strip()
                audit = audit_equation_latex(latex, base_unit=int(raw.get("base_unit", 1100)))
                if not audit["supported"]:
                    blockers.append({
                        "component_id": cid,
                        "type": kind,
                        "reason": audit["status"],
                        "unsupported": audit.get("unsupported"),
                        "repair_options": ["rewrite_with_verified_latex", "preserve_source_as_text", "await_p47_world_contact"],
                    })
                    component_map.append({"component_id": cid, "type": kind, "status": "BLOCKED", "audit": audit})
                    continue
                label = str(raw.get("label") or cid)
                number = equation_labels[label]
                emitted.append({
                    "id": cid,
                    "type": "equation",
                    "latex": latex,
                    "caption": str(raw.get("caption") or f"({number})"),
                    "caption_side": str(raw.get("caption_side") or "RIGHT"),
                    "bookmark": f"p48-eq-{label}",
                    "base_unit": int(raw.get("base_unit", 1100)),
                })

            elif kind == "equation_reference":
                label = str(raw.get("target") or "").strip()
                if label not in equation_labels:
                    raise ValueError(f"unknown equation reference target: {label}")
                prefix = str(raw.get("prefix") or "식")
                suffix = str(raw.get("suffix") or "")
                emitted.append({
                    "id": cid,
                    "type": "paragraph",
                    "text": f"{prefix} ({equation_labels[label]}){suffix}",
                })

            elif kind == "data_table":
                headers = raw.get("headers")
                rows = raw.get("rows")
                if not isinstance(headers, list) or not headers:
                    raise ValueError("data_table.headers must be a non-empty list")
                if not isinstance(rows, list):
                    raise ValueError("data_table.rows must be a list")
                cells = [[str(x) for x in headers]] + [[str(x) for x in row] for row in rows]
                if any(len(row) != len(headers) for row in cells):
                    raise ValueError("data_table row width mismatch")
                emitted.append({
                    "id": cid, "type": "table", "rows": len(cells), "cols": len(headers),
                    "cells": cells, "first_row_header": True,
                    "caption": str(raw.get("caption") or "") or None,
                })

            elif kind == "bar_chart":
                caption_id = f"{cid}_anchor"
                chart_plan = _compile_bar_chart(cid, raw, caption_id)
                emitted.append({
                    "id": caption_id,
                    "type": "paragraph",
                    "text": str(raw.get("caption") or raw.get("title") or "데이터 시각화"),
                    "run_format": {"bold": bool(raw.get("bold_caption", False))},
                    "paragraph_format": {
                        "keep_with_next": True,
                        "spacing_before_pt": 4,
                        "spacing_after_pt": chart_plan["reserved_spacing_pt"],
                    },
                })
                chart_plans.append(chart_plan)

            elif kind == "kpi_strip":
                anchor_id = f"{cid}_anchor"
                kpi_plan = _compile_kpi_strip(cid, raw, anchor_id)
                emitted.append({
                    "id": anchor_id, "type": "paragraph",
                    "text": str(raw.get("caption") or raw.get("title") or "핵심 지표"),
                    "paragraph_format": {
                        "keep_with_next": True,
                        "spacing_after_pt": kpi_plan["reserved_spacing_pt"],
                    },
                })
                chart_plans.append(kpi_plan)

            elif kind == "image":
                payload = str(raw.get("content_base64") or "")
                if not payload:
                    raise ValueError("image component requires content_base64")
                emitted.append({
                    "id": cid, "type": "picture", "content_base64": payload,
                    "image_format": str(raw.get("image_format") or "png"),
                    "width": int(raw.get("width", 18000)),
                    "height": int(raw.get("height", 12000)),
                    "caption": str(raw.get("caption") or "") or None,
                })

            elif kind == "callout":
                label = str(raw.get("label") or "핵심")
                emitted.append({
                    "id": cid, "type": "paragraph", "text": f"{label}: {str(raw.get('text') or '')}",
                    "run_format": {"bold": bool(raw.get("bold", False))},
                    "paragraph_format": {"spacing_before_pt": 4, "spacing_after_pt": 4},
                })

            elif kind == "page_break":
                emitted.append({"id": cid, "type": "page_break"})

            blocks.extend(emitted)
            component_map.append({
                "component_id": cid,
                "type": kind,
                "status": "COMPILED",
                "block_ids": [b["id"] for b in emitted],
            })
        if not blocks:
            blocks.append({"id": f"s{si+1}_empty", "type": "paragraph", "text": ""})
        rich_sections.append({"blocks": blocks})

    rich_plan = {
        "document": {"title": title},
        "preset": ARCHETYPES[archetype]["preset"],
        "sections": rich_sections,
    }
    if title:
        rich_plan["sections"][0]["blocks"].insert(0, {"id": "p48_title", "type": "title", "text": title})

    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": SCHEMA,
        "archetype": archetype,
        "ready": not blockers,
        "blockers": blockers,
        "component_count": len(component_map),
        "component_map": component_map,
        "equation_labels": equation_labels,
        "unified_spec": {"rich_plan": rich_plan, "native_bundle": {}},
        "visual_plans": chart_plans,
        "authority": "SEMANTIC_COMPONENT_COMPILER_TO_VERIFIED_P3_P4_PRIMITIVES",
    }
    result["component_plan_sha256"] = _sha({
        "archetype": archetype,
        "component_map": component_map,
        "equation_labels": equation_labels,
        "rich_plan": rich_plan,
        "visual_plans": chart_plans,
        "blockers": blockers,
    })
    return result


def plan_component_repairs(spec: dict) -> dict:
    compiled = compile_document_components(spec)
    repairs = []
    for blocker in compiled["blockers"]:
        repairs.append({
            "component_id": blocker["component_id"],
            "problem": blocker["reason"],
            "safe_options": blocker.get("repair_options") or [],
            "automatic_mutation": False,
        })
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "ready": compiled["ready"],
        "repair_count": len(repairs),
        "repairs": repairs,
        "policy": "REPAIR_PLAN_IS_ADVISORY_UNTIL_USER_OR_CALLER_SELECTS_A_SAFE_OPTION",
        "component_plan_sha256": compiled["component_plan_sha256"],
        "repair_plan_sha256": _sha(repairs),
    }


def distribution_quickstart_contract() -> dict:
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "minimal_path": [
            "CONNECT_REMOTE_OAUTH_MCP",
            "CALL_get_component_authoring_contract",
            "CALL_create_component_document_and_deliver",
            "USE_REVISION_BOUND_HWPX",
        ],
        "first_document_inputs": ["title", "archetype", "sections[].components[]"],
        "recovery": {
            "compile_blocker": "CALL_plan_component_repairs_AND_SELECT_A_SAFE_OPTION",
            "delivery_after_commit_failure": "CALL_deliver_document_DO_NOT_REPEAT_MUTATION",
            "visual_claim": "REQUIRE_RENDER_OR_HUMAN_EVIDENCE",
        },
        "public_distribution_invariant": "QUICKSTART_NEVER_BYPASSES_OAUTH_CAPABILITY_OR_EVIDENCE_BOUNDARIES",
    }
