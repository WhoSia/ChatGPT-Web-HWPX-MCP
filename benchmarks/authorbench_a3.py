from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p2_document import build_document_map
from p28_tables import build_table_map
from p321_document_composer import compose_document_plan
from p338_rich_builder import compile_rich_document_plan, evaluate_preview_readiness
from p339_design_intelligence import prepare_authoring_strategy
from p340_feedback_loop import (
    apply_document_design_repairs_atomic,
    content_aware_column_widths,
    diagnose_document_with_render,
    semantic_callout_block,
)

OUT_DIR = Path("artifacts")
RECEIPT = OUT_DIR / "authorbench-a3-receipt.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CASES = [
    {
        "id": "research-brief",
        "archetype": "RESEARCH_BRIEF",
        "preset": "polished-report",
        "title": "센서 교정 로그 이상 징후 검토 브리프",
        "subtitle": "관찰 가능한 실패와 재검증 경계를 중심으로 한 합성 연구 브리프",
        "summary": "핵심 판단: 이상 징후를 즉시 원인으로 해석하지 않고 원자료·변환·검증 단계를 분리해 재현 가능한 확인 경로를 유지한다.",
        "section1": "관찰과 질문",
        "body1": "서로 다른 계측 장치에서 생성된 로그는 정상 구간에서는 비슷해 보이지만 누락·지연·형식 변화가 섞이면 같은 수치 변화가 여러 원인에서 나타날 수 있다. 이 브리프는 원인 단정 대신 어떤 관찰을 추가해야 후보 설명을 분리할 수 있는지를 정리한다.",
        "section2": "검증 우선순위",
        "body2": "우선순위는 원자료 보존, 변환 단계의 입력·출력 해시, 독립 재실행, 그리고 실패 구간의 축소다. 각 단계는 이전 단계의 출력을 그대로 재사용할 수 있어야 하며, 자동 복구가 증거를 덮어쓰지 않도록 한다.",
        "table": [
            ["검증 지점", "관찰", "다음 행동"],
            ["원자료", "수집 직후 파일과 해시", "불변 보존"],
            ["변환", "입력·출력 쌍과 로그", "단계별 재실행"],
            ["검증", "독립 체크 결과", "불일치 국소화"],
        ],
        "conclusion": "결론은 특정 원인을 고르는 것이 아니라, 다음 관찰이 후보 설명을 실제로 갈라놓도록 검증 경로를 설계하는 것이다.",
    },
    {
        "id": "institutional-report",
        "archetype": "INSTITUTIONAL_REPORT",
        "preset": "institutional-report",
        "title": "공용장비 예약 운영 개선안",
        "subtitle": "예약 충돌·변경 이력·예외 처리의 가시성을 높이기 위한 합성 기관 보고서",
        "summary": "핵심 판단: 이용 규칙을 더 복잡하게 만드는 대신 예약 상태·변경 이유·예외 승인 근거가 같은 흐름에서 추적되도록 운영 표준을 단순화한다.",
        "section1": "현행 운영의 문제",
        "body1": "예약·변경·취소가 서로 다른 채널에서 처리되면 최종 일정은 맞더라도 어떤 판단으로 상태가 바뀌었는지 재구성하기 어렵다. 특히 예외 승인이 구두로 남으면 이후 동일 사례의 처리 기준이 흔들릴 수 있다.",
        "section2": "제안 운영 구조",
        "body2": "예약 상태와 변경 사유를 한 기록에 연결하고, 예외 승인은 최소 근거와 유효 기간을 함께 남긴다. 관리자 개입은 가능한 한 되돌릴 수 있게 설계하며, 사용자가 확인할 수 있는 현재 상태와 내부 운영 기록을 구분한다.",
        "table": [
            ["운영 항목", "기본 규칙", "예외 처리"],
            ["예약", "단일 일정 기록", "사유와 만료 시점 기록"],
            ["변경", "변경 전후 상태 보존", "관리자 승인 근거 연결"],
            ["취소", "취소 상태 명시", "복원 가능 여부 표시"],
        ],
        "conclusion": "개선안의 목표는 규칙 수를 늘리는 것이 아니라 현재 상태와 그 상태가 만들어진 과정을 함께 설명할 수 있게 하는 것이다.",
    },
    {
        "id": "academic-report",
        "archetype": "ACADEMIC_REPORT",
        "preset": "academic-report",
        "title": "합성 반복 실험의 재현성 분석 보고서",
        "subtitle": "측정 변동과 처리 파이프라인 변동을 분리하기 위한 합성 학술 보고서",
        "summary": "핵심 판단: 반복 간 차이를 단일 오차 항으로 합치지 않고 측정·전처리·요약 단계의 변동을 분리하여 어떤 결론이 어느 처리 선택에 민감한지 보고한다.",
        "section1": "분석 설계",
        "body1": "반복 실험의 차이는 측정 자체의 변동과 처리 과정의 변동이 함께 반영된 결과일 수 있다. 따라서 동일 원자료를 여러 처리 경로에 통과시키는 재현 실험과 독립 측정을 구분해 기록한다.",
        "section2": "보고 원칙",
        "body2": "요약 값만 제시하기보다 원자료 식별자, 처리 버전, 제외 규칙과 민감도 결과를 함께 남긴다. 결과가 특정 처리 규칙에만 의존할 경우 그 조건을 결론의 적용 범위로 명시한다.",
        "table": [
            ["분석 층", "고정하는 것", "변화시키는 것"],
            ["측정", "처리 파이프라인", "독립 반복"],
            ["전처리", "원자료", "처리 규칙"],
            ["요약", "전처리 출력", "집계 정의"],
        ],
        "conclusion": "재현성 평가는 같은 숫자가 반복되는지를 넘어, 어떤 처리 경로에서도 같은 해석 범위가 유지되는지 확인하는 과정으로 기록한다.",
    },
]


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finish(path: Path, h1_texts: list[str]) -> dict:
    doc_map = build_document_map(path)
    table_map = build_table_map(path)
    actions: list[dict] = []
    for table in table_map.get("tables", []):
        locator = str(table["locator"])
        cells = list(table.get("cells") or [])
        rows = int(table.get("rows") or 0)
        cols = int(table.get("cols") or 0)
        if rows == 1 and cols == 1:
            callout_text = str(cells[0].get("text") or "") if cells else ""
            nested = [
                str(p["locator"])
                for p in doc_map.get("paragraphs", [])
                if p.get("body_global_index") is None and str(p.get("text") or "") == callout_text
            ]
            actions.append({
                "action": "STYLE_SEMANTIC_CALLOUT",
                "status": "EXECUTABLE",
                "reason": "AUTHORING_SEMANTIC_ROLE",
                "operation": {"op": "style_semantic_callout", "table": locator, "paragraph_targets": nested},
            })
        else:
            actions.append({
                "action": "STYLE_ANALYTICAL_HEADER",
                "status": "EXECUTABLE",
                "reason": "AUTHORING_TABLE_ROLE",
                "operation": {"op": "style_table_header", "table": locator, "row": 0},
            })
            widths = content_aware_column_widths(table)
            if widths is not None:
                actions.append({
                    "action": "COMPILE_COLUMN_WIDTH_POLICY",
                    "status": "EXECUTABLE",
                    "reason": "AUTHORING_DENSITY_POLICY",
                    "operation": {"op": "rebalance_table_columns", "table": locator, "widths": widths["widths"]},
                })
        actions.append({
            "action": "ALLOCATE_TABLE_PADDING",
            "status": "EXECUTABLE",
            "reason": "AUTHORING_DENSITY_POLICY",
            "operation": {"op": "set_table_padding", "table": locator, "left": 560, "right": 560, "top": 420, "bottom": 420},
        })

    long_nested = [
        str(p["locator"])
        for p in doc_map.get("paragraphs", [])
        if p.get("body_global_index") is None and len(str(p.get("text") or "").strip()) >= 18
    ]
    if long_nested:
        actions.append({
            "action": "ALIGN_PROSE_LIKE_TABLE_TEXT",
            "status": "EXECUTABLE",
            "reason": "AUTHORING_READING_GEOMETRY",
            "operation": {"op": "align_nested_table_paragraphs", "targets": long_nested, "alignment": "LEFT"},
        })

    heading_targets = [
        str(p["locator"])
        for p in doc_map.get("paragraphs", [])
        if p.get("body_global_index") is not None and str(p.get("text") or "") in h1_texts
    ]
    if heading_targets:
        actions.append({
            "action": "COMPILE_SECTION_SEPARATORS",
            "status": "EXECUTABLE",
            "reason": "AUTHORING_HIERARCHY_POLICY",
            "operation": {"op": "style_section_headings", "targets": heading_targets},
        })
    plan = {
        "schema": "authorbench/a3/prospective-semantic-finish/v1",
        "repair_plan_sha256": hashlib.sha256(
            json.dumps(actions, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "actions": actions,
    }
    return apply_document_design_repairs_atomic(path, plan, expected_revision=1, current_revision=1)


def build_case(case: dict) -> dict:
    output = OUT_DIR / f"authorbench-a3-{case['id']}.hwpx"
    strategy = prepare_authoring_strategy({
        "archetype": case["archetype"],
        "semantic_outline": [
            "TITLE", "SUBTITLE", "EXECUTIVE_SUMMARY", "KEY_JUDGMENT",
            "SECTION", "ANALYTICAL_TABLE", "SECTION", "CONCLUSION",
        ],
    })
    callout = semantic_callout_block(case["summary"], block_id=f"{case['id']}-callout")
    h1_texts = ["Executive summary", case["section1"], case["section2"], "결론"]
    rich_plan = {
        "preset": case["preset"],
        "sections": [{
            "page": {
                "paper_size": "A4",
                "orientation": "PORTRAIT",
                "margin_left_mm": 22 if case["archetype"] == "RESEARCH_BRIEF" else 20,
                "margin_right_mm": 22 if case["archetype"] == "RESEARCH_BRIEF" else 20,
                "margin_top_mm": 20,
                "margin_bottom_mm": 20,
            },
            "footer": f"AUTHORBENCH A3 · {case['archetype']}",
            "page_numbers": True,
            "blocks": [
                {"id": "title", "type": "title", "text": case["title"]},
                {"id": "subtitle", "type": "paragraph", "text": case["subtitle"], "run_format": {"size": 10}, "paragraph_format": {"spacing_after_pt": 14}},
                {"id": "summary-h", "type": "heading", "level": 1, "text": "Executive summary"},
                callout,
                {"id": "s1-h", "type": "heading", "level": 1, "text": case["section1"]},
                {"id": "s1-p", "type": "paragraph", "text": case["body1"]},
                {"id": "matrix-h", "type": "heading", "level": 2, "text": "검토 매트릭스"},
                {"id": "matrix", "type": "table", "rows": 4, "cols": 3, "cells": case["table"], "first_row_header": True},
                {"id": "s2-h", "type": "heading", "level": 1, "text": case["section2"]},
                {"id": "s2-p", "type": "paragraph", "text": case["body2"]},
                {"id": "conclusion-h", "type": "heading", "level": 1, "text": "결론"},
                {"id": "conclusion", "type": "paragraph", "text": case["conclusion"], "run_format": {"bold": True}},
                {"id": "note", "type": "paragraph", "text": "이 문서는 HWPX 저작 및 페이지 구성 일반화를 평가하기 위한 합성 시나리오이며 외부 사실 주장을 포함하지 않는다.", "run_format": {"size": 9}},
            ],
        }],
    }
    compiled = compile_rich_document_plan(rich_plan)
    composer = compose_document_plan(output, compiled["plan"])
    finish = _finish(output, h1_texts)
    preview = evaluate_preview_readiness(output, mode="POLISHED_REPORT")
    diagnostic = diagnose_document_with_render(output, mode="POLISHED_REPORT")
    doc_map = build_document_map(output)
    table_map = build_table_map(output)
    return {
        "id": case["id"],
        "archetype": case["archetype"],
        "preset": case["preset"],
        "title": case["title"],
        "generated_file": str(output),
        "sha256": _sha_file(output),
        "bytes": output.stat().st_size,
        "paragraph_count": len(doc_map.get("paragraphs", [])),
        "table_count": len(table_map.get("tables", [])),
        "preview_verdict": preview["verdict"],
        "preview_render_status": preview["render_status"],
        "static_diagnostic_verdict": diagnostic["verdict"],
        "static_finding_codes": [x["code"] for x in diagnostic.get("findings", [])],
        "static_high_count": sum(1 for x in diagnostic.get("findings", []) if x.get("severity") == "HIGH"),
        "strategy_sha256": strategy["strategy_sha256"],
        "compile_sha256": compiled["compile_sha256"],
        "composition_sha256": composer["composition_sha256"],
        "semantic_finish_action_count": finish["action_count"],
        "semantic_finish_receipt_sha256": finish["repair_receipt_sha256"],
        "semantic_finish_changed_text": finish["semantic_changed"],
        "semantic_finish_changed_structure": finish["structure_changed"],
        "page_composition_authority": "PENDING_NATIVE_RENDER",
    }


def main() -> int:
    results = [build_case(case) for case in CASES]
    payload = {
        "schema": "authorbench/a3/p341/v1",
        "phase": "P3.41",
        "benchmark": "AUTHORBENCH_A3_CROSS_ARCHETYPE",
        "cases": results,
        "case_count": len(results),
        "archetypes": [x["archetype"] for x in results],
        "freshness_boundary": (
            "A3 cases are first completed only after P3.41 page-composition implementation exists. "
            "No A3 diagnosis is used to choose first-pass content or semantic-role finishing."
        ),
        "content_basis": "three synthetic scenarios; no external factual claims",
        "render_world_contact": "PENDING_EXTERNAL_HANCOM_WORLD_CONTACT",
        "human_review": "PENDING_AFTER_NATIVE_RENDER",
    }
    RECEIPT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
