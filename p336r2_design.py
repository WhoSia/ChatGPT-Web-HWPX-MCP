from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from p22_formatting import build_formatting_map
from p323_advanced_tables import build_advanced_table_map
from p336_corpus import inspect_native_style


SCHEMA = "chatgpt-web-hwpx-mcp/p3.36-r2/design-quality/v1"
TARGET_MODES = {"INSTITUTIONAL_COMPATIBILITY", "POLISHED_REPORT", "EXPLICIT"}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def design_quality_contract() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "P3.36-R2",
        "target_modes": sorted(TARGET_MODES),
        "authority_ladder": [
            "NATIVE_STRUCTURE_FACT",
            "OBSERVED_PUBLIC_DOCUMENT_CONVENTION",
            "PAIRED_VISUAL_CONTROL",
            "EXPLICIT_HUMAN_DESIGN_TARGET",
        ],
        "role_policy": (
            "Presentation-role hypotheses are derived from position, formatting, and structural-container evidence. "
            "A conservative second pass may recover at most one nested-container TITLE/HEADING only when the primary "
            "pass finds zero hierarchy. Native semantic role evidence is never overwritten."
        ),
        "aesthetic_policy": (
            "Public-document prevalence can guide compatibility and engineering priorities, "
            "but cannot become a beauty score or override an explicit polished-design request."
        ),
        "benchmark_policy": (
            "Generated-document evaluation reports separate mechanical gates, multi-container hierarchy recovery, "
            "and design-target checks. It does not emit one opaque aesthetic score."
        ),
    }


def _dominant_alignment(paragraph_property: dict | None) -> str:
    if not isinstance(paragraph_property, dict):
        return "UNKNOWN"
    alignment = paragraph_property.get("alignment")
    if not isinstance(alignment, dict):
        return "UNKNOWN"
    return str(alignment.get("horizontal") or "UNKNOWN").upper()


def _native_heading(paragraph_property: dict | None) -> bool:
    if not isinstance(paragraph_property, dict):
        return False
    heading = paragraph_property.get("heading")
    if not isinstance(heading, dict):
        return False
    return str(heading.get("type") or "NONE").upper() not in {"", "NONE"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paragraph_container_contexts(path: Path) -> list[dict]:
    """Recover structural ancestry without reading or classifying prose semantics."""
    contexts: list[dict] = []
    with zipfile.ZipFile(path, "r") as archive:
        section_names = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"Contents/section\d+\.xml", name)
        )
        for section_name in section_names:
            root = ElementTree.fromstring(archive.read(section_name))
            parents = {child: parent for parent in root.iter() for child in parent}
            for paragraph in root.iter():
                if _local(paragraph.tag) != "p":
                    continue
                chain: list[str] = []
                current = paragraph
                for _ in range(16):
                    parent = parents.get(current)
                    if parent is None:
                        break
                    chain.append(_local(parent.tag))
                    current = parent
                contexts.append({
                    "immediate_container": chain[0] if chain else "unknown",
                    "container_path": chain[:8],
                    "in_table": "tbl" in chain,
                    "in_cell": "tc" in chain,
                    "nested_container": bool(chain and chain[0] != "sec"),
                })
    return contexts


def paragraph_features_from_hwpx(path: Path | str) -> list[dict]:
    """Extract formatting/structure-only paragraph features; prose semantics are intentionally ignored."""
    path = Path(path)
    formatted = build_formatting_map(path)
    contexts = _paragraph_container_contexts(path)
    source_paragraphs = list(formatted.get("paragraphs", []))
    if len(contexts) != len(source_paragraphs):
        contexts = [{} for _ in source_paragraphs]

    rows: list[dict] = []
    for index, paragraph in enumerate(source_paragraphs):
        text = str(paragraph.get("direct_text") or "")
        if not text.strip():
            continue
        total = 0
        weighted_size = 0.0
        bold_chars = 0
        for run in paragraph.get("runs", []):
            run_text = str(run.get("text") or "")
            weight = len(run_text)
            if not weight:
                continue
            total += weight
            style = run.get("style") or {}
            size = style.get("size_pt")
            if isinstance(size, (int, float)):
                weighted_size += float(size) * weight
            if style.get("bold") is True:
                bold_chars += weight
        context = contexts[index] if index < len(contexts) else {}
        rows.append({
            "locator": paragraph.get("locator"),
            "index": index,
            "section_index": paragraph.get("section_index"),
            "paragraph_index": paragraph.get("paragraph_index"),
            "body_global_index": paragraph.get("body_global_index"),
            "text_characters": len(text),
            "size_pt": round(weighted_size / max(1, total), 4) if weighted_size else None,
            "bold_share": round(bold_chars / max(1, total), 6),
            "alignment": _dominant_alignment(paragraph.get("paragraph_property")),
            "native_heading": _native_heading(paragraph.get("paragraph_property")),
            "container": paragraph.get("container"),
            "container_path": list(context.get("container_path") or []),
            "in_table": bool(context.get("in_table")),
            "in_cell": bool(context.get("in_cell")),
            "nested_container": bool(context.get("nested_container")),
        })
    return rows

