from p411_visual_oracle import (
    DEFECT_KPI_CONTAINER_COLLAPSE,
    DEFECT_LABEL_VALUE_DETACHMENT,
    DEFECT_VECTOR_ESCAPE,
    build_golden_registry,
    detect_native_visual_defects,
    evaluate_shadow_release_gate,
    evaluate_visual_slo,
    load_calibration,
    native_render_oracle_contract,
    plan_bounded_repairs,
)

def test_p411_contract_and_calibration_registry():
    contract=native_render_oracle_contract()
    assert contract["product"]=="0.36.0-p4.11"
    registry=build_golden_registry(load_calibration())
    assert registry["case_count"]==8
    by_id={x["case_id"]:x for x in registry["archetypes"]}
    assert DEFECT_VECTOR_ESCAPE in by_id["p48-research_report"]["observed_defects"]
    assert DEFECT_KPI_CONTAINER_COLLAPSE in by_id["p48-lab_report"]["observed_defects"]

def test_p411_detector_slo_repair_and_shadow_gate():
    obs={
        "page_width":1000,"page_height":1400,
        "used_height":1100,"semantic_content_height":700,
        "vectors":[{"component_id":"c1","length":400,"intended":False}],
        "regions":[
            {"component_id":"bar","role":"bar_label","x":100,"y":100,"width":100,"height":40,
             "expected_text":"A","observed_text":"A","attached_to_shape":False},
            {"component_id":"kpi","role":"kpi_card","x":100,"y":300,"width":200,"height":100,
             "container_visible":False},
        ],
    }
    defects=detect_native_visual_defects(obs)
    codes={x["code"] for x in defects["issues"]}
    assert DEFECT_VECTOR_ESCAPE in codes
    assert DEFECT_LABEL_VALUE_DETACHMENT in codes
    assert DEFECT_KPI_CONTAINER_COLLAPSE in codes
    slo=evaluate_visual_slo(defects)
    assert slo["status"]=="FAIL"
    repair=plan_bounded_repairs(defects)
    assert repair["action_count"]>=3
    gate=evaluate_shadow_release_gate(
        static_test_pass=True, structural_fidelity_pass=True, exact_head_docker_pass=True,
        native_capture_pass=True, visual_slo=slo, blocking=False
    )
    assert gate["mode"]=="SHADOW_NONBLOCKING"
    assert gate["promotion_eligible"] is False
    assert gate["release_blocked"] is False
