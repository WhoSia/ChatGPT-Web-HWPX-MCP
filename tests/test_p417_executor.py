from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from p340_feedback_loop import apply_nested_paragraph_alignment_atomic

from hwpx_mcp.corpus.p335_atlas import _sha as atlas_sha

from p321_document_composer import compose_document_plan

from p28_tables import build_table_map

from p22_formatting import build_formatting_map

from hwpx import HwpxDocument

from p2_document import build_document_map
from p417_executor import compose_post_edit_native_authority, execute_transformation_atomic, transformation_execution_contract
from p417_planner import plan_document_transformation
from p417_semantics import recover_semantic_structure


def make_hwpx(path: Path) -> None:
    body = """<?xml version="1.0" encoding="UTF-8"?>
<section xmlns="http://www.hancom.co.kr/hwpml/2011/section">
  <p id="1"><run><t>사업 계획서</t></run></p>
  <p id="2"><run><t>1. 개요</t></run></p>
  <p id="3"><run><t>기존 본문입니다.</t></run></p>
</section>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", body)
        zf.writestr("mimetype", "application/hwp+zip")


def make_plan(path: Path, title: str = "새 사업 계획서") -> dict:
    graph = recover_semantic_structure(path)
    mapped = build_document_map(path)
    return plan_document_transformation(
        intent={
            "goal": "제목 교체",
            "actions": [{"action": "replace_role_text", "role": "TITLE", "text": title}],
            "preservation": {"required_grade": "TARGETED_PARTS_ONLY"},
        },
        semantic_graph=graph,
        document_map=mapped,
    )


def test_execution_contract_is_product_facing_and_fail_closed():
    contract = transformation_execution_contract()
    assert contract["transaction"] == "COPY_EXECUTE_VERIFY_ATOMIC_REPLACE"
    assert "P3.42_MUTATION_FOOTPRINT" in contract["required_receipts"]
    assert contract["authority"] == "EXECUTION_RECEIPT_AUTHORITY_NOT_NATIVE_VISUAL_TRUTH"


def test_direct_native_execution_commits_with_targeted_footprint(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    plan = make_plan(path)
    receipt = execute_transformation_atomic(
        path,
        plan,
        expected_revision=3,
        current_revision=3,
        validator=lambda candidate: {"sha256": __import__("hashlib").sha256(candidate.read_bytes()).hexdigest(), "bytes": candidate.stat().st_size},
    )
    assert receipt["verdict"] == "STRUCTURALLY_VERIFIED_NATIVE_RENDER_PENDING"
    assert receipt["revision_before"] == 3
    assert receipt["revision_after"] == 4
    assert receipt["preservation_enforcement"]["passed"] is True
    assert receipt["preservation_enforcement"]["actual_grade"] == "TARGETED_PARTS_ONLY"
    assert receipt["render_validation"]["native_visual_authority"] is False
    assert build_document_map(path)["paragraphs"][0]["text"] == "새 사업 계획서"


def test_caller_supplied_render_metadata_cannot_self_authorize_native_pass(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    plan = make_plan(path)
    receipt = execute_transformation_atomic(
        path,
        plan,
        expected_revision=1,
        current_revision=1,
        render_evidence={"source": "HANCOM_NATIVE", "verified": True, "sha256": "a" * 64},
    )
    assert receipt["verdict"] == "STRUCTURALLY_VERIFIED_NATIVE_RENDER_PENDING"
    assert receipt["render_validation"]["native_visual_authority"] is False
    assert receipt["render_validation"]["verdict"] == "TRUSTED_NATIVE_RECEIPT_REQUIRED_FOR_NATIVE_AUTHORITY"


def test_stale_revision_fails_before_mutation(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    before = path.read_bytes()
    plan = make_plan(path)
    with pytest.raises(ValueError, match="Stale revision"):
        execute_transformation_atomic(path, plan, expected_revision=1, current_revision=2)
    assert path.read_bytes() == before


def test_hold_plan_cannot_execute(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    graph = recover_semantic_structure(path)
    mapped = build_document_map(path)
    plan = plan_document_transformation(
        intent={
            "actions": [{"action": "replace_role_text", "role": "TITLE", "text": "금지"}],
            "preservation": {"protected_roles": ["TITLE"]},
        },
        semantic_graph=graph,
        document_map=mapped,
    )
    assert plan["decision"] == "HOLD"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not executable"):
        execute_transformation_atomic(path, plan, expected_revision=1, current_revision=1)
    assert path.read_bytes() == before


def test_post_edit_replan_generates_next_plan_without_second_mutation(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path)
    plan = make_plan(path)
    receipt = execute_transformation_atomic(
        path,
        plan,
        expected_revision=1,
        current_revision=1,
        replan_intent={
            "goal": "후속 본문 갱신",
            "actions": [{"action": "replace_role_text", "role": "BODY", "text": "후속 변경"}],
        },
    )
    assert receipt["next_plan"]["decision"] == "SAFE_TO_PLAN"
    assert build_document_map(path)["paragraphs"][2]["text"] == "기존 본문입니다."



def test_trusted_post_edit_native_authority_requires_exact_binding(tmp_path):
    path = tmp_path / "trusted.hwpx"
    make_hwpx(path)
    plan = make_plan(path)
    receipt = execute_transformation_atomic(
        path,
        plan,
        expected_revision=1,
        current_revision=1,
    )
    trust = {
        "document_id": "doc-1",
        "revision": receipt["revision_after"],
        "document_sha256": receipt["after"]["package_sha256"],
        "authority_class": "PER_DOCUMENT_NATIVE_VERIFIED",
        "trust_receipt_sha256": "b" * 64,
    }
    composed = compose_post_edit_native_authority(receipt, trust)
    assert composed["binding_verified"] is True
    assert composed["native_visual_authority"] is True
    assert composed["verdict"] == "VERIFIED"

    mismatched = compose_post_edit_native_authority(
        receipt,
        {**trust, "document_sha256": "0" * 64},
    )
    assert mismatched["binding_verified"] is False
    assert mismatched["native_visual_authority"] is False
    assert mismatched["verdict"] == "NATIVE_TRUST_RECEIPT_NOT_BOUND_TO_EXECUTION"


def test_native_failure_receipt_never_promotes_execution(tmp_path):
    path = tmp_path / "failed-native.hwpx"
    make_hwpx(path)
    receipt = execute_transformation_atomic(
        path,
        make_plan(path),
        expected_revision=4,
        current_revision=4,
    )
    trust = {
        "document_id": "doc-2",
        "revision": receipt["revision_after"],
        "document_sha256": receipt["after"]["package_sha256"],
        "authority_class": "NATIVE_VERIFICATION_FAILED",
        "trust_receipt_sha256": "c" * 64,
    }
    composed = compose_post_edit_native_authority(receipt, trust)
    assert composed["binding_verified"] is True
    assert composed["native_visual_authority"] is False
    assert composed["verdict"] == "NATIVE_RENDER_FAILED"



def _p417_reference_fixture(path: Path) -> tuple[str, str]:
    doc = HwpxDocument.new()
    doc.add_paragraph("기관 제목")
    doc.add_paragraph("본문 기준 문장")
    doc.save_to_path(path)
    doc.close()
    rows = [
        row
        for row in build_formatting_map(path)["paragraphs"]
        if row.get("direct_text_length")
    ]
    return rows[0]["locator"], rows[1]["locator"]


def _p417_reference_template() -> dict:
    row = {
        "schema": "hwpx-template-candidate/v1",
        "source_corpus_sha256": "1" * 64,
        "synthesis_mode": "EXPLICIT_EXEMPLAR",
        "role_presets": {
            "title": {
                "run_format": {"font": "Arial", "size": 15.0, "color": "112233"},
                "paragraph_format": {"alignment": "CENTER", "spacing_after_pt": 6.0},
            },
            "body": {
                "run_format": {"font": "Arial", "size": 10.5, "color": "112233"},
                "paragraph_format": {"alignment": "LEFT", "line_spacing_percent": 160},
            },
        },
        "support": {"documents": 1},
        "source_ids": ["official-a"],
        "source_receipts": {"official-a": "2" * 64},
        "institutions": ["기관A"],
        "dimension_provenance": {},
        "unresolved_dimensions": [],
        "compatibility_notes": "P4.17 delegate-only fixture",
        "authority": "EVIDENCE_GUIDED_TEMPLATE_CANDIDATE",
    }
    row["template_sha256"] = atlas_sha(row)
    row["template_id"] = "tpl_" + row["template_sha256"][:24]
    return row


def _p417_reference_policy() -> dict:
    return {
        "organization_id": "org-a",
        "policy_id": "brand-2026",
        "hard": {
            "allowed_fonts": ["Arial"],
            "allowed_colors": ["112233"],
            "min_size_pt": 9,
            "max_size_pt": 18,
            "required_roles": ["title", "body"],
            "required_literal_text": ["기관 제목"],
            "allowed_template_institutions": ["기관A"],
            "required_preservation_grade": "TARGETED_PARTS_ONLY",
        },
        "soft": {
            "preferred_fonts": ["Arial"],
            "preferred_colors": ["112233"],
        },
    }


def test_delegate_only_reference_transfer_executes_atomically(tmp_path):
    path = tmp_path / "reference-only.hwpx"
    title, body = _p417_reference_fixture(path)
    before = build_document_map(path)
    graph = recover_semantic_structure(path)
    plan = plan_document_transformation(
        intent={
            "goal": "reference-conditioned styling only",
            "actions": [
                {
                    "action": "reference_style_transfer",
                    "roles": ["TITLE", "BODY"],
                }
            ],
            "preservation": {"required_grade": "TARGETED_PARTS_ONLY"},
        },
        semantic_graph=graph,
        document_map=before,
        reference_graph=graph,
    )
    assert plan["decision"] == "DELEGATE"
    receipt = execute_transformation_atomic(
        path,
        plan,
        expected_revision=1,
        current_revision=1,
        reference_transfer={
            "template": _p417_reference_template(),
            "targets_by_role": {"title": [title], "body": [body]},
            "policy": _p417_reference_policy(),
        },
    )
    after = build_document_map(path)
    assert receipt["reference_transfer_applied"] is True
    assert receipt["repair_applied"] is False
    assert receipt["preservation_enforcement"]["passed"] is True
    assert before["semantic_sha256"] == after["semantic_sha256"]
    assert before["structure_sha256"] == after["structure_sha256"]


def test_delegate_only_repair_executes_with_outer_footprint(tmp_path):
    path = tmp_path / "repair-only.hwpx"
    compose_document_plan(
        path,
        {
            "preset": "polished-report",
            "blocks": [
                {"id": "title", "type": "title", "text": "P4.17 repair"},
                {
                    "id": "table",
                    "type": "table",
                    "rows": 2,
                    "cols": 2,
                    "first_row_header": True,
                    "cells": [
                        ["항목", "설명"],
                        ["A", "장문 표 문단의 정렬을 국소적으로 수정합니다."],
                    ],
                },
            ],
        },
    )
    mapped = build_document_map(path)
    nested = next(
        row["locator"]
        for row in mapped["paragraphs"]
        if "장문 표 문단" in row["text"] and row["body_global_index"] is None
    )
    apply_nested_paragraph_alignment_atomic(path, [nested], alignment="CENTER")
    graph = recover_semantic_structure(path)
    plan = plan_document_transformation(
        intent={
            "goal": "repair visual defect only",
            "actions": [
                {
                    "action": "repair_visual_defects",
                    "roles": ["TABLE_CELL"],
                }
            ],
            "preservation": {"required_grade": "TARGETED_PARTS_ONLY"},
        },
        semantic_graph=graph,
        document_map=build_document_map(path),
    )
    assert plan["decision"] == "DELEGATE"
    repair_plan = {
        "repair_plan_sha256": "9" * 64,
        "actions": [
            {
                "action": "LEFT_ALIGN_LONG_TABLE_TEXT",
                "status": "EXECUTABLE",
                "reason": "TABLE_LONG_TEXT_CENTERED",
                "operation": {
                    "op": "align_nested_table_paragraphs",
                    "targets": [nested],
                    "alignment": "LEFT",
                },
            }
        ],
    }
    receipt = execute_transformation_atomic(
        path,
        plan,
        expected_revision=1,
        current_revision=1,
        repair_plan=repair_plan,
    )
    assert receipt["repair_applied"] is True
    assert receipt["reference_transfer_applied"] is False
    assert receipt["preservation_enforcement"]["passed"] is True
    assert receipt["verdict"].startswith("REPAIRED_AND_STRUCTURALLY_VERIFIED")
    after = next(
        row
        for row in build_formatting_map(path)["paragraphs"]
        if row["locator"] == nested
    )
    assert str(
        (after["paragraph_property"]["alignment"] or {}).get("horizontal")
    ).upper() == "LEFT"


def test_replan_is_bounded_to_next_plan_without_recursive_mutation(tmp_path):
    path = tmp_path / "bounded-replan.hwpx"
    make_hwpx(path)
    first = make_plan(path, "첫 실행 제목")
    receipt = execute_transformation_atomic(
        path,
        first,
        expected_revision=7,
        current_revision=7,
        replan_intent={
            "goal": "plan the next title change only",
            "actions": [
                {
                    "action": "replace_role_text",
                    "role": "TITLE",
                    "text": "다음 계획 제목",
                }
            ],
        },
    )
    assert build_document_map(path)["paragraphs"][0]["text"] == "첫 실행 제목"
    assert receipt["next_plan"]["decision"] == "SAFE_TO_PLAN"
    assert receipt["next_plan"]["operations"][0]["text"] == "다음 계획 제목"
    assert receipt["revision_after"] == 8