def infer_presentation_roles(paragraphs: list[dict]) -> dict:
    if not isinstance(paragraphs, list) or not paragraphs:
        raise ValueError("PRESENTATION_ROLE_FEATURES_REQUIRED")
    if len(paragraphs) > 5000:
        raise ValueError("PRESENTATION_ROLE_FEATURE_LIMIT")

    sizes = [
        float(row["size_pt"])
        for row in paragraphs
        if isinstance(row.get("size_pt"), (int, float)) and float(row["size_pt"]) > 0
    ]
    median_size = statistics.median(sizes) if sizes else 11.0

    def is_nested(row: dict) -> bool:
        if bool(row.get("nested_container")) or bool(row.get("in_table")):
            return True
        container = str(row.get("container") or "")
        return container in {"subList", "tc", "tbl", "drawText", "textBox", "caption", "note"}

    body_rows = [row for row in paragraphs if not is_nested(row)]
    body_count = max(1, len(body_rows))
    hypotheses = []
    title_taken = False

    for ordinal, row in enumerate(paragraphs):
        size = float(row.get("size_pt") or median_size)
        ratio = size / max(0.1, median_size)
        bold = float(row.get("bold_share") or 0.0)
        alignment = str(row.get("alignment") or "UNKNOWN").upper()
        native_heading = bool(row.get("native_heading"))
        nested = is_nested(row)
        body_position = ordinal / max(1, body_count - 1)

        role = "CONTAINER_TEXT" if nested else "BODY"
        confidence = 0.58 if nested else 0.55
        evidence: list[str] = []

        if nested:
            evidence.append("NESTED_CONTAINER")
            if bool(row.get("in_table")):
                evidence.append("TABLE_ANCESTRY")
        else:
            title_signal = (
                body_position <= 0.12
                and ratio >= 1.30
                and (bold >= 0.45 or alignment == "CENTER")
            )
            if title_signal and not title_taken:
                role = "TITLE"
                title_taken = True
                confidence = min(0.98, 0.70 + min(0.18, (ratio - 1.30) * 0.35) + (0.08 if bold >= 0.7 else 0))
                evidence.extend(["EARLY_POSITION", "SIZE_CONTRAST"])
                if bold >= 0.45:
                    evidence.append("BOLD_CONTRAST")
                if alignment == "CENTER":
                    evidence.append("CENTER_ALIGNMENT")
            elif native_heading or (ratio >= 1.12 and bold >= 0.35):
                role = "HEADING"
                confidence = 0.94 if native_heading else min(0.90, 0.64 + (ratio - 1.12) * 0.45 + bold * 0.12)
                evidence.append("NATIVE_HEADING_METADATA" if native_heading else "SIZE_AND_BOLD_CONTRAST")
            elif bool(row.get("adjacent_object")) and ratio <= 1.0:
                role = "CAPTION"
                confidence = 0.72
                evidence.append("OBJECT_ADJACENCY")
            else:
                evidence.append("BODY_FALLBACK")

        hypotheses.append({
            "locator": row.get("locator"),
            "presentation_role": role,
            "confidence": round(float(confidence), 6),
            "evidence": evidence,
            "native_heading": native_heading,
            "size_ratio_to_median": round(ratio, 6),
            "bold_share": round(bold, 6),
            "alignment": alignment,
            "container": row.get("container"),
            "in_table": bool(row.get("in_table")),
            "nested_container": nested,
        })

    primary_hierarchy_count = sum(
        item["presentation_role"] in {"TITLE", "HEADING"} for item in hypotheses
    )
    recovery = {
        "eligible": primary_hierarchy_count == 0,
        "applied": False,
        "strategy": "NONE",
        "recovered_locator": None,
    }

    if primary_hierarchy_count == 0:
        limit = min(len(paragraphs), max(8, min(24, math.ceil(len(paragraphs) * 0.08))))
        title_candidates: list[tuple[float, int]] = []
        heading_candidates: list[tuple[float, int]] = []
        for ordinal, row in enumerate(paragraphs[:limit]):
            if not is_nested(row):
                continue
            size = float(row.get("size_pt") or median_size)
            ratio = size / max(0.1, median_size)
            bold = float(row.get("bold_share") or 0.0)
            alignment = str(row.get("alignment") or "UNKNOWN").upper()
            early_bonus = max(0.0, (limit - ordinal) / max(1, limit))

            if alignment == "CENTER" and ratio >= 1.15:
                score = ratio + early_bonus * 0.10 + bold * 0.05
                title_candidates.append((score, ordinal))
            if alignment == "CENTER" and ratio >= 0.90 and bold >= 0.70:
                score = bold + ratio * 0.10 + early_bonus * 0.05
                heading_candidates.append((score, ordinal))

        recovered_index = None
        recovered_role = None
        recovered_strategy = None
        if title_candidates:
            _, recovered_index = max(title_candidates)
            recovered_role = "TITLE"
            recovered_strategy = "EARLY_NESTED_SIZE_CENTER_TITLE"
        elif heading_candidates:
            _, recovered_index = max(heading_candidates)
            recovered_role = "HEADING"
            recovered_strategy = "EARLY_NESTED_BOLD_CENTER_HEADER"

        if recovered_index is not None and recovered_role is not None:
            item = hypotheses[recovered_index]
            item["presentation_role"] = recovered_role
            item["confidence"] = 0.82 if recovered_role == "TITLE" else 0.74
            item["evidence"] = list(dict.fromkeys(
                item["evidence"]
                + [
                    "RECOVERY_AFTER_EMPTY_PRIMARY_HIERARCHY",
                    "EARLY_DOCUMENT_POSITION",
                    "CENTER_ALIGNMENT",
                    "SIZE_CONTRAST" if recovered_role == "TITLE" else "BOLD_HEADER_CONTRAST",
                ]
            ))
            recovery = {
                "eligible": True,
                "applied": True,
                "strategy": recovered_strategy,
                "recovered_locator": item.get("locator"),
            }

    role_names = ("TITLE", "HEADING", "BODY", "CAPTION", "TABLE_TEXT", "CONTAINER_TEXT")
    counts = {
        role: sum(item["presentation_role"] == role for item in hypotheses)
        for role in role_names
    }
    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.36-r2/presentation-role-hypotheses/v2",
        "median_size_pt": round(float(median_size), 4),
        "hypotheses": hypotheses,
        "counts": counts,
        "primary_hierarchy_count": primary_hierarchy_count,
        "final_hierarchy_count": counts["TITLE"] + counts["HEADING"],
        "recovery": recovery,
        "authority": "PRESENTATION_ROLE_HYPOTHESIS_NOT_NATIVE_SEMANTIC_FACT",
        "content_semantics_used": False,
        "recovery_policy": (
            "Nested-container recovery activates only when the primary body/native pass finds zero "
            "TITLE/HEADING hypotheses; at most one nested TITLE or HEADING is promoted."
        ),
    }
    result["profile_sha256"] = _sha(result)
    return result

