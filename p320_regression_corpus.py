from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p2_document import build_document_map
from p313r1_fixture_pack import _validate_minimal_hwpx
from p320_annotation_apparatus import (
    apply_annotation_apparatus_atomic,
    build_annotation_apparatus_map,
)


SCHEMA = "chatgpt-web-hwpx-mcp/annotation-apparatus-regression/p3.20/v1"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _base(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.20 annotation regression")
    doc.add_paragraph("alpha reference target")
    doc.add_paragraph("beta annotation target")
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _resolve_tokens(path: Path, operations: list[dict]) -> list[dict]:
    mapped = build_document_map(path)["paragraphs"]
    tokens = {
        "$ALPHA": next(p["locator"] for p in mapped if p["text"] == "alpha reference target"),
        "$BETA": next(p["locator"] for p in mapped if p["text"] == "beta annotation target"),
    }
    resolved = json.loads(json.dumps(operations, ensure_ascii=False))
    for op in resolved:
        for key in ("paragraph", "target_paragraph"):
            value = op.get(key)
            if value in tokens:
                op[key] = tokens[value]
    return resolved


def _fixture(
    out: Path,
    fixture_id: str,
    edit_class: str,
    operations: list[dict],
) -> dict:
    root = out / fixture_id
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.hwpx"
    target = root / "target.hwpx"
    _base(source)
    shutil.copy2(source, target)

    before = build_annotation_apparatus_map(source)
    resolved = _resolve_tokens(target, operations)
    apply_annotation_apparatus_atomic(
        target,
        resolved,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    after = build_annotation_apparatus_map(target)

    return {
        "fixture_id": fixture_id,
        "edit_class": edit_class,
        "operations": resolved,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "source_annotation_sha256": before["annotation_apparatus_sha256"],
        "target_annotation_sha256": after["annotation_apparatus_sha256"],
        "before_counts": before["counts"],
        "after_counts": after["counts"],
    }


def materialize_p320_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "notes",
            "footnote_endnote",
            [
                {"op": "add_footnote", "paragraph": "$ALPHA", "text": "각주 회귀 본문"},
                {"op": "add_endnote", "paragraph": "$BETA", "text": "미주 회귀 본문"},
            ],
        ),
        _fixture(
            out,
            "memo",
            "memo_comment",
            [
                {
                    "op": "add_memo",
                    "paragraph": "$BETA",
                    "text": "출판 검토 메모",
                    "author": "P3.20",
                }
            ],
        ),
        _fixture(
            out,
            "index-marks",
            "index_mark",
            [
                {"op": "add_index_mark", "paragraph": "$ALPHA", "first": "과학"},
                {
                    "op": "add_index_mark",
                    "paragraph": "$BETA",
                    "first": "연구",
                    "second": "방법",
                },
            ],
        ),
        _fixture(
            out,
            "reference-navigation",
            "reference_navigation",
            [
                {"op": "add_bookmark", "paragraph": "$ALPHA", "name": "alpha-anchor"},
                {
                    "op": "add_hyperlink",
                    "paragraph": "$BETA",
                    "url": "https://example.com/p320",
                    "display_text": "참고 링크",
                },
            ],
        ),
        _fixture(
            out,
            "rich-fields",
            "rich_reference_fields",
            [
                {
                    "op": "add_date_field",
                    "paragraph": "$ALPHA",
                    "cached_text": "2026년 9월 21일",
                },
                {
                    "op": "add_path_field",
                    "paragraph": "$ALPHA",
                    "cached_text": "paper.hwpx",
                },
                {
                    "op": "add_mail_merge_field",
                    "paragraph": "$BETA",
                    "name": "author_name",
                },
                {
                    "op": "add_proofreading_mark",
                    "paragraph": "$BETA",
                    "mark": "space",
                },
            ],
        ),
        _fixture(
            out,
            "academic-apparatus",
            "mixed_annotation_apparatus",
            [
                {"op": "add_footnote", "paragraph": "$ALPHA", "text": "근거 주석"},
                {"op": "add_memo", "paragraph": "$BETA", "text": "편집 메모"},
                {"op": "add_index_mark", "paragraph": "$ALPHA", "first": "근거"},
                {
                    "op": "add_hyperlink",
                    "paragraph": "$BETA",
                    "url": "https://example.com/source",
                    "display_text": "원문",
                },
            ],
        ),
    ]

    manifest = {
        "schema": SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "native_batch_status": "DEFERRED_BY_DESIGN",
        "purpose": "PRODUCT_ANNOTATION_APPARATUS_REGRESSION",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p320-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
