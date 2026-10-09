from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from hwpx_mcp.document.p2_document import apply_edits_atomic, build_document_map
from hwpx_mcp.document.p22_formatting import apply_formatting_atomic
from hwpx_mcp.quality.p317_fidelity_envelope import assess_edit_fidelity_envelope
from hwpx_mcp.custody.p342_mutation_footprint import (
    build_mutation_footprint,
    enforce_preservation_grade,
)
from hwpx_mcp.orchestration.p343_design_system import (
    apply_constraint_preserving_template_migration_atomic,
    plan_constraint_preserving_style_transfer,
)
from hwpx_mcp.custody.p342_mutation_footprint import (
    apply_document_design_repairs_with_footprint_atomic,
    expected_scope_for_design_repair,
)
from hwpx_mcp.orchestration.p417_planner import PLAN_SCHEMA, plan_document_transformation
from hwpx_mcp.orchestration.p417_semantics import recover_semantic_structure

PHASE = "P4.17"
PRODUCT = "0.42.0-p4.17"
EXECUTION_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/transformation-execution/v1"
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/transformation-execution-contract/v1"
POST_EDIT_RENDER_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/post-edit-native-authority/v1"

_TEXT_OPS = {
    "replace_paragraph_text",
    "insert_paragraph_before",
    "insert_paragraph_after",
    "delete_paragraph",
    "move_paragraph_before",
    "move_paragraph_after",
}
_FORMAT_OPS = {"set_run_format", "set_paragraph_format"}


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def transformation_execution_contract() -> dict:
    body = {
        "schema": CONTRACT_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "transaction": "COPY_EXECUTE_VERIFY_ATOMIC_REPLACE",
        "entrypoints": ["PLAN_THEN_EXECUTE", "INTENT_TO_VERIFIED_EXECUTION"],
        "direct_native_lanes": ["P2_DOCUMENT_EDIT", "P2_FORMATTING"],
        "delegate_lanes": [
            "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER",
            "P3.40_P3.42_REPAIR_WITH_MUTATION_FOOTPRINT",
        ],
        "required_receipts": [
            "PLAN_HASH_BINDING",
            "NATIVE_EXECUTION_TRANSCRIPT",
            "P3.17_FIDELITY_ENVELOPE",
            "P3.42_MUTATION_FOOTPRINT",
            "STRUCTURAL_SEMANTIC_BEFORE_AFTER",
            "PACKAGE_VALIDATION",
        ],
        "render_rule": "RENDER_EVIDENCE_MAY_STRENGTHEN_POST_EDIT_VERDICT_BUT_ABSENCE_NEVER_IMPLIES_NATIVE_PASS",
        "repair_rule": "AT_MOST_ONE_EXPLICIT_REPAIR_PASS_PER_EXECUTION_RECEIPT",
        "replan_rule": "POST_EDIT_GRAPH_MAY_GENERATE_A_NEXT_PLAN_BUT_NEVER_RECURSIVELY_MUTATES_WITHOUT_A_NEW_REVISION",
        "authority": "EXECUTION_RECEIPT_AUTHORITY_NOT_NATIVE_VISUAL_TRUTH",
    }
    body["contract_sha256"] = _sha(body)
    return body


def _expected_scope(path: Path, operations: list[dict], *, delegate_changes_header: bool = False) -> dict:
    mapped = build_document_map(path)
    by_locator = {str(row["locator"]): row for row in mapped.get("paragraphs", [])}
    changed: set[str] = set()
    format_present = False
    for op in operations:
        name = str(op.get("op") or "")
        target = str(op.get("target") or "")
        row = by_locator.get(target)
        if row is None:
            raise ValueError(f"execution target locator unavailable: {target}")
        changed.add(str(row["section"]))
        if name in _FORMAT_OPS:
            format_present = True
    if format_present or delegate_changes_header:
        changed.add("Contents/header.xml")
    return {
        "changed_parts": sorted(changed),
        "added_parts": [],
        "removed_parts": [],
        "required_changed_parts": [],
        "require_untouched_record_metadata": False,
        "label": "P4.17_VERIFIED_TRANSFORMATION_TARGET_PARTS",
    }


