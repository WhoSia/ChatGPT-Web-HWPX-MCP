from __future__ import annotations

import zipfile
from pathlib import Path

from p2_document import build_document_map
from p417_planner import (
    bind_semantic_graph_to_document_map,
    plan_document_transformation,
    transformation_planning_contract,
    validate_transformation_plan,
)
from p417_semantics import recover_semantic_structure


def make_hwpx(path: Path) -> None:
    body = """<?xml version="1.0" encoding="UTF-8"?>
<section xmlns="http://www.hancom.co.kr/hwpml/2011/section">
  <p id="1"><run><t>사업 계획서</t></run></p>
  <p id="2"><run><t>1. 개요</t></run></p>
  <p id="3"><run><t>기존 본문입니다.</t></run></p>
  <p id="4"><run><t>2. 일정</t></run></p>
  <p id="5"><run><t>일정 본문입니다.</t></run></p>
</section>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", body)
        zf.writestr("mimetype", "application/hwp+zip")


def graph_and_map(path: Path):
    return recover_semantic_structure(path), build_document_map(path)


def test_binding_resolves_semantic_paragraphs_to_native_locators(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    binding = bind_semantic_graph_to_document_map(graph, mapped)
    assert binding["binding_status"] == "PASS"
    assert binding["binding_count"] == mapped["paragraph_count"]
    assert all(row["text_sha256_match"] for row in binding["bindings"])


def test_replace_role_text_compiles_to_native_text_operation(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    plan = plan_document_transformation(
        intent={
            "goal": "제목 교체",
            "actions": [{"action": "replace_role_text", "role": "TITLE", "text": "새 사업 계획서"}],
            "preservation": {"required_grade": "TARGETED_PARTS_ONLY"},
        },
        semantic_graph=graph,
        document_map=mapped,
    )
    assert plan["decision"] == "SAFE_TO_PLAN"
    assert plan["operations"][0]["op"] == "replace_paragraph_text"
    assert plan["fidelity_envelope"]["overall_authority_ceiling"] == "STRUCTURAL_AUTHORITY_ONLY"
    assert plan["execution_authority"] == "PLAN_ONLY_NO_MUTATION_PERFORMED"


def test_protected_role_blocks_mutation(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    plan = plan_document_transformation(
        intent={
            "actions": [{"action": "replace_role_text", "role": "TITLE", "text": "금지"}],
            "preservation": {"protected_roles": ["TITLE"]},
        },
        semantic_graph=graph,
        document_map=mapped,
    )
    assert plan["decision"] == "HOLD"
    assert plan["operations"] == []
    assert plan["blocked"][0]["code"] == "PROTECTED_TARGET"


def test_reference_style_transfer_routes_to_p343(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    plan = plan_document_transformation(
        intent={
            "actions": [{"action": "reference_style_transfer", "roles": ["TITLE", "HEADING"]}],
        },
        semantic_graph=graph,
        document_map=mapped,
        reference_graph=graph,
    )
    assert plan["decision"] == "DELEGATE"
    assert plan["delegates"][0]["delegate"] == "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER"
    assert plan["reference_pattern"]["present"] is True


def test_repair_route_requires_mutation_footprint(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    plan = plan_document_transformation(
        intent={"actions": [{"action": "repair_visual_defects", "roles": ["BODY"]}]},
        semantic_graph=graph,
        document_map=mapped,
    )
    assert plan["decision"] == "DELEGATE"
    assert plan["delegates"][0]["delegate"] == "P3.40_P3.42_REPAIR_WITH_MUTATION_FOOTPRINT"
    assert plan["preservation"]["mutation_footprint_required"] is True


def test_unknown_action_abstains(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    plan = plan_document_transformation(
        intent={"actions": [{"action": "magic_rewrite_everything"}]},
        semantic_graph=graph,
        document_map=mapped,
    )
    assert plan["decision"] == "ABSTAIN"
    receipt = validate_transformation_plan(plan)
    assert receipt["unknown_action_count"] == 1


def test_contract_routes_safety_to_existing_native_stack():
    contract = transformation_planning_contract()
    assert contract["style_transfer_routing"] == "P3.43_CONSTRAINT_PRESERVING_TEMPLATE_TRANSFER"
    assert contract["repair_routing"] == "P3.40_PLAN_PLUS_P3.42_MUTATION_FOOTPRINT"
    assert contract["authority_ceiling"] == "PLAN_AND_ROUTING_AUTHORITY_ONLY_UNTIL_EXECUTION_RECEIPTS"


def test_style_role_compiles_user_aliases_to_native_keys(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph, mapped = graph_and_map(path)
    plan = plan_document_transformation(
        intent={
            "actions": [{
                "action": "style_role",
                "role": "TITLE",
                "format": {
                    "bold": True,
                    "align": "CENTER",
                    "space_after": 6,
                },
            }],
        },
        semantic_graph=graph,
        document_map=mapped,
    )
    assert plan["decision"] == "SAFE_TO_PLAN"
    ops = plan["operations"]
    assert any(op["op"] == "set_run_format" and op["format"].get("bold") is True for op in ops)
    assert any(
        op["op"] == "set_paragraph_format"
        and op["format"].get("alignment") == "CENTER"
        and op["format"].get("spacing_after_pt") == 6
        for op in ops
    )
