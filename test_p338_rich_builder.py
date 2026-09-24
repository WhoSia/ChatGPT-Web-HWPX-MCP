from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p28_tables import build_table_map
from p318_document_setup import build_document_setup_map
from p321_document_composer import compose_document_plan
from p338_rich_builder import (
    compile_rich_document_plan,
    evaluate_preview_readiness,
    intelligent_fill_atomic,
    plan_intelligent_template_fill,
    rich_builder_contract,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z4i8AAAAASUVORK5CYII="
)


class P338RichBuilderTests(unittest.TestCase):
    def test_compile_and_materialize_multi_section_rich_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rich.hwpx"
            compiled = compile_rich_document_plan({
                "preset": "polished-report",
                "document": {"title": "P3.38 Rich Native Document"},
                "publishing": {"toc": False},
                "sections": [
                    {
                        "page": {
                            "paper_size": "A4",
                            "orientation": "PORTRAIT",
                            "margin_left_mm": 18,
                            "margin_right_mm": 18,
                        },
                        "header": {"text": "P3.38 Header", "page_type": "BOTH"},
                        "footer": {"text": "Internal", "page_type": "ODD"},
                        "page_numbers": {"target": "footer", "prefix": "p. "},
                        "blocks": [
                            {"id": "title", "type": "title", "text": "P3.38 Rich Native Document"},
                            {"id": "h1", "type": "heading", "level": 1, "text": "1. Overview"},
                            {"id": "body", "type": "paragraph", "text": "Rich builder body."},
                            {
                                "id": "table",
                                "type": "table",
                                "rows": 2,
                                "cols": 2,
                                "first_row_header": True,
                                "cells": [["항목", "값"], ["상태", "PASS"]],
                            },
                            {"id": "eq", "type": "equation", "latex": "x^2+y^2=1"},
                            {
                                "id": "img",
                                "type": "image",
                                "content_base64": base64.b64encode(PNG_1X1).decode(),
                                "image_format": "png",
                                "width": 3000,
                                "height": 3000,
                                "caption": "1 px fixture",
                            },
                        ],
                    },
                    {
                        "page": {
                            "paper_size": "A4",
                            "orientation": "LANDSCAPE",
                            "margin_left_mm": 15,
                            "margin_right_mm": 15,
                        },
                        "header": "Second section",
                        "start_numbering": {"page": 1},
                        "blocks": [
                            {"id": "h2", "type": "heading", "level": 1, "text": "2. Appendix"},
                            {"id": "p2", "type": "paragraph", "text": "Landscape appendix."},
                        ],
                    },
                ],
            })
            self.assertEqual(compiled["section_count"], 2)
            self.assertIn("picture", compiled["block_counts"])
            receipt = compose_document_plan(path, compiled["plan"])
            self.assertEqual(receipt["block_count"], compiled["block_count"])

            setup = build_document_setup_map(path)
            self.assertEqual(setup["section_count"], 2)
            self.assertTrue(any(
                story["kind"] == "header" and "P3.38 Header" in story["text"]
                for story in setup["sections"][0]["stories"]
            ))
            self.assertGreater(
                setup["sections"][1]["page"]["width"],
                setup["sections"][1]["page"]["height"],
            )

            preview = evaluate_preview_readiness(path)
            self.assertIn(preview["verdict"], {"PASS", "PASS_WITH_WARNINGS"})
            self.assertEqual(preview["render_status"], "NOT_RENDERED")
            self.assertEqual(preview["picture_count"], 1)
            self.assertEqual(preview["equation_count"], 1)

    def test_intelligent_fill_resolves_placeholder_and_label_right(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "template.hwpx"
            destination = root / "filled.hwpx"
            doc = HwpxDocument.new()
            doc.add_paragraph("담당자={{name}}")
            table = doc.add_table(rows=2, cols=2)
            table.set_cell_text(0, 0, "학교")
            table.set_cell_text(0, 1, "")
            table.set_cell_text(1, 0, "학년")
            table.set_cell_text(1, 1, "")
            doc.save_to_path(str(source))
            doc.close()
            before = source.read_bytes()

            plan = plan_intelligent_template_fill(
                source,
                {"name": "김우준", "학교": "창원과학고"},
            )
            self.assertEqual(plan["resolved_fields"], 2)
            self.assertEqual(plan["fields"]["name"]["strategy"], "PLACEHOLDER")
            self.assertEqual(plan["fields"]["학교"]["strategy"], "LABEL_RIGHT")

            receipt = intelligent_fill_atomic(
                source,
                destination,
                {"name": "김우준", "학교": "창원과학고"},
            )
            self.assertTrue(receipt["atomic_commit"])
            self.assertFalse(receipt["source_template_mutated"])
            self.assertEqual(source.read_bytes(), before)

            mapped = build_document_map(destination)
            self.assertIn("담당자=김우준", mapped["text"])
            tables = build_table_map(destination)
            school_value = next(
                cell["text"]
                for cell in tables["tables"][0]["cells"]
                if cell["row"] == 0 and cell["col"] == 1
            )
            self.assertEqual(school_value, "창원과학고")

    def test_intelligent_fill_fails_closed_on_ambiguous_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambiguous.hwpx"
            doc = HwpxDocument.new()
            for _ in range(2):
                table = doc.add_table(rows=1, cols=2)
                table.set_cell_text(0, 0, "학교")
                table.set_cell_text(0, 1, "")
            doc.save_to_path(str(path))
            doc.close()
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                plan_intelligent_template_fill(path, {"학교": "창원과학고"})

    def test_contract_keeps_preview_claim_bounded(self):
        contract = rich_builder_contract()
        self.assertEqual(contract["phase"], "P3.38")
        self.assertEqual(contract["preview_awareness"]["render_status"], "NOT_RENDERED")
        self.assertIn("LABEL_RIGHT", contract["intelligent_template_fill"]["strategies"])


if __name__ == "__main__":
    unittest.main()
