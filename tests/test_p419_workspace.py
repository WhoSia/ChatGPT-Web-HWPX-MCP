from types import SimpleNamespace

import pytest

from hwpx_mcp.orchestration.p419_product import workspace_overview


class Store:
    mode = "postgres-encrypted-versioned"

    def __init__(self, receipt_sha="abc"):
        self.receipt_sha = receipt_sha

    def list_revisions(self, document_id):
        return [{"revision": 1, "sha256": "old", "bytes": 10, "is_current": False},
                {"revision": 2, "sha256": "abc", "bytes": 12, "is_current": True}]

    def get_commit_receipt(self, document_id, revision):
        return {"revision": 2, "sha256": self.receipt_sha,
                "receipt_id": "receipt-test", "audit_hash": "audit-test"}


def owned(document_id):
    return ({"revision": 2, "sha256": "abc", "expires_at_epoch": 2000,
             "expires_at": "expiry", "filename": "doc.hwpx"}, None)


def test_workspace_aggregation_is_read_only_and_honest():
    result = workspace_overview(SimpleNamespace(DOCUMENT_STORE=Store()), owned, "doc_test", now=1100)
    assert result["ok"] is True
    assert result["revision"] == 2
    assert result["lifecycle"] == "EXPIRING_SOON"
    assert result["version_count"] == 2
    assert result["current_commit"]["receipt_id"] == "receipt-test"
    assert result["delivery"]["status"] == "NOT_YET_VERIFIED"
    assert result["content_preservation"] == "NOT_INFERRED_FROM_HASH_OR_BYTE_LENGTH"
    assert result["authority"] == "OWNER_SCOPED_READ_ONLY_WORKSPACE_OVERVIEW"


def test_workspace_fails_closed_on_mismatched_durable_receipt():
    with pytest.raises(RuntimeError, match="receipt mismatch"):
        workspace_overview(SimpleNamespace(DOCUMENT_STORE=Store("wrong")), owned, "doc_test", now=1100)


def test_workspace_does_not_bypass_owner_or_expiry():
    def forbidden(document_id):
        raise FileNotFoundError("Unknown document_id")
    with pytest.raises(FileNotFoundError):
        workspace_overview(SimpleNamespace(DOCUMENT_STORE=Store()), forbidden, "doc_test", now=1100)
