from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from p22_formatting import build_formatting_map
from p28_tables import build_table_map
from p336r2_design import paragraph_features_from_hwpx, infer_presentation_roles
from p338_rich_builder import evaluate_preview_readiness


SCHEMA = "chatgpt-web-hwpx-mcp/p3.39/design-intelligence/v1"

ARCHETYPES: dict[str, dict[str, Any]] = {
    "POLISHED_REPORT": {
        "design_target": "POLISHED_EDITORIAL",
        "density": "MODERATE",
        "accent_strength": "RESTRAINED",
        "table_style": "ANALYTICAL",
        "callout_style": "QUIET_EMPHASIS",
        "icons": "AVOID_BY_DEFAULT",
        "recommended_roles": [
            "TITLE", "SUBTITLE", "EXECUTIVE_SUMMARY", "KEY_JUDGMENT",
            "SECTION", "ANALYTICAL_TABLE", "RISK_CALLOUT", "CONCLUSION", "REFERENCES",
        ],
    },
    "RESEARCH_BRIEF": {
        "design_target": "POLISHED_EDITORIAL",
        "density": "MODERATE",
        "accent_strength": "RESTRAINED",
        "table_style": "ANALYTICAL",
        "callout_style": "QUIET_EMPHASIS",
        "icons": "AVOID_BY_DEFAULT",
        "recommended_roles": [
            "TITLE", "EXECUTIVE_SUMMARY", "KEY_JUDGMENT", "SECTION",
            "ANALYTICAL_TABLE", "CONCLUSION", "REFERENCES",
        ],
    },
    "INSTITUTIONAL_REPORT": {
        "design_target": "INSTITUTIONAL_COMPATIBILITY",
        "density": "MODERATE_HIGH",
        "accent_strength": "LOW",
        "table_style": "FORMAL",
        "callout_style": "BORDERED_NOTE",
        "icons": "NO",
        "recommended_roles": [
            "TITLE", "DOCUMENT_META", "SECTION", "FORMAL_TABLE", "CONCLUSION",
        ],
    },
    "ACADEMIC_REPORT": {
        "design_target": "ACADEMIC",
        "density": "MODERATE_HIGH",
        "accent_strength": "LOW",
        "table_style": "ACADEMIC",
        "callout_style": "MINIMAL",
        "icons": "NO",
        "recommended_roles": [
            "TITLE", "ABSTRACT", "SECTION", "ANALYTICAL_TABLE", "EQUATION",
            "CONCLUSION", "REFERENCES",
        ],
    },
    "FORM": {
        "design_target": "FORM_FIDELITY",
        "density": "STRUCTURED",
        "accent_strength": "LOW",
        "table_style": "FORM",
        "callout_style": "NONE",
        "icons": "NO",
        "recommended_roles": ["TITLE", "FORM_SECTION", "FIELD_TABLE", "SIGNATURE"],
    },
}

SEMANTIC_ROLES = {
    "TITLE", "SUBTITLE", "DOCUMENT_META", "ABSTRACT", "EXECUTIVE_SUMMARY",
    "KEY_JUDGMENT", "SECTION", "SUBSECTION", "BODY", "ANALYTICAL_TABLE",
    "FORMAL_TABLE", "FIELD_TABLE", "RISK_CALLOUT", "CALLOUT", "EQUATION",
    "FIGURE", "CAPTION", "CONCLUSION", "REFERENCES", "FORM_SECTION", "SIGNATURE",
}

