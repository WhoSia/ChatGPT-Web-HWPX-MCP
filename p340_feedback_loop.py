from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import statistics
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

from p2_document import _local, _paragraph_nodes, build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map
from p28_tables import apply_table_edits_atomic, build_table_map
from p312_render_harness import validate_capture
from p336r2_design import paragraph_features_from_hwpx, infer_presentation_roles
from p339_design_intelligence import (
    diagnose_document_design as p339_diagnose_document_design,
    plan_design_repairs as p339_plan_design_repairs,
    prepare_authoring_strategy,
)

SCHEMA = "chatgpt-web-hwpx-mcp/p3.40/rendered-design-feedback-loop/v1"
HEADER_NAME = "Contents/header.xml"
_HORIZONTAL_ALIGNMENTS = {"LEFT", "CENTER", "RIGHT", "JUSTIFY", "DISTRIBUTE", "DISTRIBUTE_SPACE"}
_HEADER_FILL = "#EEF2F6"
_HEADER_RULE = "#A7B2C1"
_CALLOUT_FILL = "#F4F7FA"
_CALLOUT_RULE = "#7F8C9D"


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def rendered_feedback_loop_contract() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "P3.40",
        "purpose": "RENDER_DIAGNOSE_REPAIR_RERENDER_WITH_BOUNDED_NATIVE_MUTATION",
        "inherits": "P3.39_DESIGN_CONSTITUTION_AND_EVIDENCE_LAYERING",
        "closed_loop": [
            "AUTHOR_FROM_SEMANTIC_STRATEGY",
            "NATIVE_HWPX",
            "RENDER_CAPTURE",
            "PAGE_GEOMETRY_DIAGNOSTICS",
            "MERGE_WITH_STATIC_DIAGNOSTICS",
            "PLAN_MINIMAL_REPAIRS",
            "EXECUTE_SUPPORTED_NATIVE_REPAIRS",
            "RENDER_AGAIN",
            "COMPARE_BEFORE_AFTER",
            "HUMAN_REVIEW",
        ],
        "new_native_capabilities": {
            "nested_table_paragraph_alignment": "SAFE_PARAPR_CLONE_AND_LOCATOR_BOUND_REBIND",
            "header_row_semantic_styling": "EXISTING_CELL_SHADING_BORDER_MARGIN_PRIMITIVES_BUNDLED_BY_ROW",
            "table_scoped_padding": "CELL_MARGIN_PRIMITIVES_BUNDLED_BY_TABLE_FOR_TOOL_ECONOMY",
            "section_heading_separator": "EXISTING_PARAGRAPH_SPACING_AND_BOTTOM_RULE_PRIMITIVES_BUNDLED_BY_ROLE",
            "table_column_width_policy": "CONTENT_AWARE_WIDTH_PLAN_COMPILED_TO_SET_COLUMN_WIDTHS",
            "semantic_callout_container": "ONE_CELL_NATIVE_TABLE_WITH_RESTRAINED_FILL_RULE_PADDING",
        },
        "render_authority": {
            "hancom_native": "requires hancom_native=true, executable sha, positive dpi, and raster hashes",
            "other_renderer": "EXTERNAL_RENDER_OBSERVATION",
            "static_only": "never promoted to rendered visual authority",
        },
        "non_claims": [
            "No universal beauty score.",
            "No synthetic capture is promoted to Hancom-native evidence.",
            "Narrative reordering remains agent/human authority.",
            "Rendered improvement is not claimed until a post-repair capture exists.",
        ],
    }


def semantic_callout_block(
    text: str,
    *,
    block_id: str = "semantic_callout",
    role: str = "KEY_JUDGMENT",
) -> dict:
    value = str(text)
    if not value.strip():
        raise ValueError("semantic callout text must be non-empty")
    if len(value) > 12000:
        raise ValueError("semantic callout text is too long")
    semantic_role = str(role or "KEY_JUDGMENT").strip().upper()
    if semantic_role not in {"KEY_JUDGMENT", "RISK_CALLOUT", "CALLOUT", "EXECUTIVE_SUMMARY"}:
        raise ValueError("unsupported semantic callout role")
    return {
        "id": str(block_id),
        "type": "table",
        "rows": 1,
        "cols": 1,
        "cells": [[value]],
        "first_row_header": False,
        "table_format": {
            "page_break": "CELL",
            "border_color": _CALLOUT_RULE,
            "repeat_header": False,
        },
        "semantic_role": semantic_role,
        "p340_container": "SEMANTIC_CALLOUT",
    }


def _renderer_world_contact(renderer: dict | None, normalized_capture: dict) -> bool:
    renderer = dict(renderer or {})
    raster_hashes = [str(p.get("raster_sha256") or "") for p in normalized_capture.get("pages", [])]
    return bool(
        renderer.get("hancom_native")
        and str(renderer.get("executable_sha256") or "").strip()
        and int(renderer.get("dpi") or 0) > 0
        and raster_hashes
        and all(len(x) == 64 for x in raster_hashes)
    )


