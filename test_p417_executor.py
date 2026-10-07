from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

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
