from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

import server
from p2_document import build_document_map
from p322_review_workflow import apply_review_workflow_atomic, build_review_workflow_map


def make_doc(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.22 review workflow")
    doc.add_paragraph("alpha review target")
    doc.add_paragraph("beta form target")
    doc.save_to_path(str(path))
    doc.close()


def locator_for(path: Path, text: str) -> str:
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


class P322ReviewWorkflowTests(unittest.TestCase):
    def test_tracked_replace_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha review target")
            result = apply_review_workflow_atomic(
                path,
                [{
                    "op": "tracked_replace",
                    "paragraph": alpha,
                    "old": "review",
                    "new": "revision",
                    "author": "Reviewer A",
                    "date": "2026-09-21T07:00:00Z",
                }],
                expected_revision=1,
                current_revision=1,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            self.assertTrue(result["changed"])
            mapped = build_review_workflow_map(path)
            self.assertEqual(mapped["counts"]["tracked_changes"], 2)
            self.assertEqual(mapped["counts"]["track_change_authors"], 1)
            self.assertIn("Reviewer A", {a["name"] for a in mapped["track_change_authors"]})

    def test_form_field_create_and_fill(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            beta = locator_for(path, "beta form target")
            apply_review_workflow_atomic(
                path,
                [{
                    "op": "add_form_field",
                    "paragraph": beta,
                    "name": "student_name",
                    "prompt": "이름 입력",
                    "memo": "학생 이름",
                    "editable": True,
                }],
                expected_revision=1,
                current_revision=1,
            )
            first = build_review_workflow_map(path)
            self.assertEqual(first["counts"]["form_fields"], 1)
            self.assertEqual(first["form_fields"][0]["name"], "student_name")

            apply_review_workflow_atomic(
                path,
                [{
                    "op": "fill_form_field",
                    "name": "student_name",
                    "value": "김우준",
                }],
                expected_revision=2,
                current_revision=2,
            )
            second = build_review_workflow_map(path)
            self.assertEqual(second["form_fields"][0]["value"], "김우준")
            self.assertFalse(second["form_fields"][0]["is_placeholder"])

    def test_checkbox_create_and_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            beta = locator_for(path, "beta form target")
            apply_review_workflow_atomic(
                path,
                [{
                    "op": "add_check_box",
                    "paragraph": beta,
                    "caption": "검토 완료",
                    "name": "review_done",
                    "checked": False,
                }],
                expected_revision=1,
                current_revision=1,
            )
            self.assertFalse(build_review_workflow_map(path)["check_boxes"][0]["checked"])
            apply_review_workflow_atomic(
                path,
                [{
                    "op": "set_check_box",
                    "name": "review_done",
                    "checked": True,
                }],
                expected_revision=2,
                current_revision=2,
            )
            self.assertTrue(build_review_workflow_map(path)["check_boxes"][0]["checked"])

    def test_highlight_and_proofreading_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            alpha = locator_for(path, "alpha review target")
            result = apply_review_workflow_atomic(
                path,
                [
                    {
                        "op": "add_highlight",
                        "paragraph": alpha,
                        "match": "alpha",
                        "color": "#FFF200",
                    },
                    {
                        "op": "add_proofreading_mark",
                        "paragraph": alpha,
                        "mark": "space",
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(result["changed"])
            mapped = build_review_workflow_map(path)
            self.assertEqual(mapped["counts"]["highlights"], 1)
            self.assertEqual(mapped["highlights"][0]["text"], "alpha")
            self.assertEqual(mapped["highlights"][0]["color"], "#FFF200")

    def test_document_metadata_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            apply_review_workflow_atomic(
                path,
                [{
                    "op": "set_document_metadata",
                    "title": "전자기학 검토본",
                    "creator": "P3.22",
                    "subject": "review workflow",
                    "keyword": "HWPX,review",
                    "created_date": "2026-09-21T07:00:00Z",
                    "modified_date": "2026-09-21T07:05:00Z",
                }],
                expected_revision=1,
                current_revision=1,
            )
            meta = build_review_workflow_map(path)["metadata"]
            self.assertIsNotNone(meta)
            self.assertEqual(meta["title"], "전자기학 검토본")
            self.assertEqual(meta["creator"], "P3.22")
            self.assertEqual(meta["subject"], "review workflow")
            self.assertEqual(meta["keyword"], "HWPX,review")

    def test_mixed_failure_rolls_back_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            before = path.read_bytes()
            alpha = locator_for(path, "alpha review target")
            with self.assertRaisesRegex(ValueError, "Unsupported review operation"):
                apply_review_workflow_atomic(
                    path,
                    [
                        {
                            "op": "add_highlight",
                            "paragraph": alpha,
                            "match": "alpha",
                        },
                        {"op": "invent_review_magic"},
                    ],
                    expected_revision=1,
                    current_revision=1,
                )
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
