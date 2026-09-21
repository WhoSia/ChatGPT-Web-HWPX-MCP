from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p28_tables import apply_table_edits_atomic, build_table_map
from p29_objects import apply_object_edits_atomic, build_object_map
from p210_equations import apply_equation_edits_atomic, build_equation_map
from p319_structured_publishing import (
    apply_structured_publishing_atomic,
    build_structured_publishing_map,
)


def make_doc(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.19 structured publishing")
    doc.add_paragraph("alpha")
    doc.add_paragraph("beta")
    doc.add_heading("첫 번째 장", level=1)
    doc.add_heading("하위 절", level=2)
    doc.save_to_path(str(path))
    doc.close()


def locator_for(path: Path, text: str) -> str:
    return next(
        p["locator"]
        for p in build_document_map(path)["paragraphs"]
        if p["text"] == text
    )


def tiny_png_b64() -> str:
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00" * 8
        + (1).to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + b"\x00" * 32
    )
    return base64.b64encode(payload).decode("ascii")


class P319StructuredPublishingTests(unittest.TestCase):
    def test_native_numbered_list_and_named_style_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha")
            beta = locator_for(path, "beta")
            result = apply_structured_publishing_atomic(
                path,
                [
                    {
                        "op": "apply_list_format",
                        "paragraphs": [alpha, beta],
                        "kind": "number",
                        "level": 1,
                        "number_format": "^1.",
                        "start": 3,
                    },
                    {
                        "op": "apply_named_style",
                        "paragraph": alpha,
                        "style": "본문",
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(result["changed"])
            mapped = build_structured_publishing_map(path)
            by_text = {p["text"]: p for p in mapped["paragraphs"]}
            self.assertEqual(by_text["alpha"]["style_id_ref"], "1")
            self.assertEqual(by_text["alpha"]["outline"]["type"], "NUMBER")
            self.assertEqual(by_text["beta"]["outline"]["type"], "NUMBER")

    def test_outline_hierarchy_can_promote_existing_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            beta = locator_for(path, "beta")
            apply_structured_publishing_atomic(
                path,
                [{"op": "set_outline_level", "paragraph": beta, "level": 3}],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_structured_publishing_map(path)
            item = next(p for p in mapped["paragraphs"] if p["text"] == "beta")
            self.assertEqual(item["outline"]["type"], "OUTLINE")
            self.assertEqual(str(item["outline"]["level"]), "2")

    def test_table_picture_and_equation_captions_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha")

            apply_table_edits_atomic(
                path,
                [{"op": "create_table", "rows": 2, "cols": 2}],
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            apply_object_edits_atomic(
                path,
                [{
                    "op": "insert_picture",
                    "paragraph": alpha,
                    "content_base64": tiny_png_b64(),
                    "image_format": "png",
                    "width": 7200,
                    "height": 3600,
                }],
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            apply_equation_edits_atomic(
                path,
                [{
                    "op": "insert_equation",
                    "paragraph": alpha,
                    "latex": r"x^2+y^2",
                    "base_unit": 1100,
                }],
                expected_revision=1,
                current_revision=1,
                validator=None,
            )

            table = build_table_map(path)["tables"][0]["locator"]
            picture = build_object_map(path)["pictures"][0]["locator"]
            equation = build_equation_map(path)["equations"][0]["locator"]
            apply_structured_publishing_atomic(
                path,
                [
                    {"op": "set_caption", "kind": "table", "target": table, "text": "표 1. 결과"},
                    {"op": "set_caption", "kind": "picture", "target": picture, "text": "그림 1. 개요"},
                    {"op": "set_caption", "kind": "equation", "target": equation, "text": "식 1. 관계"},
                ],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_structured_publishing_map(path)
            texts = {item["text"] for item in mapped["captions"]}
            self.assertTrue({"표 1. 결과", "그림 1. 개요", "식 1. 관계"}.issubset(texts))

    def test_bookmark_crossref_and_native_toc_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha")
            heading = locator_for(path, "첫 번째 장")
            result = apply_structured_publishing_atomic(
                path,
                [
                    {"op": "add_bookmark", "paragraph": heading, "name": "chapter-one"},
                    {
                        "op": "add_page_crossref",
                        "paragraph": alpha,
                        "target_paragraph": heading,
                        "cached_page": 1,
                    },
                    {"op": "add_native_toc", "at_index": 0, "title": "차례", "level": 2},
                ],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(result["changed"])
            mapped = build_structured_publishing_map(path)
            self.assertEqual(mapped["toc_field_count"], 1)
            self.assertEqual(mapped["crossref_field_count"], 1)
            self.assertIn("chapter-one", {b["name"] for b in mapped["bookmarks"]})
            toc = next(f for f in mapped["fields"] if f["type"] == "TABLEOFCONTENTS")
            self.assertEqual(toc["dirty"], "1")

    def test_mark_toc_dirty_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            apply_structured_publishing_atomic(
                path,
                [{"op": "add_native_toc", "level": 2}],
                expected_revision=1,
                current_revision=1,
            )
            result = apply_structured_publishing_atomic(
                path,
                [{"op": "mark_toc_dirty"}],
                expected_revision=2,
                current_revision=2,
            )
            self.assertEqual(result["receipts"][0]["marked"], 1)

    def test_invalid_operation_rolls_back_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Unsupported structured-publishing operation"):
                apply_structured_publishing_atomic(
                    path,
                    [
                        {
                            "op": "apply_named_style",
                            "paragraph": locator_for(path, "alpha"),
                            "style": "본문",
                        },
                        {"op": "invent_publish_magic"},
                    ],
                    expected_revision=1,
                    current_revision=1,
                )
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
