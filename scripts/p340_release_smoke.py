from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p2_document import build_document_map
from p321_document_composer import compose_document_plan
from p339_design_intelligence import prepare_authoring_strategy
from p340_feedback_loop import (
    apply_document_design_repairs_atomic,
    apply_nested_paragraph_alignment_atomic,
    compare_design_diagnostics,
    diagnose_document_with_render,
    plan_executable_editorial_repairs,
    rendered_feedback_loop_contract,
)

contract = rendered_feedback_loop_contract()
assert contract["phase"] == "P3.40"
assert "RENDER_AGAIN" in contract["closed_loop"]

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

plan = {
    "preset": "polished-report",
    "blocks": [
        {"id": "title", "type": "title", "text": "P3.40 Rendered Feedback Loop"},
        {"id": "heading", "type": "heading", "level": 1, "text": "Evidence"},
        {
            "id": "table",
            "type": "table",
            "rows": 3,
            "cols": 3,
            "first_row_header": True,
            "cells": [
                ["항목", "설명", "검증"],
                ["기회", "긴 설명 셀은 대칭보다 읽기 흐름을 우선해 좌측 정렬합니다.", "원문 대조"],
                ["위험", "밀도 높은 표는 글자 축소보다 여백과 열 폭을 먼저 조정합니다.", "독립 검증"],
            ],
        },
    ],
}

with tempfile.TemporaryDirectory(prefix="p340-") as tmp:
    path = Path(tmp) / "p340.hwpx"
    compose_document_plan(path, plan)
    nested = next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if "긴 설명 셀" in item["text"]
    )
    apply_nested_paragraph_alignment_atomic(path, [nested], alignment="CENTER")

    before = diagnose_document_with_render(
        path,
        render_observation={
            "authority": "EXTERNAL_RENDER_OBSERVATION",
            "findings": [{
                "code": "PAGE_VERTICAL_BALANCE_WEAK",
                "severity": "LOW",
                "scope": "PAGE_1",
                "evidence": {"source": "release-smoke-fixture"},
                "recommendation": "Retain as non-native render evidence only.",
            }],
        },
    )
    before_codes = {x["code"] for x in before["findings"]}
    assert "TABLE_LONG_TEXT_CENTERED" in before_codes
    assert "TABLE_CELL_PADDING_TIGHT" in before_codes

    repair = plan_executable_editorial_repairs(path, before, strategy=strategy)
    assert repair["executable_count"] >= 2
    assert repair["capability_gap_count"] == 0

    execution = apply_document_design_repairs_atomic(
        path,
        repair,
        expected_revision=1,
        current_revision=1,
    )
    assert execution["semantic_changed"] is False
    assert execution["structure_changed"] is False

    after = diagnose_document_with_render(path)
    after_codes = {x["code"] for x in after["findings"]}
    assert "TABLE_LONG_TEXT_CENTERED" not in after_codes
    assert "TABLE_CELL_PADDING_TIGHT" not in after_codes

    comparison = compare_design_diagnostics(before, after)
    assert comparison["high_severity_nonincrease"]
    assert comparison["native_rerender_verified"] is False

print(json.dumps({
    "status": "PASS",
    "phase": "P3.40",
    "before_findings": before["finding_count"],
    "after_findings": after["finding_count"],
    "executable_repairs": repair["executable_count"],
    "native_rerender_verified": comparison["native_rerender_verified"],
    "render_claim": comparison["render_claim"],
}, ensure_ascii=False))