PRINCIPLES = [
    {
        "id": "SEMANTIC_VISUAL_CONGRUENCE",
        "rule": "Different semantic importance must receive perceptibly different visual treatment.",
        "operational_test": "Do not rely on numbering alone to distinguish title, section, callout and conclusion.",
    },
    {
        "id": "READING_GEOMETRY",
        "rule": "Reading flow outranks geometric symmetry for prose-like content.",
        "operational_test": "Long table-cell prose should default to left/top alignment; center alignment is for short labels.",
    },
    {
        "id": "DENSITY_BUDGET",
        "rule": "Information-dense blocks need explicit width, padding and whitespace budget.",
        "operational_test": "Dense tables must not achieve fit by collapsing cell padding or font size first.",
    },
    {
        "id": "MULTI_CHANNEL_HIERARCHY",
        "rule": "Important hierarchy should use at least two channels among size, weight, whitespace, rule/background and placement.",
        "operational_test": "A section heading differentiated only by numbering is weak.",
    },
    {
        "id": "NARRATIVE_VISUAL_AGREEMENT",
        "rule": "Visual prominence and narrative position must agree.",
        "operational_test": "A formal conclusion belongs after the main development even if an executive summary appears first.",
    },
    {
        "id": "RESTRAINT",
        "rule": "Color, boxes and icons exist to encode meaning, not decorate empty space.",
        "operational_test": "Professional reports avoid emoji/icon ornament unless the document archetype explicitly benefits.",
    },
    {
        "id": "DESIGN_SYSTEM_OVER_MICROFORMAT",
        "rule": "Agents choose archetype and semantic intent; compilers choose most raw formatting values.",
        "operational_test": "Prefer POLISHED_REPORT + ANALYTICAL_TABLE over dozens of independent color/font calls.",
    },
    {
        "id": "VERIFY_BEFORE_REPAIR",
        "rule": "Inspect structure and evidence before mutation; repair the smallest proven defect.",
        "operational_test": "Diagnostics produce locator-bound findings and repair plans rather than global restyling by default.",
    },
    {
        "id": "RENDER_EVIDENCE_LAYERING",
        "rule": "Static structure, external render and human visual review are distinct authorities.",
        "operational_test": "Never call a static geometry check a rendered visual verdict.",
    },
    {
        "id": "TOOL_ECONOMY",
        "rule": "Expose high-level authoring workflows first and low-level primitives as escape hatches.",
        "operational_test": "A normal report should not require the agent to discover dozens of formatting primitives.",
    },
]


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def design_intelligence_contract() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "P3.39",
        "purpose": "AGENTIC_DOCUMENT_DESIGN_INTELLIGENCE_NOT_BEAUTY_SCORING",
        "principles": PRINCIPLES,
        "archetypes": ARCHETYPES,
        "semantic_roles": sorted(SEMANTIC_ROLES),
        "evidence_ladder": [
            "NATIVE_STRUCTURE_FACT",
            "STATIC_DESIGN_DIAGNOSTIC",
            "EXTERNAL_RENDER_OBSERVATION",
            "HANCOM_NATIVE_RENDER_EVIDENCE",
            "HUMAN_VISUAL_REVIEW",
            "EXPLICIT_HUMAN_DESIGN_TARGET",
        ],
        "agent_workflow": [
            "CLASSIFY_DOCUMENT_ARCHETYPE",
            "PLAN_SEMANTIC_ROLES_AND_NARRATIVE_ORDER",
            "COMPILE_DESIGN_STRATEGY",
            "BUILD_RICH_NATIVE_DOCUMENT",
            "RUN_STATIC_PREVIEW_AND_DESIGN_DIAGNOSTICS",
            "RENDER_WHEN_RENDER_AUTHORITY_IS_AVAILABLE",
            "MERGE_RENDER_OR_HUMAN_CRITIQUE",
            "PLAN_MINIMAL_REPAIRS",
            "APPLY_ONLY_SUPPORTED_REPAIRS",
            "RE-DIAGNOSE_THEN_DELIVER",
        ],
        "tool_policy": {
            "preferred_high_level": [
                "prepare_authoring_strategy",
                "create_rich_document_and_deliver",
                "diagnose_document_design",
                "plan_document_design_repairs",
            ],
            "escape_hatches": [
                "apply_formatting",
                "apply_table_edits",
                "apply_advanced_table_edits",
            ],
            "rule": "Use low-level tools only after a diagnostic or explicit user instruction identifies the target.",
        },
        "render_policy": {
            "static_only": "STATIC_LAYOUT_AND_EDITORIAL_RISK_AUTHORITY",
            "external_render": "RENDER_OBSERVATION_AUTHORITY_ONLY",
            "hancom_native": "HANCOM_NATIVE_RENDER_AUTHORITY_WHEN_CUSTODY_IS_VALID",
            "human_review": "HUMAN_VISUAL_REVIEW_GROUND_TRUTH_NOT_UNIVERSAL_AESTHETIC_NORM",
        },
    }