def diagnose_render_capture(
    capture: dict,
    *,
    renderer: dict | None = None,
) -> dict:
    normalized = validate_capture(capture)
    world_contact_valid = _renderer_world_contact(renderer, normalized)
    authority = (
        "HANCOM_NATIVE_RENDER_EVIDENCE"
        if world_contact_valid
        else "EXTERNAL_RENDER_OBSERVATION"
    )
    findings: list[dict] = []
    page_metrics: list[dict] = []

    for page in normalized["pages"]:
        width = float(page["width_px"])
        height = float(page["height_px"])
        lines = list(page.get("line_boxes") or [])
        if lines:
            left = min(float(x["x"]) for x in lines)
            right = max(float(x["x"]) + float(x["width"]) for x in lines)
            top = min(float(x["y"]) for x in lines)
            bottom = max(float(x["y"]) + float(x["height"]) for x in lines)
            line_area = sum(float(x["width"]) * float(x["height"]) for x in lines)
        else:
            left = right = top = bottom = line_area = 0.0

        left_margin = left / width if lines else 1.0
        right_margin = (width - right) / width if lines else 1.0
        top_margin = top / height if lines else 1.0
        bottom_margin = (height - bottom) / height if lines else 1.0
        vertical_span = (bottom - top) / height if lines else 0.0
        line_box_area_ratio = line_area / (width * height) if lines else 0.0
        metric = {
            "page_index": int(page["page_index"]),
            "line_count": len(lines),
            "left_margin_ratio": round(left_margin, 6),
            "right_margin_ratio": round(right_margin, 6),
            "top_margin_ratio": round(top_margin, 6),
            "bottom_margin_ratio": round(bottom_margin, 6),
            "vertical_span_ratio": round(vertical_span, 6),
            "line_box_area_ratio": round(line_box_area_ratio, 6),
            "raster_sha256": page.get("raster_sha256"),
        }
        page_metrics.append(metric)
        scope = f"PAGE_{int(page['page_index']) + 1}"

        if len(lines) >= 52 or vertical_span >= 0.89:
            findings.append({
                "code": "PAGE_TEXT_DENSITY_HIGH",
                "severity": "MEDIUM",
                "scope": scope,
                "principle": "DENSITY_BUDGET",
                "evidence": metric,
                "recommendation": "Reduce page crowding by rebalancing block widths, table columns, or page breaks before shrinking type.",
            })
        if lines and min(left_margin, right_margin) < 0.025:
            findings.append({
                "code": "PAGE_SIDE_MARGIN_TIGHT",
                "severity": "HIGH",
                "scope": scope,
                "principle": "READING_GEOMETRY",
                "evidence": metric,
                "recommendation": "Move rendered content away from the page edge; inspect oversized tables or objects first.",
            })
        if lines and bottom_margin < 0.022:
            findings.append({
                "code": "PAGE_BOTTOM_CROWDING",
                "severity": "HIGH",
                "scope": scope,
                "principle": "DENSITY_BUDGET",
                "evidence": metric,
                "recommendation": "Relieve the page bottom by moving or splitting the final dense block; do not compress text globally.",
            })
        if lines and abs(top_margin - bottom_margin) >= 0.18 and vertical_span >= 0.55:
            findings.append({
                "code": "PAGE_VERTICAL_BALANCE_WEAK",
                "severity": "LOW",
                "scope": scope,
                "principle": "READING_GEOMETRY",
                "evidence": metric,
                "recommendation": "Review section/page-break placement; large imbalance may be intentional and is not an automatic mutation target.",
            })

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.40/render-page-diagnostic/v1",
        "phase": "P3.40",
        "authority": authority,
        "world_contact_valid": world_contact_valid,
        "renderer": dict(renderer or {}),
        "capture_sha256": normalized["capture_sha256"],
        "page_count": normalized["page_count"],
        "line_count": normalized["line_count"],
        "page_metrics": page_metrics,
        "findings": findings,
    }
    result["render_diagnostic_sha256"] = _sha(result)
    return result


def _semantic_role_metadata_conflicts(path: Path) -> list[dict]:
    document = build_document_map(path)
    doc_index = {str(x.get("locator")): x for x in document.get("paragraphs", [])}
    features = paragraph_features_from_hwpx(path)
    roles = infer_presentation_roles(features)
    role_index = {str(x.get("locator")): x for x in roles.get("hypotheses", [])}
    conflicts: list[dict] = []

    for feature in features:
        locator = str(feature.get("locator") or "")
        if not locator or not bool(feature.get("native_heading")):
            continue
        role = role_index.get(locator) or {}
        doc_item = doc_index.get(locator) or {}
        direct_text = str(doc_item.get("text") or "").strip()
        text_chars = int(feature.get("text_characters") or 0)
        ratio = float(role.get("size_ratio_to_median") or 0.0)
        bold = float(feature.get("bold_share") or 0.0)
        alignment = str(feature.get("alignment") or "").upper()

        structural_carrier = not direct_text and text_chars > 0
        visually_body_like = bool(
            direct_text
            and text_chars >= 60
            and ratio <= 1.05
            and bold < 0.15
            and alignment in {"LEFT", "JUSTIFY"}
        )
        if not structural_carrier and not visually_body_like:
            continue

        conflicts.append({
            "locator": locator,
            "kind": "STRUCTURAL_CARRIER_DESCENDANT_TEXT" if structural_carrier else "BODY_VISUALS_WITH_OUTLINE_METADATA",
            "document_text_characters": len(direct_text),
            "feature_text_characters": text_chars,
            "size_ratio_to_median": round(ratio, 6),
            "bold_share": round(bold, 6),
            "alignment": alignment,
            "native_heading": True,
            "presentation_role": role.get("presentation_role"),
            "role_evidence": list(role.get("evidence") or []),
        })
    return conflicts


