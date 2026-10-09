"""P4.19 user-facing workspace overview: one read-only call, no approval power."""
from __future__ import annotations

import time


def workspace_overview(core, owned_document, document_id: str, *, now: float | None = None) -> dict:
    """Aggregate current owner-scoped custody, history and next actions.

    Never bypass expiry, request an edit lease, mint a download token, or claim
    content fidelity from byte counts. The caller supplies _owned_document.
    """
    metadata, _ = owned_document(document_id)
    timestamp = time.time() if now is None else now
    expires = float(metadata["expires_at_epoch"])
    seconds = max(0, int(expires - timestamp))
    revision = int(metadata["revision"])
    versions = core.DOCUMENT_STORE.list_revisions(document_id)
    receipt = core.DOCUMENT_STORE.get_commit_receipt(document_id, revision)
    if receipt is None or receipt.get("sha256") != metadata.get("sha256"):
        raise RuntimeError("Durable current-revision receipt mismatch")
    if not any(int(item["revision"]) == revision and item["sha256"] == metadata["sha256"] for item in versions):
        raise RuntimeError("Current revision missing from durable history")
    urgency = "EXPIRING_SOON" if seconds < 900 else "ACTIVE"
    return {
        "ok": True,
        "schema": "chatgpt-web-hwpx-mcp/p4.19/workspace-overview/v1",
        "document_id": document_id,
        "filename": metadata.get("filename", "document.hwpx"),
        "revision": revision,
        "sha256": metadata["sha256"],
        "storage": core.DOCUMENT_STORE.mode,
        "expires_at": metadata.get("expires_at"),
        "seconds_until_expiry": seconds,
        "lifecycle": urgency,
        "version_count": len(versions),
        "versions": [{"revision": int(v["revision"]), "sha256": v["sha256"],
                      "bytes": int(v["bytes"]), "is_current": bool(v["is_current"])}
                     for v in versions],
        "current_commit": {"revision": revision, "receipt_id": receipt["receipt_id"],
                           "audit_hash": receipt["audit_hash"], "sha256": receipt["sha256"]},
        "content_preservation": "NOT_INFERRED_FROM_HASH_OR_BYTE_LENGTH",
        "delivery": {"status": "NOT_YET_VERIFIED",
                     "next_tool": "export_document",
                     "note": "A signed link is not proof that the client downloaded and opened the HWPX."},
        "next_actions": (["Export and verify document before expiration"] if seconds < 900
                         else ["Review document", "Export when ready"]),
        "authority": "OWNER_SCOPED_READ_ONLY_WORKSPACE_OVERVIEW",
    }
