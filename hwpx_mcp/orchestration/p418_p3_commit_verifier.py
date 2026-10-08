"""Host-side independent HWPX document commit receipt verification.

The resolver and store must be trusted server dependencies, not MCP caller data.
This guards delivery and P3 ledger reconciliation against fabricated success.
"""
from __future__ import annotations
import hmac
from collections.abc import Callable, Mapping
from typing import Any

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError


def verify_owned_hwp_commit(
    *, owner: str, result: Mapping[str, Any],
    store: Any, require_owner: Callable[[str, str], bool],
    document_id: str, expected_revision: int,
) -> bool:
    if not isinstance(result, Mapping) or not callable(require_owner):
        return False
    if not isinstance(document_id, str) or not document_id:
        return False
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        return False
    if result.get("document_id") != document_id:
        return False
    revision = result.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        return False
    if revision != expected_revision + 1:
        return False
    if not require_owner(owner, document_id):
        return False
    receipt = store.get_commit_receipt(document_id, revision)
    if not isinstance(receipt, Mapping):
        return False
    if result.get("expected_revision") != expected_revision:
        return False
    for field in ("document_id", "revision", "expected_revision"):
        if receipt.get(field) != {"document_id": document_id,
                                 "revision": revision,
                                 "expected_revision": expected_revision}[field]:
            return False
    for field in ("sha256", "receipt_id", "audit_hash"):
        actual, claimed = receipt.get(field), result.get(field)
        if not isinstance(actual, str) or not actual or not isinstance(claimed, str):
            return False
        if not hmac.compare_digest(actual, claimed):
            return False
    return True
