from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p318_document_setup import (
    apply_document_setup_atomic,
    build_document_setup_map,
)


def make_doc(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.18 document setup")
    doc.add_paragraph("alpha")
    doc.add_paragraph("beta")
    doc.save_to_path(str(path))
    doc.close()


class P318DocumentSetupTests(unittest.TestCase):
    def test_page_setup_orientation_and_columns_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            result = apply_document_setup_atomic(
                path,
                [
                    {
                        "op": "set_page_setup",
                        "section_index": 0,
                        "paper_size": "A4",
                        "orientation": "LANDSCAPE",
                        "margin_left_mm": 18,
                        "margin_right_mm": 18,
                    },
                    {
                        "op": "set_columns",
                        "section_index": 0,
                        "count": 2,
                        "same_gap": 1200,
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_document_setup_map(path)
            section = mapped["sections"][0]
            self.assertTrue(result["document_setup_changed"])
            self.assertGreater(section["page"]["width"], section["page"]["height"])
            self.assertTrue(section["column_definitions"])
            self.assertEqual(
                section["column_definitions"][-1]["attrs"].get("colCount"), "2"
            )

    def test_header_footer_and_page_number_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            apply_document_setup_atomic(
                path,
                [
                    {
                        "op": "set_header",
                        "section_index": 0,
                        "page_type": "BOTH",
                        "text": "P3.18 Header",
                    },
                    {
                        "op": "set_footer",
                        "section_index": 0,
                        "page_type": "ODD",
                        "text": "Internal",
                    },
                    {
                        "op": "set_page_number",
                        "section_index": 0,
                        "target": "footer",
                        "page_type": "BOTH",
                        "prefix": "p. ",
                        "position": "BOTTOM_CENTER",
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_document_setup_map(path)
            stories = mapped["sections"][0]["stories"]
            self.assertTrue(
                any(item["kind"] == "header" and "P3.18 Header" in item["text"] for item in stories)
            )
            self.assertTrue(
                any(item["kind"] == "footer" and item["page_number_fields"] for item in stories)
            )

    def test_add_and_remove_section_are_real_section_topology_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            added = apply_document_setup_atomic(
                path,
                [{"op": "add_section", "after": 0, "text": "second section"}],
                expected_revision=1,
                current_revision=1,
            )
            self.assertEqual(added["after"]["section_count"], 2)
            self.assertEqual(build_document_setup_map(path)["section_count"], 2)
            self.assertTrue(
                any(p["text"] == "second section" for p in build_document_map(path)["paragraphs"])
            )

            removed = apply_document_setup_atomic(
                path,
                [{"op": "remove_section", "section_index": 1}],
                expected_revision=2,
                current_revision=2,
            )
            self.assertEqual(removed["after"]["section_count"], 1)

    def test_page_number_restart_control_and_section_start_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            paragraph = next(
                p for p in build_document_map(path)["paragraphs"] if p["text"] == "alpha"
            )
            apply_document_setup_atomic(
                path,
                [
                    {
                        "op": "set_section_start_numbering",
                        "section_index": 0,
                        "page_starts_on": "ODD",
                        "page": 3,
                    },
                    {
                        "op": "restart_page_number",
                        "paragraph": paragraph["locator"],
                        "number": 7,
                    },
                ],
                expected_revision=1,
                current_revision=1,
            )
            section = build_document_setup_map(path)["sections"][0]
            self.assertEqual(section["start_numbering"].get("page"), "3")
            self.assertTrue(
                any(
                    item.get("num") == "7" and item.get("numType") == "PAGE"
                    for item in section["number_restarts"]
                )
            )

    def test_invalid_operation_rolls_back_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.hwpx"
            make_doc(path)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Unsupported document-setup operation"):
                apply_document_setup_atomic(
                    path,
                    [
                        {"op": "set_header", "text": "would change"},
                        {"op": "mystery_setup"},
                    ],
                    expected_revision=1,
                    current_revision=1,
                )
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
