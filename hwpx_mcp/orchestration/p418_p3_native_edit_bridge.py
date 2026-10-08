"""P4.18-P3 host-only bridge from approved EDIT_INTENT to native document custody.

This module is NOT registered as an MCP tool or as a public HTTP endpoint.
Only a trusted authenticated host, after independent human approval, may call
this bridge with a DurableApprovalLedger approval key. An LLM-provided boolean
or workflow hash is never an authorization grant.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hwpx_mcp.orchestration.p418_p2_admission import (
    AdmissionError,
    DurableApprovalLedger,
)
from hwpx_mcp.orchestration.p418_p3_execution import execute_exact_approved_draft
from hwpx_mcp.orchestration.p418_p3_owned_commit_bridge import (
    verify_server_owned_edit_commit,
)


def execute_host_approved_native_edit(
    *, core: Any, ledger: DurableApprovalLedger, workflow_id: str,
    approval_key: str, draft: Mapping[str, Any], preview: Mapping[str, Any],
    bound_inputs: Mapping[str, Any], execution_key: str,
    native_edit_adapter: Callable[..., Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute one verified edit with a durable document-store readback.

    The host owns native_edit_adapter (e.g. _p418_edit_intent_adapter in
    server_p2.py); the MCP caller must not choose a callback. The complete
    exact-task fingerprint and staging bindings are checked before claiming,
    and the ledger rechecks bindings under its row lock.

    For a crash after a real commit but before the ledger receipt, fail closed:
    the existing coordinator marks UNCERTAIN. It never auto-reruns the edit.
    """
    if not callable(native_edit_adapter):
        raise AdmissionError("trusted native edit adapter required")
    if not callable(getattr(core, "_caller_subject", None)):
        raise AdmissionError("authenticated host request context required")
    owner = core._caller_subject()
    if not isinstance(owner, str) or not owner:
        raise AdmissionError("authenticated owner required")
    if not isinstance(draft, Mapping) or not isinstance(draft.get("steps"), list):
        raise AdmissionError("canonical approved workflow required")

    edits = [
        step["task"] for step in draft["steps"]
        if isinstance(step, Mapping) and step.get("effect") == "MUTATION"
    ]
    if len(edits) != 1 or edits[0].get("kind") != "EDIT_INTENT":
        raise AdmissionError("native edit bridge only admits one EDIT_INTENT")
    approved_task = edits[0]

    # This exact role layout is produced by stage_p418_document_workflow.
    if not isinstance(bound_inputs, Mapping) or set(bound_inputs) != {"documents"}:
        raise AdmissionError("server-staged document custody bindings required")
    rows = bound_inputs["documents"]
    if not isinstance(rows, list):
        raise AdmissionError("staged document binding list required")
    required = [("document_id", approved_task["document_id"])]
    reference_id = approved_task.get("reference_document_id")
    if reference_id:
        required.append(("reference_document_id", reference_id))
    if [(r.get("role"), r.get("document_id")) for r in rows
        if isinstance(r, Mapping)] != required or len(rows) != len(required):
        raise AdmissionError("approved task does not match staged document roles")

    def verify_live_bindings(subject: str, snapshot: Mapping[str, Any]) -> bool:
        if subject != owner or snapshot != bound_inputs:
            return False
        try:
            for row, (role, document_id) in zip(rows, required):
                metadata = core._load_metadata(document_id)
                core._require_owner(metadata)
                if row.get("role") != role or row.get("document_id") != document_id:
                    return False
                if type(row.get("revision")) is not int:
                    return False
                if row["revision"] != int(metadata["revision"]):
                    return False
                if row.get("sha256") != str(metadata.get("sha256", "")):
                    return False
                if not row["sha256"]:
                    return False
            return rows[0]["revision"] == approved_task["expected_revision"]
        except (PermissionError, FileNotFoundError, KeyError, TypeError, ValueError):
            return False

    store = getattr(core, "DOCUMENT_STORE", None)
    if not callable(getattr(store, "get_commit_receipt", None)):
        raise AdmissionError("durable document commit receipt store required")

    def verify_commit(subject: str, receipt: Mapping[str, Any]) -> bool:
        return verify_server_owned_edit_commit(
            core=core, owner=subject, task=approved_task, receipt=receipt,
        )

    def perform(task: Mapping[str, Any]) -> Mapping[str, Any]:
        if task != approved_task:
            raise AdmissionError("native adapter task differs from approved edit")
        result = native_edit_adapter(
            document_id=task["document_id"],
            expected_revision=task["expected_revision"],
            intent=task["intent"],
            reference_document_id=task["reference_document_id"],
            reference_transfer=task["reference_transfer"],
            repair_plan=task["repair_plan"],
            replan_intent=task["replan_intent"],
            lease_token=task["lease_token"],
        )
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            raise AdmissionError("native edit was not durably committed")
        if (
            result.get("document_id") != task["document_id"]
            or result.get("revision_before") != task["expected_revision"]
            or result.get("revision_after") != task["expected_revision"] + 1
        ):
            raise AdmissionError("native edit result differs from approved revision")
        receipt = store.get_commit_receipt(task["document_id"], result["revision_after"])
        if not isinstance(receipt, Mapping):
            raise AdmissionError("durable source commit receipt missing")
        return dict(receipt)

    return execute_exact_approved_draft(
        ledger=ledger, owner=owner, workflow_id=workflow_id,
        approval_key=approval_key, draft=draft, preview=preview,
        bound_inputs=bound_inputs, execution_key=execution_key,
        verify_live_bindings=verify_live_bindings,
        execute_normalized_task=perform, verify_durable_commit=verify_commit,
    )
