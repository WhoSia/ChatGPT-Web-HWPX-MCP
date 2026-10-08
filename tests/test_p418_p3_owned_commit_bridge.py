from types import SimpleNamespace

from hwpx_mcp.orchestration.p418_p3_owned_commit_bridge import verify_server_owned_edit_commit

RECEIPT = {
    "document_id": "docA", "revision": 4, "expected_revision": 3,
    "sha256": "a" * 64, "receipt_id": "receipt-4", "audit_hash": "b" * 64,
}
TASK = {"kind": "EDIT_INTENT", "document_id": "docA", "expected_revision": 3}


class FakeStore:
    def __init__(self, receipt):
        self.receipt = receipt
    def get_commit_receipt(self, document_id, revision):
        assert document_id == "docA" and revision == 4
        return self.receipt


class FakeCore:
    def __init__(self, receipt=RECEIPT, owner="owner", current_revision=4):
        self.DOCUMENT_STORE = FakeStore(receipt)
        self.owner = owner
        self.current_revision = current_revision
    def _caller_subject(self):
        return "owner"
    def _load_metadata(self, document_id):
        assert document_id == "docA"
        return {"revision": self.current_revision, "owner": self.owner}
    def _require_owner(self, metadata):
        if metadata["owner"] != "owner":
            raise PermissionError("not owner")


def verify(*, core=None, task=None, result=None, owner="owner"):
    return verify_server_owned_edit_commit(
        core=FakeCore() if core is None else core,
        owner=owner, task=TASK if task is None else task,
        receipt=RECEIPT if result is None else result,
    )


def test_server_owned_commit_receipt_matches():
    assert verify()


def test_stale_or_forged_commit_receipt_fails_closed():
    for key, value in (
        ("expected_revision", 2), ("revision", 5),
        ("receipt_id", "other"), ("sha256", "c" * 64),
        ("audit_hash", "d" * 64), ("document_id", "other"),
    ):
        assert not verify(result={**RECEIPT, key: value})


def test_source_revision_or_owner_is_checked_live():
    assert not verify(core=FakeCore(current_revision=3))
    assert not verify(core=FakeCore(owner="other"))
    assert not verify(owner="other")


def test_missing_durable_commit_is_rejected():
    assert not verify(core=FakeCore(receipt=None))
    assert not verify(task={**TASK, "kind": "CREATE"})
