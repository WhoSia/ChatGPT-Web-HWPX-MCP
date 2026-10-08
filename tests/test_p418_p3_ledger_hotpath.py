"""Fast path caches ledger setup, not transaction state."""
from hwpx_mcp.orchestration import p418_p2_admission as admission


def test_cache_reuses_init_but_isolates_different_database_urls(monkeypatch):
    admission.get_durable_approval_ledger.cache_clear()
    seen = []
    class FakeLedger:
        def __init__(self, url):
            seen.append(url)
            self.database_url = url
    monkeypatch.setattr(admission, "DurableApprovalLedger", FakeLedger)
    first = admission.get_durable_approval_ledger("postgresql://a")
    again = admission.get_durable_approval_ledger("postgresql://a")
    second = admission.get_durable_approval_ledger("postgresql://b")
    assert first is again and first is not second
    assert seen == ["postgresql://a", "postgresql://b"]
    admission.get_durable_approval_ledger.cache_clear()
