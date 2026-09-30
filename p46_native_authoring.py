from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from hwpx.equation import EquationConversionError, estimate_equation_size, latex_to_eqedit

PHASE = "P4.6"
PRODUCT = "0.32.0-p4.6"
MAX_BUNDLE_OPS = 80

_STYLE_COMMANDS = {
    r"\mathbb": "BLACKBOARD_BOLD",
    r"\mathcal": "CALLIGRAPHIC",
    r"\mathfrak": "FRAKTUR",
    r"\boldsymbol": "BOLD_SYMBOL",
    r"\mathbf": "BOLD_ROMAN",
}
_KNOWN_UNSUPPORTED = {
    r"\overbrace": "OVERBRACE",
    r"\underbrace": "UNDERBRACE",
    r"\xrightarrow": "LABELED_ARROW",
    r"\xleftarrow": "LABELED_ARROW",
    r"\widehat": "WIDE_ACCENT",
    r"\widetilde": "WIDE_ACCENT",
    r"\limsup": "LIMIT_OPERATOR",
    r"\liminf": "LIMIT_OPERATOR",
}
_ENV_RE = re.compile(r"\\begin\{([^}]+)\}")
_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_SUPPORTED_ENVIRONMENTS = {"matrix", "pmatrix", "bmatrix", "vmatrix", "cases"}
_DOCUMENTED_NATIVE_STYLE_CANDIDATES = {
    r"\\mathbf": {"eqedit": "bold", "status": "DOCUMENTED_NATIVE_NOT_RENDER_CERTIFIED"},
    r"\\boldsymbol": {"eqedit": "bold", "status": "DOCUMENTED_NATIVE_NOT_RENDER_CERTIFIED"},
}
_DOCUMENTED_ENVIRONMENT_CANDIDATES = {
    "align": {"eqedit_family": ["PILE", "LPILE", "RPILE"], "status": "SEMANTIC_MAPPING_UNRESOLVED"},
}
_DEFERRED_DRAWING_OPS = {"group_objects", "ungroup_objects", "insert_generic_shape"}
_CLOSED_TABLE_OPS = {"insert_column_by_clone"}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _features(latex: str) -> list[str]:
    features: set[str] = set()
    if "\\frac" in latex or "\\dfrac" in latex or "\\tfrac" in latex:
        features.add("FRACTION")
    if "\\sqrt" in latex:
        features.add("RADICAL")
    if "^" in latex or "_" in latex:
        features.add("SCRIPTS")
    if any(x in latex for x in ("\\int", "\\iint", "\\iiint", "\\sum", "\\prod")):
        features.add("BIG_OPERATOR")
    if "\\begin{" in latex:
        features.add("ENVIRONMENT")
    if "\\begin{cases}" in latex:
        features.add("CASES")
    if any(f"\\begin{{{name}}}" in latex for name in ("matrix", "pmatrix", "bmatrix", "vmatrix")):
        features.add("MATRIX")
    if "\\left" in latex or "\\right" in latex:
        features.add("SCALABLE_DELIMITER")
    if any(x in latex for x in ("\\bar", "\\vec", "\\hat")):
        features.add("ACCENT")
    if "\\text" in latex or "\\mathrm" in latex:
        features.add("TEXT_LITERAL")
    for command, label in _STYLE_COMMANDS.items():
        if command in latex:
            features.add(label)
    return sorted(features)


def _unsupported_semantics(latex: str, error: str) -> dict:
    for command, label in _STYLE_COMMANDS.items():
        if command in latex:
            candidate = _DOCUMENTED_NATIVE_STYLE_CANDIDATES.get(command)
            return {
                "class": "UNSUPPORTED_MATH_STYLE",
                "feature": label,
                "command": command,
                "policy": "ABSTAIN_NO_SILENT_STYLE_SUBSTITUTION",
                "documented_native_candidate": candidate,
                "documented_equivalent_found": candidate is not None,
            }
    for command, label in _KNOWN_UNSUPPORTED.items():
        if command in latex:
            return {
                "class": "UNSUPPORTED_NATIVE_CONSTRUCT",
                "feature": label,
                "command": command,
                "policy": "ABSTAIN_NO_SILENT_APPROXIMATION",
            }
    envs = _ENV_RE.findall(latex)
    unknown_env = next((env for env in envs if env not in _SUPPORTED_ENVIRONMENTS), None)
    if unknown_env:
        candidate = _DOCUMENTED_ENVIRONMENT_CANDIDATES.get(unknown_env)
        return {
            "class": "UNSUPPORTED_ENVIRONMENT",
            "feature": unknown_env,
            "command": f"\\begin{{{unknown_env}}}",
            "policy": "ABSTAIN_NO_ENVIRONMENT_FLATTENING",
            "documented_native_candidate": candidate,
            "documented_equivalent_found": candidate is not None,
        }
    commands = _COMMAND_RE.findall(latex)
    return {
        "class": "UNSUPPORTED_OR_INVALID_LATEX",
        "feature": commands[0] if commands else "SYNTAX",
        "command": commands[0] if commands else "",
        "policy": "ABSTAIN_AND_PRESERVE_SOURCE",
        "detail": error,
    }