def _merge_format(base: dict | None, extra: dict | None) -> dict:
    out = dict(base or {})
    out.update(dict(extra or {}))
    return out


def compile_design_plan(plan: dict, mode: str = "POLISHED_REPORT", *, explicit_tokens: dict | None = None) -> dict:
    """Compile a P3.21 plan into one explicit design target without changing its logical content."""
    if not isinstance(plan, dict):
        raise ValueError("DOCUMENT_PLAN_REQUIRED")
    mode = str(mode or "").upper()
    if mode not in TARGET_MODES:
        raise ValueError("INVALID_DESIGN_TARGET_MODE")
    result = deepcopy(plan)
    blocks = result.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("DOCUMENT_PLAN_BLOCKS_REQUIRED")

    if mode == "INSTITUTIONAL_COMPATIBILITY":
        result["preset"] = "institutional-report"
        table_defaults = {
            "page_break": "CELL",
            "border_color": "808080",
        }
        authority = "OBSERVED_PUBLIC_DOCUMENT_CONVENTION"
    elif mode == "POLISHED_REPORT":
        result["preset"] = "polished-report"
        table_defaults = {
            "page_break": "CELL",
            "border_color": "AEB7C2",
        }
        authority = "EXPLICIT_HUMAN_DESIGN_TARGET"
    else:
        tokens = dict(explicit_tokens or {})
        preset = str(tokens.get("preset") or result.get("preset") or "default")
        result["preset"] = preset
        table_defaults = dict(tokens.get("table") or {})
        authority = "EXPLICIT_HUMAN_DESIGN_TARGET"
        for block in blocks:
            kind = block.get("type")
            if kind == "title":
                block["run_format"] = _merge_format(block.get("run_format"), tokens.get("title_run"))
                block["paragraph_format"] = _merge_format(block.get("paragraph_format"), tokens.get("title_paragraph"))
            elif kind == "heading":
                heading_tokens = (tokens.get("heading") or {}).get(str(block.get("level", 1)), {})
                block["run_format"] = _merge_format(block.get("run_format"), heading_tokens.get("run"))
                block["paragraph_format"] = _merge_format(block.get("paragraph_format"), heading_tokens.get("paragraph"))
            elif kind in {"paragraph", "list_item"}:
                block["run_format"] = _merge_format(block.get("run_format"), tokens.get("body_run"))
                block["paragraph_format"] = _merge_format(block.get("paragraph_format"), tokens.get("body_paragraph"))

    for block in blocks:
        if block.get("type") != "table":
            continue
        table_format = dict(table_defaults)
        table_format.update(dict(block.get("table_format") or {}))
        if bool(block.get("first_row_header")):
            table_format["first_row_header"] = True
            table_format.setdefault("repeat_header", True)
        block["table_format"] = table_format

    receipt = {
        "schema": "chatgpt-web-hwpx-mcp/p3.36-r2/design-plan-receipt/v1",
        "mode": mode,
        "authority": authority,
        "aesthetic_semantics": (
            "Institutional mode is compatibility-oriented. Polished/explicit modes are design targets "
            "and are not constrained to imitate prevalent public-document aesthetics."
        ),
        "plan": result,
    }
    receipt["design_plan_sha256"] = _sha({
        "mode": mode,
        "authority": authority,
        "plan": result,
    })
    return receipt


