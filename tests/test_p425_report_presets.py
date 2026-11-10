"""P4.25 one-call report authoring: native preset plan and MCP delegation."""
from __future__ import annotations

import base64
import unittest
from unittest.mock import patch
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
        self.assertIn("preview_report_plan", self.mcp.tools)

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

    def test_ordered_content_keeps_paragraph_formula_table_discussion_order(self):
        plan = build_report_plan(
            title="물리 탐구",
            sections=[{"heading": "결과와 논의", "content": [
                {"type": "paragraph", "text": "실험 설정"},
                {"type": "equation", "latex": "V=IR", "caption": "옴의 법칙"},
                {"type": "paragraph", "text": "오차 해석"},
                {"type": "table", "caption": "측정값", "first_row_header": True,
                 "cells": [["전압", "전류"], ["5", "0.1"]]},
                {"type": "list_item", "kind": "number", "text": "조건 확인"},
            ]}],
            table_of_contents=True,
        )
        blocks = plan["sections"][0]["blocks"]
        self.assertEqual([block["type"] for block in blocks],
                         ["title", "heading", "paragraph", "equation",
                          "paragraph", "table", "list_item"])
        self.assertEqual(blocks[5]["cells"][1], ["5", "0.1"])
        self.assertTrue(blocks[5]["first_row_header"])
        self.assertEqual(plan["publishing"]["toc"]["title"], "목차")
        self.assertTrue(plan["sections"][0]["page_numbers"])

    def test_ordered_content_rejects_ambiguous_legacy_lists(self):
        with self.assertRaisesRegex(ValueError, "ORDERED_CONTENT_CONFLICT"):
            build_report_plan(
                title="보고서", sections=[{"heading": "결과",
                    "content": [{"type": "paragraph", "text": "순서"}],
                    "paragraphs": ["기존 배열"]}],
            )

    def test_unsupported_ordered_block_does_not_create_file(self):
        for content in [[{"type": "picture", "text": "unknown"}],
                        [{"type": "heading", "level": 9, "text": "잘못된 레벨"}],
                        [{"type": "table", "cells": [["A"], ["A", "B"]]}]]:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.mcp.tools["create_report_from_sections_and_deliver"](
                    title="보고서", sections=[{"heading": "결과", "content": content}],
                )
        self.assertEqual(self.calls, [])

    def test_preview_uses_real_compile_contract_without_composing(self):
        fake = {"block_count": 5, "block_counts": {"title": 1, "heading": 2, "paragraph": 2},
                "section_count": 1, "setup_operation_count": 1,
                "plan_sha256": "f" * 64}
        with patch("hwpx_mcp.orchestration.p338_rich_builder.compile_rich_document_plan",
                   return_value=fake) as compiler:
            result = self.mcp.tools["preview_report_plan"](
                title="테스트", sections=[{"heading": "방법",
                 "content": [{"type": "paragraph", "text": "실험 절차"}]}],
                table_of_contents=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["committed"])
        self.assertEqual(result["block_count"], 5)
        self.assertTrue(result["table_of_contents_requested"])
        self.assertEqual(compiler.call_args.args[0]["publishing"]["toc"]["at_index"], 1)
        self.assertEqual(self.calls, [])

    def test_embedded_picture_preserves_order_and_caption(self):
        image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"fake-image").decode("ascii")
        plan = build_report_plan(
            title="그림 보고서",
            sections=[{"heading": "결과", "content": [
                {"type": "paragraph", "text": "그림 전"},
                {"type": "figure", "image_format": "png",
                 "content_base64": image,
                 "caption": "그림 1. 그래프", "width": 4000, "height": 3000},
                {"type": "paragraph", "text": "그림 후"},
            ]}],
        )
        blocks = plan["sections"][0]["blocks"]
        self.assertEqual([b["type"] for b in blocks],
                         ["title", "heading", "paragraph", "picture", "paragraph"])
        self.assertEqual(blocks[3]["caption"], "그림 1. 그래프")
        self.assertEqual(blocks[3]["width"], 4000)

    def test_picture_rejects_nonimage_signature_and_invalid_size(self):
        for figure in [
            {"image_format": "png",
             "content_base64": base64.b64encode(b"NOT-PNG").decode("ascii")},
            {"image_format": "bmp", "content_base64": "Zm9v"},
            {"image_format": "png", "content_base64": "bad base64"},
            {"image_format": "png",
             "content_base64": base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii"),
             "width": 0},
        ]:
            with self.subTest(figure=figure), self.assertRaises(ValueError):
                build_report_plan(title="그림 보고서", sections=[
                    {"heading": "결과", "content": [{"type": "figure", **figure}]},
                ])

    def test_native_footnote_references_paragraph_block(self):
        plan = build_report_plan(
            title="탐구 보고서",
            sections=[{"heading": "논의", "content": [
                {"type": "paragraph", "text": "선행연구를 검토하였다.",
                 "footnote": "문헌 출처 및 검토 조건"},
                {"type": "equation", "latex": "V=IR"},
                {"type": "paragraph", "text": "추가 해석이다.",
                 "footnote": "실험 조건 보충 설명"},
            ]}],
        )
        notes = plan["annotations"]
        self.assertEqual(len(notes), 2)
        self.assertEqual([note["op"] for note in notes], ["add_footnote"] * 2)
        blocks = plan["sections"][0]["blocks"]
        self.assertEqual(notes[0]["paragraph"], "$block:" + blocks[2]["id"])
        self.assertEqual(notes[1]["paragraph"], "$block:" + blocks[4]["id"])
        self.assertNotIn("footnote", blocks[2])

    def test_rejects_footnote_on_unsupported_block(self):
        with self.assertRaisesRegex(ValueError, "FOOTNOTE_REQUIRES_PARAGRAPH"):
            build_report_plan(
                title="보고서", sections=[{"heading": "논의", "content": [
                    {"type": "equation", "latex": "V=IR", "footnote": "잘못된 부착"},
                ]}],
            )

    def test_auto_numbering_follows_native_object_order(self):
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"sample").decode("ascii")
        plan = build_report_plan(
            title="캡션 보고서", number_captions=True,
            sections=[{"heading": "결과", "content": [
                {"type": "equation", "latex": "V=IR", "caption": "옴의 법칙"},
                {"type": "figure", "content_base64": png, "caption": "그래프"},
                {"type": "table", "caption": "측정 결과", "cells": [["A"], ["B"]]},
                {"type": "figure", "content_base64": png,
                 "caption": "그림 2. 이미 번호 붙인 그림"},
                {"type": "equation", "latex": "P=VI", "caption": "전력"},
            ]}],
        )
        blocks = plan["sections"][0]["blocks"]
        self.assertEqual([item["caption"] for item in blocks if item.get("caption")],
                         ["식 1. 옴의 법칙", "그림 1. 그래프",
                          "표 1. 측정 결과", "그림 2. 이미 번호 붙인 그림",
                          "식 2. 전력"])

    def test_caption_numbering_disabled_preserves_exact_user_text(self):
        plan = build_report_plan(
            title="보고서", number_captions=False,
            sections=[{"heading": "본문", "equations": [{"latex": "V=IR", "caption": "옴의 법칙"}]}],
        )
        self.assertEqual(plan["sections"][0]["blocks"][-1]["caption"], "옴의 법칙")

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
