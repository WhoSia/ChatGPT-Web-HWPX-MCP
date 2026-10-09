from __future__ import annotations

from hwpx_mcp.rendering.p48_components import compile_document_components
from p49_visual_conformance import (
    ISSUE_KPI_CHILD_OUTSIDE_CONTAINER,
    ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER,
    ISSUE_VISUAL_GROUP_INCOMPLETE,
    certify_bar_chart,
    certify_kpi_strip,
    certify_visual_plans,
)


def _spec() -> dict:
    return {
        "archetype": "LAB_REPORT",
        "sections": [{
            "components": [
                {
                    "id": "bars",
                    "type": "bar_chart",
                    "data": [
                        {"label": "A", "value": 10},
                        {"label": "B", "value": 20},
                    ],
                },
                {
                    "id": "kpi",
                    "type": "kpi_strip",
                    "items": [
                        {"label": "표본", "value": "2"},
                        {"label": "합계", "value": "30"},
                    ],
                },
            ]
        }],
    }


def test_p48_visual_plans_receive_p49_geometry_certificates():
    compiled = compile_document_components(_spec())
    result = certify_visual_plans(compiled["visual_plans"])

    assert result["status"] == "PASS"
    assert result["certificate_count"] == 2
    assert [cert["type"] for cert in result["certificates"]] == ["bar_chart", "kpi_strip"]
    bar = result["certificates"][0]
    assert bar["expected_group_count"] == 2
    assert [group["children"] for group in bar["semantic_groups"]] == [
        ["shape", "label", "value"],
        ["shape", "label", "value"],
    ]


def test_bar_certificate_fails_closed_when_semantic_group_is_incomplete():
    plan = compile_document_components(_spec())["visual_plans"][0]
    plan["rows"][1]["label"] = ""
    cert = certify_bar_chart(plan)

    assert cert["status"] == "FAIL"
    assert any(issue["code"] == ISSUE_VISUAL_GROUP_INCOMPLETE for issue in cert["issues"])


def test_kpi_certificate_detects_child_extent_escape():
    plan = compile_document_components(_spec())["visual_plans"][1]
    plan["width"] = 5000
    cert = certify_kpi_strip(plan)

    assert cert["status"] == "FAIL"
    assert any(issue["code"] == ISSUE_KPI_CHILD_OUTSIDE_CONTAINER for issue in cert["issues"])


def test_bar_certificate_detects_horizontal_child_escape():
    plan = compile_document_components(_spec())["visual_plans"][0]
    plan["rows"][1]["value_x"] = plan["width"] - 100
    cert = certify_bar_chart(plan)

    assert cert["status"] == "FAIL"
    assert any(issue["code"] == ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER for issue in cert["issues"])


def test_bar_certificate_detects_vertical_escape_for_overcompressed_height():
    spec = _spec()
    spec["sections"][0]["components"][0]["height"] = 6000
    for i in range(2, 12):
        spec["sections"][0]["components"][0]["data"].append({"label": f"R{i}", "value": i + 1})
    plan = compile_document_components(spec)["visual_plans"][0]
    cert = certify_bar_chart(plan)

    assert cert["status"] == "FAIL"
    assert any(issue["code"] == ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER for issue in cert["issues"])


def test_kpi_certificate_detects_vertical_child_escape():
    plan = compile_document_components(_spec())["visual_plans"][1]
    plan["height"] = 1000
    cert = certify_kpi_strip(plan)

    assert cert["status"] == "FAIL"
    assert any(issue["code"] == ISSUE_VISUAL_CHILD_OUTSIDE_CONTAINER for issue in cert["issues"])
