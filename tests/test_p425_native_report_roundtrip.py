"""Real P4.25 native authoring acceptance, synthetic inputs only.

No user/private file, Windows COM, external renderer or database required.
The test writes a temporary HWPX with the *actual* P3.38/P3.21 composer,
then reopens it using existing native HWPX map readers.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.document.p28_tables import build_table_map
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan


class NativeP425ReportRoundtripTests(unittest.TestCase):
    def test_ordered_physics_report_creates_real_hwpx_tables_and_equations(self):
        plan = build_report_plan(
            title="회로 특성 실험 보고서",
            preset="science-report", author="합성 테스트",
            page_numbers=True,
            sections=[{"heading": "실험 결과", "content": [
                {"type": "paragraph", "text": "저항 양단의 전압을 측정하였다."},
                {"type": "equation", "latex": "V=IR", "caption": "옴의 법칙"},
                {"type": "paragraph", "text": "전류는 전압에 비례하였다."},
                {"type": "table", "first_row_header": True,
                 "caption": "전압·전류 합성 데이터",
                 "cells": [["전압 (V)", "전류 (A)"], ["3.0", "0.15"]]},
                {"type": "paragraph", "text": "추가적인 실험에서 재현성을 확인한다."},
            ]}],
        )
        compiled = compile_rich_document_plan(plan)
        self.assertEqual(compiled["block_counts"]["equation"], 1)
        self.assertEqual(compiled["block_counts"]["table"], 1)
        with tempfile.TemporaryDirectory(prefix="p425-native-report-") as tmp:
            out = Path(tmp) / "science.hwpx"
            receipt = compose_document_plan(out, compiled["plan"])
            self.assertTrue(out.is_file())
            self.assertTrue(receipt["atomic_commit"])
            self.assertGreater(out.stat().st_size, 1000)

            paragraphs = build_document_map(out)["paragraphs"]
            texts = [entry["text"] for entry in paragraphs]
            locate = lambda phrase: next(i for i, text in enumerate(texts) if phrase in text)
            self.assertLess(locate("저항 양단"), locate("전류는 전압"))
            self.assertLess(locate("전류는 전압"), locate("추가적인 실험"))
            self.assertGreaterEqual(len(build_table_map(out)["tables"]), 1)
            self.assertGreaterEqual(len(build_equation_map(out)["equations"]), 1)

    def test_native_table_of_contents_compiles_to_structured_publishing(self):
        plan = build_report_plan(
            title="탐구 보고서", table_of_contents=True,
            sections=[{"heading": "연구 배경", "content": [
                {"type": "paragraph", "text": "독립적으로 작성한 합성 문단"},
            ]}],
        )
        compiled = compile_rich_document_plan(plan)
        self.assertTrue(compiled["plan"]["publishing"]["toc"])
        with tempfile.TemporaryDirectory(prefix="p425-native-toc-") as tmp:
            out = Path(tmp) / "toc.hwpx"
            receipt = compose_document_plan(out, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
