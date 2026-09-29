from __future__ import annotations

from p41_operational import diagnose_failure, evaluate_upgrade_candidate, operational_readiness_contract, runtime_compatibility_matrix

contract = operational_readiness_contract()
assert contract["phase"] == "P4.1"
assert contract["product"] == "0.27.0-p4.1"
assert contract["new_architecture_by_default"] is False
matrix = runtime_compatibility_matrix("6.6.0")
assert matrix["production_pin_unchanged"] is True
assert diagnose_failure("stale revision CAS mismatch")["category"] == "CONCURRENCY_CONFLICT"
hold = evaluate_upgrade_candidate("6.6.0", {"candidate_probe": True})
assert hold["verdict"] == "HOLD"
print("P4.1 release smoke PASS")
