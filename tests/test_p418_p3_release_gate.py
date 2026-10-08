import pytest
from hwpx_mcp.orchestration.p418_p3_release_gate import REQUIRED, assess_p3_release

HEAD = "a" * 40

def complete():
    return {"head_sha": HEAD, "gates": {
        name: {"head_sha": HEAD, "status": "PASS", "evidence_ref": "evidence:" + name}
        for name in REQUIRED
    }}

def test_full_evidence_is_advisory_not_deploy_permission():
    verdict = assess_p3_release(complete())
    assert verdict["eligible_for_manual_release_review"] is True
    assert verdict["authorizes_release"] is False

@pytest.mark.parametrize("name", REQUIRED)
def test_each_missing_release_gate_blocks_review(name):
    evidence = complete()
    del evidence["gates"][name]
    verdict = assess_p3_release(evidence)
    assert verdict["eligible_for_manual_release_review"] is False
    assert name in verdict["failed_gates"]

def test_mismatched_head_and_forged_success_are_denied():
    evidence = complete()
    evidence["gates"]["exact_head_ci"]["head_sha"] = "b" * 40
    evidence["gates"]["production_boundary"]["status"] = "QUEUED"
    verdict = assess_p3_release(evidence)
    assert {"exact_head_ci", "production_boundary"} <= set(verdict["failed_gates"])

def test_invalid_evidence_shape_fails_closed():
    with pytest.raises(ValueError):
        assess_p3_release({"head_sha": "invalid", "gates": {}})
    with pytest.raises(ValueError):
        assess_p3_release({"head_sha": HEAD, "gates": {}, "release": True})
