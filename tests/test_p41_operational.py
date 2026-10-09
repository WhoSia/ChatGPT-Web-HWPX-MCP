from __future__ import annotations

import hwpx_mcp.operations.p41_operational as p41_operational as op

def test_contract_and_runtime_matrix_are_product_scoped():
    contract = op.operational_readiness_contract()
    assert contract["phase"] == "P4.1"
    assert contract["product"] == "0.27.0-p4.1"
    assert contract["new_architecture_by_default"] is False
    matrix = op.runtime_compatibility_matrix("6.6.0")
    assert matrix["production_pin_unchanged"] is True
    assert any(row["component"] == "python-hwpx migration candidate" for row in matrix["rows"])

def test_failure_taxonomy_is_actionable_without_raw_echo():
    auth = op.diagnose_failure("401 invalid_token from OAuth boundary")
    assert auth["category"] == "AUTH_REQUIRED"
    assert auth["retryable"] is True
    assert auth["raw_exception_echoed"] is False
    cas = op.diagnose_failure("P3.49 composition generation CAS mismatch")
    assert cas["category"] == "CONCURRENCY_CONFLICT"

def test_upgrade_candidate_never_changes_pin_implicitly():
    evidence = {
        "candidate_probe": True,
        "legacy_compatibility": True,
        "product_workflow": True,
        "full_lifecycle": True,
        "docker_smoke": True,
    }
    out = op.evaluate_upgrade_candidate("6.6.0", evidence)
    assert out["verdict"] == "READY_FOR_CONTROLLED_CANARY"
    assert out["production_pin_unchanged"] is True
    hold = op.evaluate_upgrade_candidate("6.6.0", {**evidence, "legacy_compatibility": False})
    assert hold["verdict"] == "HOLD"
    assert hold["missing_or_failed_evidence"] == ["legacy_compatibility"]

def test_profiler_records_latency_memory_and_regression_status():
    row = op.profile_callable("noop", lambda: None, sample_count=2, hard_ceiling_ms=1000)
    assert row["status"] == "PASS"
    assert row["samples"] == 2
    assert row["latency_ms"]["p95"] >= 0
    assert row["python_peak_bytes"] >= 0
