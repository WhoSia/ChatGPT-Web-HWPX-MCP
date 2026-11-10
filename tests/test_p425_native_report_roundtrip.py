"""Real P4.25 native authoring acceptance, synthetic inputs only.

No user/private file, Windows COM, external renderer or database required.
The test writes a temporary HWPX with the *actual* P3.38/P3.21 composer,
then reopens it using existing native HWPX map readers.
"""
from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.document.p28_tables import build_table_map
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p29_objects import build_object_map
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl4AAAAASUVORK5CYII="
)


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

    def test_interleaved_native_figure_equation_table_roundtrip(self):
        plan = build_report_plan(
            title="합성 그래프 보고서", preset="science-report",
            sections=[{"heading": "실험 결과", "content": [
                {"type": "paragraph", "text": "그래프 앞 문단"},
                {"type": "figure", "image_format": "png",
                 "content_base64": base64.b64encode(PNG_1X1).decode("ascii"),
                 "width": 4000, "height": 3000, "caption": "그림 1. 합성 그래프"},
                {"type": "paragraph", "text": "그래프 뒤 문단"},
                {"type": "equation", "latex": "V=IR"},
                {"type": "table", "cells": [["전압", "전류"], ["3.0", "0.15"]]},
            ]}],
        )
        compiled = compile_rich_document_plan(plan)
        self.assertEqual(compiled["block_counts"]["picture"], 1)
        with tempfile.TemporaryDirectory(prefix="p425-native-fig-") as tmp:
            path = Path(tmp) / "figures.hwpx"
            result = compose_document_plan(path, compiled["plan"])
            self.assertTrue(result["atomic_commit"])
            mapped = build_object_map(path)
            self.assertGreaterEqual(len(mapped["pictures"]), 1)
            self.assertEqual(len(build_equation_map(path)["equations"]), 1)
            self.assertEqual(len(build_table_map(path)["tables"]), 1)
            body = [p["text"] for p in build_document_map(path)["paragraphs"]]
            self.assertLess(
                next(i for i, x in enumerate(body) if "그래프 앞" in x),
                next(i for i, x in enumerate(body) if "그래프 뒤" in x),
            )

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
