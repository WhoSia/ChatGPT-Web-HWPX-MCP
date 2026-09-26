from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from p22_formatting import apply_formatting_atomic
from p2_document import build_document_map
from p335_atlas import compile_template
from p342_mutation_footprint import build_mutation_footprint, enforce_preservation_grade

POLICY_SCHEMA = "chatgpt-web-hwpx-mcp/p3.43/organization-design-policy/v1"
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.43/design-system-adaptation-contract/v1"
PLAN_SCHEMA = "chatgpt-web-hwpx-mcp/p3.43/template-migration-plan/v1"
RECEIPT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.43/template-migration-receipt/v1"
GENERALIZATION_SCHEMA = "chatgpt-web-hwpx-mcp/p3.43/cross-template-generalization-ledger/v1"

_ALLOWED_OPS = {"set_run_format", "set_paragraph_format"}
_GRADES = {"PACKAGE_VALID_ONLY": 0, "TARGETED_PARTS_ONLY": 1, "PACKAGE_IDENTICAL": 2}
_CASE_VERDICTS = {"PASS", "FAIL", "WITHHELD"}
_SPLITS = {"DISCOVERY", "HOLDOUT"}


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _bounded_strings(value: Any, field: str, limit: int = 64, item_limit: int = 256) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{field} must be a bounded list")
    out: list[str] = []
    for raw in value:
        item = str(raw or "").strip()
        if not item or len(item) > item_limit:
            raise ValueError(f"{field} contains an invalid item")
        if item in out:
            raise ValueError(f"{field} contains duplicates")
        out.append(item)
    return sorted(out)


def _color(value: Any) -> str:
    raw = str(value or "").strip().lstrip("#").upper()
    if len(raw) not in {6, 8} or any(ch not in "0123456789ABCDEF" for ch in raw):
        raise ValueError(f"invalid color token: {value!r}")
    return raw


def _colors(value: Any, field: str) -> list[str]:
    return sorted({_color(item) for item in _bounded_strings(value, field)})


def _number(value: Any, field: str, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _normalize_role_constraint(role: str, value: Any) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError(f"role constraint for {role} must be an object")
    allowed = {
        "allowed_fonts", "allowed_colors", "min_size_pt", "max_size_pt",
        "forbidden_format_keys", "required_format_keys",
    }
    if set(value) - allowed:
        raise ValueError(f"unknown role constraint fields for {role}")
    minimum = _number(value.get("min_size_pt"), f"{role}.min_size_pt")
    maximum = _number(value.get("max_size_pt"), f"{role}.max_size_pt")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"invalid size range for role {role}")
    return {
        "allowed_fonts": _bounded_strings(value.get("allowed_fonts"), f"{role}.allowed_fonts"),
        "allowed_colors": _colors(value.get("allowed_colors"), f"{role}.allowed_colors"),
        "min_size_pt": minimum,
        "max_size_pt": maximum,
        "forbidden_format_keys": _bounded_strings(
            value.get("forbidden_format_keys"), f"{role}.forbidden_format_keys"
        ),
        "required_format_keys": _bounded_strings(
            value.get("required_format_keys"), f"{role}.required_format_keys"
        ),
    }


