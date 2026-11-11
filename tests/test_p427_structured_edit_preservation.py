"""P4.27 R3: independent package-part + native-table edit preservation tests."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

from hwpx_mcp.custody.p427_structured_edit_preservation import (
    apply_bounded_table_edit_with_preservation_atomic,
)
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic,
    build_advanced_table_map,
)
from test_p427_nested_table_in_cell import make_nested_fixture, raw_nested_table_count


class NestedStructuredPreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p427-r3-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "before.hwpx"
        make_nested_fixture(self.path)

    def digest(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def edit(self, op, **kwargs):
        return apply_bounded_table_edit_with_preservation_atomic(
            self.path, op, expected_revision=2, current_revision=2, **kwargs,
        )

    def test_child_cell_edit_has_targeted_package_and_table_certificate(self):
        before = build_advanced_table_map(self.path)
        child = before["tables"][1]
        anchor = next(c for c in child["cells"] if (c["row"], c["col"]) == (0, 0))
        receipt = self.edit({
            "op": "set_cell_text", "table": child["locator"],
            "cell": anchor["locator"], "text": "Bounded R3 child edit",
        })
        self.assertEqual(receipt["preservation_enforcement"]["actual_grade"],
                         "TARGETED_PARTS_ONLY")
        self.assertEqual(receipt["semantic_preservation"]["tables_compared"], 2)
        self.assertGreaterEqual(receipt["unrelated_body_paragraphs_verified"], 2)
        self.assertEqual(receipt["semantic_preservation"]["unapproved_table_changes"], 0)
        self.assertEqual(raw_nested_table_count(self.path), 1)
        after = build_advanced_table_map(self.path)
        updated = next(c for c in after["tables"][1]["cells"]
                       if (c["row"], c["col"]) == (0, 0))
        self.assertEqual(updated["text"], "Bounded R3 child edit")

    def test_single_nested_child_metadata_edit_has_bounded_scope(self):
        child = build_advanced_table_map(self.path)["tables"][1]
        result = self.edit({
            "op": "set_table_page_break",
            "table": child["locator"], "mode": "TABLE",
        })
        self.assertEqual(result["preservation_enforcement"]["actual_grade"],
                         "TARGETED_PARTS_ONLY")
        self.assertEqual(build_advanced_table_map(self.path)["tables"][1]["page_break"],
                         "TABLE")

    def test_undisclosed_sibling_table_edit_rejects_and_preserves_original(self):
        before = self.digest()
        tables = build_advanced_table_map(self.path)["tables"]
        child_anchor = next(c for c in tables[1]["cells"]
                            if (c["row"], c["col"]) == (0, 0))
        parent_peer = next(c for c in tables[0]["cells"]
                           if (c["row"], c["col"]) == (0, 1))

        def corrupt_neighbor(candidate):
            apply_advanced_table_edits_atomic(
                candidate, [{
                    "op": "set_cell_text", "table": tables[0]["locator"],
                    "cell": parent_peer["locator"], "text": "UNDECLARED",
                }], expected_revision=2, current_revision=2,
            )

        with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_TABLE_SEMANTIC_DRIFT"):
            self.edit({
                "op": "set_cell_text", "table": tables[1]["locator"],
                "cell": child_anchor["locator"], "text": "Declared edit",
            }, candidate_validator=corrupt_neighbor)
        self.assertEqual(self.digest(), before)
        self.assertEqual(raw_nested_table_count(self.path), 1)

    def test_unrelated_body_paragraph_corruption_is_detected_atomically(self):
        source_digest = self.digest()
        child = build_advanced_table_map(self.path)["tables"][1]

        def corrupt_intro(candidate):
            staged = candidate.with_suffix(".rewritten.hwpx")
            with zipfile.ZipFile(candidate) as original, zipfile.ZipFile(staged, "w") as result:
                for info in original.infolist():
                    data = original.read(info.filename)
                    if (info.filename.startswith("Contents/section")
                            and info.filename.endswith(".xml")):
                        root = ET.fromstring(data)
                        hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
                        changed = False
                        for paragraph in list(root):
                            if paragraph.tag == hp + "p" and paragraph.find(".//" + hp + "tbl") is None:
                                first_text = paragraph.find(".//" + hp + "t")
                                if first_text is not None and first_text.text:
                                    first_text.text = "UNDECLARED BODY CHANGE"
                                    changed = True
                                    break
                        if changed:
                            data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    result.writestr(info, data)
            staged.replace(candidate)

        with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_BODY_PARAGRAPH_DRIFT"):
            self.edit({
                "op": "set_table_page_break",
                "table": child["locator"], "mode": "TABLE",
            }, candidate_validator=corrupt_intro)
        self.assertEqual(self.digest(), source_digest)

    def test_extra_zip_part_drift_rejected_without_committing(self):
        original = self.digest()
        child = build_advanced_table_map(self.path)["tables"][1]

        def add_unrelated_part(candidate):
            with zipfile.ZipFile(candidate, "a") as target:
                target.writestr("Contents/r3-unapproved.txt", "unexpected payload")

        with self.assertRaisesRegex(ValueError, "PRESERVATION_GRADE_NOT_MET"):
            self.edit({
                "op": "set_table_page_break",
                "table": child["locator"], "mode": "TABLE",
            }, candidate_validator=add_unrelated_part)
        self.assertEqual(self.digest(), original)

    def test_noop_refused_without_committing(self):
        original = self.digest()
        child = build_advanced_table_map(self.path)["tables"][1]
        anchor = next(c for c in child["cells"] if (c["row"], c["col"]) == (0, 0))
        with self.assertRaisesRegex(ValueError, "R3_TARGET_EDIT_NOT_OBSERVED"):
            self.edit({
                "op": "set_cell_text", "table": child["locator"],
                "cell": anchor["locator"], "text": anchor["text"],
            })
        self.assertEqual(self.digest(), original)

    def test_unadmitted_mutation_and_stale_revision_fail_closed(self):
        original = self.digest()
        child = build_advanced_table_map(self.path)["tables"][1]
        with self.assertRaisesRegex(ValueError, "R3_EDIT_OPERATION_NOT_ADMITTED"):
            self.edit({"op": "delete_table", "table": child["locator"]})
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            apply_bounded_table_edit_with_preservation_atomic(
                self.path,
                {"op": "set_table_page_break",
                 "table": child["locator"], "mode": "TABLE"},
                expected_revision=1, current_revision=2,
            )
        self.assertEqual(self.digest(), original)


if __name__ == "__main__":
    unittest.main()
