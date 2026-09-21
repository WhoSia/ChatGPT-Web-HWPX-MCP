from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p2_document import apply_text_edits_atomic, build_document_map
from p23_richtext import apply_rich_formatting_atomic
from p28_tables import apply_table_edits_atomic, build_table_map
from p29_objects import apply_object_edits_atomic, build_object_map
from p39_textbox import inject_textbox, build_textbox_map
from p210_equations import apply_equation_edits_atomic, build_equation_map
from p22_formatting import build_formatting_map
from p313r1_fixture_pack import _validate_minimal_hwpx
from p316_version_indexed import build_structural_oracle, compare_structural_oracles
from p317_page_geometry import apply_page_geometry_edits_atomic, build_page_geometry_map


CORPUS_SCHEMA = "chatgpt-web-hwpx-mcp/edit-regression-corpus/p3.17/v1"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _base_document(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.17 기능 회귀 기준 문서")
    doc.add_paragraph("alpha 기능 편집 기준 문단")
    doc.add_paragraph("beta 범위 서식과 텍스트 편집 대상")
    doc.add_paragraph("gamma 객체와 수식 앵커 문단")
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _tiny_png_base64() -> str:
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00" * 8
        + (1).to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + b"\x00" * 32
    )
    return base64.b64encode(payload).decode("ascii")


def _snapshot(path: Path) -> dict:
    document = build_document_map(path)
    formatting = build_formatting_map(path)
    tables = build_table_map(path)
    objects = build_object_map(path)
    textboxes = build_textbox_map(path)
    equations = build_equation_map(path)
    structural = build_structural_oracle(path)
    return {
        "semantic_sha256": document["semantic_sha256"],
        "structure_sha256": document["structure_sha256"],
        "formatting_sha256": formatting["formatting_sha256"],
        "table_structure_sha256": tables["table_structure_sha256"],
        "table_format_sha256": tables["table_format_sha256"],
        "object_structure_sha256": objects["object_structure_sha256"],
        "object_geometry_sha256": objects["object_geometry_sha256"],
        "media_custody_sha256": objects["media_custody_sha256"],
        "textbox_count": len(textboxes.get("textboxes", [])),
        "textbox_sha256": _sha(textboxes),
        "equation_structure_sha256": equations["equation_structure_sha256"],
        "equation_geometry_sha256": equations["equation_geometry_sha256"],
        "equation_script_custody_sha256": equations[
            "equation_script_custody_sha256"
        ],
        "page_geometry_sha256": build_page_geometry_map(path)["page_geometry_sha256"],
        "structural_oracle_sha256": structural["structural_oracle_sha256"],
        "structural_oracle": structural,
    }


def _changed_dimensions(before: dict, after: dict) -> list[str]:
    ignored = {"structural_oracle", "structural_oracle_sha256"}
    return sorted(
        key
        for key in before
        if key not in ignored and before.get(key) != after.get(key)
    )


def _pair_receipt(
    fixture_id: str,
    edit_class: str,
    source: Path,
    target: Path,
    operation: dict,
) -> dict:
    before = _snapshot(source)
    after = _snapshot(target)
    structural_diff = compare_structural_oracles(
        before["structural_oracle"], after["structural_oracle"]
    )
    return {
        "fixture_id": fixture_id,
        "edit_class": edit_class,
        "operation": operation,
        "source": source.name,
        "target": target.name,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "changed_runtime_dimensions": _changed_dimensions(before, after),
        "structural_changed_dimensions": structural_diff["changed_dimensions"],
        "source_snapshot_sha256": _sha(
            {k: v for k, v in before.items() if k != "structural_oracle"}
        ),
        "target_snapshot_sha256": _sha(
            {k: v for k, v in after.items() if k != "structural_oracle"}
        ),
    }