def _normalize_role(value: Any) -> str:
    role = str(value or "").strip().upper()
    if role not in SEMANTIC_ROLES:
        raise ValueError(f"unsupported semantic role: {role}")
    return role


def prepare_authoring_strategy(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("authoring strategy spec must be an object")
    archetype = str(spec.get("archetype") or "POLISHED_REPORT").strip().upper()
    if archetype not in ARCHETYPES:
        raise ValueError("unsupported document archetype")
    defaults = ARCHETYPES[archetype]

    outline_raw = spec.get("semantic_outline") or []
    if not isinstance(outline_raw, list):
        raise ValueError("semantic_outline must be a list")
    outline = [_normalize_role(item) for item in outline_raw]

    warnings: list[dict] = []
    if outline:
        conclusion_positions = [i for i, role in enumerate(outline) if role == "CONCLUSION"]
        section_positions = [i for i, role in enumerate(outline) if role in {"SECTION", "SUBSECTION", "BODY"}]
        if conclusion_positions and section_positions and conclusion_positions[0] < max(section_positions):
            warnings.append({
                "code": "NARRATIVE_ORDER_CONCLUSION_EARLY",
                "severity": "HIGH",
                "message": "Formal conclusion appears before the main development is complete.",
            })
        if archetype in {"POLISHED_REPORT", "RESEARCH_BRIEF"} and "TITLE" not in outline:
            warnings.append({
                "code": "TITLE_ROLE_MISSING",
                "severity": "MEDIUM",
                "message": "A polished report should declare a TITLE semantic role.",
            })
        if outline.count("EXECUTIVE_SUMMARY") > 1:
            warnings.append({
                "code": "MULTIPLE_EXECUTIVE_SUMMARIES",
                "severity": "MEDIUM",
                "message": "Use one executive summary unless the user explicitly requests multiple summary layers.",
            })

    normalized = {
        "archetype": archetype,
        "design_target": str(spec.get("design_target") or defaults["design_target"]).upper(),
        "density": str(spec.get("density") or defaults["density"]).upper(),
        "accent_strength": str(spec.get("accent_strength") or defaults["accent_strength"]).upper(),
        "table_style": str(spec.get("table_style") or defaults["table_style"]).upper(),
        "callout_style": str(spec.get("callout_style") or defaults["callout_style"]).upper(),
        "icons": str(spec.get("icons") or defaults["icons"]).upper(),
        "semantic_outline": outline,
        "recommended_roles": list(defaults["recommended_roles"]),
        "constraints": {
            "table_long_text_alignment": "LEFT_TOP",
            "table_short_label_alignment": "CENTER_ALLOWED",
            "table_min_padding_hwpunit": {"left": 560, "right": 560, "top": 420, "bottom": 420},
            "title_body_size_ratio_target": [1.70, 2.60],
            "section_body_size_ratio_target": [1.18, 1.60],
            "icons_default": defaults["icons"],
            "color_policy": "RESTRAINED_SEMANTIC_ACCENT_ONLY",
            "callout_policy": "USE_FOR_PRIORITY_OR_WARNING_NOT_DECORATION",
        },
        "warnings": warnings,
        "authority": "AGENT_AUTHORING_STRATEGY_NOT_NATIVE_DOCUMENT_FACT",
    }
    normalized["strategy_sha256"] = _sha(normalized)
    return normalized


def _paragraph_index(formatting: dict) -> dict[str, dict]:
    return {str(item["locator"]): item for item in formatting.get("paragraphs", [])}


def _margin_number(paragraph: dict, name: str) -> int:
    prop = paragraph.get("paragraph_property") or {}
    values = prop.get("margin_values") or {}
    raw = (values.get(name) or {}).get("value")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _finding(
    code: str,
    severity: str,
    scope: str,
    evidence: dict,
    *,
    principle: str,
    recommendation: str,
    authority: str = "STATIC_DESIGN_DIAGNOSTIC",
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "principle": principle,
        "evidence": evidence,
        "recommendation": recommendation,
        "authority": authority,
    }


def diagnose_document_design(
    path: Path | str,
    *,
    mode: str = "POLISHED_REPORT",
    render_observation: dict | None = None,
    human_feedback: list[dict] | None = None,
) -> dict:
    path = Path(path)
    formatting = build_formatting_map(path)
    features = paragraph_features_from_hwpx(path)
    roles = infer_presentation_roles(features)
    tables = build_table_map(path)
    preview = evaluate_preview_readiness(path, mode=mode)
    fmt_index = _paragraph_index(formatting)
    role_by_locator = {
        str(item.get("locator")): item
        for item in roles.get("hypotheses", [])
    }

    findings: list[dict] = []
    body_sizes = [
        float(item.get("size_pt") or 0)
        for item in features
        if not item.get("in_table")
        and role_by_locator.get(str(item.get("locator")), {}).get("presentation_role") == "BODY"
        and float(item.get("size_pt") or 0) > 0
    ]
    body_median = statistics.median(body_sizes) if body_sizes else float(roles.get("median_size_pt") or 11.0)

    hierarchy_items = [
        item for item in roles.get("hypotheses", [])
        if item.get("presentation_role") in {"TITLE", "HEADING"}
    ]
    if not hierarchy_items:
        findings.append(_finding(
            "HIERARCHY_SIGNAL_MISSING", "HIGH", "DOCUMENT",
            {"title_or_heading_count": 0},
            principle="SEMANTIC_VISUAL_CONGRUENCE",
            recommendation="Declare title/section semantic roles and compile them through a design system before delivery.",
        ))
    else:
        title_items = [x for x in hierarchy_items if x.get("presentation_role") == "TITLE"]
        if title_items:
            strongest = max(float(x.get("size_ratio_to_median") or 0) for x in title_items)
            if strongest < 1.55:
                findings.append(_finding(
                    "TITLE_CONTRAST_WEAK", "MEDIUM", str(title_items[0].get("locator")),
                    {"max_title_size_ratio": round(strongest, 4), "body_median_size_pt": body_median},
                    principle="MULTI_CHANNEL_HIERARCHY",
                    recommendation="Increase title contrast using size plus whitespace/weight; do not rely on numbering alone.",
                ))
        heading_items = [x for x in hierarchy_items if x.get("presentation_role") == "HEADING"]
        weak_headings = [
            x for x in heading_items
            if float(x.get("size_ratio_to_median") or 0) < 1.10 and float(x.get("bold_share") or 0) < 0.70
        ]
        if weak_headings:
            findings.append(_finding(
                "SECTION_HIERARCHY_CONTRAST_WEAK", "MEDIUM", "MULTIPLE_PARAGRAPHS",
                {"count": len(weak_headings), "locators": [x.get("locator") for x in weak_headings[:20]]},
                principle="MULTI_CHANNEL_HIERARCHY",
                recommendation="Use at least two hierarchy channels such as size+weight or weight+spacing.",
            ))

    centered_long = [
        item for item in features
        if bool(item.get("in_table"))
        and int(item.get("text_characters") or 0) >= 18
        and str(item.get("alignment") or "").upper() == "CENTER"
    ]
    if centered_long:
        findings.append(_finding(
            "TABLE_LONG_TEXT_CENTERED", "HIGH", "TABLE_PARAGRAPHS",
            {
                "count": len(centered_long),
                "locators": [item.get("locator") for item in centered_long[:40]],
                "threshold_characters": 18,
            },
            principle="READING_GEOMETRY",
            recommendation="Left-align prose-like table text; reserve center alignment for short labels.",
        ))

    centered_body = [
        item for item in features
        if not item.get("in_table")
        and int(item.get("text_characters") or 0) >= 60
        and str(item.get("alignment") or "").upper() == "CENTER"
    ]
    if centered_body:
        findings.append(_finding(
            "LONG_BODY_TEXT_CENTERED", "MEDIUM", "BODY_PARAGRAPHS",
            {"count": len(centered_body), "locators": [x.get("locator") for x in centered_body[:20]]},
            principle="READING_GEOMETRY",
            recommendation="Use left or justified alignment for long-form body prose unless the user explicitly requests centered display text.",
        ))

    tight_cells: list[dict] = []
    dense_tables: list[dict] = []
    weak_header_tables: list[dict] = []
    for table in tables.get("tables", []):
        cells = list(table.get("cells", []))
        for cell in cells:
            margin = cell.get("margin") or {}
            if any(int(margin.get(side) or 0) < threshold for side, threshold in {
                "left": 420, "right": 420, "top": 280, "bottom": 280
            }.items()):
                tight_cells.append({
                    "table": table.get("locator"),
                    "cell": cell.get("locator"),
                    "margin": margin,
                })
        text_lengths = [len(str(cell.get("text") or "")) for cell in cells]
        if text_lengths and (statistics.mean(text_lengths) >= 24 or max(text_lengths) >= 80):
            dense_tables.append({
                "table": table.get("locator"),
                "mean_cell_characters": round(statistics.mean(text_lengths), 2),
                "max_cell_characters": max(text_lengths),
                "rows": table.get("rows"),
                "cols": table.get("cols"),
            })
        header_cells = [c for c in cells if str(c.get("header") or "0") == "1"]
        body_cells = [c for c in cells if str(c.get("header") or "0") != "1"]
        if header_cells and body_cells:
            header_refs = {str(c.get("border_fill_id_ref") or "") for c in header_cells}
            body_refs = {str(c.get("border_fill_id_ref") or "") for c in body_cells}
            if len(header_refs) == 1 and header_refs == body_refs:
                weak_header_tables.append({
                    "table": table.get("locator"),
                    "header_border_fill_refs": sorted(header_refs),
                })

    if tight_cells:
        findings.append(_finding(
            "TABLE_CELL_PADDING_TIGHT", "HIGH", "TABLE_CELLS",
            {"count": len(tight_cells), "cells": tight_cells[:80]},
            principle="DENSITY_BUDGET",
            recommendation="Allocate explicit horizontal and vertical cell margins before reducing font size.",
        ))
    if dense_tables:
        findings.append(_finding(
            "TABLE_DENSITY_HIGH", "MEDIUM", "TABLES",
            {"tables": dense_tables[:20]},
            principle="DENSITY_BUDGET",
            recommendation="Rebalance column widths, padding and content chunking; do not center long prose to make dense tables appear symmetric.",
        ))
    if weak_header_tables:
        findings.append(_finding(
            "TABLE_HEADER_CONTRAST_WEAK", "MEDIUM", "TABLES",
            {"tables": weak_header_tables[:20]},
            principle="SEMANTIC_VISUAL_CONGRUENCE",
            recommendation="Give header rows a restrained but distinct treatment such as bold text plus subtle fill/rule contrast.",
        ))

    low_spacing_headings = []
    for item in hierarchy_items:
        if item.get("presentation_role") != "HEADING":
            continue
        locator = str(item.get("locator"))
        paragraph = fmt_index.get(locator) or {}
        before = _margin_number(paragraph, "prev")
        after = _margin_number(paragraph, "next")
        if before <= 0 and after <= 0:
            low_spacing_headings.append(locator)
    if low_spacing_headings:
        findings.append(_finding(
            "SECTION_SEPARATION_WEAK", "MEDIUM", "HEADINGS",
            {"count": len(low_spacing_headings), "locators": low_spacing_headings[:30]},
            principle="MULTI_CHANNEL_HIERARCHY",
            recommendation="Use whitespace as a hierarchy channel: add spacing before/after major headings rather than relying on numbering.",
        ))

    for gate in preview.get("gates", []):
        if str(gate.get("status")) in {"WARN", "FAIL", "HOLD"}:
            findings.append(_finding(
                "PREVIEW_READINESS_" + str(gate.get("gate") or "UNKNOWN"),
                "HIGH" if gate.get("status") in {"FAIL", "HOLD"} else "MEDIUM",
                str(gate.get("locator") or gate.get("section_index") or "DOCUMENT"),
                {"gate": gate},
                principle="VERIFY_BEFORE_REPAIR",
                recommendation="Resolve the mechanical/static preview issue before aesthetic repair.",
                authority="STATIC_LAYOUT_RISK_AUTHORITY",
            ))

    render_status = "NOT_PROVIDED"
    if render_observation is not None:
        if not isinstance(render_observation, dict):
            raise ValueError("render_observation must be an object")
        authority = str(render_observation.get("authority") or "EXTERNAL_RENDER_OBSERVATION")
        render_status = authority
        raw_findings = render_observation.get("findings") or []
        if not isinstance(raw_findings, list):
            raise ValueError("render_observation.findings must be a list")
        for raw in raw_findings:
            if not isinstance(raw, dict):
                raise ValueError("render findings must be objects")
            findings.append(_finding(
                str(raw.get("code") or "RENDER_VISUAL_NOTE").upper(),
                str(raw.get("severity") or "MEDIUM").upper(),
                str(raw.get("scope") or "RENDERED_PAGE"),
                dict(raw.get("evidence") or {}),
                principle=str(raw.get("principle") or "RENDER_EVIDENCE_LAYERING"),
                recommendation=str(raw.get("recommendation") or "Review the rendered page before native repair."),
                authority=authority,
            ))

    if human_feedback is not None:
        if not isinstance(human_feedback, list):
            raise ValueError("human_feedback must be a list")
        for raw in human_feedback:
            if not isinstance(raw, dict):
                raise ValueError("human feedback entries must be objects")
            findings.append(_finding(
                str(raw.get("code") or "HUMAN_VISUAL_NOTE").upper(),
                str(raw.get("severity") or "MEDIUM").upper(),
                str(raw.get("scope") or "DOCUMENT"),
                {"note": str(raw.get("note") or raw.get("summary") or "")},
                principle=str(raw.get("principle") or "RENDER_EVIDENCE_LAYERING"),
                recommendation=str(raw.get("recommendation") or "Preserve the human review as repair evidence."),
                authority="HUMAN_VISUAL_REVIEW",
            ))

    severity_order = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    max_severity = max((severity_order.get(str(x["severity"]).upper(), 1) for x in findings), default=0)
    verdict = "NEEDS_REPAIR" if max_severity >= 3 else "PASS_WITH_WARNINGS" if findings else "PASS"

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.39/design-diagnostic/v1",
        "phase": "P3.39",
        "verdict": verdict,
        "finding_count": len(findings),
        "findings": findings,
        "summary": {
            "body_median_size_pt": round(body_median, 4),
            "paragraph_count": len(features),
            "table_count": len(tables.get("tables", [])),
            "hierarchy_count": len(hierarchy_items),
            "static_preview_verdict": preview.get("verdict"),
            "render_observation": render_status,
        },
        "authorities": sorted({str(item.get("authority")) for item in findings}),
        "aesthetic_score": None,
        "aesthetic_verdict": "NOT_REDUCED_TO_SINGLE_SCORE",
        "authority": "STRUCTURED_DESIGN_DIAGNOSTICS_WITH_EVIDENCE_LAYERING",
    }
    result["diagnostic_sha256"] = _sha(result)
    return result


