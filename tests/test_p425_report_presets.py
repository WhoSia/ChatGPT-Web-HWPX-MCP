"""P4.25 one-call report authoring: native preset plan and MCP delegation."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from hwpx_mcp.interfaces.p425_report_presets import (
    build_report_plan, register_report_preset_tools, PRESETS,
)


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class ReportPresetTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.mcp = FakeMcp()
        def fake_rich(plan, filename):
            self.calls.append((plan, filename))
            return {"native": True, "filename": filename, "sections": plan["sections"]}
        self.core = SimpleNamespace(
            mcp=self.mcp, _caller_subject=lambda: "synthetic-test-owner",
            _p425_create_rich_document_and_deliver=fake_rich,
        )
        register_report_preset_tools(self.core)

    def test_uses_registered_native_report_presets(self):
        result = self.mcp.tools["list_report_presets"]()
        self.assertTrue(result["ok"])
        self.assertEqual({x["id"] for x in result["presets"]}, set(PRESETS))
        self.assertEqual(result["next_tool"], "create_report_from_sections_and_deliver")

    def test_single_call_creates_science_report_with_real_table_blocks(self):
        result = self.mcp.tools["create_report_from_sections_and_deliver"](
            title="산화환원 실험",
            sections=[{
                "heading": "실험 결과",
                "paragraphs": ["실험 조건을 비교하였다."],
                "tables": [{"caption": "측정치", "cells": [
                    ["조건", "흡광도"], ["A", 0.31], ["B", 0.27],
                ]}],
            }],
            preset="science-report", filename="lab.hwpx",
            author="작성자", page_numbers=True,
        )
        self.assertTrue(result["native"])
        self.assertEqual(result["filename"], "lab.hwpx")
        plan, filename = self.calls[0]
        self.assertEqual(filename, "lab.hwpx")
        self.assertEqual(plan["preset"], "academic-report")
        self.assertTrue(plan["sections"][0]["page_numbers"])
        blocks = plan["sections"][0]["blocks"]
        self.assertEqual([block["type"] for block in blocks],
                         ["title", "paragraph", "heading", "paragraph", "table"])
        self.assertEqual(blocks[-1]["cells"][1], ["A", "0.31"])
        self.assertEqual(blocks[-1]["caption"], "측정치")

    def test_science_equations_become_editable_native_equation_blocks(self):
        result = self.mcp.tools["create_report_from_sections_and_deliver"](
            title="회로 실험",
            sections=[{
                "heading": "이론 및 분석",
                "equations": [
                    {"latex": r"V=IR", "caption": "옴의 법칙"},
                    r"P=VI",
                ],
            }],
        )
        self.assertTrue(result["native"])
        blocks = self.calls[0][0]["sections"][0]["blocks"]
        eq = [block for block in blocks if block["type"] == "equation"]
        self.assertEqual([block["latex"] for block in eq], ["V=IR", "P=VI"])
        self.assertEqual(eq[0]["caption"], "옴의 법칙")

    def test_invalid_equation_blocks_never_reach_native_composer(self):
        for equations in ([{"latex": ""}], [123], [{"latex": "x", "caption": 1}]):
            with self.subTest(equations=equations), self.assertRaises(ValueError):
                self.mcp.tools["create_report_from_sections_and_deliver"](
                    title="보고서",
                    sections=[{"heading": "수식", "equations": equations}],
                )
        self.assertEqual(self.calls, [])

    def test_unknown_preset_or_invalid_cells_never_calls_composer(self):
        for args in [
            {"preset": "nonexistent"},
            {"sections": [{"heading": "결과",
                           "tables": [{"cells": [["A", "B"], ["C"]]}]}]},
            {"sections": [{"heading": "결과",
                           "tables": [{"cells": [[False]]}]}]},
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.mcp.tools["create_report_from_sections_and_deliver"](
                    title="실험", **{
                        "sections": [{"heading": "본론"}], **args,
                    },
                )
        self.assertEqual(self.calls, [])

    def test_more_than_native_block_limit_rejected(self):
        with self.assertRaisesRegex(ValueError, "TOO_MANY_BLOCKS"):
            build_report_plan(
                title="큰 문서",
                sections=[{"heading": "본문 1", "paragraphs": ["내용"] * 100},
                          {"heading": "본문 2", "paragraphs": ["내용"] * 100},
                          {"heading": "본문 3", "paragraphs": ["내용"] * 100}],
            )

    def test_page_setting_is_boolean(self):
        with self.assertRaisesRegex(ValueError, "PAGE_NUMBER_SETTING"):
            build_report_plan(
                title="제목", sections=[{"heading": "본문"}],
                page_numbers="yes",
            )

    def test_presets_do_not_return_mutable_shared_config(self):
        presets = self.mcp.tools["list_report_presets"]()["presets"]
        presets[0]["default_sections"].clear()
        self.assertTrue(PRESETS["science-report"]["default_sections"])


if __name__ == "__main__":
    unittest.main()