def normalize_organization_policy(policy: Mapping[str, Any]) -> dict:
    if not isinstance(policy, Mapping):
        raise ValueError("organization policy must be an object")
    allowed_top = {"organization_id", "policy_id", "hard", "soft", "notes"}
    if set(policy) - allowed_top:
        raise ValueError("unknown organization policy fields")
    organization_id = str(policy.get("organization_id") or "").strip()
    policy_id = str(policy.get("policy_id") or "").strip()
    if not organization_id or len(organization_id) > 160:
        raise ValueError("organization_id is required and bounded")
    if not policy_id or len(policy_id) > 160:
        raise ValueError("policy_id is required and bounded")

    hard = policy.get("hard") or {}
    soft = policy.get("soft") or {}
    if not isinstance(hard, Mapping) or not isinstance(soft, Mapping):
        raise ValueError("hard/soft policy sections must be objects")
    hard_allowed = {
        "allowed_operations", "forbidden_operations", "allowed_fonts", "allowed_colors",
        "min_size_pt", "max_size_pt", "forbidden_format_keys", "required_roles",
        "role_constraints", "protected_targets", "immutable_parts",
        "required_literal_text", "allowed_template_institutions",
        "require_source_receipts", "require_semantic_preservation",
        "require_structure_preservation", "required_preservation_grade",
    }
    soft_allowed = {"preferred_fonts", "preferred_colors", "notes"}
    if set(hard) - hard_allowed:
        raise ValueError("unknown hard policy fields")
    if set(soft) - soft_allowed:
        raise ValueError("unknown soft policy fields")

    allowed_ops = set(_bounded_strings(hard.get("allowed_operations"), "allowed_operations"))
    if not allowed_ops:
        allowed_ops = set(_ALLOWED_OPS)
    if allowed_ops - _ALLOWED_OPS:
        raise ValueError("P3.43 admits formatting-only migration operations")
    forbidden_ops = set(_bounded_strings(hard.get("forbidden_operations"), "forbidden_operations"))
    allowed_ops -= forbidden_ops
    if not allowed_ops:
        raise ValueError("organization policy forbids every admitted operation")

    min_size = _number(hard.get("min_size_pt"), "min_size_pt")
    max_size = _number(hard.get("max_size_pt"), "max_size_pt")
    if min_size is not None and max_size is not None and min_size > max_size:
        raise ValueError("invalid global size range")

    role_constraints_raw = hard.get("role_constraints") or {}
    if not isinstance(role_constraints_raw, Mapping) or len(role_constraints_raw) > 32:
        raise ValueError("role_constraints must be a bounded object")
    role_constraints = {
        str(role): _normalize_role_constraint(str(role), value)
        for role, value in sorted(role_constraints_raw.items())
        if str(role).strip()
    }
    required_grade = str(hard.get("required_preservation_grade") or "TARGETED_PARTS_ONLY").upper()
    if required_grade not in _GRADES:
        raise ValueError("unsupported required preservation grade")

    normalized = {
        "schema": POLICY_SCHEMA,
        "organization_id": organization_id,
        "policy_id": policy_id,
        "hard": {
            "allowed_operations": sorted(allowed_ops),
            "forbidden_operations": sorted(forbidden_ops),
            "allowed_fonts": _bounded_strings(hard.get("allowed_fonts"), "allowed_fonts"),
            "allowed_colors": _colors(hard.get("allowed_colors"), "allowed_colors"),
            "min_size_pt": min_size,
            "max_size_pt": max_size,
            "forbidden_format_keys": _bounded_strings(
                hard.get("forbidden_format_keys"), "forbidden_format_keys"
            ),
            "required_roles": _bounded_strings(hard.get("required_roles"), "required_roles"),
            "role_constraints": role_constraints,
            "protected_targets": _bounded_strings(hard.get("protected_targets"), "protected_targets", 100),
            "immutable_parts": _bounded_strings(hard.get("immutable_parts"), "immutable_parts", 256, 512),
            "required_literal_text": _bounded_strings(
                hard.get("required_literal_text"), "required_literal_text", 50, 1000
            ),
            "allowed_template_institutions": _bounded_strings(
                hard.get("allowed_template_institutions"), "allowed_template_institutions"
            ),
            "require_source_receipts": bool(hard.get("require_source_receipts", True)),
            "require_semantic_preservation": bool(hard.get("require_semantic_preservation", True)),
            "require_structure_preservation": bool(hard.get("require_structure_preservation", True)),
            "required_preservation_grade": required_grade,
        },
        "soft": {
            "preferred_fonts": _bounded_strings(soft.get("preferred_fonts"), "preferred_fonts"),
            "preferred_colors": _colors(soft.get("preferred_colors"), "preferred_colors"),
            "notes": _bounded_strings(soft.get("notes"), "soft.notes", 32, 500),
        },
        "notes": _bounded_strings(policy.get("notes"), "notes", 32, 500),
    }
    normalized["policy_sha256"] = _sha(normalized)
    return normalized


