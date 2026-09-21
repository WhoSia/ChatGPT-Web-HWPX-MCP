from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p313r1_fixture_pack import _validate_minimal_hwpx
from p321_document_composer import compose_document_plan


SCHEMA = "chatgpt-web-hwpx-mcp/document-composition-regression/p3.21/v1"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlY4AAAAASUVORK5CYII="
)


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


def _blank(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _template(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("템플릿 고정 본문")
    doc.page.set_header(text="템플릿 머리말", section=0)
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _fixture(
    out: Path,
    fixture_id: str,
    plan: dict,
    *,
    template: bool = False,
) -> dict:
    root = out / fixture_id
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.hwpx"
    target = root / "target.hwpx"
    (_template if template else _blank)(source)
    receipt = compose_document_plan(
        target,
        plan,
        template_path=source if template else None,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    return {
        "fixture_id": fixture_id,
        "template_mode": receipt["template_mode"],
        "plan_sha256": receipt["plan_sha256"],
        "composition_sha256": receipt["composition_sha256"],
        "block_count": receipt["block_count"],
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "stage_names": [item["stage"] for item in receipt["stages"]],
    }


def materialize_p321_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "basic-report",
            {
                "preset": "school-report",
                "blocks": [
                    {"id": "title", "type": "title", "text": "기본 보고서"},
                    {"id": "h1", "type": "heading", "level": 1, "text": "1. 서론"},
                    {"id": "p1", "type": "paragraph", "text": "한 번의 plan으로 생성된 본문."},
                ],
                "publishing": {"page_numbers": True},
            },
        ),
        _fixture(
            out,
            "mixed-blocks",
            {
                "blocks": [
                    {"id": "h1", "type": "heading", "level": 1, "text": "측정"},
                    {"id": "p1", "type": "paragraph", "text": "측정 결과"},
                    {
                        "id": "tbl",
                        "type": "table",
                        "rows": 2,
                        "cols": 2,
                        "cells": [["x", "y"], ["1", "2"]],
                    },
                    {"id": "eq", "type": "equation", "latex": "y=2x"},
                    {
                        "id": "pic",
                        "type": "picture",
                        "content_base64": base64.b64encode(PNG_1X1).decode("ascii"),
                        "image_format": "png",
                        "width": 7200,
                        "height": 7200,
                    },
                ],
            },
        ),
        _fixture(
            out,
            "publishing-references",
            {
                "blocks": [
                    {"id": "h1", "type": "heading", "level": 1, "text": "첫 장", "bookmark": "chapter-1"},
                    {"id": "p1", "type": "paragraph", "text": "첫 장 본문"},
                    {"id": "h2", "type": "heading", "level": 1, "text": "둘째 장"},
                    {"id": "p2", "type": "paragraph", "text": "앞 장을 참조한다."},
                ],
                "publishing": {"toc": True},
                "post_operations": [
                    {
                        "op": "add_page_crossref",
                        "paragraph": "$block:p2",
                        "target_paragraph": "$block:h1",
                        "cached_page": 1,
                    }
                ],
                "annotations": [
                    {"op": "add_footnote", "paragraph": "$block:p1", "text": "각주"},
                ],
            },
        ),
        _fixture(
            out,
            "template-append",
            {
                "blocks": [
                    {"id": "h", "type": "heading", "level": 1, "text": "추가 장"},
                    {"id": "p", "type": "paragraph", "text": "템플릿 뒤에 추가된 내용"},
                ],
            },
            template=True,
        ),
    ]

    manifest = {
        "schema": SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "purpose": "CHATGPT_NATIVE_ONE_SHOT_COMPOSITION_REGRESSION",
        "native_batch_status": "DEFERRED_BY_DESIGN",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p321-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
