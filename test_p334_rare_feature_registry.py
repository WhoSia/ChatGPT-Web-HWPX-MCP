from p334_rare_feature_registry import (
    EVIDENCE_KEYS,
    evaluate_rare_feature,
    plan_rare_feature_promotion,
    rare_feature_registry,
    ux_regression_contract,
)


def _all_true():
    return {key: True for key in EVIDENCE_KEYS}


def test_registry_is_deterministic_and_keeps_known_gates_closed():
    first = rare_feature_registry()
    second = rare_feature_registry()
    assert first["registry_sha256"] == second["registry_sha256"]
    assert first["features"]["column_insertion"]["state"] == "NATIVE_EVIDENCE_REQUIRED"
    assert first["features"]["smart_connectline"]["state"] == "BLOCKED_SEMANTIC_AMBIGUITY"
    assert first["authority"] == "EVIDENCE_GATED_REGISTRY_ONLY"


def test_incomplete_evidence_does_not_promote():
    result = evaluate_rare_feature("column_insertion", {"semantic_contract": True})
    assert result["promotion_ready"] is False
    assert "native_open_resave_or_render" in result["missing_evidence"]
    assert result["verdict"] == "EVIDENCE_INCOMPLETE"


def test_complete_nonblocked_lane_can_only_generate_a_sealed_plan():
    evidence = _all_true()
    result = evaluate_rare_feature("polygon_preserving_resize", evidence)
    assert result["promotion_ready"] is True
    plan = plan_rare_feature_promotion("polygon_preserving_resize", evidence)
    assert plan["authority_change"] == "NOT_APPLIED_BY_THIS_PLAN"
    assert len(plan["promotion_plan_sha256"]) == 64


def test_connectline_stays_blocked_even_if_boolean_evidence_is_claimed():
    result = evaluate_rare_feature("smart_connectline", _all_true())
    assert result["promotion_ready"] is False
    assert result["verdict"] == "BLOCKED_SEMANTIC_AMBIGUITY"


def test_ux_guard_repeats_each_production_phase():
    guard = ux_regression_contract()
    assert "every production phase before closure" in guard["cadence"]
    assert any("deliver_document" in item for item in guard["checks"])