def plan_design_repairs(diagnostic: dict, *, strategy: dict | None = None) -> dict:
    if not isinstance(diagnostic, dict):
        raise ValueError("diagnostic must be an object")
    findings = diagnostic.get("findings") or []
    if not isinstance(findings, list):
        raise ValueError("diagnostic.findings must be a list")
    strategy = strategy or prepare_authoring_strategy({"archetype": "POLISHED_REPORT"})
    actions: list[dict] = []
    seen: set[tuple] = set()

    for finding in findings:
        code = str(finding.get("code") or "").upper()
        evidence = dict(finding.get("evidence") or {})
        if code == "TABLE_CELL_PADDING_TIGHT":
            for cell in evidence.get("cells", []):
                table = str(cell.get("table") or "")
                locator = str(cell.get("cell") or "")
                key = ("PAD", table, locator)
                if not table or not locator or key in seen:
                    continue
                seen.add(key)
                actions.append({
                    "action": "SET_CELL_PADDING",
                    "status": "EXECUTABLE",
                    "tool": "apply_table_edits",
                    "operation": {
                        "op": "set_cell_margin",
                        "table": table,
                        "cell": locator,
                        **dict(strategy["constraints"]["table_min_padding_hwpunit"]),
                    },
                    "reason": code,
                })
        elif code == "TABLE_LONG_TEXT_CENTERED":
            actions.append({
                "action": "LEFT_ALIGN_LONG_TABLE_TEXT",
                "status": "CAPABILITY_GAP",
                "tool": None,
                "targets": list(evidence.get("locators") or []),
                "reason": code,
                "required_capability": "NESTED_TABLE_PARAGRAPH_HORIZONTAL_ALIGNMENT",
            })
        elif code == "TABLE_HEADER_CONTRAST_WEAK":
            actions.append({
                "action": "APPLY_RESTRAINED_HEADER_CONTRAST",
                "status": "CAPABILITY_GAP",
                "tool": None,
                "targets": [x.get("table") for x in evidence.get("tables", [])],
                "reason": code,
                "required_capability": "ROW_SCOPED_HEADER_FILL_OR_RULE_STYLE",
            })
        elif code in {"TITLE_CONTRAST_WEAK", "SECTION_HIERARCHY_CONTRAST_WEAK", "SECTION_SEPARATION_WEAK"}:
            actions.append({
                "action": "RECOMPILE_HIERARCHY_WITH_DESIGN_SYSTEM",
                "status": "AGENT_PLAN",
                "tool": "compile_document_design",
                "reason": code,
                "guidance": "Use semantic roles and design-system tokens rather than isolated formatting edits.",
            })
        elif code == "TABLE_DENSITY_HIGH":
            actions.append({
                "action": "REBUDGET_TABLE_DENSITY",
                "status": "AGENT_PLAN",
                "tool": None,
                "reason": code,
                "guidance": "Rebalance column widths/content chunking before reducing type size; preserve meaning.",
            })
        elif code.startswith("PREVIEW_READINESS_"):
            actions.append({
                "action": "RESOLVE_MECHANICAL_PREVIEW_GATE",
                "status": "AGENT_PLAN",
                "tool": "evaluate_document_preview_readiness",
                "reason": code,
            })
        elif code == "NARRATIVE_ORDER_CONCLUSION_EARLY":
            actions.append({
                "action": "REORDER_SEMANTIC_OUTLINE",
                "status": "AGENT_PLAN",
                "tool": "prepare_authoring_strategy",
                "reason": code,
                "guidance": "Keep executive summary early; move formal conclusion after the main development.",
            })

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.39/design-repair-plan/v1",
        "phase": "P3.39",
        "diagnostic_sha256": diagnostic.get("diagnostic_sha256"),
        "strategy_sha256": strategy.get("strategy_sha256"),
        "actions": actions,
        "executable_count": sum(x["status"] == "EXECUTABLE" for x in actions),
        "agent_plan_count": sum(x["status"] == "AGENT_PLAN" for x in actions),
        "capability_gap_count": sum(x["status"] == "CAPABILITY_GAP" for x in actions),
        "repair_policy": "MINIMAL_EVIDENCE_BOUND_REPAIR; RE-DIAGNOSE_AFTER_EACH_MUTATING_TRANSACTION",
        "authority": "REPAIR_PLAN_NOT_AUTOMATIC_MUTATION_AUTHORITY",
    }
    result["repair_plan_sha256"] = _sha(result)
    return result
