"""Server-owned bridge for independently checking committed edit receipts.

No approval or mutation endpoint is exposed by this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hwpx_mcp.orchestration.p418_p3_commit_verifier import verify_owned_hwp_commit


def verify_server_owned_edit_commit(
    *, core: Any, owner: str, task: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> bool:
    """Require exact owner, revision and persisted commit proof."""
    caller = getattr(core, "_caller_subject", None)
    if not callable(caller) or caller() != owner:
        return False
    if not isinstance(task, Mapping) or task.get("kind") != "EDIT_INTENT":
        return False
    document_id = task.get("document_id")
    expected = task.get("expected_revision")
    if not isinstance(document_id, str) or not document_id:
        return False
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        return False
    store = getattr(core, "DOCUMENT_STORE", None)
    if store is None or not callable(getattr(store, "get_commit_receipt", None)):
        return False

    def verify_owner(subject: str, target_id: str) -> bool:
        if subject != owner or target_id != document_id:
            return False
        metadata = core._load_metadata(target_id)
        core._require_owner(metadata)
        return int(metadata.get("revision", -1)) >= expected + 1

    return verify_owned_hwp_commit(
        owner=owner, result=receipt, store=store,
        require_owner=verify_owner, document_id=document_id,
        expected_revision=expected,
    )
