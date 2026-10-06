from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

from p317_fidelity_envelope import assess_edit_fidelity_envelope

PHASE = "P4.17"
PRODUCT = "0.42.0-p4.17"
PLAN_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/transformation-plan/v1"
DECISION_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/authoring-decision/v1"

DIRECT_ACTIONS = {
    "replace_role_text",
    "style_role",
    "insert_after_role",
}
DELEGATED_ACTIONS = {
    "reference_style_transfer": "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER",
    "repair_visual_defects": "P3.40_P3.42_REPAIR_WITH_MUTATION_FOOTPRINT",
}


def _stable(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value)).hexdigest()


def _normalize_roles(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("roles must be a list")
    out = []
    for raw in value:
        role = str(raw or "").strip().upper()
        if not role:
            raise ValueError("role must not be empty")
        if role not in out:
            out.append(role)
    return out


def transformation_planning_contract() -> dict:
    body = {
        "phase": PHASE,
        "product": PRODUCT,
        "direct_actions": sorted(DIRECT_ACTIONS),
        "delegated_actions": DELEGATED_ACTIONS,
        "semantic_binding": "SECTION_INDEX_PLUS_PARAGRAPH_INDEX_WITH_TEXT_HASH_CHECK",
        "minimal_mutation": "ONLY_TARGET_BLOCKS_SELECTED_BY_EXPLICIT_ROLE_OR_ANCHOR",
        "reference_transfer": "TRANSFER_PATTERNS_AND_TOKENS_NOT_RAW_PACKAGE_BYTES",
        "repair_routing": "P3.40_PLAN_PLUS_P3.42_MUTATION_FOOTPRINT",
        "style_transfer_routing": "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER",
        "authority_ceiling": "PLAN_AND_ROUTING_AUTHORITY_ONLY_UNTIL_EXECUTION_RECEIPTS",
    }
    return {**body, "contract_sha256": _sha(body)}


def bind_semantic_graph_to_document_map(graph: Mapping[str, Any], document_map: Mapping[str, Any]) -> dict:
    by_coordinate = {
        (int(p.get("section_index", -1)), int(p.get("paragraph_index", -1))): p
        for p in document_map.get("paragraphs", [])
    }
    bindings = []
    unresolved = []
    for block in graph.get("blocks", []):
        if block.get("kind") != "PARAGRAPH":
            continue
        pi = block.get("paragraph_index")
        if pi is None:
            unresolved.append({"block_id": block.get("block_id"), "reason": "MISSING_PARAGRAPH_INDEX"})
            continue
        key = (int(block.get("section_index", -1)), int(pi))
        paragraph = by_coordinate.get(key)
        if paragraph is None:
            unresolved.append({"block_id": block.get("block_id"), "reason": "COORDINATE_NOT_FOUND"})
            continue
        hash_match = str(block.get("text_sha256") or "") == str(paragraph.get("text_sha256") or "")
        bindings.append({
            "block_id": block.get("block_id"),
            "role": block.get("role"),
            "section_index": key[0],
            "paragraph_index": key[1],
            "locator": paragraph.get("locator"),
            "text_sha256_match": hash_match,
            "address_stability": paragraph.get("address_stability"),
        })
        if not hash_match:
            unresolved.append({"block_id": block.get("block_id"), "reason": "TEXT_HASH_MISMATCH"})
    payload = {
        "binding_count": len(bindings),
        "unresolved_count": len(unresolved),
        "bindings": bindings,
        "unresolved": unresolved,
        "binding_status": "PASS" if not unresolved else "PARTIAL",
    }
    payload["binding_sha256"] = _sha(payload)
    return payload


def extract_reference_pattern(reference_graph: Mapping[str, Any] | None) -> dict:
    if not reference_graph:
        return {
            "present": False,
            "role_counts": {},
            "component_counts": {},
            "repeated_patterns": [],
        }
    grammar = reference_graph.get("repeated_layout_grammar") or {}
    payload = {
        "present": True,
        "role_counts": dict(reference_graph.get("role_counts") or {}),
        "component_counts": dict(reference_graph.get("component_counts") or {}),
        "repeated_patterns": [
            {
                "signature": list(row.get("signature") or []),
                "occurrences": int(row.get("occurrences") or 0),
            }
            for row in (grammar.get("patterns") or [])[:25]
        ],
    }
    payload["reference_pattern_sha256"] = _sha(payload)
    return payload


def _bindings_by_role(binding: Mapping[str, Any]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in binding.get("bindings", []):
        out.setdefault(str(row.get("role") or "UNKNOWN"), []).append(row)
    return out


def _protected_locator_set(binding: Mapping[str, Any], protected_roles: Sequence[str]) -> set[str]:
    roles = {str(x).upper() for x in protected_roles}
    return {
        str(row.get("locator"))
        for row in binding.get("bindings", [])
        if str(row.get("role") or "").upper() in roles
    }


def _compile_direct_action(
    action: Mapping[str, Any],
    *,
    by_role: Mapping[str, list[dict]],
    protected: set[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    kind = str(action.get("action") or "")
    operations: list[dict] = []
    warnings: list[dict] = []
    blocked: list[dict] = []

    if kind == "replace_role_text":
        role = str(action.get("role") or "").upper()
        text = action.get("text")
        if not role or not isinstance(text, str):
            raise ValueError("replace_role_text requires role and text")
        targets = list(by_role.get(role, []))
        if not targets:
            warnings.append({"code": "ROLE_TARGET_NOT_FOUND", "role": role})
            return operations, warnings, blocked
        if len(targets) > 1 and not bool(action.get("allow_multiple", False)):
            blocked.append({"code": "AMBIGUOUS_MULTI_TARGET_ROLE", "role": role, "target_count": len(targets)})
            return operations, warnings, blocked
        for row in targets:
            locator = str(row["locator"])
            if locator in protected:
                blocked.append({"code": "PROTECTED_TARGET", "locator": locator, "role": role})
                continue
            operations.append({"op": "replace_paragraph_text", "target": locator, "text": text})

    elif kind == "style_role":
        role = str(action.get("role") or "").upper()
        fmt = dict(action.get("format") or {})
        if not role or not fmt:
            raise ValueError("style_role requires role and format")
        for row in by_role.get(role, []):
            locator = str(row["locator"])
            if locator in protected:
                blocked.append({"code": "PROTECTED_TARGET", "locator": locator, "role": role})
                continue
            run_fmt = {k: v for k, v in fmt.items() if k in {"font", "fonts", "size", "bold", "italic", "underline", "color"}}
            para_fmt = {k: v for k, v in fmt.items() if k in {"align", "space_before", "space_after", "line_spacing", "keep_with_next"}}
            if run_fmt:
                operations.append({"op": "set_run_format", "target": locator, "format": run_fmt})
            if para_fmt:
                operations.append({"op": "set_paragraph_format", "target": locator, "format": para_fmt})

    elif kind == "insert_after_role":
        role = str(action.get("role") or "").upper()
        text = action.get("text")
        if not role or not isinstance(text, str):
            raise ValueError("insert_after_role requires role and text")
        anchors = list(by_role.get(role, []))
        if not anchors:
            warnings.append({"code": "ANCHOR_ROLE_NOT_FOUND", "role": role})
            return operations, warnings, blocked
        anchor = anchors[-1]
        locator = str(anchor["locator"])
        if locator in protected:
            blocked.append({"code": "PROTECTED_ANCHOR", "locator": locator, "role": role})
            return operations, warnings, blocked
        operations.append({"op": "insert_paragraph_after", "target": locator, "text": text})

    else:
        raise ValueError(f"unsupported direct action: {kind}")

    return operations, warnings, blocked


def plan_document_transformation(
    *,
    intent: Mapping[str, Any],
    semantic_graph: Mapping[str, Any],
    document_map: Mapping[str, Any],
    reference_graph: Mapping[str, Any] | None = None,
    archetype: Mapping[str, Any] | None = None,
) -> dict:
    if not isinstance(intent, Mapping):
        raise ValueError("intent must be an object")
    actions = intent.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("intent.actions must be a non-empty list")
    if len(actions) > 50:
        raise ValueError("too many intent actions")

    preservation = dict(intent.get("preservation") or {})
    protected_roles = _normalize_roles(preservation.get("protected_roles"))
    required_grade = str(preservation.get("required_grade") or "TARGETED_PARTS_ONLY").upper()

    binding = bind_semantic_graph_to_document_map(semantic_graph, document_map)
    by_role = _bindings_by_role(binding)
    protected = _protected_locator_set(binding, protected_roles)
    reference_pattern = extract_reference_pattern(reference_graph)

    operations: list[dict] = []
    delegates: list[dict] = []
    warnings: list[dict] = []
    blocked: list[dict] = []
    unknown: list[dict] = []

    for index, raw in enumerate(actions):
        if not isinstance(raw, Mapping):
            raise ValueError("each intent action must be an object")
        kind = str(raw.get("action") or "").strip()
        if kind in DIRECT_ACTIONS:
            compiled, warn, stop = _compile_direct_action(raw, by_role=by_role, protected=protected)
            operations.extend(compiled)
            warnings.extend(warn)
            blocked.extend(stop)
        elif kind in DELEGATED_ACTIONS:
            delegates.append({
                "action_index": index,
                "action": kind,
                "delegate": DELEGATED_ACTIONS[kind],
                "roles": _normalize_roles(raw.get("roles")),
                "reference_pattern_sha256": reference_pattern.get("reference_pattern_sha256"),
                "required_preservation_grade": required_grade,
            })
        else:
            unknown.append({"action_index": index, "action": kind or None})

    fidelity = assess_edit_fidelity_envelope(operations) if operations else None
    unique_targets = {
        str(op.get("target"))
        for op in operations
        if op.get("target") is not None
    }
    minimality = {
        "operation_count": len(operations),
        "unique_target_count": len(unique_targets),
        "protected_role_count": len(protected_roles),
        "unresolved_binding_count": int(binding.get("unresolved_count") or 0),
    }

    if unknown:
        decision = "ABSTAIN"
    elif blocked:
        decision = "HOLD"
    elif not operations and delegates:
        decision = "DELEGATE"
    elif operations or delegates:
        decision = "SAFE_TO_PLAN"
    else:
        decision = "ABSTAIN"

    plan = {
        "schema": PLAN_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "decision": decision,
        "intent_goal": str(intent.get("goal") or ""),
        "archetype": dict(archetype or {}),
        "binding": binding,
        "reference_pattern": reference_pattern,
        "operations": operations,
        "delegates": delegates,
        "warnings": warnings,
        "blocked": blocked,
        "unknown_actions": unknown,
        "preservation": {
            "protected_roles": protected_roles,
            "required_grade": required_grade,
            "mutation_footprint_required": bool(operations or delegates),
        },
        "minimality": minimality,
        "fidelity_envelope": fidelity,
        "execution_authority": "PLAN_ONLY_NO_MUTATION_PERFORMED",
        "native_visual_authority": False,
    }
    plan["plan_sha256"] = _sha(plan)
    return plan


def validate_transformation_plan(plan: Mapping[str, Any]) -> dict:
    if str(plan.get("schema") or "") != PLAN_SCHEMA:
        raise ValueError("unexpected transformation plan schema")
    decision = str(plan.get("decision") or "")
    if decision not in {"SAFE_TO_PLAN", "DELEGATE", "HOLD", "ABSTAIN"}:
        raise ValueError("invalid plan decision")
    operations = list(plan.get("operations") or [])
    delegates = list(plan.get("delegates") or [])
    if decision == "SAFE_TO_PLAN" and not (operations or delegates):
        raise ValueError("SAFE_TO_PLAN requires operations or delegates")
    if decision == "ABSTAIN" and not (plan.get("unknown_actions") or plan.get("warnings")):
        raise ValueError("ABSTAIN requires an explicit reason")
    receipt = {
        "schema": DECISION_SCHEMA,
        "phase": PHASE,
        "plan_sha256": plan.get("plan_sha256"),
        "decision": decision,
        "operation_count": len(operations),
        "delegate_count": len(delegates),
        "blocked_count": len(plan.get("blocked") or []),
        "unknown_action_count": len(plan.get("unknown_actions") or []),
        "mutation_footprint_required": bool((plan.get("preservation") or {}).get("mutation_footprint_required")),
        "authority": "PLAN_VALIDATION_ONLY_EXECUTION_REQUIRES_NATIVE_TRANSACTION_RECEIPTS",
    }
    receipt["receipt_sha256"] = _sha(receipt)
    return receipt