def audit_equation_latex(latex: str, *, base_unit: int = 1100) -> dict:
    if not isinstance(latex, str) or not latex.strip():
        return {
            "latex": latex,
            "supported": False,
            "status": "REJECTED_EMPTY_INPUT",
            "features": [],
            "loss_class": "NOT_AUTHORED",
            "fallback": "PRESERVE_SOURCE_AND_ASK_FOR_EXPLICIT_ALTERNATIVE",
        }
    features = _features(latex)
    try:
        script = latex_to_eqedit(latex)
        width, height = estimate_equation_size(script, base_unit=base_unit)
    except EquationConversionError as exc:
        unsupported = _unsupported_semantics(latex, str(exc))
        return {
            "latex": latex,
            "supported": False,
            "status": unsupported["class"],
            "features": features,
            "unsupported": unsupported,
            "loss_class": "NOT_AUTHORED",
            "fallback": "PRESERVE_LATEX_SOURCE_NO_AUTOMATIC_IMAGE_OR_TEXT_SUBSTITUTE",
            "native_render_authority": "NONE_FOR_THIS_EXPRESSION",
        }
    return {
        "latex": latex,
        "supported": True,
        "status": "NATIVE_EQEDIT_VERIFIED_TOKEN_SET",
        "features": features,
        "eqedit_script": script,
        "eqedit_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "estimated_hwpunit": {"width": int(width), "height": int(height), "base_unit": int(base_unit)},
        "loss_class": "NO_KNOWN_SEMANTIC_LOSS_WITHIN_VERIFIED_TOKEN_SET",
        "native_render_authority": "UPSTREAM_RENDER_VERIFIED_TOKEN_SET",
    }


def equation_capability_matrix(samples: list[str] | None = None) -> dict:
    probes = samples or [
        r"\frac{a}{b}",
        r"x_{i}^{2}",
        r"\sqrt[3]{x}",
        r"\int_{0}^{1} x^2 dx",
        r"\sum_{k=1}^{n} k",
        r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
        r"\begin{cases} x & x>0 \\ 0 & x\leq0 \end{cases}",
        r"\bar{x}+\vec{v}+\hat{y}",
        r"\mathbb{R}",
        r"\mathcal{F}",
        r"\begin{align} x&=1 \end{align}",
        r"\widehat{xy}",
        r"\xrightarrow{f}",
    ]
    rows = [audit_equation_latex(value) for value in probes]
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "rows": rows,
        "probe_count": len(rows),
        "supported_count": sum(1 for row in rows if row["supported"]),
        "abstained_count": sum(1 for row in rows if not row["supported"]),
        "policy": "MEASURE_NATIVE_CAPABILITY_THEN_FAIL_CLOSED",
        "matrix_sha256": _sha(rows),
    }


def documented_equation_native_candidates() -> dict:
    return {
        "font_commands": {
            "roman": "rm",
            "italic": "it",
            "bold": "bold",
            "roman_bold": "rmbold",
        },
        "vertical_alignment_commands": ["PILE", "LPILE", "RPILE"],
        "script_color_command": "COLOR {r,g,b}",
        "latex_candidates_not_auto_authored": {
            r"\\mathbf": "bold",
            r"\\boldsymbol": "bold",
            "align": "PILE/LPILE/RPILE family; semantic correspondence unresolved",
        },
        "no_documented_style_equivalent_found": [r"\\mathbb", r"\\mathcal", r"\\mathfrak"],
        "authority": "HANCOM_OFFICIAL_DOCUMENTATION_ONLY_NOT_P46_RENDER_CERTIFIED",
        "policy": "DOCUMENTED_COMMAND_DOES_NOT_BYPASS_RENDER_CERTIFICATION_GATE",
    }


