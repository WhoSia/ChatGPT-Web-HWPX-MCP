from __future__ import annotations
import tempfile
from pathlib import Path
import pytest
from hwpx import HwpxDocument
from p2_document import build_document_map
from p22_formatting import build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light
from p335_atlas import _sha as atlas_sha
from p343_design_system import (
    adjudicate_policy_gate, apply_constraint_preserving_template_migration_atomic,
    build_cross_template_generalization_ledger, normalize_organization_policy,
    plan_constraint_preserving_style_transfer,
)

def fixture(path: Path):
    doc=HwpxDocument.new();doc.add_paragraph("기관 제목");doc.add_paragraph("본문 기준 문장");doc.save_to_path(path);doc.close()
    rows=[r for r in build_formatting_map(path)["paragraphs"] if r.get("direct_text_length")]
    return rows[0]["locator"],rows[1]["locator"]

def template():
    row={"schema":"hwpx-template-candidate/v1","source_corpus_sha256":"1"*64,"synthesis_mode":"EXPLICIT_EXEMPLAR",
         "role_presets":{"title":{"run_format":{"font":"Arial","size":15.0,"color":"112233"},"paragraph_format":{"alignment":"CENTER","spacing_after_pt":6.0}},
                         "body":{"run_format":{"font":"Arial","size":10.5,"color":"112233"},"paragraph_format":{"alignment":"LEFT","line_spacing_percent":160}}},
         "support":{"documents":1},"source_ids":["official-a"],"source_receipts":{"official-a":"2"*64},
         "institutions":["기관A"],"dimension_provenance":{},"unresolved_dimensions":[],"compatibility_notes":"fixture",
         "authority":"EVIDENCE_GUIDED_TEMPLATE_CANDIDATE"}
    row["template_sha256"]=atlas_sha(row);row["template_id"]="tpl_"+row["template_sha256"][:24];return row

def policy(**overrides):
    hard={"allowed_fonts":["Arial"],"allowed_colors":["112233"],"min_size_pt":9,"max_size_pt":18,
          "required_roles":["title","body"],"required_literal_text":["기관 제목"],
          "allowed_template_institutions":["기관A"],"required_preservation_grade":"TARGETED_PARTS_ONLY"}
    hard.update(overrides)
    return {"organization_id":"org-a","policy_id":"brand-2026","hard":hard,
            "soft":{"preferred_fonts":["Arial"],"preferred_colors":["112233"]}}

def test_policy_normalization_deterministic():
    assert normalize_organization_policy(policy())["policy_sha256"]==normalize_organization_policy(policy())["policy_sha256"]

def test_plan_and_atomic_migration():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"target.hwpx";title,body=fixture(path);before=build_document_map(path)
        plan=plan_constraint_preserving_style_transfer(path,template(),{"title":[title],"body":[body]},policy(),expected_revision=1)
        assert "Contents/header.xml" in plan["expected_scope"]["changed_parts"]
        receipt=apply_constraint_preserving_template_migration_atomic(
            path,template(),{"title":[title],"body":[body]},policy(),expected_revision=1,current_revision=1,
            validator=validate_hwpx_package_light)
        after=build_document_map(path)
        assert receipt["policy_gate"]=="PASS"
        assert receipt["mutation_footprint"]["preservation"]["actual_grade"] in {"TARGETED_PARTS_ONLY","PACKAGE_IDENTICAL"}
        assert before["semantic_sha256"]==after["semantic_sha256"] and before["structure_sha256"]==after["structure_sha256"]

def test_disallowed_font_and_immutable_target_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"target.hwpx";title,body=fixture(path);bad=template()
        bad["role_presets"]["title"]["run_format"]["font"]="Comic Sans MS"
        clean={k:v for k,v in bad.items() if k not in {"template_id","template_sha256"}}
        bad["template_sha256"]=atlas_sha(clean);bad["template_id"]="tpl_"+bad["template_sha256"][:24]
        with pytest.raises(ValueError,match="ORGANIZATION_POLICY_VIOLATION"):
            plan_constraint_preserving_style_transfer(path,bad,{"title":[title],"body":[body]},policy(),expected_revision=1)
        section=next(r["section"] for r in build_document_map(path)["paragraphs"] if r["locator"]==title)
        with pytest.raises(ValueError,match="IMMUTABLE_PART_TARGETED"):
            plan_constraint_preserving_style_transfer(path,template(),{"title":[title],"body":[body]},policy(immutable_parts=[section]),expected_revision=1)

def test_generalization_gate():
    assert adjudicate_policy_gate(hard_violation_count=0,semantic_preserved=True,structure_preserved=True,preservation_grade="TARGETED_PARTS_ONLY")=="PASS"
    cases=[
      {"case_id":"h1","split":"HOLDOUT","institution":"A","template_sha256":"2"*64,"policy_sha256":"a"*64,"verdict":"PASS","preservation_grade":"TARGETED_PARTS_ONLY","hard_constraint_violations":0},
      {"case_id":"h2","split":"HOLDOUT","institution":"B","template_sha256":"3"*64,"policy_sha256":"b"*64,"verdict":"PASS","preservation_grade":"PACKAGE_IDENTICAL","hard_constraint_violations":0},
    ]
    assert build_cross_template_generalization_ledger(cases)["promotion_gate"]=="PASS"
    cases[1]["verdict"]="WITHHELD"
    assert build_cross_template_generalization_ledger(cases)["promotion_gate"]=="WITHHELD"