def _merge_expected_scopes(*scopes: Mapping[str, Any] | None) -> dict:
    changed: set[str] = set()
    added: set[str] = set()
    removed: set[str] = set()
    required: set[str] = set()
    require_metadata = False
    labels: list[str] = []
    for scope in scopes:
        if not scope:
            continue
        changed.update(str(x) for x in scope.get("changed_parts") or [])
        added.update(str(x) for x in scope.get("added_parts") or [])
        removed.update(str(x) for x in scope.get("removed_parts") or [])
        required.update(str(x) for x in scope.get("required_changed_parts") or [])
        require_metadata = require_metadata or bool(scope.get("require_untouched_record_metadata"))
        if scope.get("label"):
            labels.append(str(scope.get("label")))
    return {
        "changed_parts": sorted(changed),
        "added_parts": sorted(added),
        "removed_parts": sorted(removed),
        "required_changed_parts": sorted(required),
        "require_untouched_record_metadata": require_metadata,
        "label": " + ".join(labels)[:240] or "P4.17_VERIFIED_TRANSFORMATION_TARGET_PARTS",
    }


def _rebind_operations_after_text(operations: list[dict], text_receipt: Mapping[str, Any] | None) -> list[dict]:
    if not operations or not text_receipt:
        return operations
    if not bool(text_receipt.get("structure_changed")):
        return operations
    rebinding = dict(text_receipt.get("locator_rebinding") or {})
    invalidated = {str(x) for x in rebinding.get("invalidated_revision_bound_locators") or []}
    mapping = {
        str(row.get("before_locator")): str(row.get("after_locator"))
        for row in rebinding.get("bindings") or []
        if row.get("before_locator") and row.get("after_locator")
    }
    out: list[dict] = []
    for op in operations:
        target = str(op.get("target") or "")
        if target in invalidated and target not in mapping:
            raise ValueError(f"LOCATOR_REACQUIRE_REQUIRED:{target}")
        rebound = mapping.get(target, target)
        out.append({**op, "target": rebound})
    return out


def _render_adjudication(render_evidence: Mapping[str, Any] | None) -> dict:
    if not render_evidence:
        return {
            "status": "NOT_PROVIDED",
            "native_visual_authority": False,
            "verdict": "NATIVE_RENDER_PENDING",
        }
    source = str(render_evidence.get("source") or "").strip().upper()
    return {
        "status": "EVIDENCE_PRESENT_UNADJUDICATED",
        "source": source or "UNSPECIFIED",
        "evidence_sha256": render_evidence.get("sha256"),
        "native_visual_authority": False,
        "verdict": "TRUSTED_NATIVE_RECEIPT_REQUIRED_FOR_NATIVE_AUTHORITY",
        "authority_boundary": "CALLER_SUPPLIED_RENDER_METADATA_CANNOT_SELF_AUTHORIZE_NATIVE_PASS",
    }


def _semantic_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict:
    before_roles = dict(before.get("role_counts") or {})
    after_roles = dict(after.get("role_counts") or {})
    roles = sorted(set(before_roles) | set(after_roles))
    return {
        "graph_changed": before.get("graph_sha256") != after.get("graph_sha256"),
        "block_count_before": int(before.get("block_count") or 0),
        "block_count_after": int(after.get("block_count") or 0),
        "role_count_delta": {
            role: int(after_roles.get(role, 0)) - int(before_roles.get(role, 0))
            for role in roles
            if int(after_roles.get(role, 0)) != int(before_roles.get(role, 0))
        },
    }


