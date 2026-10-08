from copy import deepcopy

from hwpx_mcp.orchestration.p418_p3_commit_verifier import verify_owned_hwp_commit

COMMIT = {
    "document_id": "docA", "revision": 7, "expected_revision": 6,
    "sha256": "a" * 64, "receipt_id": "receipt-A",
    "audit_hash": "b" * 64,
}

class Store:
    def __init__(self, receipt=None):
        self.receipt = deepcopy(COMMIT if receipt is None else receipt)
    def get_commit_receipt(self, document_id, revision):
        assert document_id == "docA" and revision == 7
        return self.receipt

def verify(result=None, receipt=None, owner="owner", authorized=True, **kwargs):
    return verify_owned_hwp_commit(
        owner=owner, result=COMMIT if result is None else result,
        store=Store(receipt),
        require_owner=lambda who, doc: authorized and who == "owner" and doc == "docA",
        document_id="docA", expected_revision=6, **kwargs,
    )

def test_exact_owned_durable_commit_is_accepted():
    assert verify()

def test_different_owner_or_missing_document_custody_is_rejected():
    assert not verify(owner="other")
    assert not verify(authorized=False)
    assert not verify(receipt={})

def test_mismatched_digest_audit_receipt_or_revision_fails():
    for field, changed in [
        ("sha256", "0"*64), ("receipt_id", "forged"),
        ("audit_hash", "c"*64), ("expected_revision", 5),
        ("revision", 6), ("document_id", "other")
    ]:
        forged = {**COMMIT, field: changed}
        assert not verify(result=forged)

def test_missing_audit_hash_fails_closed():
    assert not verify(receipt={**COMMIT, "audit_hash": None})
