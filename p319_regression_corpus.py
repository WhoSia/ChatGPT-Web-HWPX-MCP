from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p2_document import build_document_map
from p28_tables import apply_table_edits_atomic, build_table_map
from p313r1_fixture_pack import _validate_minimal_hwpx
from p319_structured_publishing import (
    apply_structured_publishing_atomic,
    build_structured_publishing_map,
)


SCHEMA = "chatgpt-web-hwpx-mcp/structured-publishing-regression/p3.19/v1"


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
    doc.add_paragraph("P3.19 구조화 출판 기준")
    doc.add_paragraph("alpha")
    doc.add_paragraph("beta")
    doc.add_heading("제1장 서론", level=1)
    doc.add_heading("1.1 배경", level=2)
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _locator(path: Path, text: str) -> str:
    return next(
        p["locator"]
        for p in build_document_map(path)["paragraphs"]
        if p["text"] == text
    )


def _fixture(
    out: Path,
    fixture_id: str,
    edit_class: str,
    operations: list[dict],
    *,
    prepare=None,
) -> dict:
    d = out / fixture_id
    d.mkdir(parents=True, exist_ok=True)
    source = d / "source.hwpx"
    target = d / "target.hwpx"
    _base(source)
    if prepare is not None:
        prepare(source)
    shutil.copy2(source, target)

    resolved = json.loads(json.dumps(operations, ensure_ascii=False))
    replacements = {
        "$ALPHA": lambda: _locator(target, "alpha"),
        "$BETA": lambda: _locator(target, "beta"),
        "$H1": lambda: _locator(target, "제1장 서론"),
        "$H2": lambda: _locator(target, "1.1 배경"),
        "$TABLE0": lambda: build_table_map(target)["tables"][0]["locator"],
    }
    for op in resolved:
        for key in ("paragraph", "target_paragraph", "target"):
            value = op.get(key)
            if value in replacements:
                op[key] = replacements[value]()

    before = build_structured_publishing_map(source)
    apply_structured_publishing_atomic(
        target,
        resolved,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    after = build_structured_publishing_map(target)
    return {
        "fixture_id": fixture_id,
        "edit_class": edit_class,
        "operations": resolved,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "source_publishing_sha256": before["structured_publishing_sha256"],
        "target_publishing_sha256": after["structured_publishing_sha256"],
        "toc_field_count_after": after["toc_field_count"],
        "crossref_field_count_after": after["crossref_field_count"],
        "caption_count_after": len(after["captions"]),
    }


def _prepare_table(path: Path) -> None:
    apply_table_edits_atomic(
        path,
        [{"op": "create_table", "rows": 2, "cols": 2}],
        expected_revision=1,
        current_revision=1,
        validator=None,
    )


def materialize_p319_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "native-numbering",
            "list_numbering",
            [{
                "op": "apply_list_format",
                "paragraphs": ["$ALPHA", "$BETA"],
                "kind": "number",
                "level": 1,
                "number_format": "^1.",
                "start": 1,
            }],
        ),
        _fixture(
            out,
            "named-style-outline",
            "named_styles",
            [
                {"op": "apply_named_style", "paragraph": "$ALPHA", "style": "본문"},
                {"op": "set_outline_level", "paragraph": "$BETA", "level": 3},
            ],
        ),
        _fixture(
            out,
            "table-caption",
            "captions",
            [{"op": "set_caption", "kind": "table", "target": "$TABLE0", "text": "표 1. 회귀 표"}],
            prepare=_prepare_table,
        ),
        _fixture(
            out,
            "bookmark-crossref",
            "cross_reference",
            [
                {"op": "add_bookmark", "paragraph": "$H1", "name": "chapter-one"},
                {
                    "op": "add_page_crossref",
                    "paragraph": "$ALPHA",
                    "target_paragraph": "$H1",
                    "cached_page": 1,
                },
            ],
        ),
        _fixture(
            out,
            "native-toc",
            "table_of_contents",
            [{"op": "add_native_toc", "at_index": 0, "title": "차례", "level": 2}],
        ),
        _fixture(
            out,
            "outline-hierarchy",
            "outline_hierarchy",
            [
                {"op": "set_outline_level", "paragraph": "$ALPHA", "level": 2},
                {"op": "add_heading", "text": "새 하위 항목", "level": 3},
            ],
        ),
    ]

    manifest = {
        "schema": SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "native_batch_status": "DEFERRED_BY_DESIGN",
        "purpose": "PRODUCT_STRUCTURED_PUBLISHING_REGRESSION",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p319-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