def _reconcile_static_hierarchy_findings(path: Path, base: dict) -> dict:
    conflicts = _semantic_role_metadata_conflicts(path)
    conflict_locators = {str(x["locator"]) for x in conflicts}
    if not conflict_locators:
        return base

    findings: list[dict] = []
    for item in base.get("findings", []) or []:
        code = str(item.get("code") or "").upper()
        if code not in {"SECTION_HIERARCHY_CONTRAST_WEAK", "SECTION_SEPARATION_WEAK"}:
            findings.append(dict(item))
            continue
        copied = dict(item)
        evidence = dict(copied.get("evidence") or {})
        locators = [str(x) for x in evidence.get("locators", []) if str(x) not in conflict_locators]
        if not locators:
            continue
        evidence["locators"] = locators
        evidence["count"] = len(locators)
        copied["evidence"] = evidence
        findings.append(copied)

    findings.append({
        "code": "NATIVE_HEADING_METADATA_VISUAL_MISMATCH",
        "severity": "MEDIUM",
        "scope": "PARAGRAPH_ROLE_METADATA",
        "evidence": {
            "count": len(conflicts),
            "paragraphs": conflicts[:40],
        },
        "principle": "SEMANTIC_VISUAL_CONGRUENCE",
        "recommendation": (
            "Treat outline metadata and visual/body evidence as conflicting authorities. "
            "Do not repair this by making body text look like a heading; normalize the semantic carrier or paragraph role separately."
        ),
        "authority": "STATIC_STRUCTURE_CROSSCHECK",
    })

    severity_order = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    max_severity = max(
        (severity_order.get(str(x.get("severity") or "").upper(), 1) for x in findings),
        default=0,
    )
    reconciled = dict(base)
    reconciled["findings"] = findings
    reconciled["finding_count"] = len(findings)
    reconciled["verdict"] = (
        "NEEDS_REPAIR" if max_severity >= 3 else "PASS_WITH_WARNINGS" if findings else "PASS"
    )
    summary = dict(reconciled.get("summary") or {})
    summary["native_heading_metadata_visual_mismatch_count"] = len(conflicts)
    reconciled["summary"] = summary
    return reconciled


def diagnose_document_with_render(
    path: Path | str,
    *,
    mode: str = "POLISHED_REPORT",
    capture: dict | None = None,
    renderer: dict | None = None,
    render_observation: dict | None = None,
    human_feedback: list[dict] | None = None,
) -> dict:
    if capture is not None and render_observation is not None:
        raise ValueError("provide capture or render_observation, not both")
    page_diagnostic = None
    observation = render_observation
    if capture is not None:
        page_diagnostic = diagnose_render_capture(capture, renderer=renderer)
        observation = {
            "authority": page_diagnostic["authority"],
            "findings": page_diagnostic["findings"],
        }

    base = p339_diagnose_document_design(
        Path(path),
        mode=mode,
        render_observation=observation,
        human_feedback=human_feedback,
    )
    base = _reconcile_static_hierarchy_findings(Path(path), base)
    result = {
        **base,
        "schema": "chatgpt-web-hwpx-mcp/p3.40/design-diagnostic/v1",
        "phase": "P3.40",
        "p339_diagnostic_sha256": base.get("diagnostic_sha256"),
        "render_page_diagnostic": page_diagnostic,
    }
    if page_diagnostic is not None:
        authorities = set(result.get("authorities") or [])
        authorities.add(page_diagnostic["authority"])
        result["authorities"] = sorted(authorities)
        result["summary"] = {
            **dict(result.get("summary") or {}),
            "render_world_contact_valid": page_diagnostic["world_contact_valid"],
            "render_page_count": page_diagnostic["page_count"],
        }
    result["diagnostic_sha256"] = _sha({
        k: v for k, v in result.items() if k != "diagnostic_sha256"
    })
    return result


def _header_para_props(root: ElementTree.Element) -> tuple[dict[str, ElementTree.Element], dict[ElementTree.Element, ElementTree.Element]]:
    parents = {child: parent for parent in root.iter() for child in parent}
    props = {
        str(node.attrib.get("id")): node
        for node in root.iter()
        if _local(node.tag) == "paraPr" and node.attrib.get("id") is not None
    }
    return props, parents