def design_system_adaptation_contract() -> dict:
    return {
        "schema": CONTRACT_SCHEMA,
        "phase": "P3.43",
        "purpose": "ORGANIZATION_TEMPLATE_CONSTRAINED_STYLE_TRANSFER_WITH_EVIDENCE_CARRYING_MIGRATION_AND_FAIL_CLOSED_POLICY_BINDING",
        "authority_order": [
            "USER_OR_ORGANIZATION_HARD_CONSTRAINT",
            "SOURCE_TEMPLATE_EVIDENCE",
            "MEASURED_PACKAGE_PRESERVATION",
            "SOFT_BRAND_PREFERENCE",
            "DESCRIPTIVE_CORPUS_FREQUENCY",
        ],
        "migration_transaction": (
            "original -> temporary candidate -> compile evidence-bound template -> hard-policy preflight "
            "-> formatting mutation -> semantic/structure postcondition -> P3.42 exact-part footprint "
            "-> immutable-part check -> preservation-grade gate -> atomic replace"
        ),
        "generalization": {
            "split": "DISCOVERY/HOLDOUT",
            "denominator_policy": "all holdout cases remain visible including WITHHELD",
            "no_automatic_style_winner": True,
        },
        "non_claims": [
            "Policy conformance is not aesthetic superiority.",
            "Package-local preservation is not Hancom-native visual equivalence.",
            "Discovery success does not count as held-out generalization.",
            "Soft preferences never override hard institutional constraints.",
        ],
    }


def _template_evidence(template: Mapping[str, Any], policy: Mapping[str, Any]) -> list[dict]:
    violations: list[dict] = []
    hard = policy["hard"]
    receipts = template.get("source_receipts") or {}
    if hard["require_source_receipts"] and (not isinstance(receipts, Mapping) or not receipts):
        violations.append({"code": "SOURCE_RECEIPTS_REQUIRED"})
    if isinstance(receipts, Mapping):
        for source_id, receipt in receipts.items():
            if not str(source_id).strip() or len(str(receipt or "")) != 64:
                violations.append({"code": "INVALID_SOURCE_RECEIPT", "source_id": str(source_id)})
    allowed_inst = set(hard["allowed_template_institutions"])
    institutions = {str(x) for x in (template.get("institutions") or []) if str(x)}
    if allowed_inst and (not institutions or not institutions.issubset(allowed_inst)):
        violations.append({"code": "TEMPLATE_INSTITUTION_NOT_ALLOWED", "observed": sorted(institutions), "allowed": sorted(allowed_inst)})
    if str(template.get("authority") or "") != "EVIDENCE_GUIDED_TEMPLATE_CANDIDATE":
        violations.append({"code": "TEMPLATE_AUTHORITY_NOT_EVIDENCE_GUIDED"})
    return violations


