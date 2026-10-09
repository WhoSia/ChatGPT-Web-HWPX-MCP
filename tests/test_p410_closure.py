from p410_closure import PRODUCT, adjudicate_closure, closure_contract


def test_p410_contract_preserves_p48_failure_and_p47_mapping_holds():
    contract = closure_contract()
    assert contract["product"] == "0.35.0-p4.10"
    assert contract["inherits"]["p48_human_visual_failure"] == "RETAINED_AS_GENESIS_REGRESSION_EVIDENCE"
    assert "bold_to_mathbf_or_boldsymbol" in contract["p47_high_level_mapping_hold"]


def test_p410_cannot_close_without_native_human_evidence():
    result = adjudicate_closure(None)
    assert result["status"] == "HUMAN_RENDER_EVIDENCE_PENDING"
    assert result["deployable"] is False
    assert result["geometry_authority_promoted"] is False


def test_p410_closes_only_with_release_and_native_visual_evidence():
    evidence = {
        "exact_head": "a" * 40,
        "exact_head_ci_pass": True,
        "exact_head_docker_pass": True,
        "production_boundary_pass": True,
        "native_hancom": {
            "capture_pass": True,
            "fail_count": 0,
            "pdf_count": 8,
            "manifest_sha256": "b" * 64,
        },
        "human_visual": {
            "status": "PASS",
            "lab_report_vector_escape_absent": True,
            "bar_label_value_preserved": True,
            "kpi_card_preserved": True,
        },
    }
    result = adjudicate_closure(evidence)
    assert result["status"] == "CLOSED"
    assert result["deployable"] is True
    assert result["geometry_authority_promoted"] is True
    assert result["held"] == []