def _fresh_para_pr_id(props: dict[str, ElementTree.Element]) -> str:
    numbers = []
    for key in props:
        try:
            numbers.append(int(key))
        except (TypeError, ValueError):
            pass
    candidate = max(numbers, default=0) + 1
    while str(candidate) in props:
        candidate += 1
    return str(candidate)


def _set_para_alignment(node: ElementTree.Element, alignment: str) -> None:
    align = next((x for x in node.iter() if _local(x.tag) == "align"), None)
    if align is None:
        if "}" in node.tag:
            namespace = node.tag.split("}", 1)[0] + "}"
            tag = namespace + "align"
        else:
            tag = "align"
        align = ElementTree.SubElement(node, tag)
    align.set("horizontal", alignment)


def _refresh_property_count(parent: ElementTree.Element) -> None:
    count = sum(1 for child in list(parent) if _local(child.tag) == "paraPr")
    for key in ("itemCnt", "count"):
        if key in parent.attrib:
            parent.set(key, str(count))


def apply_nested_paragraph_alignment_atomic(
    path: Path | str,
    targets: list[str],
    *,
    alignment: str = "LEFT",
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    path = Path(path)
    alignment = str(alignment or "").upper()
    if alignment not in _HORIZONTAL_ALIGNMENTS:
        raise ValueError("unsupported nested paragraph alignment")
    if not isinstance(targets, list) or not targets:
        raise ValueError("targets must be a non-empty locator list")
    if len(targets) > 120:
        raise ValueError("too many nested paragraph targets")

    before_doc = build_document_map(path)
    before_fmt = build_formatting_map(path)
    index = {str(x["locator"]): x for x in before_doc["paragraphs"]}
    fmt_index = {str(x["locator"]): x for x in before_fmt["paragraphs"]}
    normalized: list[str] = []
    for target in targets:
        locator = str(target)
        item = index.get(locator)
        if item is None:
            raise ValueError(f"unknown paragraph locator: {locator}")
        if item.get("body_global_index") is not None:
            raise ValueError("nested alignment primitive only admits non-section-body paragraphs")
        if locator not in fmt_index:
            raise ValueError(f"formatting locator unavailable: {locator}")
        if locator not in normalized:
            normalized.append(locator)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p340-nested-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    shutil.copy2(path, candidate)

    target_new_ref: dict[str, str] = {}
    validation = None
    try:
        with zipfile.ZipFile(candidate, "r") as source:
            header_root = ElementTree.fromstring(source.read(HEADER_NAME))
            props, parents = _header_para_props(header_root)
            style_cache: dict[tuple[str, str], str] = {}
            touched_parents: set[ElementTree.Element] = set()

            for locator in normalized:
                base_ref = str(fmt_index[locator].get("para_pr_id_ref") or "")
                base = props.get(base_ref)
                if base is None:
                    raise ValueError(f"paragraph property {base_ref!r} is not safely resolvable")
                key = (base_ref, alignment)
                new_ref = style_cache.get(key)
                if new_ref is None:
                    clone = copy.deepcopy(base)
                    new_ref = _fresh_para_pr_id(props)
                    clone.set("id", new_ref)
                    _set_para_alignment(clone, alignment)
                    parent = parents.get(base)
                    if parent is None:
                        raise ValueError("paragraph property table parent is unavailable")
                    parent.append(clone)
                    props[new_ref] = clone
                    style_cache[key] = new_ref
                    touched_parents.add(parent)
                target_new_ref[locator] = new_ref

            for parent in touched_parents:
                _refresh_property_count(parent)
            header_payload = ElementTree.tostring(header_root, encoding="utf-8", xml_declaration=True)

            by_section: dict[str, list[tuple[int, str, str]]] = {}
            for locator in normalized:
                item = index[locator]
                by_section.setdefault(str(item["section"]), []).append(
                    (int(item["paragraph_index"]), locator, target_new_ref[locator])
                )

            fd2, out_name = tempfile.mkstemp(prefix=path.stem + ".p340-zip-", suffix=".hwpx", dir=str(path.parent))
            os.close(fd2)
            out_path = Path(out_name)
            try:
                with zipfile.ZipFile(out_path, "w") as target_zip:
                    for info in source.infolist():
                        payload = source.read(info.filename)
                        if info.filename == HEADER_NAME:
                            payload = header_payload
                        elif info.filename in by_section:
                            root = ElementTree.fromstring(payload)
                            paragraphs = _paragraph_nodes(root)
                            for para_index, locator, new_ref in by_section[info.filename]:
                                if para_index >= len(paragraphs):
                                    raise ValueError(f"paragraph target disappeared: {locator}")
                                paragraph = paragraphs[para_index]
                                paragraph.set("paraPrIDRef", new_ref)
                                for child in list(paragraph):
                                    if _local(child.tag).lower() == "linesegarray":
                                        paragraph.remove(child)
                            payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                        target_zip.writestr(info, payload)
                os.replace(out_path, candidate)
            finally:
                try:
                    out_path.unlink()
                except FileNotFoundError:
                    pass

        after_doc = build_document_map(candidate)
        after_fmt = build_formatting_map(candidate)
        if before_doc["semantic_sha256"] != after_doc["semantic_sha256"]:
            raise ValueError("nested paragraph alignment changed semantic text")
        if before_doc["structure_sha256"] != after_doc["structure_sha256"]:
            raise ValueError("nested paragraph alignment changed paragraph structure")
        after_index = {str(x["locator"]): x for x in after_fmt["paragraphs"]}
        for locator in normalized:
            attrs = ((after_index[locator].get("paragraph_property") or {}).get("alignment") or {})
            if str(attrs.get("horizontal") or "").upper() != alignment:
                raise ValueError(f"nested paragraph alignment did not read back for {locator}")
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
        "schema": "chatgpt-web-hwpx-mcp/p3.40/nested-paragraph-alignment-receipt/v1",
        "phase": "P3.40",
        "targets": normalized,
        "alignment": alignment,
        "before_formatting_sha256": before_fmt["formatting_sha256"],
        "after_formatting_sha256": after_fmt["formatting_sha256"],
        "semantic_changed": False,
        "structure_changed": False,
        "formatting_changed": before_fmt["formatting_sha256"] != after_fmt["formatting_sha256"],
        "validation": validation,
        "authority": "LOCATOR_BOUND_NATIVE_PARAGRAPH_PROPERTY_REBIND",
    }


