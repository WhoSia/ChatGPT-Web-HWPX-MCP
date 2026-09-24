from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p2_document import build_document_map
from p22_formatting import build_formatting_map
from p28_tables import build_table_map
from p321_document_composer import compose_document_plan
from p340_feedback_loop import (
    apply_document_design_repairs_atomic,
    apply_nested_paragraph_alignment_atomic,
    compare_design_diagnostics,
    diagnose_render_capture,
    plan_executable_editorial_repairs,
    rendered_feedback_loop_contract,
    semantic_callout_block,
)


def _make_document(path: Path) -> tuple[str, str, str]:
    plan = {
        "preset": "polished-report",
        "blocks": [
            {"id": "title", "type": "title", "text": "P3.40 feedback loop"},
            {"id": "heading", "type": "heading", "level": 1, "text": "Evidence"},
            {
                "id": "table",
                "type": "table",
                "rows": 3,
                "cols": 3,
                "first_row_header": True,
                "cells": [
                    ["항목", "설명", "검증"],
                    ["A", "장문 표 문단은 중앙정렬보다 좌측 정렬이 읽기 흐름에 유리합니다.", "원문 대조"],
                    ["B", "두 번째 긴 설명 열은 더 넓은 폭과 명시적인 셀 여백이 필요합니다.", "독립 검증"],
                ],
            },
        ],
    }
    compose_document_plan(path, plan)
    doc = build_document_map(path)
    table = build_table_map(path)["tables"][0]
    nested = next(
        x["locator"] for x in doc["paragraphs"]
        if "장문 표 문단" in x["text"] and x["body_global_index"] is None
    )
    heading = next(x["locator"] for x in doc["paragraphs"] if x["text"] == "Evidence")
    return table["locator"], nested, heading


