from __future__ import annotations

import hashlib
import json
from pathlib import Path

from p2_document import build_document_map
from p28_tables import build_table_map
from p321_document_composer import compose_document_plan
from p338_rich_builder import compile_rich_document_plan, evaluate_preview_readiness

OUT = Path("artifacts/authorbench-a1-generative-ai-science.hwpx")
RECEIPT = Path("artifacts/authorbench-a1-receipt.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

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
            "footer": "AUTHORBENCH A1 · 생성형 AI와 과학 연구",
            "page_numbers": True,
            "blocks": [
                {
                    "id": "cover-kicker",
                    "type": "paragraph",
                    "text": "AUTHORBENCH A1 · TECHNOLOGY & SCIENCE",
                    "run_format": {"size": 9, "bold": True},
                    "paragraph_format": {"spacing_after_pt": 14},
                },
                {
                    "id": "cover-title",
                    "type": "title",
                    "text": "생성형 AI가 과학 연구에 미치는 영향",
                    "run_format": {"size": 26, "bold": True},
                    "paragraph_format": {"spacing_after_pt": 12, "keep_with_next": True},
                },
                {
                    "id": "cover-subtitle",
                    "type": "paragraph",
                    "text": "생산성의 확대와 연구 다양성·검증·거버넌스의 새로운 긴장",
                    "run_format": {"size": 13},
                    "paragraph_format": {"spacing_after_pt": 22},
                },
                {
                    "id": "cover-meta",
                    "type": "paragraph",
                    "text": "2026.09.24  |  Research Brief",
                    "run_format": {"size": 9},
                    "paragraph_format": {"spacing_after_pt": 18},
                },
                {
                    "id": "summary-heading",
                    "type": "heading",
                    "level": 1,
                    "text": "Executive summary",
                },
                {
                    "id": "summary-box",
                    "type": "table",
                    "rows": 4,
                    "cols": 2,
                    "cells": [
                        ["핵심 판단", "생성형 AI는 과학자의 탐색·요약·코딩·초안 작성 속도를 높일 수 있지만, 그 자체가 검증된 과학적 이해를 보장하지는 않는다."],
                        ["기회", "문헌 탐색, 가설 정교화, 코드 작성, 데이터 설명, 연구 커뮤니케이션에서 반복 업무를 압축한다."],
                        ["위험", "환각·근거 없는 확신, 데이터 유출, 동일한 데이터가 풍부한 문제로 연구가 쏠리는 현상이 누적될 수 있다."],
                        ["운영 원칙", "AI를 ‘대체 연구자’가 아니라 검증 가능한 보조 계층으로 두고, 출처·데이터·모델 사용 내역을 추적 가능하게 남겨야 한다."],
                    ],
                    "table_format": {"border_color": "B8C0CC", "page_break": "CELL"},
                },
                {
                    "id": "summary-close",
                    "type": "paragraph",
                    "text": "결론적으로 연구 경쟁력은 AI 사용 여부보다 ‘어디까지 위임하고 어디에서 사람이 책임질지’를 설계하는 능력에 더 크게 좌우될 가능성이 높다.",
                    "run_format": {"size": 11, "bold": True},
                    "paragraph_format": {"spacing_before_pt": 12, "spacing_after_pt": 4},
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
            "header": "생성형 AI가 과학 연구에 미치는 영향",
            "footer": "AUTHORBENCH A1",
            "page_numbers": True,
            "blocks": [
                {"id": "s2-title", "type": "heading", "level": 1, "text": "1. 연구 과정은 어떻게 달라지는가"},
                {
                    "id": "s2-intro",
                    "type": "paragraph",
                    "text": "대규모 언어모델은 연구의 한 단계만 자동화하는 도구라기보다, 문헌 탐색에서 실험 설계·코드 작성·결과 설명·원고 작성까지 여러 단계 사이를 연결하는 범용 인터페이스로 확장되고 있다. 2025년 npj Artificial Intelligence의 리뷰는 LLM이 가설 설정부터 발견까지 과학적 방법의 여러 단계에 통합될 수 있다고 정리하면서도, 인간의 과학적 목표와 명시적 평가 지표에 맞춰 운용되어야 한다고 강조한다.",
                },
                {"id": "s2-h1", "type": "heading", "level": 2, "text": "반복 작업의 압축"},
                {
                    "id": "s2-p1",
                    "type": "paragraph",
                    "text": "연구자는 검색식을 다듬고, 관련 논문을 묶어 읽고, 분석 코드를 작성하고, 그래프 설명과 초안을 만드는 데 상당한 시간을 쓴다. 생성형 AI는 이 가운데 형식화가 쉬운 부분을 빠르게 처리해 연구자가 문제 정의와 실험 판단에 더 많은 시간을 배분하도록 도울 수 있다. 특히 새로운 분야에 진입할 때 용어와 방법을 빠르게 정리하거나, 코드와 수식의 첫 버전을 만드는 용도는 비용 대비 효율이 높다.",
                },
                {"id": "s2-h2", "type": "heading", "level": 2, "text": "개인 생산성과 집단 과학의 역설"},
                {
                    "id": "s2-p2",
                    "type": "paragraph",
                    "text": "2026년 Nature에 실린 대규모 관찰 연구는 4,130만 편의 자연과학 논문을 분석해 AI 활용 연구자에게 높은 출판·인용 성과가 연관되어 있음을 보고했다. 다만 같은 분석에서 과학 전체가 다루는 주제 범위는 좁아지고 연구자 간 후속 상호작용도 감소하는 경향이 나타났다. 이 결과는 AI가 개인의 생산성을 높이는 동시에, 데이터가 풍부하고 자동화하기 쉬운 문제로 관심을 집중시킬 수 있다는 긴장을 보여준다. 이는 인과효과가 확정되었다는 뜻이 아니라, AI 도입을 평가할 때 개인 성과와 지식 생태계 수준을 구분해야 한다는 신호다.",
                },
                {
                    "id": "s2-table",
                    "type": "table",
                    "rows": 6,
                    "cols": 4,
                    "first_row_header": True,
                    "cells": [
                        ["연구 단계", "생성형 AI의 역할", "기대 효익", "필수 통제"],
                        ["문헌 탐색", "질문 확장·요약·검색어 생성", "탐색 속도 향상", "원문 대조·인용 확인"],
                        ["가설 설계", "대안 가설·변수 제안", "탐색 공간 확대", "새로움·검증 가능성 판단"],
                        ["분석/코딩", "코드 초안·디버깅·설명", "반복 작업 단축", "테스트·재현성 검사"],
                        ["결과 해석", "패턴 설명·반례 제시", "해석 후보 확대", "통계·도메인 검증"],
                        ["논문 작성", "구조화·문장 개선·번역", "커뮤니케이션 비용 절감", "저자 책임·AI 사용 공개"],
                    ],
                    "table_format": {"border_color": "AEB7C2", "repeat_header": True, "page_break": "CELL"},
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
            "header": "생성형 AI가 과학 연구에 미치는 영향",
            "footer": "AUTHORBENCH A1",
            "page_numbers": True,
            "blocks": [
                {"id": "s3-title", "type": "heading", "level": 1, "text": "2. 빨라진 연구가 곧 더 나은 연구는 아니다"},
                {
                    "id": "s3-lead",
                    "type": "paragraph",
                    "text": "생성형 AI의 가장 큰 위험은 명백한 오류만이 아니다. 더 어려운 문제는 그럴듯한 설명이 ‘이해한 느낌’을 만들어 검증 단계를 약화시키는 것이다. Nature의 2024년 Perspective는 이를 ‘이해의 환상’으로 설명하며, 생산성과 객관성의 약속이 오히려 연구자의 인지적 취약성을 확대할 수 있다고 경고했다.",
                },
                {"id": "s3-h1", "type": "heading", "level": 2, "text": "환각과 검증 비용"},
                {
                    "id": "s3-p1",
                    "type": "paragraph",
                    "text": "LLM은 존재하지 않는 사실이나 근거를 자신감 있게 생성할 수 있다. 2024년 Nature의 연구는 의미적 불확실성을 이용해 이러한 환각을 탐지하는 방법을 제시했지만, 모든 오류를 자동으로 걸러내는 해결책은 아니다. 과학 연구에서는 틀린 숫자 하나보다 잘못된 인용, 부정확한 방법 설명, 조건이 빠진 코드가 더 늦게 발견될 수 있다. 따라서 AI가 절약한 작성 시간의 일부를 검증 예산으로 되돌려야 한다.",
                },
                {"id": "s3-h2", "type": "heading", "level": 2, "text": "데이터 거버넌스와 기밀성"},
                {
                    "id": "s3-p2",
                    "type": "paragraph",
                    "text": "연구 데이터는 일반 문서보다 민감한 경우가 많다. NIH는 2025년 생성형 AI 개발·활용 과정에서 통제 접근 유전체 데이터와 그 파생정보가 승인되지 않은 외부 시스템으로 전달되지 않도록 주의를 요구했다. 개인 식별 가능 데이터, 미공개 결과, 공동연구 계약이 걸린 자료는 모델 입력 전에 사용 조건과 저장·학습 정책을 먼저 확인해야 한다.",
                },
                {"id": "s3-h3", "type": "heading", "level": 2, "text": "과학적 다양성의 축소 가능성"},
                {
                    "id": "s3-p3",
                    "type": "paragraph",
                    "text": "AI가 잘 작동하는 영역은 대체로 데이터와 선행 사례가 풍부하다. 연구자가 효율을 최적화할수록 비주류 문제, 희귀한 데이터, 장기 탐색이 필요한 주제는 상대적으로 불리해질 수 있다. AI의 평균적 제안은 빠른 시작점이지만, 연구 포트폴리오 전체가 같은 도구의 제안 분포를 따라가면 과학의 탐색 폭이 줄어들 수 있다.",
                },
                {
                    "id": "s3-risk",
                    "type": "table",
                    "rows": 5,
                    "cols": 3,
                    "first_row_header": True,
                    "cells": [
                        ["위험", "조기 신호", "대응"],
                        ["근거 없는 확신", "원문 없이 단정적 설명", "원문·데이터와 독립 대조"],
                        ["재현성 저하", "코드가 실행되지만 조건이 불명확", "테스트·환경·버전 고정"],
                        ["데이터 유출", "민감자료를 외부 모델에 직접 입력", "승인된 환경·비식별화"],
                        ["연구 편향", "익숙하고 데이터가 많은 주제만 반복", "의도적 반례·비주류 가설 탐색"],
                    ],
                    "table_format": {"border_color": "AEB7C2", "repeat_header": True, "page_break": "CELL"},
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
            "header": "생성형 AI가 과학 연구에 미치는 영향",
            "footer": "AUTHORBENCH A1",
            "page_numbers": True,
            "blocks": [
                {"id": "s4-title", "type": "heading", "level": 1, "text": "3. 좋은 연구팀은 AI를 어떻게 써야 하는가"},
                {
                    "id": "s4-intro",
                    "type": "paragraph",
                    "text": "핵심은 사용 여부를 이분법적으로 결정하는 것이 아니라 업무별 권한을 설계하는 것이다. 생성형 AI는 초안·탐색·형식 변환에는 넓게 활용하되, 사실 판정·방법 선택·결과 해석·최종 주장에는 더 높은 인간 책임을 두는 편이 안전하다.",
                },
                {"id": "s4-h1", "type": "heading", "level": 2, "text": "권장 운영 원칙 5가지"},
                {"id": "s4-l1", "type": "list_item", "text": "1. 출처 없는 문장을 결과가 아니라 가설로 취급한다."},
                {"id": "s4-l2", "type": "list_item", "text": "2. 분석 코드와 수치 결과는 독립 테스트와 원자료 대조를 거친다."},
                {"id": "s4-l3", "type": "list_item", "text": "3. 민감 데이터는 승인된 모델·환경에서만 사용하고 입력 이력을 관리한다."},
                {"id": "s4-l4", "type": "list_item", "text": "4. 중요한 연구 판단은 사람의 이유와 반례 검토를 함께 기록한다."},
                {"id": "s4-l5", "type": "list_item", "text": "5. AI 사용을 생산성 지표뿐 아니라 다양성·재현성·검증 비용으로도 평가한다."},
                {"id": "s4-h2", "type": "heading", "level": 2, "text": "최종 판단"},
                {
                    "id": "s4-conclusion",
                    "type": "paragraph",
                    "text": "생성형 AI는 과학 연구의 속도를 분명히 바꾸고 있다. 그러나 속도 향상은 연구의 질과 동일하지 않다. 가장 유망한 모델은 사람이 질문과 책임을 보유하고, AI가 탐색·구성·반복 작업을 증폭하며, 모든 중요한 주장이 다시 세계와 데이터에 연결되는 구조다. 장기적으로 차이를 만드는 것은 더 강한 모델 자체보다 검증 가능한 연구 워크플로를 설계하는 능력일 가능성이 크다.",
                    "run_format": {"bold": True},
                },
                {"id": "s4-h3", "type": "heading", "level": 2, "text": "참고 문헌"},
                {
                    "id": "ref1",
                    "type": "paragraph",
                    "text": "Messeri, L. & Crockett, M. J. (2024). Artificial intelligence and illusions of understanding in scientific research. Nature 627, 49–58.",
                    "run_format": {"size": 9},
                },
                {
                    "id": "ref2",
                    "type": "paragraph",
                    "text": "Farquhar, S. et al. (2024). Detecting hallucinations in large language models using semantic entropy. Nature 630, 625–630.",
                    "run_format": {"size": 9},
                },
                {
                    "id": "ref3",
                    "type": "paragraph",
                    "text": "González-Márquez, R. et al. (2025). Exploring the role of large language models in the scientific method: from hypothesis to discovery. npj Artificial Intelligence 1, 14.",
                    "run_format": {"size": 9},
                },
                {
                    "id": "ref4",
                    "type": "paragraph",
                    "text": "Hao, Q. et al. (2026). Artificial intelligence tools expand scientists’ impact but contract science’s focus. Nature 649, 1237–1243.",
                    "run_format": {"size": 9},
                },
                {
                    "id": "ref5",
                    "type": "paragraph",
                    "text": "National Institutes of Health (2025). Protecting Human Genomic Data when Developing Generative Artificial Intelligence Tools and Applications (NOT-OD-25-081).",
                    "run_format": {"size": 9},
                },
            ],
        },
    ],
}

compiled = compile_rich_document_plan(rich_plan)
receipt = compose_document_plan(OUT, compiled["plan"])
preview = evaluate_preview_readiness(OUT, mode="POLISHED_REPORT")
doc_map = build_document_map(OUT)
table_map = build_table_map(OUT)

if preview["verdict"] not in {"PASS", "PASS_WITH_WARNINGS"}:
    raise RuntimeError(f"preview gate failed: {preview['verdict']}")

sha256 = hashlib.sha256(OUT.read_bytes()).hexdigest()
payload = {
    "schema": "authorbench/a1/v0.1",
    "title": "생성형 AI가 과학 연구에 미치는 영향",
    "generated_file": str(OUT),
    "sha256": sha256,
    "bytes": OUT.stat().st_size,
    "section_count": compiled["section_count"],
    "block_count": compiled["block_count"],
    "paragraph_count": len(doc_map.get("paragraphs", [])),
    "table_count": len(table_map.get("tables", [])),
    "preview_verdict": preview["verdict"],
    "preview_render_status": preview["render_status"],
    "preview_warning_count": sum(1 for g in preview.get("gates", []) if g.get("status") == "WARN"),
    "compile_sha256": compiled["compile_sha256"],
    "composer_receipt": {
        "preset": receipt.get("preset"),
        "output_sha256": receipt.get("output_sha256"),
    },
    "benchmark_intent": "polished Word/PDF-like Korean report, not bureaucratic public-document aesthetics",
    "content_basis": [
        "Nature 2024: illusions of understanding",
        "Nature 2024: semantic-entropy hallucination detection",
        "npj Artificial Intelligence 2025: LLMs across the scientific method",
        "Nature 2026: individual impact versus collective focus",
        "NIH 2025: genomic-data governance for generative AI",
    ],
}
RECEIPT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
