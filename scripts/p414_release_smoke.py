from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p414_evidence_service import (
    PRODUCT,
    capture_agent_contract,
    compare_native_visual_drift,
    document_native_trust_receipt,
    evaluate_release_capture_obligation,
    evaluate_rollback_authority,
    hancom_build_matrix,
    release_change_vectors,
)

contract = capture_agent_contract()
assert contract["product"] == PRODUCT and contract["protocol_version"] == "1.0"
assert "NO_WATCHER" in contract["source_access"] and "NEVER_GLOBAL_KILL" in contract["process_custody"]
previous, candidate = release_change_vectors(exact_head="a" * 40)
obligation = evaluate_release_capture_obligation(previous=previous, candidate=candidate)
assert obligation["status"] == "FRESH_CAPTURE_REQUIRED"
assert obligation["triggers"][0]["code"] == "CAPTURE_AGENT_PROTOCOL_CHANGE"
matrix = hancom_build_matrix([])
assert matrix["prior_certified_release"]["exact_head"] == "adeb06e6f55fbc0b7116e998ebbfe3ed18811754"
assert matrix["inherited_release_baseline_is_not_agent_cell"]
drift = compare_native_visual_drift({"cases": []}, {"cases": [{"fixture_id": "f", "semantic_visible": False}]})
assert drift["status"] == "BLOCKING_REGRESSION"
pending = document_native_trust_receipt(document_id="smoke", revision=1, sha256="a" * 64)
assert pending["authority_class"] == "NATIVE_VERIFICATION_PENDING"
denied = evaluate_rollback_authority(signed_evidence_validation={"accepted": False}, drift_receipt=drift, current_release={}, target_release={})
assert denied["status"] == "DENIED"
print("P4.14 protocol/obligation/matrix/drift/rollback/trust smoke PASS; native capture remains unclaimed")