def _bounded_shares(weights: list[float], min_share: float, max_share: float) -> list[float]:
    if not weights:
        return []
    total = sum(max(0.0001, x) for x in weights)
    shares = [max(0.0001, x) / total for x in weights]
    for _ in range(8):
        clipped = [min(max(s, min_share), max_share) for s in shares]
        delta = 1.0 - sum(clipped)
        if abs(delta) < 1e-9:
            shares = clipped
            break
        free = [i for i, s in enumerate(clipped) if min_share < s < max_share]
        if not free:
            shares = [s / sum(clipped) for s in clipped]
            break
        per = delta / len(free)
        shares = [s + (per if i in free else 0.0) for i, s in enumerate(clipped)]
    total = sum(shares)
    return [s / total for s in shares]


def content_aware_column_widths(table: dict) -> dict | None:
    cols = int(table.get("cols") or 0)
    cells = list(table.get("cells") or [])
    if cols < 2 or not cells:
        return None
    if any(int(c.get("col_span") or 1) != 1 for c in cells):
        return None

    current = [0 for _ in range(cols)]
    lengths: list[list[int]] = [[] for _ in range(cols)]
    for cell in cells:
        col = int(cell.get("col") or 0)
        if 0 <= col < cols:
            current[col] = max(current[col], int(cell.get("width") or 0))
            lengths[col].append(len(str(cell.get("text") or "").strip()))
    total_width = sum(current)
    if total_width <= 0 or any(x <= 0 for x in current):
        return None

    means = [statistics.mean(x) if x else 0.0 for x in lengths]
    weights = [1.0 + min(90.0, value) / 32.0 for value in means]
    min_share = 0.08 if cols >= 6 else 0.11
    shares = _bounded_shares(weights, min_share, 0.55)
    widths = [max(1, int(round(total_width * share))) for share in shares]
    widths[-1] += total_width - sum(widths)
    if any(x <= 0 for x in widths):
        return None
    return {
        "widths": widths,
        "total_width": total_width,
        "mean_characters_by_column": [round(x, 3) for x in means],
        "shares": [round(x, 6) for x in shares],
        "policy": "CONTENT_LENGTH_WEIGHTED_BOUNDED_SHARE",
    }


def _find_table(table_map: dict, locator: str) -> dict | None:
    return next((x for x in table_map.get("tables", []) if str(x.get("locator")) == str(locator)), None)