def _format_fonts(fmt: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    if fmt.get("font"):
        values.append(str(fmt["font"]))
    by_script = fmt.get("font_by_script")
    if isinstance(by_script, Mapping):
        values.extend(str(v) for v in by_script.values() if str(v))
    return sorted(set(values))


def _format_colors(fmt: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("color", "highlight", "underline_color", "border_color"):
        if fmt.get(key) not in (None, "", "NONE"):
            try:
                values.append(_color(fmt[key]))
            except ValueError:
                values.append(f"INVALID:{fmt[key]}")
    return sorted(set(values))


def _constraint_violations(operation: Mapping[str, Any], *, role: str, policy: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    hard = policy["hard"]
    soft = policy["soft"]
    name = str(operation.get("op") or "")
    target = str(operation.get("target") or "")
    fmt = operation.get("format") or {}
    violations: list[dict] = []
    warnings: list[dict] = []
    if name not in hard["allowed_operations"] or name in hard["forbidden_operations"]:
        violations.append({"code": "OPERATION_FORBIDDEN", "operation": name, "target": target})
    if target in set(hard["protected_targets"]):
        violations.append({"code": "TARGET_PROTECTED", "target": target})
    if not isinstance(fmt, Mapping):
        violations.append({"code": "FORMAT_PAYLOAD_INVALID", "target": target})
        return violations, warnings

    role_policy = hard["role_constraints"].get(role) or {}
    forbidden_keys = set(hard["forbidden_format_keys"]) | set(role_policy.get("forbidden_format_keys") or [])
    for key in sorted(set(fmt) & forbidden_keys):
        violations.append({"code": "FORMAT_KEY_FORBIDDEN", "target": target, "role": role, "key": key})
    for key in sorted(set(role_policy.get("required_format_keys") or []) - set(fmt)):
        violations.append({"code": "ROLE_REQUIRED_FORMAT_KEY_MISSING", "role": role, "target": target, "key": key})

    fonts = _format_fonts(fmt)
    allowed_fonts = set(role_policy.get("allowed_fonts") or hard["allowed_fonts"])
    if allowed_fonts:
        for font in fonts:
            if font not in allowed_fonts:
                violations.append({"code": "FONT_NOT_ALLOWED", "role": role, "target": target, "font": font})

    colors = _format_colors(fmt)
    allowed_colors = set(role_policy.get("allowed_colors") or hard["allowed_colors"])
    if allowed_colors:
        for color in colors:
            if color not in allowed_colors:
                violations.append({"code": "COLOR_NOT_ALLOWED", "role": role, "target": target, "color": color})

    if "size" in fmt:
        size = _number(fmt.get("size"), "format.size")
        minimum = role_policy.get("min_size_pt")
        maximum = role_policy.get("max_size_pt")
        if minimum is None:
            minimum = hard["min_size_pt"]
        if maximum is None:
            maximum = hard["max_size_pt"]
        if minimum is not None and size is not None and size < minimum:
            violations.append({"code": "FONT_SIZE_BELOW_MIN", "role": role, "target": target, "size": size, "min": minimum})
        if maximum is not None and size is not None and size > maximum:
            violations.append({"code": "FONT_SIZE_ABOVE_MAX", "role": role, "target": target, "size": size, "max": maximum})

    preferred_fonts = set(soft["preferred_fonts"])
    if preferred_fonts and fonts and not set(fonts).issubset(preferred_fonts):
        warnings.append({"code": "NON_PREFERRED_FONT", "role": role, "target": target, "fonts": fonts})
    preferred_colors = set(soft["preferred_colors"])
    if preferred_colors and colors and not set(colors).issubset(preferred_colors):
        warnings.append({"code": "NON_PREFERRED_COLOR", "role": role, "target": target, "colors": colors})
    return violations, warnings


def _expected_scope(path: Path, targets_by_role: Mapping[str, list[str]]) -> dict:
    mapped = build_document_map(path)
    by_locator = {str(row.get("locator")): row for row in mapped.get("paragraphs", [])}
    parts = {"Contents/header.xml"}
    for role, targets in targets_by_role.items():
        for target in targets:
            row = by_locator.get(str(target))
            if row is None:
                raise ValueError(f"target paragraph is unavailable for role {role}: {target}")
            section = str(row.get("section") or "").strip()
            if not section:
                raise ValueError(f"target paragraph has no package section: {target}")
            parts.add(section)
    return {
        "changed_parts": sorted(parts),
        "added_parts": [],
        "removed_parts": [],
        "required_changed_parts": [],
        "require_untouched_record_metadata": False,
        "label": "P3.43_ORGANIZATION_TEMPLATE_STYLE_TRANSFER",
    }


def plan_constraint_preserving_style_transfer(path: Path | str, template: Mapping[str, Any], targets_by_role: Mapping[str, list[str]], policy: Mapping[str, Any], *, expected_revision: int) -> dict:
    path = Path(path)
    normalized_policy = normalize_organization_policy(policy)
    if not isinstance(targets_by_role, Mapping) or not targets_by_role:
        raise ValueError("targets_by_role must be a non-empty object")
    clean_targets: dict[str, list[str]] = {}
    for role, raw_targets in targets_by_role.items():
        role_name = str(role or "").strip()
        if not role_name:
            raise ValueError("target role is empty")
        clean_targets[role_name] = _bounded_strings(raw_targets, f"targets_by_role.{role_name}", 100, 512)
    if set(normalized_policy["hard"]["required_roles"]) - set(clean_targets):
        raise ValueError("ORGANIZATION_POLICY_VIOLATION:REQUIRED_ROLE_MISSING")

    compiled = compile_template(dict(template), clean_targets, expected_revision=int(expected_revision))
    target_role = {target: role for role, targets in clean_targets.items() for target in targets}
    violations = _template_evidence(template, normalized_policy)
    warnings: list[dict] = []
    for operation in compiled["operations"]:
        hard_rows, soft_rows = _constraint_violations(
            operation,
            role=target_role.get(str(operation.get("target") or ""), ""),
            policy=normalized_policy,
        )
        violations.extend(hard_rows)
        warnings.extend(soft_rows)
    if violations:
        raise ValueError("ORGANIZATION_POLICY_VIOLATION:" + _stable(violations[:25]))

    expected_scope = _expected_scope(path, clean_targets)
    collision = sorted(set(normalized_policy["hard"]["immutable_parts"]) & set(expected_scope["changed_parts"]))
    if collision:
        raise ValueError("ORGANIZATION_POLICY_VIOLATION:IMMUTABLE_PART_TARGETED:" + ",".join(collision))

    payload = {
        "schema": PLAN_SCHEMA,
        "phase": "P3.43",
        "expected_revision": int(expected_revision),
        "template_sha256": str(template.get("template_sha256") or ""),
        "source_corpus_sha256": str(template.get("source_corpus_sha256") or ""),
        "source_receipts": dict(template.get("source_receipts") or {}),
        "template_institutions": sorted(str(x) for x in (template.get("institutions") or [])),
        "targets_by_role": clean_targets,
        "operations": compiled["operations"],
        "organization_policy": normalized_policy,
        "expected_scope": expected_scope,
        "soft_warnings": warnings,
        "unresolved_template_dimensions": list(template.get("unresolved_dimensions") or []),
        "authority": "HARD_POLICY_PREFLIGHT_PASS_WITH_EVIDENCE_BOUND_TEMPLATE",
    }
    payload["plan_sha256"] = _sha(payload)
    return payload


def adjudicate_policy_gate(*, hard_violation_count: int, semantic_preserved: bool, structure_preserved: bool, preservation_grade: str) -> str:
    grade = str(preservation_grade or "").upper()
    if grade not in _GRADES:
        return "FAIL"
    return "PASS" if int(hard_violation_count) == 0 and bool(semantic_preserved) and bool(structure_preserved) and _GRADES[grade] >= 1 else "FAIL"


def apply_constraint_preserving_template_migration_atomic(path: Path | str, template: Mapping[str, Any], targets_by_role: Mapping[str, list[str]], policy: Mapping[str, Any], *, expected_revision: int, current_revision: int, validator: Callable[[Path], dict] | None = None) -> dict:
    path = Path(path)
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    plan = plan_constraint_preserving_style_transfer(path, template, targets_by_role, policy, expected_revision=int(expected_revision))
    hard = plan["organization_policy"]["hard"]
    before_doc = build_document_map(path)
    before_text = "\n".join(str(row.get("text") or "") for row in before_doc.get("paragraphs", []))

    fd, temp_name = tempfile.mkstemp(prefix=path.stem + ".p343-migration-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(temp_name)
    shutil.copy2(path, candidate)
    try:
        formatting_receipt = apply_formatting_atomic(
            candidate, list(plan["operations"]), expected_revision=int(expected_revision),
            current_revision=int(current_revision), validator=validator,
        )
        after_doc = build_document_map(candidate)
        after_text = "\n".join(str(row.get("text") or "") for row in after_doc.get("paragraphs", []))
        semantic_preserved = before_doc.get("semantic_sha256") == after_doc.get("semantic_sha256")
        structure_preserved = before_doc.get("structure_sha256") == after_doc.get("structure_sha256")
        violations: list[dict] = []
        if hard["require_semantic_preservation"] and not semantic_preserved:
            violations.append({"code": "SEMANTIC_HASH_CHANGED"})
        if hard["require_structure_preservation"] and not structure_preserved:
            violations.append({"code": "STRUCTURE_HASH_CHANGED"})
        for literal in hard["required_literal_text"]:
            if literal not in before_text:
                violations.append({"code": "REQUIRED_LITERAL_NOT_PRESENT_BEFORE", "literal": literal})
            elif literal not in after_text:
                violations.append({"code": "REQUIRED_LITERAL_LOST", "literal": literal})

        footprint = build_mutation_footprint(path, candidate, expected_scope=plan["expected_scope"])
        enforcement = enforce_preservation_grade(footprint, hard["required_preservation_grade"])
        observed = footprint.get("observed") or {}
        changed = set(observed.get("changed_parts") or []) | set(observed.get("added_parts") or []) | set(observed.get("removed_parts") or [])
        immutable_drift = sorted(set(hard["immutable_parts"]) & changed)
        if immutable_drift:
            violations.append({"code": "IMMUTABLE_PART_CHANGED", "parts": immutable_drift})

        gate = adjudicate_policy_gate(
            hard_violation_count=len(violations),
            semantic_preserved=semantic_preserved or not hard["require_semantic_preservation"],
            structure_preserved=structure_preserved or not hard["require_structure_preservation"],
            preservation_grade=footprint["preservation"]["actual_grade"],
        )
        if violations or gate != "PASS":
            raise ValueError("P3.43_POSTCONDITION_FAILED:" + _stable(violations))

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "phase": "P3.43",
            "plan_sha256": plan["plan_sha256"],
            "policy_sha256": plan["organization_policy"]["policy_sha256"],
            "organization_id": plan["organization_policy"]["organization_id"],
            "policy_id": plan["organization_policy"]["policy_id"],
            "template_sha256": plan["template_sha256"],
            "source_corpus_sha256": plan["source_corpus_sha256"],
            "source_receipts": plan["source_receipts"],
            "template_institutions": plan["template_institutions"],
            "formatting_receipt": formatting_receipt,
            "semantic_preserved": semantic_preserved,
            "structure_preserved": structure_preserved,
            "mutation_footprint": footprint,
            "preservation_enforcement": enforcement,
            "immutable_part_drift": immutable_drift,
            "soft_warnings": plan["soft_warnings"],
            "unresolved_template_dimensions": plan["unresolved_template_dimensions"],
            "policy_gate": gate,
            "source_template_mutated": False,
            "atomic_commit": True,
            "authority": "ORGANIZATION_CONSTRAINED_EVIDENCE_CARRYING_TEMPLATE_MIGRATION_PASS / NOT_HANCOM_NATIVE_VISUAL_EQUIVALENCE",
        }
        receipt["migration_receipt_sha256"] = _sha(receipt)
        os.replace(candidate, path)
        return receipt
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def build_cross_template_generalization_ledger(cases: list[Mapping[str, Any]], *, min_holdout_templates: int = 2, min_holdout_institutions: int = 2) -> dict:
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("cases must be a non-empty bounded list")
    normalized: list[dict] = []
    seen: set[str] = set()
    for raw in cases:
        if not isinstance(raw, Mapping):
            raise ValueError("generalization case must be an object")
        case_id = str(raw.get("case_id") or "").strip()
        split = str(raw.get("split") or "").upper()
        verdict = str(raw.get("verdict") or "").upper()
        institution = str(raw.get("institution") or "").strip()
        template_sha = str(raw.get("template_sha256") or "").strip()
        policy_sha = str(raw.get("policy_sha256") or "").strip()
        grade = str(raw.get("preservation_grade") or "").upper()
        hard_count = int(raw.get("hard_constraint_violations") or 0)
        if not case_id or case_id in seen:
            raise ValueError("case_id must be unique and non-empty")
        seen.add(case_id)
        if split not in _SPLITS or verdict not in _CASE_VERDICTS:
            raise ValueError("invalid split or verdict")
        if not institution or len(template_sha) != 64 or len(policy_sha) != 64 or grade not in _GRADES:
            raise ValueError("case provenance is incomplete")
        effective = verdict
        reasons: list[str] = []
        if verdict == "PASS" and hard_count:
            effective = "FAIL"; reasons.append("HARD_CONSTRAINT_VIOLATION")
        if verdict == "PASS" and _GRADES[grade] < 1:
            effective = "FAIL"; reasons.append("PRESERVATION_GRADE_BELOW_TARGETED_PARTS_ONLY")
        normalized.append({
            "case_id": case_id, "split": split, "institution": institution,
            "template_sha256": template_sha, "policy_sha256": policy_sha,
            "verdict": verdict, "effective_verdict": effective,
            "preservation_grade": grade, "hard_constraint_violations": hard_count,
            "evidence_class": str(raw.get("evidence_class") or "STRUCTURAL_NATIVE_XML_ONLY"),
            "reasons": reasons,
        })

    holdout = [row for row in normalized if row["split"] == "HOLDOUT"]
    templates = {row["template_sha256"] for row in holdout}
    institutions = {row["institution"] for row in holdout}
    counts = {status: sum(row["effective_verdict"] == status for row in holdout) for status in sorted(_CASE_VERDICTS)}
    if counts["FAIL"]:
        promotion, rationale = "FAIL", "AT_LEAST_ONE_HELD_OUT_CASE_FAILED"
    elif not holdout or len(templates) < int(min_holdout_templates) or len(institutions) < int(min_holdout_institutions) or counts["WITHHELD"]:
        promotion, rationale = "WITHHELD", "HELD_OUT_DENOMINATOR_INSUFFICIENT_OR_WITHHELD"
    else:
        promotion, rationale = "PASS", "ALL_HELD_OUT_CASES_PASS_WITH_TARGETED_PRESERVATION_OR_BETTER"
    result = {
        "schema": GENERALIZATION_SCHEMA, "phase": "P3.43",
        "case_count": len(normalized),
        "discovery_count": sum(row["split"] == "DISCOVERY" for row in normalized),
        "holdout_count": len(holdout), "holdout_template_count": len(templates),
        "holdout_institution_count": len(institutions), "holdout_verdict_counts": counts,
        "promotion_gate": promotion, "promotion_rationale": rationale,
        "thresholds": {"min_holdout_templates": int(min_holdout_templates), "min_holdout_institutions": int(min_holdout_institutions)},
        "cases": normalized,
        "authority": "DENOMINATOR_PRESERVING_CROSS_TEMPLATE_GATE / DISCOVERY_DOES_NOT_COUNT_AS_HELD_OUT_GENERALIZATION",
    }
    result["ledger_sha256"] = _sha(result)
    return result
