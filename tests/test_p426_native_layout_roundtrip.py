"""P4.26 real native HWPX writer/re-reader typography and A4 geometry."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p22_formatting import build_formatting_map
from hwpx_mcp.document.p318_document_setup import build_document_setup_map
from hwpx_mcp.document.p2_document import build_document_map


class P426ActualLayoutRoundtripTests(unittest.TestCase):
    def _make(self, directory: Path, name: str, layout: dict | str):
        requested = build_report_plan(
            title="서식 설계 검증", layout=layout,
            sections=[{"heading": "실험", "content": [
                {"type": "paragraph", "text": "문서 내용은 같은 상태에서 스타일만 변경한다."},
                {"type": "paragraph", "text": "단위와 수치의 의미는 그대로 보존한다."},
            ]}],
        )
        compiled = compile_rich_document_plan(requested)
        target = directory / f"{name}.hwpx"
        receipt = compose_document_plan(target, compiled["plan"])
        self.assertTrue(receipt["atomic_commit"])
        return {
            "path": target,
            "text": build_document_map(target)["semantic_sha256"],
            "setup": build_document_setup_map(target)["document_setup_sha256"],
            "format": build_formatting_map(target)["formatting_sha256"],
            "style_profile": compiled["plan"]["style_profile"],
        }

    def test_real_native_document_obeys_distinct_layout_profiles(self):
        with tempfile.TemporaryDirectory(prefix="p426-real-layout-") as tmp:
            root = Path(tmp)
            science = self._make(root, "science", "science-lab")
            journal = self._make(root, "journal", {
                "base": "academic-journal",
                "typography": {"body_line_percent": 170},
                "page": {"margins_mm": [28, 27, 22, 23]},
            })
            self.assertEqual(science["text"], journal["text"])
            self.assertNotEqual(science["setup"], journal["setup"])
            self.assertNotEqual(science["format"], journal["format"])
            self.assertNotEqual(science["style_profile"], journal["style_profile"])


if __name__ == "__main__":
    unittest.main()