def plan_executable_editorial_repairs(
    path: Path | str,
    diagnostic: dict,
    *,
    strategy: dict | None = None,
) -> dict:
    path = Path(path)
    strategy = strategy or prepare_authoring_strategy({"archetype": "POLISHED_REPORT"})
    base = p339_plan_design_repairs(diagnostic, strategy=strategy)
    findings = {str(x.get("code") or "").upper(): x for x in diagnostic.get("findings", [])}
    tables = build_table_map(path)
    actions: list[dict] = []
    padding_compiled = False

    for action in base.get("actions", []):
        reason = str(action.get("reason") or "").upper()
        if reason == "TABLE_CELL_PADDING_TIGHT":
            if not padding_compiled:
                evidence = dict((findings.get(reason) or {}).get("evidence") or {})
                by_table: dict[str, int] = {}
                for cell in evidence.get("cells", []):
                    locator = str(cell.get("table") or "")
                    if locator:
                        by_table[locator] = by_table.get(locator, 0) + 1
                for table, count in sorted(by_table.items()):
                    actions.append({
                        "action": "ALLOCATE_TABLE_PADDING",
                        "status": "EXECUTABLE",
                        "tool": "apply_document_design_repairs",
                        "operation": {
                            "op": "set_table_padding",
                            "table": table,
                            **dict(strategy["constraints"]["table_min_padding_hwpunit"]),
                        },
                        "target_cell_count": count,
                        "reason": reason,
                    })
                padding_compiled = True
            continue

        if reason == "TABLE_LONG_TEXT_CENTERED":
            evidence = dict((findings.get(reason) or {}).get("evidence") or {})
            targets = [str(x) for x in evidence.get("locators", []) if x]
            if targets:
                actions.append({
                    **action,
                    "status": "EXECUTABLE",
                    "tool": "apply_document_design_repairs",
                    "operation": {
                        "op": "align_nested_table_paragraphs",
                        "targets": targets,
                        "alignment": "LEFT",
                    },
                    "required_capability": None,
                })
                continue

        if reason == "TABLE_HEADER_CONTRAST_WEAK":
            evidence = dict((findings.get(reason) or {}).get("evidence") or {})
            targets = [str(x.get("table")) for x in evidence.get("tables", []) if x.get("table")]
            if targets:
                for table in targets:
                    actions.append({
                        "action": "APPLY_RESTRAINED_HEADER_CONTRAST",
                        "status": "EXECUTABLE",
                        "tool": "apply_document_design_repairs",
                        "operation": {
                            "op": "style_table_header",
                            "table": table,
                            "row": 0,
                            "fill": _HEADER_FILL,
                            "border_color": _HEADER_RULE,
                        },
                        "reason": reason,
                    })
                continue

        if reason in {"SECTION_SEPARATION_WEAK", "SECTION_HIERARCHY_CONTRAST_WEAK"}:
            evidence = dict((findings.get(reason) or {}).get("evidence") or {})
            targets = [str(x) for x in evidence.get("locators", []) if x]
            if targets:
                actions.append({
                    "action": "APPLY_SECTION_HEADING_SEPARATOR",
                    "status": "EXECUTABLE",
                    "tool": "apply_document_design_repairs",
                    "operation": {
                        "op": "style_section_headings",
                        "targets": targets,
                    },
                    "reason": reason,
                })
                continue

        if reason == "NATIVE_HEADING_METADATA_VISUAL_MISMATCH":
            actions.append({
                "action": "RECONCILE_PARAGRAPH_ROLE_METADATA",
                "status": "AGENT_PLAN",
                "tool": None,
                "reason": reason,
                "guidance": (
                    "Keep the paragraph visually as body text; inspect the structural carrier or outline metadata "
                    "instead of increasing heading contrast."
                ),
            })
            continue

        if reason == "TABLE_DENSITY_HIGH":
            evidence = dict((findings.get(reason) or {}).get("evidence") or {})
            compiled = 0
            for row in evidence.get("tables", []):
                locator = str(row.get("table") or "")
                table = _find_table(tables, locator)
                width_plan = None if table is None else content_aware_column_widths(table)
                if width_plan is None:
                    continue
                actions.append({
                    "action": "REBUDGET_TABLE_COLUMN_WIDTHS",
                    "status": "EXECUTABLE",
                    "tool": "apply_document_design_repairs",
                    "operation": {
                        "op": "rebalance_table_columns",
                        "table": locator,
                        "widths": width_plan["widths"],
                    },
                    "policy_evidence": width_plan,
                    "reason": reason,
                })
                compiled += 1
            if compiled:
                continue

        actions.append(dict(action))

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.40/design-repair-plan/v1",
        "phase": "P3.40",
        "p339_repair_plan_sha256": base.get("repair_plan_sha256"),
        "diagnostic_sha256": diagnostic.get("diagnostic_sha256"),
        "strategy_sha256": strategy.get("strategy_sha256"),
        "actions": actions,
        "executable_count": sum(x.get("status") == "EXECUTABLE" for x in actions),
        "agent_plan_count": sum(x.get("status") == "AGENT_PLAN" for x in actions),
        "capability_gap_count": sum(x.get("status") == "CAPABILITY_GAP" for x in actions),
        "repair_policy": "MINIMAL_EVIDENCE_BOUND_ATOMIC_REPAIR_THEN_REDIAGNOSE",
        "authority": "P3.40_EXECUTABLE_REPAIR_PLAN_NOT_RENDERED_IMPROVEMENT_CLAIM",
    }
    result["repair_plan_sha256"] = _sha(result)
    return result


