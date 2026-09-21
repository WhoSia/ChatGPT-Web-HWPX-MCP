from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p320_annotation_apparatus import (
    apply_annotation_apparatus_atomic,
    build_annotation_apparatus_map,
)


def make_doc(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.20 annotation apparatus")
    doc.add_paragraph("alpha reference target")
    doc.add_paragraph("beta annotation target")
    doc.save_to_path(str(path))
    doc.close()


def locator_for(path: Path, text: str) -> str:
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


class P320AnnotationApparatusTests(unittest.TestCase):
    def test_footnote_and_endnote_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha reference target")
            beta = locator_for(path, "beta annotation target")
            result = apply_annotation_apparatus_atomic(
                path,
                [
                    {"op": "add_footnote", "paragraph": alpha, "text": "각주 본문"},
                    {"op": "add_endnote", "paragraph": beta, "text": "미주 본문"},
                ],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(result["changed"])
            mapped = build_annotation_apparatus_map(path)
            self.assertEqual(mapped["counts"]["footnotes"], 1)
            self.assertEqual(mapped["counts"]["endnotes"], 1)
            self.assertTrue(any("각주 본문" in item["text"] for item in mapped["footnotes"]))
            self.assertTrue(any("미주 본문" in item["text"] for item in mapped["endnotes"]))

    def test_memo_add_and_remove_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            beta = locator_for(path, "beta annotation target")
            added = apply_annotation_apparatus_atomic(
                path,
                [{"op": "add_memo", "paragraph": beta, "text": "검토 메모", "author": "P3.20"}],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(added["changed"])
            mapped = build_annotation_apparatus_map(path)
            self.assertEqual(mapped["counts"]["memos"], 1)
            self.assertTrue(any("검토 메모" in item["text"] for item in mapped["memos"]))

            removed = apply_annotation_apparatus_atomic(
                path,
                [{"op": "remove_memo", "memo_index": 0}],
                expected_revision=2,
                current_revision=2,
            )
            self.assertTrue(removed["changed"])
            self.assertEqual(build_annotation_apparatus_map(path)["counts"]["memos"], 0)

    def test_index_mark_one_and_two_key_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha reference target")
            beta = locator_for(path, "beta annotation target")
            apply_annotation_apparatus_atomic(
                path,
                [
                    {"op": "add_index_mark", "paragraph": alpha, "first": "과학"},
                    {
                        "op": "add_index_mark",
                        "paragraph": beta,
                        "first": "연구",
                        "second": "방법",
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            marks = build_annotation_apparatus_map(path)["index_marks"]
            self.assertEqual(len(marks), 2)
            self.assertIn(("과학", None), {(m["first"], m["second"]) for m in marks})
            self.assertIn(("연구", "방법"), {(m["first"], m["second"]) for m in marks})

    def test_bookmark_and_external_hyperlink_navigation_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha reference target")
            beta = locator_for(path, "beta annotation target")
            apply_annotation_apparatus_atomic(
                path,
                [
                    {"op": "add_bookmark", "paragraph": alpha, "name": "alpha-anchor"},
                    {
                        "op": "add_hyperlink",
                        "paragraph": beta,
                        "url": "https://example.com/reference",
                        "display_text": "외부 참고 자료",
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_annotation_apparatus_map(path)
            self.assertIn("alpha-anchor", {item["name"] for item in mapped["bookmarks"]})
            self.assertEqual(mapped["counts"]["hyperlinks"], 1)
            self.assertTrue(
                any(
                    "https://example.com/reference" in json.dumps(item["parameters"], ensure_ascii=False)
                    for item in mapped["hyperlinks"]
                )
            )

    def test_rich_reference_fields_roundtrip(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha reference target")
            beta = locator_for(path, "beta annotation target")
            apply_annotation_apparatus_atomic(
                path,
                [
                    {
                        "op": "add_date_field",
                        "paragraph": alpha,
                        "cached_text": "2026년 9월 21일",
                    },
                    {
                        "op": "add_path_field",
                        "paragraph": alpha,
                        "cached_text": "report.hwpx",
                    },
                    {
                        "op": "add_mail_merge_field",
                        "paragraph": beta,
                        "name": "student_name",
                    },
                    {"op": "add_proofreading_mark", "paragraph": beta, "mark": "space"},
                ],
                expected_revision=1,
                current_revision=1,
            )
            fields = build_annotation_apparatus_map(path)["rich_fields"]
            self.assertEqual(
                {item["type"] for item in fields},
                {"DATE", "PATH", "MAILMERGE", "PROOFREADING_MARKS_SIGN"},
            )
            payload = json.dumps(fields, ensure_ascii=False)
            self.assertIn("student_name", payload)
            self.assertIn("$F", payload)

    def test_invalid_operation_rolls_back_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            before = path.read_bytes()
            alpha = locator_for(path, "alpha reference target")
            with self.assertRaisesRegex(ValueError, "Unsupported annotation operation"):
                apply_annotation_apparatus_atomic(
                    path,
                    [
                        {"op": "add_index_mark", "paragraph": alpha, "first": "valid"},
                        {"op": "invent_annotation_magic"},
                    ],
                    expected_revision=1,
                    current_revision=1,
                )
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
