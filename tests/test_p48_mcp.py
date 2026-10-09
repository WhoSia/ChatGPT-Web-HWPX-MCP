from __future__ import annotations

import hashlib
import json
import tempfile

import pytest
from pathlib import Path

from hwpx.tools.package_validator import validate_editor_open_safety

from p321_document_composer import compose_document_plan
from p325_drawing_layer import build_drawing_layer_map
from p326_drawing_style import build_drawing_style_map
from p47_native_authoring import compile_unified_authoring_plan
from p48_components import compile_document_components
from hwpx_mcp.interfaces.p48_mcp import _execute_visual_plans, register_p48_tools
from p49_visual_conformance import audit_materialized_visuals
from p412_native_repair import audit_repaired_visuals


def _visual_spec():
    return {
        "title": "실험 지표",
        "archetype": "LAB_REPORT",
        "sections": [{
            "heading": "결과",
            "components": [
                {
                    "id": "bars",
                    "type": "bar_chart",
                    "title": "조건별 반응",
                    "data": [
                        {"label": "대조군", "value": 2},
                        {"label": "처리군", "value": 5},
                    ],
                },
                {
                    "id": "kpi",
                    "type": "kpi_strip",
                    "items": [
                        {"label": "표본", "value": "64"},
                        {"label": "평균", "value": "3.5"},
                    ],
                },
            ],
        }],
    }


def test_visual_plans_materialize_p412_paragraph_visuals_on_private_candidate():
    components = compile_document_components(_visual_spec())
    assert components["ready"] is True
    unified = compile_unified_authoring_plan(components["unified_spec"])

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "visuals.hwpx"
        composition = compose_document_plan(path, unified["rich"]["plan"])
        receipts = _execute_visual_plans(path, components["visual_plans"], composition["bindings"])

        assert [x["type"] for x in receipts] == ["bar_chart", "kpi_strip"]
        assert all(x["primitive_family"] == "PARAGRAPH_TEXT_VISUALIZATION" for x in receipts)
        mapped = build_drawing_layer_map(path)
        assert mapped["family_counts"].get("polygon", 0) == 0
        assert mapped["family_counts"].get("rect", 0) == 0
        repaired = audit_repaired_visuals(path, receipts)
        assert repaired["status"] == "PASS", repaired["issues"]
        safety = validate_editor_open_safety(path.read_bytes())
        assert safety.ok, safety.issues


def test_bar_chart_receipts_preserve_semantic_rows_under_p412_substitution():
    components = compile_document_components(_visual_spec())
    unified = compile_unified_authoring_plan(components["unified_spec"])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "chart.hwpx"
        composition = compose_document_plan(path, unified["rich"]["plan"])
        receipt = _execute_visual_plans(path, [components["visual_plans"][0]], composition["bindings"])[0]
        assert [r["label"] for r in receipt["semantic_rows"]] == ["대조군", "처리군"]
        assert receipt["primitive_family"] == "PARAGRAPH_TEXT_VISUALIZATION"
        assert receipt["substituted_from"] == "DRAWING_RECTANGLE_TEXTBOX_OVERLAY"
        assert "대조군" in receipt["paragraph_text"] and "처리군" in receipt["paragraph_text"]


class _MCP:
    def __init__(self):
        self.tools = {}

    def tool(self, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class _Core:
    def __init__(self):
        self.mcp = _MCP()

    def _caller_subject(self):
        return "subject"


def test_p48_registers_five_tool_surface():
    core = _Core()
    register_p48_tools(core, lambda *a, **k: None, lambda *a, **k: None)
    expected = {
        "get_component_authoring_contract",
        "compile_document_components",
        "plan_component_repairs",
        "get_p48_distribution_quickstart",
        "create_component_document_and_deliver",
    }
    assert expected == set(core.mcp.tools)


def test_compile_tool_exposes_typed_blockers_before_mutation():
    core = _Core()
    register_p48_tools(core, lambda *a, **k: None, lambda *a, **k: None)
    result = core.mcp.tools["compile_document_components"]({
        "archetype": "TECHNICAL_NOTE",
        "sections": [{"components": [{"id": "bad", "type": "line_chart", "data": []}]}],
    })
    assert result["ready"] is False
    assert result["blockers"][0]["reason"] == "UNSUPPORTED_CHART_PRIMITIVE"


def test_p49_runtime_certificate_refuses_incomplete_visual_group_before_mutation():
    components = compile_document_components(_visual_spec())
    bad = components["visual_plans"][0]
    bad["rows"][1]["label"] = ""

    with pytest.raises(ValueError, match="P4.9 visual geometry certificate refused lowering"):
        _execute_visual_plans(Path("unused.hwpx"), [bad], {})


def test_compile_tool_surfaces_p49_visual_extent_blocker_before_mutation():
    core = _Core()
    register_p48_tools(core, lambda *a, **k: None, lambda *a, **k: None)
    data = [{"label": f"R{i}", "value": i + 1} for i in range(12)]
    result = core.mcp.tools["compile_document_components"]({
        "archetype": "LAB_REPORT",
        "sections": [{"components": [{
            "id": "crowded",
            "type": "bar_chart",
            "height": 6000,
            "data": data,
        }]}],
    })

    assert result["ready"] is False
    assert result["p49_visual_certificate"]["status"] == "FAIL"
    assert any(
        blocker["reason"] == "P49_VISUAL_CHILD_OUTSIDE_CONTAINER"
        for blocker in result["blockers"]
    )


def test_repair_tool_surfaces_non_mutating_p49_geometry_options():
    core = _Core()
    register_p48_tools(core, lambda *a, **k: None, lambda *a, **k: None)
    result = core.mcp.tools["plan_component_repairs"]({
        "archetype": "POLICY_BRIEF",
        "sections": [{"components": [{
            "id": "narrow-kpi",
            "type": "kpi_strip",
            "width": 5000,
            "items": [
                {"label": "A", "value": "1"},
                {"label": "B", "value": "2"},
            ],
        }]}],
    })

    assert result["ready"] is False
    p49 = [r for r in result["repairs"] if r["problem"].startswith("P49_")]
    assert p49
    assert all(r["automatic_mutation"] is False for r in p49)
    expected_hash = hashlib.sha256(
        json.dumps(
            result["repairs"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert result["repair_plan_sha256"] == expected_hash
