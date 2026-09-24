from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p321_document_composer import compose_document_plan
from p338_rich_builder import compile_rich_document_plan
from p339_design_intelligence import (
    design_intelligence_contract,
    diagnose_document_design,
    plan_design_repairs,
    prepare_authoring_strategy,
)


class P339DesignIntelligenceTests(unittest.TestCase):
    def test_strategy_detects_early_conclusion(self):
        strategy = prepare_authoring_strategy({
            "archetype": "POLISHED_REPORT",
            "semantic_outline": [
                "TITLE",
                "EXECUTIVE_SUMMARY",
                "CONCLUSION",
                "SECTION",
                "BODY",
            ],
        })
        codes = {item["code"] for item in strategy["warnings"]}
        self.assertIn("NARRATIVE_ORDER_CONCLUSION_EARLY", codes)
        self.assertEqual(strategy["icons"], "AVOID_BY_DEFAULT")

    def test_contract_prefers_high_level_workflow(self):
        contract = design_intelligence_contract()
        self.assertEqual(contract["phase"], "P3.39")
        self.assertEqual(contract["purpose"], "AGENTIC_DOCUMENT_DESIGN_INTELLIGENCE_NOT_BEAUTY_SCORING")
        self.assertIn("prepare_authoring_strategy", contract["tool_policy"]["preferred_high_level"])
        self.assertEqual(contract["agent_workflow"][0], "CLASSIFY_DOCUMENT_ARCHETYPE")

    def test_generated_dense_table_gets_padding_diagnostic_without_beauty_score(self):
        plan = {
            "preset": "polished-report",
            "sections": [
                {
                    "page": {"paper_size": "A4", "orientation": "PORTRAIT"},
                    "blocks": [
                        {"id": "title", "type": "title", "text": "Design Intelligence Test"},
                        {"id": "heading", "type": "heading", "level": 1, "text": "Evidence"},
                        {
                            "id": "table",
                            "type": "table",
                            "rows": 4,
                            "cols": 3,
                            "first_row_header": True,
                            "cells": [
                                ["항목", "설명", "통제"],
                                ["A", "장문 설명이 들어가는 분석 셀입니다. 읽기 흐름과 밀도를 확인합니다.", "원문 대조"],
                                ["B", "두 번째 장문 설명 역시 표 안에서 충분한 여백이 필요합니다.", "독립 검증"],
                                ["C", "세 번째 설명은 표가 단순한 그리드가 아니라 읽기 구조임을 보여줍니다.", "기록 보존"],
                            ],
                        },
                    ],
                }
            ],
        }
        compiled = compile_rich_document_plan(plan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diag.hwpx"
            compose_document_plan(path, compiled["plan"])
            diagnostic = diagnose_document_design(path)

        codes = {item["code"] for item in diagnostic["findings"]}
        self.assertIn("TABLE_CELL_PADDING_TIGHT", codes)
        self.assertIsNone(diagnostic["aesthetic_score"])
        self.assertEqual(diagnostic["aesthetic_verdict"], "NOT_REDUCED_TO_SINGLE_SCORE")

    def test_render_and_human_evidence_are_layered(self):
        plan = {
            "preset": "polished-report",
            "sections": [{
                "blocks": [
                    {"id": "title", "type": "title", "text": "Evidence layering"},
                    {"id": "body", "type": "paragraph", "text": "Body."},
                ]
            }],
        }
        compiled = compile_rich_document_plan(plan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.hwpx"
            compose_document_plan(path, compiled["plan"])
            diagnostic = diagnose_document_design(
                path,
                render_observation={
                    "authority": "PDF_RENDER_OBSERVATION",
                    "findings": [{
                        "code": "PAGE_DENSITY_HIGH",
                        "severity": "MEDIUM",
                        "scope": "PAGE_2",
                        "evidence": {"text_coverage": 0.82},
                        "recommendation": "Increase whitespace or split the block.",
                    }],
                },
                human_feedback=[{
                    "code": "INFORMATION_PRIORITY_ENCODING_WEAK",
                    "severity": "HIGH",
                    "note": "핵심 판단이 본문과 거의 구분되지 않음.",
                }],
            )
        authorities = set(diagnostic["authorities"])
        self.assertIn("PDF_RENDER_OBSERVATION", authorities)
        self.assertIn("HUMAN_VISUAL_REVIEW", authorities)
        self.assertEqual(diagnostic["verdict"], "NEEDS_REPAIR")

    def test_repair_plan_emits_executable_padding_and_capability_gaps(self):
        strategy = prepare_authoring_strategy({"archetype": "POLISHED_REPORT"})
        diagnostic = {
            "diagnostic_sha256": "a" * 64,
            "findings": [
                {
                    "code": "TABLE_CELL_PADDING_TIGHT",
                    "evidence": {
                        "cells": [{
                            "table": "table:0",
                            "cell": "cell:0:0",
                            "margin": {"left": 0, "right": 0, "top": 0, "bottom": 0},
                        }]
                    },
                },
                {
                    "code": "TABLE_LONG_TEXT_CENTERED",
                    "evidence": {"locators": ["p:table:0"]},
                },
                {
                    "code": "TABLE_HEADER_CONTRAST_WEAK",
                    "evidence": {"tables": [{"table": "table:0"}]},
                },
            ],
        }
        repair = plan_design_repairs(diagnostic, strategy=strategy)
        self.assertEqual(repair["executable_count"], 1)
        self.assertEqual(repair["capability_gap_count"], 2)
        op = next(x for x in repair["actions"] if x["status"] == "EXECUTABLE")["operation"]
        self.assertEqual(op["op"], "set_cell_margin")
        self.assertEqual(op["left"], 560)


if __name__ == "__main__":
    unittest.main()
