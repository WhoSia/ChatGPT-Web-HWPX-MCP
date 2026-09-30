from __future__ import annotations

import base64

import pytest

from p48_components import (
    component_authoring_contract,
    compile_document_components,
    distribution_quickstart_contract,
    plan_component_repairs,
)


PNG_1X1 = base64.b64encode(
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d"
    b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
).decode("ascii")


def _base_spec():
    return {
        "title": "벡터 공간 노트",
        "archetype": "TECHNICAL_NOTE",
        "sections": [
            {
                "heading": "정의와 정리",
                "components": [
                    {"id": "def-v", "type": "definition", "title": "벡터 공간", "text": "공리들을 만족하는 집합이다."},
                    {"id": "thm-1", "type": "theorem", "title": "영벡터의 유일성", "text": "영벡터는 유일하다."},
                    {"id": "eq-1", "type": "equation", "label": "zero", "latex": r"x+0=x"},
                    {"id": "ref-1", "type": "equation_reference", "target": "zero", "prefix": "위 식"},
                    {"id": "pf-1", "type": "proof", "text": "두 영벡터가 있다고 두고 서로 더한다."},
                ],
            }
        ],
    }


def test_contract_is_small_and_honest_about_charts():
    contract = component_authoring_contract()
    assert contract["product"] == "0.34.0-p4.8"
    assert "bar_chart" in contract["chart_support"]["native_structural"]
    assert "line_chart" in contract["chart_support"]["typed_hold"]
    assert contract["semantic_math"]["p47_frontier_inherited"] == "NO_P4.7_PENDING_EQEDIT_CANDIDATE_IS_USED"


def test_semantic_math_compiles_with_stable_labels():
    compiled = compile_document_components(_base_spec())
    assert compiled["ready"] is True
    assert compiled["equation_labels"] == {"zero": "1"}
    blocks = compiled["unified_spec"]["rich_plan"]["sections"][0]["blocks"]
    by_id = {b["id"]: b for b in blocks}
    assert by_id["eq-1"]["caption"] == "(1)"
    assert by_id["eq-1"]["bookmark"] == "p48-eq-zero"
    assert by_id["ref-1"]["text"] == "위 식 (1)"
    assert by_id["thm-1_heading"]["run_format"]["bold"] is True
    assert by_id["pf-1"]["text"].endswith("□")


def test_unsupported_math_fails_closed_without_using_p47_candidates():
    spec = _base_spec()
    spec["sections"][0]["components"].append({
        "id": "eq-bad",
        "type": "equation",
        "label": "blackboard",
        "latex": r"\mathbb{R}",
    })
    compiled = compile_document_components(spec)
    assert compiled["ready"] is False
    blocker = next(x for x in compiled["blockers"] if x["component_id"] == "eq-bad")
    assert blocker["reason"] == "UNSUPPORTED_MATH_STYLE"
    assert "await_p47_world_contact" in blocker["repair_options"]


def test_unsupported_chart_returns_typed_repair_options():
    spec = {
        "archetype": "RESEARCH_REPORT",
        "sections": [{"components": [{"id": "trend", "type": "line_chart", "data": []}]}],
    }
    compiled = compile_document_components(spec)
    assert compiled["ready"] is False
    assert compiled["blockers"][0]["reason"] == "UNSUPPORTED_CHART_PRIMITIVE"
    repair = plan_component_repairs(spec)
    assert repair["repair_count"] == 1
    assert "data_table" in repair["repairs"][0]["safe_options"]


def test_bar_chart_and_kpi_compile_to_visual_plans():
    spec = {
        "title": "지표",
        "archetype": "POLICY_BRIEF",
        "sections": [{
            "components": [
                {
                    "id": "bars",
                    "type": "bar_chart",
                    "title": "부문별 값",
                    "data": [{"label": "A", "value": 10}, {"label": "B", "value": 20}],
                },
                {
                    "id": "kpis",
                    "type": "kpi_strip",
                    "items": [{"label": "표본", "value": "128"}, {"label": "정확도", "value": "94%"}],
                },
            ]
        }],
    }
    compiled = compile_document_components(spec)
    assert compiled["ready"] is True
    assert [x["type"] for x in compiled["visual_plans"]] == ["bar_chart", "kpi_strip"]
    chart = compiled["visual_plans"][0]
    assert chart["rows"][1]["bar_width"] > chart["rows"][0]["bar_width"]
    assert chart["authority"].startswith("P3.26")


def test_data_table_image_and_callout_lower_to_existing_rich_blocks():
    spec = {
        "archetype": "LAB_REPORT",
        "sections": [{
            "components": [
                {"id": "t", "type": "data_table", "headers": ["x", "y"], "rows": [[1, 2], [3, 4]]},
                {"id": "i", "type": "image", "content_base64": PNG_1X1, "image_format": "png"},
                {"id": "c", "type": "callout", "label": "주의", "text": "대조군을 유지한다."},
            ]
        }],
    }
    compiled = compile_document_components(spec)
    blocks = compiled["unified_spec"]["rich_plan"]["sections"][0]["blocks"]
    by_id = {b["id"]: b for b in blocks}
    assert by_id["t"]["type"] == "table"
    assert by_id["t"]["first_row_header"] is True
    assert by_id["i"]["type"] == "picture"
    assert by_id["c"]["text"].startswith("주의:")


def test_duplicate_equation_label_and_unknown_reference_are_refused():
    bad = _base_spec()
    bad["sections"][0]["components"].append({"id": "eq-2", "type": "equation", "label": "zero", "latex": "y=1"})
    with pytest.raises(ValueError, match="duplicate equation label"):
        compile_document_components(bad)

    bad_ref = _base_spec()
    bad_ref["sections"][0]["components"].append({"id": "ref-x", "type": "equation_reference", "target": "missing"})
    with pytest.raises(ValueError, match="unknown equation reference target"):
        compile_document_components(bad_ref)


def test_quickstart_keeps_oauth_and_evidence_boundaries():
    q = distribution_quickstart_contract()
    assert q["minimal_path"][0] == "CONNECT_REMOTE_OAUTH_MCP"
    assert "DO_NOT_REPEAT_MUTATION" in q["recovery"]["delivery_after_commit_failure"]
