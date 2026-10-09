from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.document.p28_tables import apply_table_edits_atomic, build_table_map
from hwpx_mcp.document.p210_equations import apply_equation_edits_atomic, build_equation_map
from hwpx_mcp.document.p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from hwpx_mcp.rendering.p46_native_authoring import audit_equation_latex, equation_capability_matrix


def make_base(path: Path, label: str) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph(label)
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    path.write_bytes(buffer.getvalue())
    mapped = build_document_map(path)
    return next(p["locator"] for p in mapped["paragraphs"] if p.get("text") == label)


def safety(path: Path) -> dict:
    report = validate_editor_open_safety(path.read_bytes())
    return {"ok": bool(report.ok), "issues": list(getattr(report, "issues", []) or [])}


def main(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []

    equation = out / "technical-note-native-math.hwpx"
    anchor = make_base(equation, "Technical note equation anchor")
    apply_equation_edits_atomic(
        equation,
        [
            {"op": "insert_equation", "paragraph": anchor, "latex": r"\frac{a}{b}"},
            {"op": "insert_equation", "paragraph": anchor, "latex": r"\sqrt[3]{x+1}"},
            {"op": "insert_equation", "paragraph": anchor, "latex": r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"},
            {"op": "insert_equation", "paragraph": anchor, "latex": r"\begin{cases} x & x>0 \\ 0 & x\leq0 \end{cases}"},
        ],
        expected_revision=1,
        current_revision=1,
    )
    eq_map = build_equation_map(equation)
    rows.append({
        "id": "technical-note-native-math",
        "file": equation.name,
        "bytes": equation.stat().st_size,
        "open_safety": safety(equation),
        "equation_count": eq_map["equation_count"],
        "equation_structure_sha256": eq_map["equation_structure_sha256"],
    })

    table = out / "public-form-table.hwpx"
    make_base(table, "Public form table anchor")
    apply_table_edits_atomic(
        table,
        [{
            "op": "create_table",
            "rows": 3,
            "cols": 3,
            "cells": [
                ["항목", "값", "비고"],
                ["문서 형식", "HWPX", "native table"],
                ["검증", "PASS", "P4.6"],
            ],
        }],
        expected_revision=1,
        current_revision=1,
    )
    table_map = build_table_map(table)
    rows.append({
        "id": "public-form-table",
        "file": table.name,
        "bytes": table.stat().st_size,
        "open_safety": safety(table),
        "table_count": table_map["table_count"],
        "table_structure_sha256": table_map["table_structure_sha256"],
    })

    drawing = out / "diagrammatic-report.hwpx"
    anchor = make_base(drawing, "Drawing anchor")
    apply_drawing_layer_atomic(
        drawing,
        [{
            "op": "insert_textbox",
            "anchor": anchor,
            "text": "Native HWPX callout",
            "width": 9000,
            "height": 4500,
            "treat_as_char": False,
            "horizontal_offset": 1200,
            "vertical_offset": 800,
            "z_order": 5,
        }],
        expected_revision=1,
        current_revision=1,
    )
    drawing_map = build_drawing_layer_map(drawing)
    rows.append({
        "id": "diagrammatic-report",
        "file": drawing.name,
        "bytes": drawing.stat().st_size,
        "open_safety": safety(drawing),
        "drawing_count": drawing_map["drawing_count"],
        "drawing_structure_sha256": drawing_map["drawing_structure_sha256"],
    })

    mixed = out / "mixed-native-authoring.hwpx"
    anchor = make_base(mixed, "Mixed authoring anchor")
    apply_equation_edits_atomic(
        mixed,
        [{"op": "insert_equation", "paragraph": anchor, "latex": r"\sum_{k=1}^{n} k"}],
        expected_revision=1,
        current_revision=1,
    )
    apply_table_edits_atomic(
        mixed,
        [{"op": "create_table", "rows": 2, "cols": 2, "cells": [["A", "B"], ["1", "2"]]}],
        expected_revision=1,
        current_revision=1,
    )
    apply_drawing_layer_atomic(
        mixed,
        [{"op": "insert_rectangle", "anchor": anchor, "width": 7200, "height": 3600, "treat_as_char": False}],
        expected_revision=1,
        current_revision=1,
    )
    rows.append({
        "id": "mixed-native-authoring",
        "file": mixed.name,
        "bytes": mixed.stat().st_size,
        "open_safety": safety(mixed),
        "equation_count": build_equation_map(mixed)["equation_count"],
        "table_count": build_table_map(mixed)["table_count"],
        "drawing_count": build_drawing_layer_map(mixed)["drawing_count"],
    })

    unsupported = {
        "mathbb": audit_equation_latex(r"\mathbb{R}"),
        "mathcal": audit_equation_latex(r"\mathcal{F}"),
        "align": audit_equation_latex(r"\begin{align} x&=1 \end{align}"),
    }
    capability = equation_capability_matrix()
    result = {
        "phase": "P4.6",
        "product": "0.32.0-p4.6",
        "scenario_count": len(rows),
        "scenarios": rows,
        "all_open_safe": all(row["open_safety"]["ok"] for row in rows),
        "unsupported_equation_abstention": unsupported,
        "default_equation_capability": {
            "probe_count": capability["probe_count"],
            "supported_count": capability["supported_count"],
            "abstained_count": capability["abstained_count"],
            "matrix_sha256": capability["matrix_sha256"],
        },
        "authority": "STRUCTURAL_AND_EDITOR_OPEN_SAFETY_NOT_NATIVE_RENDER_OR_HUMAN_AESTHETIC_AUTHORITY",
    }
    if not result["all_open_safe"]:
        raise RuntimeError(f"P4.6 real-document benchmark open-safety failure: {result}")
    if any(item["supported"] for item in unsupported.values()):
        raise RuntimeError(f"P4.6 unsupported equation style silently admitted: {unsupported}")
    (out / "p46-real-document-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/p46-real-documents"))
    args = parser.parse_args()
    main(args.out)