def _chunked(values: list[dict], size: int) -> list[list[dict]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def _style_table_header(candidate: Path, operation: dict) -> dict:
    tables = build_table_map(candidate)
    table = _find_table(tables, str(operation.get("table") or ""))
    if table is None:
        raise ValueError("header table locator is unavailable")
    row = int(operation.get("row", 0))
    cells = [c for c in table.get("cells", []) if int(c.get("row") or 0) == row]
    if not cells:
        raise ValueError("header row has no addressable cells")
    fill = str(operation.get("fill") or _HEADER_FILL)
    border = str(operation.get("border_color") or _HEADER_RULE)
    ops: list[dict] = []
    for cell in cells:
        locator = str(cell["locator"])
        ops.extend([
            {"op": "set_cell_shading", "table": table["locator"], "cell": locator, "color": fill},
            {"op": "set_cell_borders", "table": table["locator"], "cell": locator, "color": border, "line_type": "SOLID"},
            {
                "op": "set_cell_margin",
                "table": table["locator"],
                "cell": locator,
                "left": 560,
                "right": 560,
                "top": 420,
                "bottom": 420,
            },
            {"op": "set_cell_properties", "table": table["locator"], "cell": locator, "header": True},
        ])
    receipts = []
    for chunk in _chunked(ops, 48):
        receipts.append(apply_table_edits_atomic(
            candidate,
            chunk,
            expected_revision=1,
            current_revision=1,
            validator=None,
        ))
    return {"table": table["locator"], "row": row, "cell_count": len(cells), "receipts": receipts}


def _set_table_padding(candidate: Path, operation: dict) -> dict:
    tables = build_table_map(candidate)
    table = _find_table(tables, str(operation.get("table") or ""))
    if table is None:
        raise ValueError("table padding locator is unavailable")
    margins = {
        "left": int(operation.get("left", 560)),
        "right": int(operation.get("right", 560)),
        "top": int(operation.get("top", 420)),
        "bottom": int(operation.get("bottom", 420)),
    }
    if any(value < 0 or value > 100000 for value in margins.values()):
        raise ValueError("table padding is outside admitted bounds")
    ops = [
        {
            "op": "set_cell_margin",
            "table": table["locator"],
            "cell": str(cell["locator"]),
            **margins,
        }
        for cell in table.get("cells", [])
    ]
    if not ops:
        raise ValueError("table has no addressable cells")
    receipts = []
    for chunk in _chunked(ops, 48):
        receipts.append(apply_table_edits_atomic(
            candidate,
            chunk,
            expected_revision=1,
            current_revision=1,
            validator=None,
        ))
    return {
        "table": table["locator"],
        "cell_count": len(ops),
        "margins": margins,
        "receipts": receipts,
    }


def _style_semantic_callout(candidate: Path, operation: dict) -> dict:
    tables = build_table_map(candidate)
    table = _find_table(tables, str(operation.get("table") or ""))
    if table is None:
        raise ValueError("callout table locator is unavailable")
    cells = list(table.get("cells") or [])
    if len(cells) != 1:
        raise ValueError("semantic callout primitive requires a one-cell table")
    cell = cells[0]
    ops = [
        {"op": "set_cell_shading", "table": table["locator"], "cell": cell["locator"], "color": str(operation.get("fill") or _CALLOUT_FILL)},
        {"op": "set_cell_borders", "table": table["locator"], "cell": cell["locator"], "color": str(operation.get("border_color") or _CALLOUT_RULE), "line_type": "SOLID"},
        {
            "op": "set_cell_margin",
            "table": table["locator"],
            "cell": cell["locator"],
            "left": 720,
            "right": 720,
            "top": 520,
            "bottom": 520,
        },
    ]
    receipt = apply_table_edits_atomic(
        candidate,
        ops,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    paragraph_targets = [str(x) for x in operation.get("paragraph_targets", []) if x]
    paragraph_receipt = None
    if paragraph_targets:
        paragraph_receipt = apply_nested_paragraph_alignment_atomic(
            candidate,
            paragraph_targets,
            alignment="LEFT",
            validator=None,
        )
    return {
        "table": table["locator"],
        "cell": cell["locator"],
        "table_receipt": receipt,
        "paragraph_receipt": paragraph_receipt,
    }


def apply_document_design_repairs_atomic(
    path: Path | str,
    repair_plan: dict,
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    path = Path(path)
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not isinstance(repair_plan, dict):
        raise ValueError("repair_plan must be an object")
    actions = [x for x in (repair_plan.get("actions") or []) if x.get("status") == "EXECUTABLE"]
    if not actions:
        raise ValueError("repair plan contains no executable actions")
    if len(actions) > 160:
        raise ValueError("too many executable repair actions")

    before_doc = build_document_map(path)
    before_fmt = build_formatting_map(path)
    before_tables = build_table_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p340-repair-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    shutil.copy2(path, candidate)
    transcripts: list[dict] = []
    validation = None

    try:
        for action in actions:
            operation = dict(action.get("operation") or {})
            name = str(operation.get("op") or "")
            if name in {
                "set_cell_margin", "set_cell_shading", "set_cell_borders", "set_cell_properties",
                "set_column_widths", "autofit_columns",
            }:
                receipt = apply_table_edits_atomic(
                    candidate,
                    [operation],
                    expected_revision=1,
                    current_revision=1,
                    validator=None,
                )
            elif name == "align_nested_table_paragraphs":
                receipt = apply_nested_paragraph_alignment_atomic(
                    candidate,
                    list(operation.get("targets") or []),
                    alignment=str(operation.get("alignment") or "LEFT"),
                    validator=None,
                )
            elif name == "style_table_header":
                receipt = _style_table_header(candidate, operation)
            elif name == "set_table_padding":
                receipt = _set_table_padding(candidate, operation)
            elif name == "style_semantic_callout":
                receipt = _style_semantic_callout(candidate, operation)
            elif name == "style_section_headings":
                targets = [str(x) for x in operation.get("targets", []) if x]
                fmt_ops = [
                    {
                        "op": "set_paragraph_format",
                        "target": target,
                        "format": {
                            "spacing_before_pt": 14,
                            "spacing_after_pt": 7,
                            "keep_with_next": True,
                            "bottom_border": True,
                            "border_color": _HEADER_RULE,
                            "border_width": 0.5,
                        },
                    }
                    for target in targets
                ]
                receipt = apply_formatting_atomic(
                    candidate,
                    fmt_ops,
                    expected_revision=1,
                    current_revision=1,
                    validator=None,
                )
            elif name == "rebalance_table_columns":
                receipt = apply_table_edits_atomic(
                    candidate,
                    [{
                        "op": "set_column_widths",
                        "table": str(operation.get("table") or ""),
                        "widths": list(operation.get("widths") or []),
                    }],
                    expected_revision=1,
                    current_revision=1,
                    validator=None,
                )
            else:
                raise ValueError(f"unsupported P3.40 executable repair operation: {name}")
            transcripts.append({
                "action": action.get("action"),
                "reason": action.get("reason"),
                "operation": operation,
                "receipt": receipt,
            })

        after_doc = build_document_map(candidate)
        if before_doc["semantic_sha256"] != after_doc["semantic_sha256"]:
            raise ValueError("editorial repair transaction changed semantic text")
        if before_doc["structure_sha256"] != after_doc["structure_sha256"]:
            raise ValueError("editorial repair transaction changed paragraph structure")
        after_fmt = build_formatting_map(candidate)
        after_tables = build_table_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.40/design-repair-receipt/v1",
        "phase": "P3.40",
        "repair_plan_sha256": repair_plan.get("repair_plan_sha256"),
        "action_count": len(actions),
        "transcripts": transcripts,
        "before": {
            "semantic_sha256": before_doc["semantic_sha256"],
            "structure_sha256": before_doc["structure_sha256"],
            "formatting_sha256": before_fmt["formatting_sha256"],
            "table_format_sha256": before_tables["table_format_sha256"],
        },
        "after": {
            "semantic_sha256": after_doc["semantic_sha256"],
            "structure_sha256": after_doc["structure_sha256"],
            "formatting_sha256": after_fmt["formatting_sha256"],
            "table_format_sha256": after_tables["table_format_sha256"],
        },
        "semantic_changed": False,
        "structure_changed": False,
        "formatting_changed": before_fmt["formatting_sha256"] != after_fmt["formatting_sha256"],
        "table_format_changed": before_tables["table_format_sha256"] != after_tables["table_format_sha256"],
        "validation": validation,
        "atomic_commit": True,
        "authority": "EXECUTED_NATIVE_REPAIR_NOT_RENDERED_IMPROVEMENT_CLAIM",
    }
    result["repair_receipt_sha256"] = _sha(result)
    return result


def compare_design_diagnostics(before: dict, after: dict) -> dict:
    def keyed(diag: dict) -> dict[tuple[str, str], dict]:
        out = {}
        for item in diag.get("findings", []) or []:
            out[(str(item.get("code") or ""), str(item.get("scope") or ""))] = item
        return out

    b = keyed(before)
    a = keyed(after)
    resolved = sorted([{"code": k[0], "scope": k[1]} for k in b if k not in a], key=lambda x: (x["code"], x["scope"]))
    introduced = sorted([{"code": k[0], "scope": k[1]} for k in a if k not in b], key=lambda x: (x["code"], x["scope"]))
    remaining = sorted([{"code": k[0], "scope": k[1]} for k in a if k in b], key=lambda x: (x["code"], x["scope"]))
    high = {"HIGH", "CRITICAL"}
    before_high = sum(str(x.get("severity") or "").upper() in high for x in before.get("findings", []) or [])
    after_high = sum(str(x.get("severity") or "").upper() in high for x in after.get("findings", []) or [])
    before_render = (before.get("render_page_diagnostic") or {})
    after_render = (after.get("render_page_diagnostic") or {})
    native_rerender_verified = bool(
        before_render.get("world_contact_valid")
        and after_render.get("world_contact_valid")
    )
    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.40/before-after-design-comparison/v1",
        "phase": "P3.40",
        "before_diagnostic_sha256": before.get("diagnostic_sha256"),
        "after_diagnostic_sha256": after.get("diagnostic_sha256"),
        "resolved": resolved,
        "introduced": introduced,
        "remaining": remaining,
        "before_high_count": before_high,
        "after_high_count": after_high,
        "high_severity_nonincrease": after_high <= before_high,
        "native_rerender_verified": native_rerender_verified,
        "render_claim": (
            "HANCOM_NATIVE_BEFORE_AFTER_AVAILABLE"
            if native_rerender_verified
            else "POST_REPAIR_NATIVE_RENDER_EVIDENCE_PENDING_OR_NON_NATIVE"
        ),
        "authority": "DIAGNOSTIC_COMPARISON_NOT_HUMAN_AESTHETIC_VERDICT",
    }
    result["comparison_sha256"] = _sha(result)
    return result
