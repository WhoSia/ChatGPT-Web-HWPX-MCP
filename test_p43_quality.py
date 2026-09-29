from __future__ import annotations
from p43_quality import (
    adjudicate_release_health,build_failure_bundle,calibrate_budget,
    load_release_history,localize_regression,quality_service_contract,
)

def test_contract_and_history_are_bounded():
    c=quality_service_contract()
    assert c["phase"]=="P4.3"
    assert c["product"]=="0.29.0-p4.3"
    assert c["independent_oracles"][2]["name"]=="hwpxkit"
    h=load_release_history()
    assert h["entry_count"]==2
    b=calibrate_budget(h,"create_validate_p95_ms")
    assert b["mode"]=="PROVISIONAL_HARD_BUDGET"
    assert b["calibrated_slo"] is False

def test_regression_localizer_distinguishes_engine_and_container():
    x=localize_regression({"raw_owpml_pass":True,"python_hwpx_pass":False,"hwpxkit_pass":True,"feature_family":"TABLES"})
    assert x["locus"]=="PRIMARY_ENGINE_COMPATIBILITY"
    y=localize_regression({"raw_owpml_pass":False,"python_hwpx_pass":False,"hwpxkit_pass":False})
    assert y["locus"]=="PACKAGE_OR_CONTAINER"

def test_failure_bundle_is_reproducible_and_privacy_bounded():
    c={"feature_family":"DRAWING_LAYER","document_sha256":"a"*64,"oracle":"python-hwpx","oracle_version":"6.6.0","error_class":"ValueError","message":"bad fixture","raw_owpml_pass":True,"python_hwpx_pass":False,"hwpxkit_pass":True}
    a=build_failure_bundle(c);b=build_failure_bundle(c)
    assert a["bundle_id"]==b["bundle_id"]
    assert a["raw_document_bytes_included"] is False
    assert a["raw_stack_trace_included"] is False
    assert "traceback" not in a

def test_health_gate_requires_representative_and_operational_evidence():
    r=adjudicate_release_health({"feature_family_count":5,"public_document_count":3,"generated_fixture_count":24,"product_authority_pass":True,"independent_oracle_coverage":0.9,"performance_budget_pass":True,"diagnostic_negative_control_pass":True,"docker_pass":True,"rollback_ready":True,"critical_failure_count":0})
    assert r["verdict"]=="PASS"
    r2=adjudicate_release_health({"feature_family_count":4})
    assert r2["verdict"]=="HOLD"
