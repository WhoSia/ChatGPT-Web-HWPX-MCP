"""End-to-end professional diagnostics -> native composite -> bounded edit."""
import base64
from pathlib import Path

import pytest

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.quality.p421_composite_workflow import (
    compose_reviewed_document, edit_reviewed_document,
)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlY4AAAAASUVORK5CYII="
)


@pytest.fixture
def plan():
    return {"preset": "academic-report", "blocks": [
        {"id": "title", "type": "title", "text": "전기회로 관측 보고서"},
        {"id": "section", "type": "heading", "level": 1, "text": "실험"},
        {"id": "body", "type": "paragraph", "text": "전류와 전압을 측정했다."},
        {"id": "table", "type": "table", "rows": 2, "cols": 2,
         "cells": [["전압", "전류"], ["3 V", "0.1 A"]], "caption": "표 1"},
        {"id": "eq", "type": "equation", "latex": "V=IR", "caption": "식 1"},
        {"id": "pic", "type": "picture",
         "content_base64": base64.b64encode(PNG).decode(),
         "image_format": "png", "width": 7200, "height": 7200,
         "caption": "그림 1"},
    ], "annotations": [{"op": "add_footnote",
                        "paragraph": "$block:body", "text": "시험 데이터"}]}


def test_real_composition_includes_diagnostics_and_preserves_objects(tmp_path, plan):
    dest = tmp_path / "composite.hwpx"
    out = compose_reviewed_document(dest, plan)
    assert dest.is_file()
    assert out["composition"]["professional_authoring_review"]["status"] == "NO_STATIC_DESIGN_WARNINGS"
    assert out["professional_review"]["mutated_plan"] is False
    assert out["quality"]["counts"]["tables"] == 1
    assert out["quality"]["counts"]["equations"] == 1
    assert out["quality"]["counts"]["pictures"] == 1
    assert out["quality"]["counts"]["footnotes"] == 1
    assert out["quality"]["status"] == "PASS_STRUCTURE_HOLD_RELEASE"


def test_bounded_edit_retains_native_components(tmp_path, plan):
    p = tmp_path / "reviewed.hwpx"
    compose_reviewed_document(p, plan)
    doc = build_document_map(p)
    target = next(x["locator"] for x in doc["paragraphs"]
                  if x["text"] == "전류와 전압을 측정했다.")
    out = edit_reviewed_document(
        p, [{"op": "replace_paragraph_text", "target": target,
             "text": "전압과 전류를 각각 측정하였다."}],
        expected_revision=1, current_revision=1,
        minimum_counts={"tables": 1, "equations": 1, "pictures": 1, "footnotes": 1},
    )
    assert out["status"] == "PASS_STRUCTURE_HOLD_VISUAL"
    assert out["after"]["counts"] == out["before"]["counts"]
    assert out["after"]["semantic_sha256"] != out["before"]["semantic_sha256"]


def test_unbounded_or_unauthorized_edits_rejected(tmp_path, plan):
    p = tmp_path / "bounded.hwpx"
    compose_reviewed_document(p, plan)
    with pytest.raises(ValueError):
        edit_reviewed_document(p, [{"op": "delete_paragraph"}],
                               expected_revision=1, current_revision=1,
                               minimum_counts={"tables": 1})
    with pytest.raises(ValueError):
        edit_reviewed_document(p, [{"op": "replace_paragraph_text", "text": "x"}] * 3,
                               expected_revision=1, current_revision=1,
                               minimum_counts={"tables": 1})
