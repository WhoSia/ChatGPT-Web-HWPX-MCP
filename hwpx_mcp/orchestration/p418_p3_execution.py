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
