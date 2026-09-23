from __future__ import annotations

import tempfile
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map
from p23_richtext import apply_rich_formatting_atomic
from p334r2_package_validation import validate_hwpx_package_light


def paragraph_locator(path: Path, text: str) -> str:
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


def text_runs(path: Path, target: str) -> list[dict]:
    mapped = build_formatting_map(path)
    para = next(item for item in mapped["paragraphs"] if item["locator"] == target)
    return [run for run in para["runs"] if run.get("text")]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Whole-run native typography surface.
        path = root / "p335-run.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("한글 ABC 漢字")
        doc.save_to_path(str(path))
        doc.close()
        loc = paragraph_locator(path, "한글 ABC 漢字")
        apply_formatting_atomic(
            path,
            [{
                "op": "set_run_format",
                "target": loc,
                "format": {
                    "font": "함초롬바탕",
                    "font_by_script": {"latin": "Times New Roman"},
                    "size": 13.5,
                    "letter_spacing": 20,
                },
            }],
            expected_revision=1,
            current_revision=1,
            validator=validate_hwpx_package_light,
        )
        run = text_runs(path, loc)[0]
        style = run["style"]
        assert style["font_faces"]["hangul"] == "함초롬바탕"
        assert style["font_faces"]["hanja"] == "함초롬바탕"
        assert style["font_faces"]["latin"] == "Times New Roman"
        assert style["size_pt"] == 13.5
        assert int(style["letter_spacing_by_script"]["hangul"]) == 20

        # Mixed-run / range authoring surface.
        path2 = root / "p335-range.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("한글 ABC 漢字")
        doc.save_to_path(str(path2))
        doc.close()
        loc2 = paragraph_locator(path2, "한글 ABC 漢字")
        # "ABC" occupies [3, 6).
        apply_rich_formatting_atomic(
            path2,
            [{
                "op": "set_range_format",
                "target": loc2,
                "start": 3,
                "end": 6,
                "format": {
                    "font_by_script": {"latin": "Times New Roman"},
                    "size": 11,
                    "letter_spacing": -20,
                },
            }],
            expected_revision=1,
            current_revision=1,
            validator=validate_hwpx_package_light,
        )
        runs = text_runs(path2, loc2)
        abc = next(run for run in runs if run["text"] == "ABC")
        assert abc["style"]["font_faces"]["latin"] == "Times New Roman"
        assert abc["style"]["size_pt"] == 11
        assert int(abc["style"]["letter_spacing_by_script"]["latin"]) == -20
        assert "".join(run["text"] for run in runs) == "한글 ABC 漢字"

        # Native UI bounds from Hancom 13.0.0.3622.
        try:
            apply_formatting_atomic(
                path,
                [{"op": "set_run_format", "target": loc, "format": {"letter_spacing": 51}}],
                expected_revision=2,
                current_revision=2,
            )
        except ValueError as exc:
            assert "-50 to 50" in str(exc)
        else:
            raise AssertionError("letter_spacing=51 must fail closed")

    print("P3.35 core typography smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