class P340RenderedFeedbackLoopTests(unittest.TestCase):
    def test_contract_declares_bounded_closed_loop(self):
        contract = rendered_feedback_loop_contract()
        self.assertEqual(contract["phase"], "P3.40")
        self.assertIn("RENDER_AGAIN", contract["closed_loop"])
        self.assertIn("nested_table_paragraph_alignment", contract["new_native_capabilities"])
        self.assertIn("semantic_callout_container", contract["new_native_capabilities"])

    def test_semantic_callout_compiles_to_native_one_cell_table(self):
        block = semantic_callout_block("핵심 판단입니다.", block_id="judgment")
        self.assertEqual(block["type"], "table")
        self.assertEqual(block["rows"], 1)
        self.assertEqual(block["cols"], 1)
        self.assertEqual(block["semantic_role"], "KEY_JUDGMENT")

    def test_nested_table_paragraph_alignment_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested.hwpx"
            _table, nested, _heading = _make_document(path)
            apply_nested_paragraph_alignment_atomic(path, [nested], alignment="CENTER")
            centered = next(x for x in build_formatting_map(path)["paragraphs"] if x["locator"] == nested)
            self.assertEqual(
                str((centered["paragraph_property"]["alignment"] or {}).get("horizontal")).upper(),
                "CENTER",
            )
            receipt = apply_nested_paragraph_alignment_atomic(path, [nested], alignment="LEFT")
            self.assertTrue(receipt["formatting_changed"])
            left = next(x for x in build_formatting_map(path)["paragraphs"] if x["locator"] == nested)
            self.assertEqual(
                str((left["paragraph_property"]["alignment"] or {}).get("horizontal")).upper(),
                "LEFT",
            )

    def test_render_capture_diagnostics_preserve_native_authority_boundary(self):
        capture = {
            "pages": [{
                "page_index": 0,
                "width_px": 1000,
                "height_px": 1400,
                "raster_sha256": "a" * 64,
                "line_boxes": [
                    {"x": 60, "y": 60 + i * 25, "width": 880, "height": 20, "baseline": 78 + i * 25}
                    for i in range(52)
                ],
            }]
        }
        renderer = {
            "name": "Hancom Office",
            "version": "fixture",
            "hancom_native": True,
            "executable_sha256": "b" * 64,
            "dpi": 144,
        }
        result = diagnose_render_capture(capture, renderer=renderer)
        self.assertTrue(result["world_contact_valid"])
        self.assertEqual(result["authority"], "HANCOM_NATIVE_RENDER_EVIDENCE")
        codes = {x["code"] for x in result["findings"]}
        self.assertIn("PAGE_TEXT_DENSITY_HIGH", codes)

        non_native = diagnose_render_capture(capture, renderer={"name": "other", "version": "1"})
        self.assertFalse(non_native["world_contact_valid"])
        self.assertEqual(non_native["authority"], "EXTERNAL_RENDER_OBSERVATION")

    def test_p339_capability_gaps_are_promoted_to_executable_native_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.hwpx"
            table, nested, heading = _make_document(path)
            diagnostic = {
                "diagnostic_sha256": "c" * 64,
                "findings": [
                    {
                        "code": "TABLE_LONG_TEXT_CENTERED",
                        "evidence": {"locators": [nested]},
                    },
                    {
                        "code": "TABLE_HEADER_CONTRAST_WEAK",
                        "evidence": {"tables": [{"table": table}]},
                    },
                    {
                        "code": "TABLE_DENSITY_HIGH",
                        "evidence": {"tables": [{"table": table}]},
                    },
                    {
                        "code": "SECTION_SEPARATION_WEAK",
                        "evidence": {"locators": [heading]},
                    },
                ],
            }
            plan = plan_executable_editorial_repairs(path, diagnostic)
            self.assertEqual(plan["capability_gap_count"], 0)
            self.assertEqual(plan["agent_plan_count"], 0)
            self.assertGreaterEqual(plan["executable_count"], 4)
            ops = {x["operation"]["op"] for x in plan["actions"] if x["status"] == "EXECUTABLE"}
            self.assertIn("align_nested_table_paragraphs", ops)
            self.assertIn("style_table_header", ops)
            self.assertIn("rebalance_table_columns", ops)
            self.assertIn("style_section_headings", ops)

    def test_atomic_executor_applies_nested_header_and_width_repairs_without_text_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repair.hwpx"
            table, nested, _heading = _make_document(path)
            apply_nested_paragraph_alignment_atomic(path, [nested], alignment="CENTER")
            before_doc = build_document_map(path)
            table_map = build_table_map(path)
            width_plan = [int(x) for x in [
                max(c["width"] for c in table_map["tables"][0]["cells"] if int(c["col"]) == col)
                for col in range(3)
            ]]
            total = sum(width_plan)
            desired = [max(1, int(total * 0.16)), max(1, int(total * 0.58)), 1]
            desired[2] = total - desired[0] - desired[1]

            plan = {
                "repair_plan_sha256": "d" * 64,
                "actions": [
                    {
                        "action": "LEFT_ALIGN_LONG_TABLE_TEXT",
                        "status": "EXECUTABLE",
                        "reason": "TABLE_LONG_TEXT_CENTERED",
                        "operation": {"op": "align_nested_table_paragraphs", "targets": [nested], "alignment": "LEFT"},
                    },
                    {
                        "action": "APPLY_RESTRAINED_HEADER_CONTRAST",
                        "status": "EXECUTABLE",
                        "reason": "TABLE_HEADER_CONTRAST_WEAK",
                        "operation": {"op": "style_table_header", "table": table, "row": 0},
                    },
                    {
                        "action": "REBUDGET_TABLE_COLUMN_WIDTHS",
                        "status": "EXECUTABLE",
                        "reason": "TABLE_DENSITY_HIGH",
                        "operation": {"op": "rebalance_table_columns", "table": table, "widths": desired},
                    },
                ],
            }
            receipt = apply_document_design_repairs_atomic(
                path,
                plan,
                expected_revision=1,
                current_revision=1,
            )
            after_doc = build_document_map(path)
            self.assertEqual(before_doc["semantic_sha256"], after_doc["semantic_sha256"])
            self.assertEqual(before_doc["structure_sha256"], after_doc["structure_sha256"])
            self.assertTrue(receipt["formatting_changed"] or receipt["table_format_changed"])

            nested_after = next(x for x in build_formatting_map(path)["paragraphs"] if x["locator"] == nested)
            self.assertEqual(
                str((nested_after["paragraph_property"]["alignment"] or {}).get("horizontal")).upper(),
                "LEFT",
            )
            header_cells = [x for x in build_table_map(path)["tables"][0]["cells"] if int(x["row"]) == 0]
            self.assertTrue(all(str(x.get("header") or "") == "1" for x in header_cells))
            self.assertTrue(all(int((x.get("margin") or {}).get("left") or 0) >= 560 for x in header_cells))

    def test_semantic_callout_style_executes_as_native_one_cell_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callout.hwpx"
            block = semantic_callout_block("핵심 판단은 검증 가능성과 읽기 구조를 함께 보존해야 합니다.", block_id="judgment")
            compose_document_plan(path, {
                "preset": "polished-report",
                "blocks": [
                    {"id": "title", "type": "title", "text": "Callout execution"},
                    block,
                ],
            })
            table = build_table_map(path)["tables"][0]
            paragraph = next(
                x["locator"] for x in build_document_map(path)["paragraphs"]
                if "핵심 판단은" in x["text"]
            )
            plan = {
                "repair_plan_sha256": "a" * 64,
                "actions": [{
                    "action": "STYLE_SEMANTIC_CALLOUT",
                    "status": "EXECUTABLE",
                    "reason": "AUTHORING_SEMANTIC_ROLE",
                    "operation": {
                        "op": "style_semantic_callout",
                        "table": table["locator"],
                        "paragraph_targets": [paragraph],
                    },
                }],
            }
            receipt = apply_document_design_repairs_atomic(
                path, plan, expected_revision=1, current_revision=1
            )
            self.assertTrue(receipt["table_format_changed"])
            after = build_table_map(path)["tables"][0]["cells"][0]
            self.assertGreaterEqual(int((after.get("margin") or {}).get("left") or 0), 720)
            para = next(x for x in build_formatting_map(path)["paragraphs"] if x["locator"] == paragraph)
            self.assertEqual(
                str((para["paragraph_property"]["alignment"] or {}).get("horizontal")).upper(),
                "LEFT",
            )

    def test_section_heading_separator_executes_through_existing_paragraph_primitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heading-separator.hwpx"
            _table, _nested, heading = _make_document(path)
            before = build_formatting_map(path)["formatting_sha256"]
            plan = {
                "repair_plan_sha256": "b" * 64,
                "actions": [{
                    "action": "APPLY_SECTION_HEADING_SEPARATOR",
                    "status": "EXECUTABLE",
                    "reason": "SECTION_SEPARATION_WEAK",
                    "operation": {"op": "style_section_headings", "targets": [heading]},
                }],
            }
            receipt = apply_document_design_repairs_atomic(
                path, plan, expected_revision=1, current_revision=1
            )
            after = build_formatting_map(path)
            self.assertNotEqual(before, after["formatting_sha256"])
            self.assertTrue(receipt["formatting_changed"])
            heading_after = next(x for x in after["paragraphs"] if x["locator"] == heading)
            prop = heading_after["paragraph_property"] or {}
            self.assertTrue(prop.get("border") is not None)

    def test_before_after_comparison_does_not_fake_native_rerender(self):
        before = {
            "diagnostic_sha256": "e" * 64,
            "findings": [{"code": "TABLE_LONG_TEXT_CENTERED", "scope": "TABLE_PARAGRAPHS", "severity": "HIGH"}],
            "render_page_diagnostic": None,
        }
        after = {
            "diagnostic_sha256": "f" * 64,
            "findings": [],
            "render_page_diagnostic": None,
        }
        result = compare_design_diagnostics(before, after)
        self.assertEqual(result["after_high_count"], 0)
        self.assertTrue(result["high_severity_nonincrease"])
        self.assertFalse(result["native_rerender_verified"])
        self.assertIn("PENDING", result["render_claim"])


if __name__ == "__main__":
    unittest.main()
