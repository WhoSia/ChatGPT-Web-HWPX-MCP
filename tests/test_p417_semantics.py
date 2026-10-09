from __future__ import annotations

import zipfile
from pathlib import Path

from p417_semantics import (
    align_semantic_graphs,
    classify_native_components,
    infer_corpus_schema,
    recover_semantic_structure,
    semantic_structure_contract,
)


def make_semantic_hwpx(path: Path, *, variant: str = "a") -> None:
    title = "연구개발 신규과제 공고" if variant == "a" else "사업 제안요청서"
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<section xmlns="http://www.hancom.co.kr/hwpml/2011/section">
  <p><run><t>{title}</t></run></p>
  <p><run><t>1. 사업 개요</t></run></p>
  <p><run><t>본 사업의 목적과 범위를 설명한다.</t></run></p>
  <tbl>
    <tr><tc><p><run><t>항목</t></run></p></tc><tc><p><run><t>내용</t></run></p></tc></tr>
    <tr><tc><p><run><t>기간</t></run></p></tc><tc><p><run><t>12개월</t></run></p></tc></tr>
  </tbl>
  <p><run><t>표 1. 사업 일정</t></run></p>
  <p><run><t>2. 세부 내용</t></run></p>
  <p><run><t>세부 수행 내용을 기술한다.</t></run></p>
  <equation><script>x+y</script></equation>
  <p><run><t>3. 제출 방법</t></run></p>
  <p><run><t>온라인으로 제출한다.</t></run></p>
</section>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", body)
        zf.writestr("mimetype", "application/hwp+zip")


def test_semantic_structure_recovers_roles_hierarchy_and_components(tmp_path):
    path = tmp_path / "a.hwpx"
    make_semantic_hwpx(path)
    graph = recover_semantic_structure(path)
    assert graph["block_count"] >= 10
    assert graph["role_counts"]["HEADING"] >= 3
    assert graph["role_counts"]["CAPTION"] == 1
    assert graph["component_counts"]["TABLE"] == 1
    assert graph["component_counts"]["EQUATION"] == 1
    assert graph["native_visual_authority"] is False
    headings = [b for b in graph["blocks"] if b["role"] == "HEADING"]
    assert any(b["heading_level"] == 2 for b in headings)


def test_table_first_row_is_classified_as_header(tmp_path):
    path = tmp_path / "a.hwpx"
    make_semantic_hwpx(path)
    graph = recover_semantic_structure(path)
    roles = [b["role"] for b in graph["blocks"]]
    assert "TABLE_HEADER" in roles
    assert "TABLE_CELL" in roles


def test_repeated_layout_grammar_detects_heading_body_pattern(tmp_path):
    path = tmp_path / "a.hwpx"
    make_semantic_hwpx(path)
    graph = recover_semantic_structure(path)
    grammar = graph["repeated_layout_grammar"]
    assert grammar["pattern_count"] >= 1
    assert any(
        p["signature"] == ["PARAGRAPH:HEADING", "PARAGRAPH:BODY"]
        for p in grammar["patterns"]
    )


def test_native_component_classification_is_structural(tmp_path):
    path = tmp_path / "a.hwpx"
    make_semantic_hwpx(path)
    graph = recover_semantic_structure(path)
    classified = classify_native_components(graph)
    assert classified["component_count"] == graph["block_count"]
    assert classified["native_kinds"]["TABLE"] == 1
    assert classified["native_kinds"]["EQUATION"] == 1


def test_cross_document_alignment_is_role_component_based(tmp_path):
    a = tmp_path / "a.hwpx"
    b = tmp_path / "b.hwpx"
    make_semantic_hwpx(a, variant="a")
    make_semantic_hwpx(b, variant="b")
    ga = recover_semantic_structure(a)
    gb = recover_semantic_structure(b)
    alignment = align_semantic_graphs(ga, gb)
    assert alignment["structural_similarity"] >= 0.8
    assert alignment["native_visual_equivalence_claimed"] is False


def test_corpus_schema_requires_support_threshold(tmp_path):
    a = tmp_path / "a.hwpx"
    b = tmp_path / "b.hwpx"
    make_semantic_hwpx(a, variant="a")
    make_semantic_hwpx(b, variant="b")
    schema = infer_corpus_schema(
        [recover_semantic_structure(a), recover_semantic_structure(b)],
        support_threshold=1.0,
    )
    roles = {row["value"] for row in schema["required_roles"]}
    assert "HEADING" in roles
    assert "BODY" in roles
    assert schema["generalization_status"] == "MULTI_INSTITUTION_REQUIRED_FOR_CROSS_INSTITUTION_AUTHORITY"


def test_semantic_contract_has_bounded_authority():
    contract = semantic_structure_contract()
    assert contract["phase"] == "P4.17"
    assert contract["product"] == "0.42.0-p4.17"
    assert contract["authority_ceiling"] == "STRUCTURAL_SEMANTIC_HEURISTICS_NOT_NATIVE_VISUAL_TRUTH"
