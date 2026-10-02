from p411_release_service import evaluate_release_candidate, release_promotion_contract

def test_p411_release_contract_is_shadow_first():
    c=release_promotion_contract()
    assert c["product"]=="0.36.0-p4.11"
    assert c["modes"][0]=="SHADOW_NONBLOCKING"

def test_p411_shadow_can_deploy_oracle_without_laundering_visual_failures():
    evidence={
        "exact_head":"a"*40,
        "static_test_pass":True,
        "full_lifecycle_pass":True,
        "exact_head_docker_pass":True,
        "production_boundary_pass":True,
        "native_capture_pass":True,
        "visual_slo_status":"FAIL",
        "novel_unadjudicated":0,
    }
    shadow=evaluate_release_candidate(evidence,mode="SHADOW_NONBLOCKING")
    assert shadow["deployable"] is True
    assert shadow["visual_authority_promoted"] is False
    assert shadow["verdict"]=="SERVICE_DEPLOYABLE_VISUAL_AUTHORITY_HOLD"

    blocking=evaluate_release_candidate(evidence,mode="BLOCKING")
    assert blocking["deployable"] is False
    assert blocking["verdict"]=="HOLD"
