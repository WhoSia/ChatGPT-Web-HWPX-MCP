from __future__ import annotations

import hashlib
import json
import statistics
from copy import deepcopy
from pathlib import Path
from typing import Any

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
            "Presentation-role hypotheses are derived from position and formatting evidence. "
            "They never replace native semantic role evidence."
        ),
        "aesthetic_policy": (
            "Public-document prevalence can guide compatibility and engineering priorities, "
            "but cannot become a beauty score or override an explicit polished-design request."
        ),
        "benchmark_policy": (
            "Generated-document evaluation reports separate mechanical gates and design-target "
            "checks. It does not emit one opaque aesthetic score."
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


def paragraph_features_from_hwpx(path: Path | str) -> list[dict]:
    """Extract formatting-only paragraph features; prose semantics are intentionally ignored."""
    formatted = build_formatting_map(Path(path))
    rows: list[dict] = []
    for index, paragraph in enumerate(formatted.get("paragraphs", [])):
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
        rows.append({
            "locator": paragraph.get("locator"),
            "index": index,
            "text_characters": len(text),
            "size_pt": round(weighted_size / max(1, total), 4) if weighted_size else None,
            "bold_share": round(bold_chars / max(1, total), 6),
            "alignment": _dominant_alignment(paragraph.get("paragraph_property")),
            "native_heading": _native_heading(paragraph.get("paragraph_property")),
            "container": paragraph.get("container"),
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
    body_rows = [
        row for row in paragraphs
        if not str(row.get("container") or "").lower().startswith("table")
    ]
    body_count = max(1, len(body_rows))

    hypotheses = []
    title_taken = False
    for ordinal, row in enumerate(paragraphs):
        size = float(row.get("size_pt") or median_size)
        ratio = size / max(0.1, median_size)
        bold = float(row.get("bold_share") or 0.0)
        alignment = str(row.get("alignment") or "UNKNOWN").upper()
        native_heading = bool(row.get("native_heading"))
        container = str(row.get("container") or "")
        body_position = ordinal / max(1, body_count - 1)

        role = "BODY"
        confidence = 0.55
        evidence: list[str] = []

        if container and "table" in container.lower():
            role = "TABLE_TEXT"
            confidence = 0.98
            evidence.append("TABLE_CONTAINER")
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
        })

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.36-r2/presentation-role-hypotheses/v1",
        "median_size_pt": round(float(median_size), 4),
        "hypotheses": hypotheses,
        "counts": {
            role: sum(item["presentation_role"] == role for item in hypotheses)
            for role in ("TITLE", "HEADING", "BODY", "CAPTION", "TABLE_TEXT")
        },
        "authority": "PRESENTATION_ROLE_HYPOTHESIS_NOT_NATIVE_SEMANTIC_FACT",
        "content_semantics_used": False,
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