def table_capability_map() -> dict:
    return {
        "authority": "P2.7_P2.8_NATIVE_TABLE_TRANSACTIONS_REUSED",
        "create": ["create_table"],
        "edit": [
            "set_cell_text", "merge_cells", "split_cell", "insert_row", "delete_row",
            "delete_column", "set_cell_properties", "set_cell_margin", "set_cell_size",
            "set_cell_border_fill", "set_cell_gradient", "delete_table",
        ],
        "closed": sorted(_CLOSED_TABLE_OPS),
        "principle": "BACKEND_NATIVE_TRANSACTION_IS_FINAL_AUTHORITY",
    }


def drawing_capability_map() -> dict:
    return {
        "authority": "P3.25_NATIVE_DRAWING_LAYER_REUSED",
        "create": ["insert_textbox", "insert_rectangle"],
        "edit": [
            "set_drawing_layout", "resize_drawing_object", "rotate_drawing_object",
            "flip_drawing_object", "remove_drawing_object",
        ],
        "deferred": sorted(_DEFERRED_DRAWING_OPS),
        "principle": "NO_GENERIC_SHAPE_FABRICATION_OUTSIDE_EVIDENCE_GATE",
    }


def _first_paragraph(document_map: dict | None) -> str | None:
    if not document_map:
        return None
    paragraphs = list(document_map.get("paragraphs") or [])
    if not paragraphs:
        return None
    nonempty = next((p for p in paragraphs if str(p.get("text") or "").strip()), None)
    return str((nonempty or paragraphs[0]).get("locator") or "") or None


def _resolve_anchor(value: object, document_map: dict | None) -> object:
    if value == "first_body":
        return _first_paragraph(document_map)
    if isinstance(value, dict) and "text" in value and document_map:
        wanted = str(value.get("text") or "")
        matches = [p for p in document_map.get("paragraphs", []) if str(p.get("text") or "") == wanted]
        if len(matches) == 1:
            return matches[0]["locator"]
        if len(matches) > 1:
            raise ValueError(f"paragraph text selector is ambiguous: {wanted!r}")
        raise ValueError(f"paragraph text selector not found: {wanted!r}")
    return value


def compile_native_authoring_bundle(bundle: dict, *, document_map: dict | None = None) -> dict:
    if not isinstance(bundle, dict):
        raise ValueError("bundle must be an object")
    raw_equations = list(bundle.get("equations") or [])
    raw_tables = list(bundle.get("tables") or [])
    raw_drawings = list(bundle.get("drawings") or [])
    total = len(raw_equations) + len(raw_tables) + len(raw_drawings)
    if total < 1 or total > MAX_BUNDLE_OPS:
        raise ValueError(f"native authoring bundle requires 1..{MAX_BUNDLE_OPS} operations")

    blockers: list[dict] = []
    equations: list[dict] = []
    for index, raw in enumerate(raw_equations):
        if not isinstance(raw, dict):
            blockers.append({"lane": "equation", "index": index, "reason": "OPERATION_NOT_OBJECT"})
            continue
        op = dict(raw)
        if op.get("op") in {"insert_equation", "replace_equation"}:
            audit = audit_equation_latex(str(op.get("latex") or ""), base_unit=int(op.get("base_unit", 1100)))
            op["p46_equation_audit"] = audit
            if not audit["supported"]:
                blockers.append({
                    "lane": "equation", "index": index, "reason": audit["status"],
                    "unsupported": audit.get("unsupported"), "latex": audit["latex"],
                })
        if op.get("op") == "insert_equation":
            try:
                op["paragraph"] = _resolve_anchor(op.get("paragraph", "first_body"), document_map)
            except ValueError as exc:
                blockers.append({"lane": "equation", "index": index, "reason": "ANCHOR_RESOLUTION_FAILED", "detail": str(exc)})
            if not op.get("paragraph"):
                blockers.append({"lane": "equation", "index": index, "reason": "PARAGRAPH_ANCHOR_REQUIRED"})
        equations.append(op)

    tables: list[dict] = []
    for index, raw in enumerate(raw_tables):
        if not isinstance(raw, dict):
            blockers.append({"lane": "table", "index": index, "reason": "OPERATION_NOT_OBJECT"})
            continue
        op = dict(raw)
        if op.get("op") in _CLOSED_TABLE_OPS:
            blockers.append({"lane": "table", "index": index, "reason": "EVIDENCE_GATE_CLOSED", "op": op.get("op")})
        tables.append(op)

    drawings: list[dict] = []
    for index, raw in enumerate(raw_drawings):
        if not isinstance(raw, dict):
            blockers.append({"lane": "drawing", "index": index, "reason": "OPERATION_NOT_OBJECT"})
            continue
        op = dict(raw)
        if op.get("op") in _DEFERRED_DRAWING_OPS:
            blockers.append({"lane": "drawing", "index": index, "reason": "EVIDENCE_GATE_CLOSED", "op": op.get("op")})
        if op.get("op") in {"insert_textbox", "insert_rectangle"}:
            try:
                op["anchor"] = _resolve_anchor(op.get("anchor", "first_body"), document_map)
            except ValueError as exc:
                blockers.append({"lane": "drawing", "index": index, "reason": "ANCHOR_RESOLUTION_FAILED", "detail": str(exc)})
            if not op.get("anchor"):
                blockers.append({"lane": "drawing", "index": index, "reason": "PARAGRAPH_ANCHOR_REQUIRED"})
        drawings.append(op)

    normalized = {"equations": equations, "tables": tables, "drawings": drawings}
    clean = {
        lane: [
            {k: v for k, v in op.items() if k != "p46_equation_audit"}
            for op in ops
        ]
        for lane, ops in normalized.items()
    }
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "ready": not blockers,
        "operation_count": total,
        "lane_counts": {key: len(value) for key, value in normalized.items()},
        "blockers": blockers,
        "normalized_bundle": normalized,
        "execution_bundle": clean,
        "bundle_sha256": _sha(clean),
        "execution_semantics": "ONE_CALL_ONE_DURABLE_REVISION_ALL_OR_NOTHING",
    }


