from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p321_document_composer import compose_document_plan
from p338_rich_builder import compile_rich_document_plan
from p339_design_intelligence import (
    diagnose_document_design,
    plan_design_repairs,
    prepare_authoring_strategy,
)

strategy = prepare_authoring_strategy({
    "archetype": "POLISHED_REPORT",
    "semantic_outline": [
        "TITLE",
        "EXECUTIVE_SUMMARY",
        "KEY_JUDGMENT",
        "SECTION",
        "ANALYTICAL_TABLE",
        "CONCLUSION",
        "REFERENCES",
    ],
})

rich = {
    "preset": "polished-report",
    "sections": [{
        "page": {"paper_size": "A4", "orientation": "PORTRAIT"},
        "blocks": [
            {"id": "title", "type": "title", "text": "P3.39 Design Intelligence"},
            {"id": "heading", "type": "heading", "level": 1, "text": "Analytical table"},
            {
                "id": "table",
                "type": "table",
                "rows": 4,
                "cols": 3,
                "first_row_header": True,
                "cells": [
                    ["항목", "분석", "통제"],
                    ["기회", "긴 설명이 들어가는 셀은 시각적 대칭보다 읽기 흐름이 우선입니다.", "검증"],
                    ["위험", "두 번째 장문 셀도 충분한 padding과 읽기 친화적 정렬이 필요합니다.", "추적"],
                    ["원칙", "문서 디자인은 의미적 역할과 시각적 처리가 일치해야 합니다.", "재검토"],
                ],
            },
        ],
    }],
}
compiled = compile_rich_document_plan(rich)

with tempfile.TemporaryDirectory(prefix="p339-") as tmp:
    path = Path(tmp) / "p339.hwpx"
    compose_document_plan(path, compiled["plan"])
    diagnostic = diagnose_document_design(
        path,
        human_feedback=[{
            "code": "A1_HUMAN_REVIEW_PRESENT",
            "severity": "INFO",
            "note": "A1 is retained as a frozen human-review failure specimen.",
        }],
    )
    repair = plan_design_repairs(diagnostic, strategy=strategy)
    codes = {item["code"] for item in diagnostic["findings"]}
    assert "TABLE_CELL_PADDING_TIGHT" in codes
    assert diagnostic["aesthetic_score"] is None
    assert repair["executable_count"] >= 1
    assert strategy["warnings"] == []

print(json.dumps({
    "status": "PASS",
    "phase": "P3.39",
    "diagnostic_verdict": diagnostic["verdict"],
    "finding_count": diagnostic["finding_count"],
    "repair_actions": len(repair["actions"]),
    "aesthetic_score": diagnostic["aesthetic_score"],
}, ensure_ascii=False))
