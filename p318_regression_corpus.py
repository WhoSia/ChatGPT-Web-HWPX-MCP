from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p2_document import build_document_map
from p313r1_fixture_pack import _validate_minimal_hwpx
from p318_document_setup import (
    apply_document_setup_atomic,
    build_document_setup_map,
)


CORPUS_SCHEMA = "chatgpt-web-hwpx-mcp/document-setup-regression/p3.18/v1"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _base(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.18 문서 설정 회귀 기준")
    doc.add_paragraph("alpha")
    doc.add_paragraph("beta")
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _fixture(
    out: Path,
    fixture_id: str,
    edit_class: str,
    operations: list[dict],
) -> dict:
    d = out / fixture_id
    d.mkdir(parents=True, exist_ok=True)
    source = d / "source.hwpx"
    target = d / "target.hwpx"
    _base(source)
    shutil.copy2(source, target)

    before = build_document_setup_map(source)
    resolved_ops = json.loads(json.dumps(operations, ensure_ascii=False))
    for op in resolved_ops:
        if op.get("paragraph") == "$ALPHA":
            paragraph = next(
                p for p in build_document_map(target)["paragraphs"]
                if p["text"] == "alpha"
            )
            op["paragraph"] = paragraph["locator"]

    apply_document_setup_atomic(
        target,
        resolved_ops,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    after = build_document_setup_map(target)
    return {
        "fixture_id": fixture_id,
        "edit_class": edit_class,
        "operations": resolved_ops,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "source_setup_sha256": before["document_setup_sha256"],
        "target_setup_sha256": after["document_setup_sha256"],
        "section_count_before": before["section_count"],
        "section_count_after": after["section_count"],
    }


def materialize_p318_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "paper-orientation",
            "page_composition",
            [{
                "op": "set_page_setup",
                "section_index": 0,
                "paper_size": "A4",
                "orientation": "LANDSCAPE",
                "margin_left_mm": 18,
                "margin_right_mm": 18,
            }],
        ),
        _fixture(
            out,
            "header-footer",
            "header_footer",
            [
                {"op": "set_header", "section_index": 0, "text": "P3.18 Header"},
                {"op": "set_footer", "section_index": 0, "text": "P3.18 Footer"},
            ],
        ),
        _fixture(
            out,
            "page-number",
            "page_numbering",
            [{
                "op": "set_page_number",
                "section_index": 0,
                "target": "footer",
                "prefix": "Page ",
                "position": "BOTTOM_CENTER",
            }],
        ),
        _fixture(
            out,
            "section-break",
            "section_structure",
            [{"op": "add_section", "after": 0, "text": "두 번째 구역"}],
        ),
        _fixture(
            out,
            "multi-column",
            "page_composition",
            [{
                "op": "set_columns",
                "section_index": 0,
                "count": 2,
                "same_gap": 1200,
                "separator_type": "SOLID",
            }],
        ),
        _fixture(
            out,
            "page-number-restart",
            "page_numbering",
            [{"op": "restart_page_number", "paragraph": "$ALPHA", "number": 5}],
        ),
    ]

    manifest = {
        "schema": CORPUS_SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "native_batch_status": "DEFERRED_BY_DESIGN",
        "purpose": "PRODUCT_DOCUMENT_SETUP_REGRESSION",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p318-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