def materialize_p317_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixtures: list[dict] = []

    # 1. Text content
    d = out / "text-content"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    mapped = build_document_map(target)
    beta = next(p for p in mapped["paragraphs"] if p["text"].startswith("beta "))
    op = {
        "op": "replace_paragraph_text",
        "target": beta["locator"],
        "text": "beta 교체된 실제 텍스트 편집 결과",
    }
    apply_text_edits_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(_pair_receipt("text-content", "text_content", source, target, op))

    # 2. Run formatting
    d = out / "run-format"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    mapped = build_document_map(target)
    beta = next(p for p in mapped["paragraphs"] if p["text"].startswith("beta "))
    op = {
        "op": "set_range_format",
        "target": beta["locator"],
        "start": 0,
        "end": 4,
        "format": {"bold": True, "color": "#2450A4"},
    }
    apply_rich_formatting_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(_pair_receipt("run-format", "run_format", source, target, op))

    # 3. Paragraph formatting
    d = out / "paragraph-format"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    mapped = build_document_map(target)
    alpha = next(p for p in mapped["paragraphs"] if p["text"].startswith("alpha "))
    op = {
        "op": "set_paragraph_format",
        "target": alpha["locator"],
        "format": {"alignment": "CENTER", "spacing_after_pt": 4},
    }
    apply_rich_formatting_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(
        _pair_receipt("paragraph-format", "paragraph_format", source, target, op)
    )

    # 4. Table
    d = out / "table"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    op = {
        "op": "create_table",
        "rows": 2,
        "cols": 3,
        "cells": [["항목", "값", "비고"], ["A", "17", "회귀"]],
    }
    apply_table_edits_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(_pair_receipt("table", "table", source, target, op))

    # 5. Picture
    d = out / "picture"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    mapped = build_document_map(target)
    anchor = next(p for p in mapped["paragraphs"] if p["text"].startswith("gamma "))
    op = {
        "op": "insert_picture",
        "paragraph": anchor["locator"],
        "content_base64": _tiny_png_base64(),
        "image_format": "png",
        "width": 7200,
        "height": 3600,
        "placement": "inline",
    }
    apply_object_edits_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(_pair_receipt("picture", "object_picture", source, target, op))

    # 6. Text box
    d = out / "textbox"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    mapped = build_document_map(target)
    anchor = next(p for p in mapped["paragraphs"] if p["text"].startswith("gamma "))
    op = {
        "op": "insert_textbox",
        "anchor": anchor["locator"],
        "paragraphs": ["P3.17 텍스트박스", "실전 편집 회귀"],
        "width": 18000,
        "height": 8000,
        "treat_as_char": True,
    }
    inject_textbox(
        target,
        anchor_locator=anchor["locator"],
        paragraphs=list(op["paragraphs"]),
        width=int(op["width"]),
        height=int(op["height"]),
        treat_as_char=True,
        shape_seed="p317-regression",
    )
    fixtures.append(_pair_receipt("textbox", "textbox", source, target, op))

    # 7. Page geometry (actual runtime feature, inherits P3.16 boundary authority)
    d = out / "page-geometry"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    before_page = build_page_geometry_map(target)
    right_before = int(before_page["sections"][0]["margin"].get("right", "0") or 0)
    op = {
        "op": "set_page_margin",
        "section_index": 0,
        "right": right_before + 283,
    }
    apply_page_geometry_edits_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(
        _pair_receipt(
            "page-geometry", "page_section_geometry", source, target, op
        )
    )

    # 8. Equation
    d = out / "equation"
    d.mkdir(exist_ok=True)
    source, target = d / "source.hwpx", d / "target.hwpx"
    _base_document(source)
    shutil.copy2(source, target)
    mapped = build_document_map(target)
    anchor = next(p for p in mapped["paragraphs"] if p["text"].startswith("gamma "))
    op = {
        "op": "insert_equation",
        "paragraph": anchor["locator"],
        "latex": r"\frac{x^2+y^2}{2}",
        "base_unit": 1100,
    }
    apply_equation_edits_atomic(
        target, [op], expected_revision=1, current_revision=1, validator=None
    )
    fixtures.append(_pair_receipt("equation", "equation", source, target, op))

    for item in fixtures:
        fixture_dir = out / item["fixture_id"]
        _validate_minimal_hwpx(fixture_dir / "source.hwpx")
        _validate_minimal_hwpx(fixture_dir / "target.hwpx")

    manifest = {
        "schema": CORPUS_SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "inherited_native_certification": {
            "page_section_geometry": {
                "source": "P3.16",
                "renderer_version": "13.0.0.3622",
                "advance_boundary": "advance-10120",
                "frame_boundary": "frame-283",
                "runtime_operation": "set_page_margin",
            }
        },
        "native_batch_status": "PENDING",
        "purpose": "PRODUCT_REGRESSION_AND_EDIT_CLASS_CERTIFICATION",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p317-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