def real_document_benchmark_contract() -> dict:
    scenarios = [
        {
            "id": "technical-note-native-math",
            "must_exercise": ["fractions", "radicals", "scripts", "matrix", "cases", "unsupported-math-style-abstention"],
            "quality_axes": ["open_safety", "semantic_fidelity", "equation_box_fit", "human_readability"],
        },
        {
            "id": "public-form-table",
            "must_exercise": ["table-create", "cell-text", "merge-or-span", "padding", "border-fill"],
            "quality_axes": ["open_safety", "table_semantics", "overflow_risk", "scanability"],
        },
        {
            "id": "diagrammatic-report",
            "must_exercise": ["textbox-or-rectangle", "positioning", "wrap", "z-order"],
            "quality_axes": ["open_safety", "drawing_semantics", "anchor_stability", "page_composition"],
        },
        {
            "id": "mixed-authoring-one-call",
            "must_exercise": ["equation", "table", "drawing"],
            "quality_axes": ["atomicity", "single_revision", "package_validity", "mutation_scope"],
        },
    ]
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "pass_rule": "PACKAGE_VALIDITY_IS_NECESSARY_NOT_SUFFICIENT",
        "render_rule": "NATIVE_RENDER_OR_HUMAN_REVIEW_IS_SEPARATE_EVIDENCE_WHEN_REQUIRED",
    }


def native_authoring_contract() -> dict:
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "purpose": "DISTRIBUTION_READY_NATIVE_AUTHORING_WITH_SMALL_HIGH_LEVEL_MCP_SURFACE",
        "principles": [
            "FUNCTIONALLY_DEEP_SURFACE_SMALL",
            "NATIVE_PRIMITIVES_BEFORE_BESPOKE_REIMPLEMENTATION",
            "UNSUPPORTED_EQUATION_SEMANTICS_ABSTAIN",
            "ONE_HIGH_LEVEL_BUNDLE_ONE_DURABLE_REVISION",
            "PACKAGE_VALIDITY_NOT_EQUAL_VISUAL_QUALITY",
            "LOW_LEVEL_TOOLS_REMAIN_ESCAPE_HATCHES",
        ],
        "high_level_tools": [
            "get_native_authoring_contract",
            "inspect_native_authoring_capabilities",
            "compile_native_authoring_bundle",
            "apply_native_authoring_bundle",
            "get_real_document_generation_benchmark",
        ],
        "equations": {
            "input_semantics": "LATEX_INTENT",
            "native_target": "HANCOM_EQEDIT",
            "current_gap_examples": ["mathbb", "mathcal", "align", "widehat", "xrightarrow"],
            "fallback": "EXPLICIT_ABSTENTION_NO_SILENT_APPROXIMATION",
            "documented_native_candidates": documented_equation_native_candidates(),
        },
        "tables": table_capability_map(),
        "drawings": drawing_capability_map(),
        "benchmark": real_document_benchmark_contract(),
    }