def evaluate_generated_document(path: Path | str, mode: str = "POLISHED_REPORT") -> dict:
    """Mechanically evaluate one generated HWPX; no opaque beauty score is produced."""
    path = Path(path)
    mode = str(mode or "").upper()
    if mode not in TARGET_MODES:
        raise ValueError("INVALID_DESIGN_TARGET_MODE")

    native = inspect_native_style(path)
    formatting_features = paragraph_features_from_hwpx(path) if native.get("status") == "PASS" else []
    roles = infer_presentation_roles(formatting_features) if formatting_features else None
    tables = build_advanced_table_map(path) if native.get("status") == "PASS" else {"tables": [], "table_count": 0}

    table_payloads = list(tables.get("tables", []))
    long_tables = [t for t in table_payloads if int(t.get("rows") or 0) >= 12]
    mechanically_valid_tables = all(
        int(t.get("rows") or 0) >= 1 and int(t.get("cols") or 0) >= 1
        for t in table_payloads
    )
    pagination_ok = all(
        bool(t.get("repeat_header")) or str(t.get("page_break") or "").upper() in {"CELL", "TABLE"}
        for t in long_tables
    )

    hierarchy_count = 0 if roles is None else (
        int(roles["counts"].get("TITLE", 0)) + int(roles["counts"].get("HEADING", 0))
    )
    gates = [
        {
            "gate": "NATIVE_STRUCTURE_READABLE",
            "status": "PASS" if native.get("status") == "PASS" else "HOLD",
            "evidence": native.get("status"),
        },
        {
            "gate": "TABLE_STRUCTURE_VALID",
            "status": "PASS" if mechanically_valid_tables else "FAIL",
            "evidence": {"tables": len(table_payloads)},
        },
        {
            "gate": "LONG_TABLE_PAGINATION",
            "status": "PASS" if pagination_ok else "FAIL",
            "evidence": {"long_tables": len(long_tables)},
        },
        {
            "gate": "PRESENTATION_HIERARCHY_SIGNAL",
            "status": "PASS" if hierarchy_count > 0 else "WARN",
            "evidence": {"title_or_heading_hypotheses": hierarchy_count},
        },
        {
            "gate": "MULTI_CONTAINER_HIERARCHY_RECOVERY",
            "status": (
                "PASS"
                if roles is not None and bool(roles.get("recovery", {}).get("applied"))
                else "NOT_NEEDED"
                if roles is not None and int(roles.get("primary_hierarchy_count", 0)) > 0
                else "WARN"
            ),
            "evidence": None if roles is None else dict(roles.get("recovery") or {}),
        },
    ]
    hard_fail = any(item["status"] == "FAIL" for item in gates)
    hold = any(item["status"] == "HOLD" for item in gates)

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.36-r2/generated-document-benchmark/v1",
        "mode": mode,
        "mechanical_verdict": "HOLD" if hold else "FAIL" if hard_fail else "PASS",
        "aesthetic_verdict": "NOT_ADJUDICATED",
        "gates": gates,
        "native_observation": native,
        "presentation_roles": roles,
        "table_summary": {
            "tables": len(table_payloads),
            "long_tables": len(long_tables),
            "repeat_header_tables": sum(bool(t.get("repeat_header")) for t in table_payloads),
        },
        "authority": "MECHANICAL_AND_DESIGN_TARGET_CHECKS_NOT_BEAUTY_SCORE",
    }
    result["benchmark_sha256"] = _sha(result)
    return result
