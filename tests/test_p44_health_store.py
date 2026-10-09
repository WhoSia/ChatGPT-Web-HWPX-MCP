import os,uuid,pytest
from hwpx_mcp.quality.p44_health_store import DurableHealthIntelligenceStore
DB=os.environ.get("P44_TEST_DATABASE_URL","")
@pytest.mark.skipif(not DB,reason="P44_TEST_DATABASE_URL not configured")
def test_store_append_only_idempotent():
 s=DurableHealthIntelligenceStore(DB);x=uuid.uuid4().hex;o={"phase":"P4.4-TEST","product":"0.30.0-p4.4","exact_head":x,"observed_at":"2026-09-29T05:30:00+00:00","python_hwpx":"6.6.0","metrics":{"create_validate_p95_ms":101.0}};assert s.append_release_observation(o)["inserted"] is True;assert s.append_release_observation(o)["inserted"] is False;assert any(r["exact_head"]==x for r in s.query_release_observations(phase="P4.4-TEST"));sid="test-"+x;assert s.append_corpus_provenance({"source_id":sid,"federation_namespace":"pytest","source_kind":"TEST","observed_at":"2026-09-29T05:30:00+00:00"})["inserted"] is True;assert any(r["source_id"]==sid for r in s.query_corpus_provenance(namespace="pytest"));assert not hasattr(s,"update_release_observation")
