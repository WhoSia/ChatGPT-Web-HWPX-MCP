"""P4.20 independently measurable authoring quality and negative controls."""
from __future__ import annotations

import base64
import shutil
import tempfile
from pathlib import Path

import pytest

from hwpx_mcp.document.p2_document import apply_text_edits_atomic, build_document_map
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p334r2_package_validation import validate_hwpx_package_light
from hwpx_mcp.quality.p420_document_quality import judge_document_quality


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlY4AAAAASUVORK5CYII="
)


@pytest.fixture()
def report(tmp_path):
    path = tmp_path / "native-report.hwpx"
    compose_document_plan(path, {
        "preset": "academic-report",
        "blocks": [
            {"id": "title", "type": "title", "text": "연구 결과와 해석"},
            {"id": "h", "type": "heading", "level": 1, "text": "1. 관찰"},
            {"id": "body", "type": "paragraph", "text": "전압과 전류 사이의 관계를 관찰했다."},
            {"id": "table", "type": "table", "rows": 2, "cols": 2,
             "cells": [["전압", "전류"], ["3 V", "0.1 A"]]},
            {"id": "equation", "type": "equation", "latex": "V=IR"},
            {"id": "image", "type": "picture",
             "content_base64": base64.b64encode(PNG_1X1).decode("ascii"),
             "image_format": "png", "width": 7200, "height": 7200},
        ],
        "annotations": [{
            "op": "add_footnote", "paragraph": "$block:body",
            "text": "이 문서는 테스트 자료다.",
        }],
    }, validator=validate_hwpx_package_light)
    return path


def test_all_native_objects_measured_but_unrendered_stays_hold(report):
    result = judge_document_quality(
        report,
        minimum_counts={"sections": 1, "tables": 1, "equations": 1,
                        "pictures": 1, "footnotes": 1},
        required_texts=["연구 결과와 해석", "전압과 전류 사이의 관계"],
    )
    assert result["status"] == "PASS_STRUCTURE_HOLD_RELEASE"
    assert result["native_render"]["status"] == "HOLD_NATIVE_CAPTURE"
    assert result["release_eligible"] is False
    assert len(result["receipt_sha256"]) == 64


def test_missing_native_object_and_text_are_typed_failures(report):
    result = judge_document_quality(
        report,
        minimum_counts={"tables": 2},
        required_texts=["이 문서에 없는 근거"],
    )
    assert result["status"] == "FAIL_REQUIREMENTS"
    assert {row["code"] for row in result["issues"]} == {
        "MISSING_REQUIRED_OBJECT", "MISSING_REQUIRED_TEXT",
    }


def test_text_only_edit_preserves_all_required_native_objects(report, tmp_path):
    baseline = tmp_path / "baseline.hwpx"
    shutil.copy2(report, baseline)
    doc = build_document_map(report)
    target = next(p for p in doc["paragraphs"]
                  if p["text"] == "전압과 전류 사이의 관계를 관찰했다.")
    receipt = apply_text_edits_atomic(
        report, [{"op": "replace_paragraph_text", "target": target["locator"],
                 "text": "전압과 전류의 관계는 관찰됐으나 인과적 결론은 보류한다."}],
        expected_revision=1, current_revision=1,
        validator=validate_hwpx_package_light,
    )
    assert receipt["no_op"] is False
    result = judge_document_quality(
        report, baseline_path=baseline, minimum_counts={
            "tables": 1, "equations": 1, "pictures": 1, "footnotes": 1,
        }, required_texts=["인과적 결론은 보류한다."],
    )
    assert result["status"] == "PASS_STRUCTURE_HOLD_RELEASE"
    assert result["issues"] == []
    assert result["baseline_sha256"] != result["document_sha256"]
    assert result["release_eligible"] is False


def test_no_physical_artifact_does_not_get_quality_credit(tmp_path):
    path = tmp_path / "corrupt.hwpx"
    path.write_bytes(b"not a valid native package")
    result = judge_document_quality(path)
    assert result["status"] == "FAIL_PACKAGE"
    assert result["issues"][0]["code"] == "PACKAGE_INVALID"


@pytest.mark.parametrize("minimums", [
    {"tables": -1}, {"tables": True}, {"unverified_beauty_score": 100},
])
def test_invalid_expectations_are_rejected(report, minimums):
    with pytest.raises(ValueError):
        judge_document_quality(report, minimum_counts=minimums)