def execute_transformation_atomic(
    path: Path | str,
    plan: Mapping[str, Any],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
    reference_transfer: Mapping[str, Any] | None = None,
    repair_plan: Mapping[str, Any] | None = None,
    render_evidence: Mapping[str, Any] | None = None,
    replan_intent: Mapping[str, Any] | None = None,
) -> dict:
    path = Path(path)
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if str(plan.get("schema") or "") != PLAN_SCHEMA:
        raise ValueError("unsupported transformation plan schema")
    plan_decision = str(plan.get("decision") or "")
    if plan_decision not in {"SAFE_TO_PLAN", "DELEGATE"}:
        raise ValueError(f"transformation plan is not executable: {plan.get('decision')}")
    operations = [dict(x) for x in (plan.get("operations") or [])]
    delegates = [dict(x) for x in (plan.get("delegates") or [])]
    if not operations and not delegates:
        raise ValueError("transformation plan has no executable work")

    known = _TEXT_OPS | _FORMAT_OPS
    unknown = sorted({str(x.get("op") or "") for x in operations} - known)
    if unknown:
        raise ValueError("unsupported native execution operations: " + ", ".join(unknown))

    before_graph = recover_semantic_structure(path)
    before_doc = build_document_map(path)
    before_bytes = path.read_bytes()
    fidelity = assess_edit_fidelity_envelope(operations) if operations else None

    delegate_names = {str(x.get("delegate") or "") for x in delegates}
    reference_requested = "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER" in delegate_names
    repair_requested = "P3.40_P3.42_REPAIR_WITH_MUTATION_FOOTPRINT" in delegate_names
    if reference_requested and not reference_transfer:
        raise ValueError("reference-conditioned delegate requires reference_transfer payload")
    if repair_requested and not repair_plan:
        raise ValueError("repair delegate requires repair_plan payload")

    direct_scope = _expected_scope(
        path,
        operations,
        delegate_changes_header=False,
    )
    reference_scope = None
    if reference_requested:
        payload = dict(reference_transfer or {})
        reference_preview = plan_constraint_preserving_style_transfer(
            path,
            dict(payload.get("template") or {}),
            dict(payload.get("targets_by_role") or {}),
            dict(payload.get("policy") or {}),
            expected_revision=1,
        )
        reference_scope = reference_preview.get("expected_scope")
    repair_scope = (
        expected_scope_for_design_repair(path, dict(repair_plan or {}))
        if repair_requested
        else None
    )
    expected_scope = _merge_expected_scopes(direct_scope, reference_scope, repair_scope)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p417-exec-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(before_bytes)

    transcript: list[dict] = []
    validation = None
    reference_receipt = None
    repair_receipt = None
    try:
        text_ops = [op for op in operations if str(op.get("op") or "") in _TEXT_OPS]
        format_ops = [op for op in operations if str(op.get("op") or "") in _FORMAT_OPS]

        text_receipt = None
        if text_ops:
            text_receipt = apply_edits_atomic(
                candidate,
                text_ops,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            transcript.append({"lane": "P2_DOCUMENT_EDIT", "operation_count": len(text_ops), "receipt": text_receipt})

        if format_ops:
            rebound_format_ops = _rebind_operations_after_text(format_ops, text_receipt)
            receipt = apply_formatting_atomic(
                candidate,
                rebound_format_ops,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            transcript.append({"lane": "P2_FORMATTING", "operation_count": len(format_ops), "receipt": receipt})

        if reference_requested:
            payload = dict(reference_transfer or {})
            reference_receipt = apply_constraint_preserving_template_migration_atomic(
                candidate,
                dict(payload.get("template") or {}),
                dict(payload.get("targets_by_role") or {}),
                dict(payload.get("policy") or {}),
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            transcript.append({"lane": "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER", "receipt": reference_receipt})

        if repair_requested:
            repair_receipt = apply_document_design_repairs_with_footprint_atomic(
                candidate,
                dict(repair_plan or {}),
                expected_revision=1,
                current_revision=1,
                validator=None,
                required_grade=str((plan.get("preservation") or {}).get("required_grade") or "TARGETED_PARTS_ONLY"),
            )
            transcript.append({"lane": "P3.40_P3.42_REPAIR", "receipt": repair_receipt})

        if validator is not None:
            validation = validator(candidate)

        # The outer footprint remains authoritative across every composed lane.
        footprint = build_mutation_footprint(path, candidate, expected_scope=expected_scope)
        enforcement = enforce_preservation_grade(
            footprint,
            str((plan.get("preservation") or {}).get("required_grade") or "TARGETED_PARTS_ONLY"),
        )

        after_graph = recover_semantic_structure(candidate)
        after_doc = build_document_map(candidate)
        render = _render_adjudication(render_evidence)

        next_plan = None
        if replan_intent:
            next_plan = plan_document_transformation(
                intent=dict(replan_intent),
                semantic_graph=after_graph,
                document_map=after_doc,
                reference_graph=None,
                archetype=None,
            )

        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    semantic_delta = _semantic_delta(before_graph, after_graph)
    structure_changed = before_doc.get("structure_sha256") != after_doc.get("structure_sha256")
    package_sha_after = hashlib.sha256(path.read_bytes()).hexdigest()

    if repair_receipt is not None:
        verdict = "REPAIRED_AND_STRUCTURALLY_VERIFIED_NATIVE_RENDER_PENDING"
    else:
        verdict = "STRUCTURALLY_VERIFIED_NATIVE_RENDER_PENDING"

    result = {
        "schema": EXECUTION_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "plan_sha256": plan.get("plan_sha256"),
        "revision_before": int(current_revision),
        "revision_after": int(current_revision) + 1,
        "operation_count": len(operations),
        "delegate_count": len(delegates),
        "transcript": transcript,
        "fidelity_envelope": fidelity,
        "mutation_footprint": footprint,
        "preservation_enforcement": enforcement,
        "before": {
            "package_sha256": hashlib.sha256(before_bytes).hexdigest(),
            "semantic_graph_sha256": before_graph.get("graph_sha256"),
            "semantic_sha256": before_doc.get("semantic_sha256"),
            "structure_sha256": before_doc.get("structure_sha256"),
        },
        "after": {
            "package_sha256": package_sha_after,
            "semantic_graph_sha256": after_graph.get("graph_sha256"),
            "semantic_sha256": after_doc.get("semantic_sha256"),
            "structure_sha256": after_doc.get("structure_sha256"),
        },
        "semantic_delta": semantic_delta,
        "structure_changed": structure_changed,
        "package_validation": validation,
        "render_validation": render,
        "repair_applied": repair_receipt is not None,
        "reference_transfer_applied": reference_receipt is not None,
        "next_plan": next_plan,
        "verdict": verdict,
        "authority": "EXECUTED_VERIFIED_NATIVE_TRANSFORMATION_WITH_BOUNDED_VISUAL_AUTHORITY",
    }
    result["execution_receipt_sha256"] = _sha(result)
    return result



def compose_post_edit_native_authority(
    execution_receipt: Mapping[str, Any],
    native_trust_receipt: Mapping[str, Any],
) -> dict:
    if str(execution_receipt.get("schema") or "") != EXECUTION_SCHEMA:
        raise ValueError("unsupported execution receipt schema")
    expected_execution_sha = str(execution_receipt.get("execution_receipt_sha256") or "")
    if not expected_execution_sha:
        raise ValueError("execution receipt hash is required")
    unhashed = dict(execution_receipt)
    unhashed.pop("execution_receipt_sha256", None)
    if _sha(unhashed) != expected_execution_sha:
        raise ValueError("execution receipt hash mismatch")

    authority_class = str(native_trust_receipt.get("authority_class") or "")
    after_sha = str((execution_receipt.get("after") or {}).get("package_sha256") or "")
    trust_sha = str(native_trust_receipt.get("document_sha256") or "")
    revision_after = int(execution_receipt.get("revision_after") or 0)
    trust_revision = int(native_trust_receipt.get("revision") or 0)
    binding_ok = bool(after_sha) and after_sha == trust_sha and revision_after == trust_revision

    if not binding_ok:
        verdict = "NATIVE_TRUST_RECEIPT_NOT_BOUND_TO_EXECUTION"
        native = False
    elif authority_class == "PER_DOCUMENT_NATIVE_VERIFIED":
        verdict = "VERIFIED"
        native = True
    elif authority_class == "NATIVE_VERIFICATION_FAILED":
        verdict = "NATIVE_RENDER_FAILED"
        native = False
    else:
        verdict = "STRUCTURALLY_VERIFIED_NATIVE_RENDER_PENDING"
        native = False

    result = {
        "schema": POST_EDIT_RENDER_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "execution_receipt_sha256": expected_execution_sha,
        "document_id": native_trust_receipt.get("document_id"),
        "revision": trust_revision,
        "package_sha256": after_sha,
        "trust_receipt_sha256": native_trust_receipt.get("trust_receipt_sha256"),
        "native_authority_class": authority_class or "NATIVE_VERIFICATION_PENDING",
        "binding_verified": binding_ok,
        "native_visual_authority": native,
        "verdict": verdict,
        "authority": "P417_POST_EDIT_NATIVE_AUTHORITY_COMPOSED_FROM_P414_SIGNED_EVIDENCE",
    }
    result["post_edit_authority_sha256"] = _sha(result)
    return result
