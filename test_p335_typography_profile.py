from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p22_formatting import apply_formatting_atomic
from p23_richtext import apply_rich_formatting_atomic
from p335_typography import build_typography_profile, compare_typography_profiles, typography_contract
from p334r2_package_validation import validate_hwpx_package_light


def _loc(path: Path, text: str) -> str:
    return next(
        p["locator"] for p in build_document_map(path)["paragraphs"]
        if p["text"] == text
    )


def _make(path: Path, text: str) -> str:
    doc=HwpxDocument.new()
    doc.add_paragraph(text)
    doc.save_to_path(str(path))
    doc.close()
    return _loc(path,text)


def test_typography_contract_exposes_native_spacing_and_script_fonts():
    contract=typography_contract()
    assert contract["character_spacing_percent"]["min"]==-50
    assert contract["character_spacing_percent"]["max"]==50
    assert contract["font_model"]["script_specific_face_key"]=="font_by_script"
    assert contract["font_model"]["scripts"]==[
        "hangul","latin","hanja","japanese","other","symbol","user"
    ]


def test_typography_profile_counts_dominant_script_fonts(tmp_path: Path):
    path=tmp_path/"profile.hwpx"
    loc=_make(path,"한글 ABC 漢字")
    apply_formatting_atomic(
        path,
        [{
            "op":"set_run_format",
            "target":loc,
            "format":{
                "font":"함초롬바탕",
                "font_by_script":{"latin":"Times New Roman"},
                "size":13.5,
                "letter_spacing":20,
            },
        }],
        expected_revision=1,current_revision=1,
        validator=validate_hwpx_package_light,
    )
    profile=build_typography_profile(path)
    assert profile["text_characters"]==len("한글 ABC 漢字")
    assert profile["font_faces_by_script"]["hangul"][0]["value"]=="함초롬바탕"
    assert profile["font_faces_by_script"]["latin"][0]["value"]=="Times New Roman"
    assert profile["font_sizes_pt"][0]["value"]=="13.5"
    assert profile["letter_spacing_by_script"]["latin"][0]["value"]=="20"


def test_typography_profile_detects_mixed_run_paragraph(tmp_path: Path):
    path=tmp_path/"mixed.hwpx"
    loc=_make(path,"한글 ABC 漢字")
    apply_rich_formatting_atomic(
        path,
        [{
            "op":"set_range_format",
            "target":loc,
            "start":3,
            "end":6,
            "format":{"font_by_script":{"latin":"Times New Roman"},"size":11},
        }],
        expected_revision=1,current_revision=1,
        validator=validate_hwpx_package_light,
    )
    profile=build_typography_profile(path)
    assert profile["paragraphs_with_multiple_text_runs"]==1
    assert profile["text_runs"]>=3


def test_typography_profile_comparison_reports_dominant_difference(tmp_path: Path):
    left=tmp_path/"left.hwpx"; right=tmp_path/"right.hwpx"
    l=_make(left,"ABC"); r=_make(right,"ABC")
    apply_formatting_atomic(
        left,[{"op":"set_run_format","target":l,"format":{"font":"Arial","size":10}}],
        expected_revision=1,current_revision=1,validator=validate_hwpx_package_light,
    )
    apply_formatting_atomic(
        right,[{"op":"set_run_format","target":r,"format":{"font":"함초롬바탕","size":12}}],
        expected_revision=1,current_revision=1,validator=validate_hwpx_package_light,
    )
    diff=compare_typography_profiles(build_typography_profile(left),build_typography_profile(right))
    dims={row["dimension"] for row in diff["dominant_differences"]}
    assert "font_size_pt" in dims
    assert "font_face.latin" in dims
