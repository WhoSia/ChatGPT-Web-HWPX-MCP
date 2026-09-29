from p45_quality_control import active_corpus_governance,audit_feature_attribution,build_operator_alerts,create_incident_event,derive_incident_lifecycle,quality_control_contract,slo_readiness

def _row(i):
 return {"phase":f"P4.{i}","product":f"0.{26+i}","exact_head":f"{i:040x}","observed_at":f"2026-09-{20+i:02d}T00:00:00+00:00","metrics":{"create_validate_p95_ms":100+i}}

def test_contract_preserves_authority():
 c=quality_control_contract();assert c["authority_boundary"]["authoring"]=="python-hwpx==6.6.0" and c["authority_boundary"]["native_render"].startswith("explicit")

def test_slo_governance_does_not_prematurely_calibrate():
 assert slo_readiness([_row(i) for i in range(4)])["state"]=="PROVISIONAL_HARD_BUDGET"
 assert slo_readiness([_row(i) for i in range(5)])["state"]=="CALIBRATION_READY_PENDING_NEXT_OBSERVATION"
 assert slo_readiness([_row(i) for i in range(6)])["calibrated_slo"] is True

def test_attribution_incident_and_alert_lifecycle():
 assert audit_feature_attribution({"top_family":"TABLES","top_confidence":.8,"candidates":[1]},required_family="tables")["verdict"]=="MATCH"
 assert audit_feature_attribution({"abstain":True})["verdict"]=="ABSTAIN"
 opened=create_incident_event({"locus":"INDEPENDENT_ORACLE_DIVERGENCE","severity":"HIGH"})
 resolved=create_incident_event({},incident_id=opened["incident_id"],action="RESOLVE")
 life=derive_incident_lifecycle([opened,resolved]);assert life[0]["status"]=="RESOLVED"
 assert build_operator_alerts([_row(1),_row(2)],[opened])["alert_count"]>=1

def test_corpus_governance_keeps_freshness_nonblocking():
 r=active_corpus_governance([{ "source_id":"a","federation_namespace":"live","source_kind":"LIVE_OFFICIAL_FRESHNESS","blocking":False}]);assert r["freshness_is_release_blocking"] is False
