"""P4.20 composite HWPX: preserve native objects through a revisioned text edit.

This is a structural roundtrip only. It does not claim Hancom render authority.
"""
from __future__ import annotations

import base64
import hashlib
import tempfile
import zipfile
from pathlib import Path

import pytest

from hwpx_mcp.document.p2_document import apply_text_edits_atomic, build_document_map
from hwpx_mcp.document.p28_tables import build_table_map
from hwpx_mcp.document.p29_objects import build_object_map
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p318_document_setup import build_document_setup_map
from hwpx_mcp.document.p320_annotation_apparatus import build_annotation_apparatus_map
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p334r2_package_validation import validate_hwpx_package_light

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlY4AAAAASUVORK5CYII="
)


def test_composite_report_native_features_survive_revisioned_edit():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "composite-research-report.hwpx"
        plan = {
            "preset": "academic-report",
            "blocks": [
                {"id": "title", "type": "title", "text": "전기회로 관측 보고서"},
                {"id": "intro", "type": "heading", "level": 1, "text": "1. 실험과 방법"},
                {"id": "method", "type": "paragraph", "text": "전압과 전류를 독립적으로 관찰한다."},
                {"id": "table", "type": "table", "rows": 2, "cols": 2,
                 "cells": [["전압", "전류"], ["3 V", "0.1 A"]], "caption": "표 1. 원자료"},
                {"id": "equation", "type": "equation", "latex": "V=IR", "caption": "식 1"},
                {"id": "image", "type": "picture",
                 "content_base64": base64.b64encode(PNG_1X1).decode("ascii"),
                 "image_format": "png", "width": 7200, "height": 7200, "caption": "그림 1"},
                {"id": "conclusion", "type": "heading", "level": 1, "text": "2. 해석"},
                {"id": "conclusion_text", "type": "paragraph", "text": "선형 관계를 확인하였다."},
            ],
            "annotations": [
                {"op": "add_footnote", "paragraph": "$block:method",
                 "text": "측정 조건은 동일하게 유지했다."},
            ],
        }
        receipt = compose_document_plan(
            path, plan, validator=validate_hwpx_package_light,
        )
        assert receipt["atomic_commit"] is True
        assert validate_hwpx_package_light(path)["valid"] is True
        before = build_document_map(path)
        assert len(build_table_map(path)["tables"]) == 1
        assert len(build_equation_map(path)["equations"]) == 1
        assert len(build_object_map(path)["pictures"]) == 1
        assert build_annotation_apparatus_map(path)["counts"]["footnotes"] == 1
        assert build_document_setup_map(path)["section_count"] >= 1
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        original = next(p for p in before["paragraphs"]
                        if p["text"].startswith("선형 관계를 확인하였다."))

        with pytest.raises(ValueError):
            apply_text_edits_atomic(
                path, [{"op": "replace_paragraph_text",
                        "target": original["locator"], "text": "검증한 관측 결과."}],
                expected_revision=1, current_revision=2,
                validator=validate_hwpx_package_light,
            )
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source_sha

        changed = apply_text_edits_atomic(
            path, [{"op": "replace_paragraph_text",
                    "target": original["locator"], "text": "선형성이 관측되며 인과 추론은 보류한다."}],
            expected_revision=2, current_revision=2,
            validator=validate_hwpx_package_light,
        )
        assert changed["no_op"] is False
        assert validate_hwpx_package_light(path)["valid"] is True
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert "Contents/section0.xml" in archive.namelist()
        after = build_document_map(path)
        assert after["structure_sha256"] == before["structure_sha256"]
        assert after["semantic_sha256"] != before["semantic_sha256"]
        edited = next(p for p in after["paragraphs"]
                      if p["locator"] == original["locator"])
        assert edited["text"] == "선형성이 관측되며 인과 추론은 보류한다."
        assert len(build_table_map(path)["tables"]) == 1
        assert len(build_equation_map(path)["equations"]) == 1
        assert len(build_object_map(path)["pictures"]) == 1
        assert build_annotation_apparatus_map(path)["counts"]["footnotes"] == 1
