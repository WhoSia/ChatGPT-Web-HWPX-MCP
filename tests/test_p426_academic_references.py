"""P4.26 stable native bookmarks, page references and footnotes."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p319_structured_publishing import build_structured_publishing_map


class P426AcademicReferencesTests(unittest.TestCase):
    def _request(self):
        return build_report_plan(
            title="수식 참조 문서",
            sections=[{"heading": "결과", "content": [
                {"type": "paragraph", "id": "result_anchor",
                 "bookmark": "MeasuredResult", "text": "실험 결과를 분석하였다.",
                 "footnote": "실험 조건을 기록한 합성 각주"},
                {"type": "equation", "latex": "V=IR", "id": "ohms_equation"},
                {"type": "paragraph", "id": "page_reference",
                 "text": "결과의 위치를 확인한다. ",
                 "page_ref_target": "result_anchor"},
            ]}],
        )

    def test_plan_contains_native_resolvable_cross_reference_operations(self):
        plan = self._request()
        self.assertEqual(plan["post_operations"], [{
            "op": "add_page_crossref",
            "paragraph": "$block:page_reference",
            "target_paragraph": "$block:result_anchor",
            "cached_page": 1,
        }])
        self.assertEqual(plan["annotations"][0]["paragraph"], "$block:result_anchor")
        self.assertEqual(plan["sections"][0]["blocks"][2]["bookmark"], "MeasuredResult")

    def test_native_hwp_file_preserves_bookmark_and_page_reference_field(self):
        compiled = compile_rich_document_plan(self._request())
        with tempfile.TemporaryDirectory(prefix="p426-native-references-") as tmp:
            path = Path(tmp) / "references.hwpx"
            receipt = compose_document_plan(path, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            observed = build_structured_publishing_map(path)
            self.assertIn(
                "MeasuredResult",
                [b["name"] for b in observed["bookmarks"]],
            )
            self.assertGreaterEqual(len(observed["fields"]), 1)

    def test_cross_reference_to_missing_block_fails_before_composition(self):
        with self.assertRaisesRegex(ValueError, "TARGET_MISSING"):
            build_report_plan(
                title="보고서", sections=[{"heading": "내용", "content": [
                    {"type": "paragraph", "id": "ref1",
                     "text": "없는 대상", "page_ref_target": "not_defined"},
                ]}],
            )

    def test_duplicate_block_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "BLOCK_ID_DUPLICATE"):
            build_report_plan(title="보고서", sections=[{"heading": "내용", "content": [
                {"type": "paragraph", "id": "same", "text": "첫째"},
                {"type": "paragraph", "id": "same", "text": "둘째"},
            ]}])

    def test_page_reference_requires_paragraph_source(self):
        with self.assertRaisesRegex(ValueError, "REQUIRES_PARAGRAPH"):
            build_report_plan(title="보고서", sections=[{"heading": "내용", "content": [
                {"type": "equation", "latex": "V=IR",
                 "page_ref_target": "example"},
            ]}])


if __name__ == "__main__":
    unittest.main()
