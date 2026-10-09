from p411_visual_oracle import (
    adjudicate_repair_candidate,
    calibration_summary,
    DEFECT_KPI_CONTAINER_COLLAPSE,
    DEFECT_LABEL_VALUE_DETACHMENT,
    DEFECT_VECTOR_ESCAPE,
    build_golden_registry,
    build_page_raster_manifest,
    structural_region_provenance_from_audit,
    evaluate_archetype_identity,
    detect_native_visual_defects,
    evaluate_shadow_release_gate,
    evaluate_visual_slo,
    load_calibration,
    load_native_raster_calibration,
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


def test_p411_page_raster_and_region_provenance():
    manifest=build_page_raster_manifest(
        [{"page":1,"width_px":1200,"height_px":1600,"sha256":"a"*64,"source_pdf_sha256":"b"*64}],
        renderer="pdfium",
        dpi=160,
    )
    assert manifest["status"]=="PASS"
    audit={"components":[{"component_id":"c","semantic_groups":[{"semantic_group_id":"g","objects":[
        {"role":"label","locator":"loc","kind":"rect","width":10,"height":20,"position":{"x":1,"y":2}}
    ]}]}]}
    provenance=structural_region_provenance_from_audit(audit)
    assert provenance["region_count"]==1
    assert provenance["regions"][0]["coordinate_space"]=="HWPX_SERIALIZED_OBJECT"

def test_p411_archetype_aliasing_is_measurable_but_not_beauty_score():
    identity=evaluate_archetype_identity({"A":[1,0,0],"B":[1,0,0],"C":[0,1,0]},minimum_distance=0.1)
    assert identity["status"]=="FAIL"
    assert any(x["code"]=="ARCHETYPE_ALIASING" for x in identity["issues"])


def test_p411_calibration_promotes_equation_alignment_but_preserves_visual_failures():
    summary=calibration_summary()
    assert summary["native_capture_pass"] is True
    assert set(summary["alignment_promotion_eligible"])=={"lpile","pile","rpile"}
    assert set(summary["vector_escape_cases"])=={"p48-research_report","p48-technical_note"}
    assert len(summary["bar_series_absent_cases"])==5
    assert len(summary["kpi_card_absent_cases"])==5

def test_p411_repair_candidate_requires_native_rerender_and_reduces_hard_defects():
    before={"issues":[{"code":"VECTOR_ESCAPE"},{"code":"KPI_CONTAINER_COLLAPSE"}]}
    after={"issues":[{"code":"KPI_CONTAINER_COLLAPSE"}]}
    held=adjudicate_repair_candidate(
        before=before, after=after, semantic_equivalence_pass=True,
        structural_proof_pass=True, native_rerender_pass=False
    )
    assert held["status"]=="HOLD"
    promoted=adjudicate_repair_candidate(
        before=before, after=after, semantic_equivalence_pass=True,
        structural_proof_pass=True, native_rerender_pass=True
    )
    assert promoted["status"]=="PROMOTION_ELIGIBLE"
    assert promoted["hard_defect_reduction"]==1


def test_p411_native_raster_calibration_is_hash_bound():
    raster=load_native_raster_calibration()
    assert raster["status"]=="PASS"
    assert raster["case_count"]==8
    assert raster["renderer"]=="pdfium"
    assert raster["dpi"]==160
