import tempfile
from pathlib import Path

from p321_document_composer import compose_document_plan
from p47_native_authoring import compile_unified_authoring_plan
from p48_components import compile_document_components
from p412_native_repair import (
    SAFE_NATIVE_FAMILY,
    audit_repaired_visuals,
    causal_localization,
    compile_repaired_visual_payload,
    defect_eradication_contract,
    evaluate_blocking_promotion,
    execute_repaired_visual_plans,
    requalify_golden_corpus,
)

def _spec():
    return {
        "title":"P4.12 visual repair",
        "archetype":"LAB_REPORT",
        "sections":[{"heading":"결과","components":[
            {"id":"bars","type":"bar_chart","title":"비교","data":[
                {"label":"A","value":10},{"label":"B","value":20}
            ]},
            {"id":"kpi","type":"kpi_strip","items":[
                {"label":"표본","value":"2"},{"label":"합계","value":"30"}
            ]},
        ]}],
    }

def test_contract_localizes_unsafe_drawing_family():
    c=defect_eradication_contract()
    assert c["product"]=="0.37.0-p4.12"
    loc=causal_localization("bar_chart")
    assert loc["lowering_family"]=="DRAWING_RECTANGLE_TEXTBOX_OVERLAY"
    assert loc["substitution_family"]==SAFE_NATIVE_FAMILY

def test_repaired_payload_preserves_bar_and_kpi_semantics():
    compiled=compile_document_components(_spec())
    bar=compile_repaired_visual_payload(compiled["visual_plans"][0])
    kpi=compile_repaired_visual_payload(compiled["visual_plans"][1])
    assert "A" in bar["paragraph_text"] and "10" in bar["paragraph_text"]
    assert "B" in bar["paragraph_text"] and "20" in bar["paragraph_text"]
    assert bar["semantic_rows"][1]["bar_blocks"] > bar["semantic_rows"][0]["bar_blocks"]
    assert "표본" in kpi["paragraph_text"] and "30" in kpi["paragraph_text"]

def test_repaired_visuals_materialize_without_drawing_overlay_dependency():
    compiled=compile_document_components(_spec())
    unified=compile_unified_authoring_plan(compiled["unified_spec"])
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"p412.hwpx"
        composition=compose_document_plan(path,unified["rich"]["plan"])
        receipts=execute_repaired_visual_plans(path,compiled["visual_plans"],composition["bindings"])
        assert all(r["primitive_family"]==SAFE_NATIVE_FAMILY for r in receipts)
        audit=audit_repaired_visuals(path,receipts)
        assert audit["status"]=="PASS",audit["issues"]

def test_blocking_promotion_requires_requalified_golden_controls():
    obs=[{
        "case_id":"x","native_capture_pass":True,"bar_visible":True,"kpi_visible":True,
        "vector_escape":False,"defects":{"issues":[]},"novel_unadjudicated":0,
    }]
    golden=requalify_golden_corpus(obs)
    assert golden["status"]=="PASS"
    evidence={
        "exact_head":"a"*40,
        "exact_head_ci_pass":True,
        "full_lifecycle_pass":True,
        "exact_head_docker_pass":True,
        "production_boundary_pass":True,
        "native_capture_pass":True,
        "visual_slo_status":"PASS",
        "novel_unadjudicated":0,
        "golden_requalification":golden,
    }
    promoted=evaluate_blocking_promotion(evidence)
    assert promoted["promotion_eligible"] is True
    evidence["visual_slo_status"]="FAIL"
    held=evaluate_blocking_promotion(evidence)
    assert held["promotion_eligible"] is False
