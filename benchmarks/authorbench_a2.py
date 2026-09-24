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

OUT = Path("artifacts/authorbench-a2-research-data-infrastructure.hwpx")
RECEIPT = Path("artifacts/authorbench-a2-receipt.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

TITLE = "연구실 계측 데이터 파이프라인 개편안"
H1_TEXTS = [
    "Executive summary",
    "1. 문제와 설계 목표",
    "2. 제안 아키텍처",
    "3. 전환 계획과 의사결정",
]

strategy = prepare_authoring_strategy({
    "archetype": "POLISHED_REPORT",
    "semantic_outline": [
        "TITLE",
        "SUBTITLE",
        "EXECUTIVE_SUMMARY",
        "KEY_JUDGMENT",
        "SECTION",
        "ANALYTICAL_TABLE",
        "SECTION",
        "ANALYTICAL_TABLE",
        "SECTION",
        "ANALYTICAL_TABLE",
        "CONCLUSION",
    ],
})

callout = semantic_callout_block(
    "핵심 판단: 검증 가능성을 우선한다.",
    block_id="summary-callout",
    role="KEY_JUDGMENT",
)

rich_plan = {
    "preset": "polished-report",
    "sections": [
        {
            "page": {
                "paper_size": "A4",
                "orientation": "PORTRAIT",
                "margin_left_mm": 22,
                "margin_right_mm": 22,
                "margin_top_mm": 22,
                "margin_bottom_mm": 20,
            },
            "footer": "AUTHORBENCH A2 · RESEARCH INFRASTRUCTURE",
            "page_numbers": True,
            "blocks": [
                {
                    "id": "cover-kicker",
                    "type": "paragraph",
                    "text": "AUTHORBENCH A2 · ENGINEERING DECISION BRIEF",
                    "run_format": {"size": 9, "bold": True},
                    "paragraph_format": {"spacing_after_pt": 14},
                },
                {
                    "id": "cover-title",
                    "type": "title",
                    "text": TITLE,
                    "run_format": {"size": 26, "bold": True},
                    "paragraph_format": {"spacing_after_pt": 12, "keep_with_next": True},
                },
                {
                    "id": "cover-subtitle",
                    "type": "paragraph",
                    "text": "수집·검증·재현성·운영 부담을 함께 다루는 연구 인프라 설계",
                    "run_format": {"size": 13},
                    "paragraph_format": {"spacing_after_pt": 20},
                },
                {
                    "id": "cover-meta",
                    "type": "paragraph",
                    "text": "2026.09.24  |  Synthetic benchmark scenario",
                    "run_format": {"size": 9},
                    "paragraph_format": {"spacing_after_pt": 18},
                },
                {"id": "summary-heading", "type": "heading", "level": 1, "text": "Executive summary"},
                callout,
                {
                    "id": "summary-p",
                    "type": "paragraph",
                    "text": "이 벤치마크 시나리오는 여러 계측 장치의 데이터를 한 경로로 모으면서도 원자료 보존, 변환 이력, 검증 실패의 격리, 재실행 가능성을 잃지 않는 파이프라인을 설계한다.",
                },
                {"id": "summary-l1", "type": "list_item", "text": "원자료는 수정하지 않고 수집 시점의 해시와 함께 보존한다."},
                {"id": "summary-l2", "type": "list_item", "text": "변환 단계마다 입력·출력·검증 결과를 연결해 원인을 추적한다."},
                {"id": "summary-l3", "type": "list_item", "text": "자동 복구보다 실패 상태를 명시하고 재실행 경계를 좁힌다."},
            ],
        },
        {
            "page": {
                "paper_size": "A4",
                "orientation": "PORTRAIT",
                "margin_left_mm": 22,
                "margin_right_mm": 22,
                "margin_top_mm": 20,
                "margin_bottom_mm": 20,
            },
            "header": TITLE,
            "footer": "AUTHORBENCH A2",
            "page_numbers": True,
            "blocks": [
                {"id": "s2-title", "type": "heading", "level": 1, "text": "1. 문제와 설계 목표"},
                {
                    "id": "s2-intro",
                    "type": "paragraph",
                    "text": "기존 수집 경로는 장치별 스크립트가 서로 다른 파일 구조와 오류 처리를 사용한다. 정상 실행에서는 문제가 드러나지 않지만, 장치 교체나 네트워크 지연이 발생하면 어느 단계에서 값이 달라졌는지 재구성하기 어렵다.",
                },
                {"id": "s2-h1", "type": "heading", "level": 2, "text": "설계 목표"},
                {
                    "id": "s2-p1",
                    "type": "paragraph",
                    "text": "새 구조의 목표는 더 많은 기능을 한 서비스에 넣는 것이 아니다. 수집, 정규화, 검증, 저장, 분석 전달의 책임을 분리하고 각 경계에서 실패를 관찰할 수 있게 만드는 것이다.",
                },
                {
                    "id": "s2-table",
                    "type": "table",
                    "rows": 6,
                    "cols": 4,
                    "first_row_header": True,
                    "cells": [
                        ["영역", "현재 병목", "영향", "설계 응답"],
                        ["수집", "장치별 형식 차이", "입력 편차", "원본 어댑터 분리"],
                        ["시각", "시간 기준 혼재", "순서 불명", "UTC 기준 고정"],
                        ["검증", "오류 즉시 덮어씀", "원인 소실", "격리 큐 사용"],
                        ["저장", "원본과 파생 혼합", "추적 곤란", "계층 저장"],
                        ["재실행", "전체 작업 반복", "비용 증가", "구간 재실행"],
                    ],
                    "table_format": {"border_color": "AEB7C2", "repeat_header": True, "page_break": "CELL"},
                },
                {
                    "id": "s2-close",
                    "type": "paragraph",
                    "text": "따라서 성공 기준은 평균 처리 속도 하나가 아니라 원자료 보존, 실패 위치 식별, 동일 입력의 재실행 일치, 운영자가 이해할 수 있는 상태 표현을 함께 만족하는가로 정의한다.",
                },
            ],
        },
        {
            "page": {
                "paper_size": "A4",
                "orientation": "PORTRAIT",
                "margin_left_mm": 22,
                "margin_right_mm": 22,
                "margin_top_mm": 20,
                "margin_bottom_mm": 20,
            },
            "header": TITLE,
            "footer": "AUTHORBENCH A2",
            "page_numbers": True,
            "blocks": [
                {"id": "s3-title", "type": "heading", "level": 1, "text": "2. 제안 아키텍처"},
                {
                    "id": "s3-intro",
                    "type": "paragraph",
                    "text": "파이프라인은 각 단계가 이전 단계의 산출물을 덮어쓰지 않는 append-oriented 구조를 사용한다. 모든 산출물은 입력 식별자와 변환 버전을 남기며, 검증 실패는 정상 데이터와 같은 경로로 흘려보내지 않는다.",
                },
                {"id": "s3-h1", "type": "heading", "level": 2, "text": "처리 단계"},
                {
                    "id": "s3-table",
                    "type": "table",
                    "rows": 6,
                    "cols": 4,
                    "first_row_header": True,
                    "cells": [
                        ["단계", "입력", "핵심 처리", "검증"],
                        ["1. 수집", "장치 패킷", "원본 봉인", "해시 확인"],
                        ["2. 정규화", "원본 레코드", "스키마 변환", "필드 검사"],
                        ["3. 시간 정렬", "정규 레코드", "기준시각 적용", "역전 탐지"],
                        ["4. 품질 검사", "정렬 레코드", "범위·결측 검사", "격리 판정"],
                        ["5. 전달", "승인 레코드", "분석 저장", "수량 대조"],
                    ],
                    "table_format": {"border_color": "AEB7C2", "repeat_header": True, "page_break": "CELL"},
                },
                {"id": "s3-h2", "type": "heading", "level": 2, "text": "경계 조건"},
                {"id": "s3-l1", "type": "list_item", "text": "장치 연결이 끊겨도 이미 수집한 원본은 삭제하지 않는다."},
                {"id": "s3-l2", "type": "list_item", "text": "스키마 변경은 새 버전으로 기록하고 과거 결과를 재작성하지 않는다."},
                {"id": "s3-l3", "type": "list_item", "text": "검증 규칙이 바뀌면 규칙 버전과 재판정 범위를 함께 남긴다."},
                {
                    "id": "s3-close",
                    "type": "paragraph",
                    "text": "이 구조는 오류를 없애기보다 오류가 어디에서 생겼고 어떤 데이터에 영향을 주었는지를 제한된 범위에서 재구성할 수 있게 만드는 데 초점을 둔다.",
                },
            ],
        },
        {
            "page": {
                "paper_size": "A4",
                "orientation": "PORTRAIT",
                "margin_left_mm": 22,
                "margin_right_mm": 22,
                "margin_top_mm": 20,
                "margin_bottom_mm": 20,
            },
            "header": TITLE,
            "footer": "AUTHORBENCH A2",
            "page_numbers": True,
            "blocks": [
                {"id": "s4-title", "type": "heading", "level": 1, "text": "3. 전환 계획과 의사결정"},
                {
                    "id": "s4-intro",
                    "type": "paragraph",
                    "text": "전환은 기존 경로를 즉시 폐기하지 않고 동일 입력을 구·신 경로에 병렬로 흘려 차이를 관찰하는 방식으로 진행한다. 새 경로가 일정 기간 일치성을 보인 뒤에만 분석 소비자를 순차적으로 이동한다.",
                },
                {"id": "s4-h1", "type": "heading", "level": 2, "text": "단계별 게이트"},
                {
                    "id": "s4-table",
                    "type": "table",
                    "rows": 5,
                    "cols": 4,
                    "first_row_header": True,
                    "cells": [
                        ["단계", "완료 기준", "회귀 신호", "중단 조건"],
                        ["Shadow", "원본 수량 일치", "누락 발생", "해시 불일치"],
                        ["Replay", "재실행 일치", "결과 흔들림", "버전 불명"],
                        ["Pilot", "분석 결과 일치", "지연 급증", "검증 우회"],
                        ["Cutover", "운영 승인", "격리 증가", "원인 미상"],
                    ],
                    "table_format": {"border_color": "AEB7C2", "repeat_header": True, "page_break": "CELL"},
                },
                {"id": "s4-h2", "type": "heading", "level": 2, "text": "최종 권고"},
                {
                    "id": "s4-conclusion",
                    "type": "paragraph",
                    "text": "개편의 핵심 가치는 더 복잡한 자동화가 아니라 실패를 숨기지 않는 구조다. 원자료를 보존하고, 단계별 검증을 분리하며, 재실행 범위를 작게 유지하면 장치와 분석 요구가 바뀌어도 변경의 영향을 추적할 수 있다. 따라서 전환은 기능 수보다 관찰 가능성과 재현 가능성을 우선해 진행한다.",
                    "run_format": {"bold": True},
                },
                {"id": "s4-h3", "type": "heading", "level": 2, "text": "벤치마크 주석"},
                {
                    "id": "s4-note",
                    "type": "paragraph",
                    "text": "이 문서는 실제 기관의 운영 자료가 아니라 HWPX 저작 품질을 평가하기 위해 만든 합성 공학 시나리오다. 수치 성능이나 특정 장치에 대한 외부 사실 주장은 포함하지 않는다.",
                    "run_format": {"size": 9},
                },
            ],
        },
    ],
}

compiled = compile_rich_document_plan(rich_plan)
composer_receipt = compose_document_plan(OUT, compiled["plan"])

# One-pass semantic finishing is part of A2 authoring, not a diagnosis-driven repair.
# The first completed A2 artifact is sealed only after these declared design-role
# transforms have been compiled to native primitives.
doc_map_before_finish = build_document_map(OUT)
table_map_before_finish = build_table_map(OUT)
finish_actions: list[dict] = []

for table in table_map_before_finish.get("tables", []):
    locator = str(table["locator"])
    cells = list(table.get("cells") or [])
    if int(table.get("rows") or 0) == 1 and int(table.get("cols") or 0) == 1:
        callout_text = str(cells[0].get("text") or "") if cells else ""
        paragraph_targets = [
            str(p["locator"])
            for p in doc_map_before_finish.get("paragraphs", [])
            if p.get("body_global_index") is None and str(p.get("text") or "") == callout_text
        ]
        finish_actions.append({
            "action": "STYLE_SEMANTIC_CALLOUT",
            "status": "EXECUTABLE",
            "reason": "AUTHORING_SEMANTIC_ROLE",
            "operation": {
                "op": "style_semantic_callout",
                "table": locator,
                "paragraph_targets": paragraph_targets,
            },
        })
    else:
        finish_actions.append({
            "action": "STYLE_ANALYTICAL_HEADER",
            "status": "EXECUTABLE",
            "reason": "AUTHORING_TABLE_ROLE",
            "operation": {
                "op": "style_table_header",
                "table": locator,
                "row": 0,
            },
        })
        width_plan = content_aware_column_widths(table)
        if width_plan is not None:
            finish_actions.append({
                "action": "COMPILE_COLUMN_WIDTH_POLICY",
                "status": "EXECUTABLE",
                "reason": "AUTHORING_DENSITY_POLICY",
                "operation": {
                    "op": "rebalance_table_columns",
                    "table": locator,
                    "widths": width_plan["widths"],
                },
                "policy_evidence": width_plan,
            })

    finish_actions.append({
        "action": "ALLOCATE_TABLE_PADDING",
        "status": "EXECUTABLE",
        "reason": "AUTHORING_DENSITY_POLICY",
        "operation": {
            "op": "set_table_padding",
            "table": locator,
            "left": 560,
            "right": 560,
            "top": 420,
            "bottom": 420,
        },
    })

long_nested = [
    str(p["locator"])
    for p in doc_map_before_finish.get("paragraphs", [])
    if p.get("body_global_index") is None and len(str(p.get("text") or "").strip()) >= 18
]
if long_nested:
    finish_actions.append({
        "action": "ALIGN_PROSE_LIKE_TABLE_TEXT",
        "status": "EXECUTABLE",
        "reason": "AUTHORING_READING_GEOMETRY",
        "operation": {
            "op": "align_nested_table_paragraphs",
            "targets": long_nested,
            "alignment": "LEFT",
        },
    })

heading_targets = [
    str(p["locator"])
    for p in doc_map_before_finish.get("paragraphs", [])
    if p.get("body_global_index") is not None and str(p.get("text") or "") in H1_TEXTS
]
if heading_targets:
    finish_actions.append({
        "action": "COMPILE_SECTION_SEPARATORS",
        "status": "EXECUTABLE",
        "reason": "AUTHORING_HIERARCHY_POLICY",
        "operation": {"op": "style_section_headings", "targets": heading_targets},
    })

finish_plan = {
    "schema": "authorbench/a2/semantic-authoring-finish/v1",
    "repair_plan_sha256": hashlib.sha256(
        json.dumps(finish_actions, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest(),
    "actions": finish_actions,
}
finish_receipt = apply_document_design_repairs_atomic(
    OUT,
    finish_plan,
    expected_revision=1,
    current_revision=1,
)

preview = evaluate_preview_readiness(OUT, mode="POLISHED_REPORT")
diagnostic = diagnose_document_with_render(OUT, mode="POLISHED_REPORT")
doc_map = build_document_map(OUT)
table_map = build_table_map(OUT)

if preview["verdict"] not in {"PASS", "PASS_WITH_WARNINGS"}:
    raise RuntimeError(f"A2 preview gate failed: {preview['verdict']}")
if finish_receipt["semantic_changed"] or finish_receipt["structure_changed"]:
    raise RuntimeError("A2 semantic finishing changed content or paragraph structure")

sha256 = hashlib.sha256(OUT.read_bytes()).hexdigest()
payload = {
    "schema": "authorbench/a2/v0.1",
    "phase": "P3.40",
    "title": TITLE,
    "generated_file": str(OUT),
    "sha256": sha256,
    "bytes": OUT.stat().st_size,
    "section_count": compiled["section_count"],
    "block_count": compiled["block_count"],
    "paragraph_count": len(doc_map.get("paragraphs", [])),
    "table_count": len(table_map.get("tables", [])),
    "preview_verdict": preview["verdict"],
    "preview_render_status": preview["render_status"],
    "diagnostic_verdict": diagnostic["verdict"],
    "finding_count": diagnostic["finding_count"],
    "finding_codes": [x["code"] for x in diagnostic["findings"]],
    "strategy_sha256": strategy["strategy_sha256"],
    "compile_sha256": compiled["compile_sha256"],
    "semantic_finish_action_count": len(finish_actions),
    "semantic_finish_receipt_sha256": finish_receipt["repair_receipt_sha256"],
    "semantic_finish_changed_text": finish_receipt["semantic_changed"],
    "semantic_finish_changed_structure": finish_receipt["structure_changed"],
    "composer_receipt": {
        "preset": composer_receipt.get("preset"),
        "output_sha256": composer_receipt.get("output_sha256"),
    },
    "benchmark_intent": (
        "fresh first completed artifact after P3.40 implementation; synthetic engineering "
        "decision brief testing cross-domain document-design generalization"
    ),
    "freshness_boundary": (
        "No A2 design diagnosis or A1 comparison was used before the completed A2 artifact was sealed. "
        "Semantic finishing was compiled prospectively from declared authoring roles."
    ),
    "content_basis": "synthetic benchmark scenario; no external factual claims required",
    "render_authority": "NOT_RENDERED",
    "human_review_status": "PENDING",
}
RECEIPT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
