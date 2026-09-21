from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p2_document import build_document_map
from p313r1_fixture_pack import _validate_minimal_hwpx
from p322_review_workflow import apply_review_workflow_atomic, build_review_workflow_map


SCHEMA = "chatgpt-web-hwpx-mcp/review-workflow-regression/p3.22/v1"


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
    doc.add_paragraph("P3.22 review regression")
    doc.add_paragraph("alpha review target")
    doc.add_paragraph("beta form target")
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _resolve(path: Path, operations: list[dict]) -> list[dict]:
    paragraphs = build_document_map(path)["paragraphs"]
    tokens = {
        "$ALPHA": next(p["locator"] for p in paragraphs if p["text"] == "alpha review target"),
        "$BETA": next(p["locator"] for p in paragraphs if p["text"] == "beta form target"),
    }
    resolved = json.loads(json.dumps(operations, ensure_ascii=False))
    for op in resolved:
        if op.get("paragraph") in tokens:
            op["paragraph"] = tokens[op["paragraph"]]
    return resolved


def _fixture(out: Path, fixture_id: str, operations: list[dict]) -> dict:
    root = out / fixture_id
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.hwpx"
    target = root / "target.hwpx"
    _base(source)
    target.write_bytes(source.read_bytes())

    before = build_review_workflow_map(source)
    resolved = _resolve(target, operations)
    result = apply_review_workflow_atomic(
        target,
        resolved,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    after = build_review_workflow_map(target)

    return {
        "fixture_id": fixture_id,
        "operations": resolved,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "source_review_sha256": before["review_workflow_sha256"],
        "target_review_sha256": after["review_workflow_sha256"],
        "before_counts": before["counts"],
        "after_counts": after["counts"],
        "changed": result["changed"],
    }


def materialize_p322_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "tracked-review",
            [{
                "op": "tracked_replace",
                "paragraph": "$ALPHA",
                "old": "review",
                "new": "revision",
                "author": "P3.22 Reviewer",
                "date": "2026-09-21T07:00:00Z",
            }],
        ),
        _fixture(
            out,
            "form-field",
            [{
                "op": "add_form_field",
                "paragraph": "$BETA",
                "name": "student_name",
                "prompt": "이름 입력",
                "memo": "검토 양식",
            }],
        ),
        _fixture(
            out,
            "check-box",
            [{
                "op": "add_check_box",
                "paragraph": "$BETA",
                "caption": "검토 완료",
                "name": "review_done",
                "checked": True,
            }],
        ),
        _fixture(
            out,
            "highlight-proofreading",
            [
                {
                    "op": "add_highlight",
                    "paragraph": "$ALPHA",
                    "match": "alpha",
                    "color": "#FFF200",
                },
                {
                    "op": "add_proofreading_mark",
                    "paragraph": "$ALPHA",
                    "mark": "space",
                },
            ],
        ),
        _fixture(
            out,
            "document-metadata",
            [{
                "op": "set_document_metadata",
                "title": "P3.22 검토본",
                "creator": "ChatGPT Web HWPX MCP",
                "subject": "review workflow",
                "keyword": "HWPX,review",
                "created_date": "2026-09-21T07:00:00Z",
                "modified_date": "2026-09-21T07:05:00Z",
            }],
        ),
        _fixture(
            out,
            "mixed-review",
            [
                {
                    "op": "tracked_insert",
                    "paragraph": "$ALPHA",
                    "text": " [검토 추가]",
                    "author": "AI Agent",
                },
                {
                    "op": "add_form_field",
                    "paragraph": "$BETA",
                    "name": "approval",
                    "prompt": "승인자",
                },
                {
                    "op": "add_check_box",
                    "paragraph": "$BETA",
                    "caption": "승인",
                    "name": "approved",
                    "checked": False,
                },
                {
                    "op": "add_highlight",
                    "paragraph": "$ALPHA",
                    "match": "alpha",
                    "color": "#FFFF00",
                },
                {
                    "op": "set_document_metadata",
                    "title": "혼합 검토 문서",
                    "creator": "P3.22",
                },
            ],
        ),
    ]

    manifest = {
        "schema": SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "purpose": "PRODUCT_REVIEW_WORKFLOW_REGRESSION",
        "native_batch_status": "DEFERRED_BY_DESIGN",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p322-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
