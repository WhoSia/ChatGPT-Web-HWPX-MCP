"""Trusted host-only P4.18-P3 mutation execution coordination.

No MCP tool calls this module. It MUST be invoked by an authenticated,
independent user-confirmation host with a verified approval key, current owned
document bindings, and a deterministic commit-receipt verifier.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError, DurableApprovalLedger


def execute_approved_once(
    *, ledger: DurableApprovalLedger, owner: str, workflow_id: str,
    approval_key: str, draft_sha256: str, preview_sha256: str,
    bound_inputs: Mapping[str, Any], effect_scope: str, execution_key: str,
    verify_live_bindings: Callable[[str, Mapping], bool],
    perform_authorized_effect: Callable[[], Mapping[str, Any]],
    verify_durable_commit: Callable[[str, Mapping], bool],
) -> dict[str, Any]:
    """Conservatively execute one approved operation, never blindly retry.

    Atomicity across a database claim and an external HWPX document commit is
    impossible without shared transaction ownership. If a crash occurs
    between the two, later callers receive UNCERTAIN and only a verified
    existing commit may be reconciled; *no second execution is attempted*.
    """
    for name, callback in (
        ("verify_live_bindings", verify_live_bindings),
        ("perform_authorized_effect", perform_authorized_effect),
        ("verify_durable_commit", verify_durable_commit),
    ):
        if not callable(callback):
            raise AdmissionError(f"trusted host {name} callback required")
    claim = ledger.claim(
        owner=owner, workflow_id=workflow_id, approval_key=approval_key,
        draft_sha256=draft_sha256, preview_sha256=preview_sha256,
        bound_inputs=bound_inputs, effect_scope=effect_scope,
        execution_key=execution_key, verify_live_bindings=verify_live_bindings)
    if claim["state"] == "COMMITTED":
        return {"state": "COMMITTED", "mutation_executed": False,
                "delivery_only": True, "result": claim["result"]}
    if claim["state"] != "CLAIMED":
        return {"state": "UNCERTAIN", "mutation_executed": False,
                "delivery_only": False, "requires_reconciliation": True}
    try:
        receipt = perform_authorized_effect()
        if not isinstance(receipt, Mapping) or not verify_durable_commit(owner, receipt):
            raise AdmissionError("underlying durable commit receipt not verified")
        committed = ledger.committed(
            owner=owner, workflow_id=workflow_id, execution_key=execution_key,
            result=receipt, verify_commit=verify_durable_commit)
        return {"state": "COMMITTED", "mutation_executed": True,
                "delivery_only": False, "result": committed["result"]}
    except Exception:
        # A mutation might already have been committed. Quarantine; do not retry.
        ledger.recover(owner=owner, workflow_id=workflow_id)
        raise


def execute_exact_approved_draft(
    *, ledger: DurableApprovalLedger, owner: str, workflow_id: str,
    approval_key: str, draft: Mapping[str, Any], preview: Mapping[str, Any],
    bound_inputs: Mapping[str, Any], execution_key: str,
    verify_live_bindings: Callable[[str, Mapping], bool],
    execute_normalized_task: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    verify_durable_commit: Callable[[str, Mapping], bool],
) -> dict[str, Any]:
    """Bind the executed semantic task to the exact displayed approved draft.

    Never expose this function to arbitrary MCP clients; authorization and
    execution callbacks belong to the trusted independent host.
    """
    from p418_product import normalize_document_task
    from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
    canonical_preview = preview_workflow(draft)
    if not isinstance(preview, Mapping) or dict(preview) != canonical_preview:
        raise AdmissionError("approved preview differs from canonical draft")
    steps = draft["steps"]
    mutations = [s for s in steps if s["effect"] == "MUTATION"]
    if len(mutations) != 1:
        raise AdmissionError("a single approved mutation is required")
    task = mutations[0]["task"]
    if not isinstance(task, Mapping) or normalize_document_task(task) != task:
        raise AdmissionError("executed task differs from normalized approved task")
    if not callable(execute_normalized_task):
        raise AdmissionError("trusted normalized-task executor required")
    return execute_approved_once(
        ledger=ledger, owner=owner, workflow_id=workflow_id,
        approval_key=approval_key,
        draft_sha256=draft["draft_sha256"],
        preview_sha256=canonical_preview["preview_sha256"],
        bound_inputs=bound_inputs, effect_scope=task["kind"],
        execution_key=execution_key,
        verify_live_bindings=verify_live_bindings,
        perform_authorized_effect=lambda: execute_normalized_task(dict(task)),
        verify_durable_commit=verify_durable_commit)
