from __future__ import annotations

from pathlib import Path

import pytest
from hwpx import HwpxDocument

from p2_document import build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light


def _paragraph(path: Path, text: str) -> str:
    doc=HwpxDocument.new()
    doc.add_paragraph(text)
    doc.save_to_path(str(path))
    doc.close()
    return next(
        p["locator"] for p in build_document_map(path)["paragraphs"]
        if p["text"]==text
    )


def _text_run(path: Path, text: str) -> dict:
    mapped=build_formatting_map(path)
    return next(
        r for p in mapped["paragraphs"] for r in p["runs"]
        if r.get("text")==text
    )


@pytest.mark.parametrize("value",[-50,-20,0,20,50])
def test_native_letter_spacing_bounds_are_admitted(tmp_path: Path, value: int):
    path=tmp_path/f"spacing-{value}.hwpx"
    loc=_paragraph(path,"자간 ABC 漢字")
    apply_formatting_atomic(
        path,
        [{"op":"set_run_format","target":loc,"format":{"letter_spacing":value}}],
        expected_revision=1,current_revision=1,
        validator=validate_hwpx_package_light,
    )
    spacing=(_text_run(path,"자간 ABC 漢字")["style"] or {})["letter_spacing_by_script"]
    assert all(int(spacing[k])==value for k in ("hangul","latin","hanja","japanese","other","symbol","user"))


@pytest.mark.parametrize("value",[-51,51,100])
def test_non_native_letter_spacing_is_rejected(tmp_path: Path, value: int):
    path=tmp_path/f"spacing-{value}.hwpx"
    loc=_paragraph(path,"자간 ABC 漢字")
    before=path.read_bytes()
    with pytest.raises(ValueError,match="-50 to 50"):
        apply_formatting_atomic(
            path,
            [{"op":"set_run_format","target":loc,"format":{"letter_spacing":value}}],
            expected_revision=1,current_revision=1,
        )
    assert path.read_bytes()==before


def test_script_specific_font_mapping_matches_native_model(tmp_path: Path):
    path=tmp_path/"script-fonts.hwpx"
    loc=_paragraph(path,"한글 ABC 漢字")
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
    style=_text_run(path,"한글 ABC 漢字")["style"]
    assert style["font_faces"]["hangul"]=="함초롬바탕"
    assert style["font_faces"]["hanja"]=="함초롬바탕"
    assert style["font_faces"]["latin"]=="Times New Roman"
    assert style["size_pt"]==13.5
    assert int(style["letter_spacing_by_script"]["latin"])==20


def test_font_by_script_rejects_unknown_script(tmp_path: Path):
    path=tmp_path/"bad-script.hwpx"
    loc=_paragraph(path,"ABC")
    with pytest.raises(ValueError,match="Unsupported font_by_script keys"):
        apply_formatting_atomic(
            path,
            [{"op":"set_run_format","target":loc,"format":{"font_by_script":{"emoji":"Segoe UI Emoji"}}}],
            expected_revision=1,current_revision=1,
        )
