"""P4.27 R3: independent package-part + native-table edit preservation tests."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.tools.table_navigation import _collect_document_tables

from hwpx_mcp.custody.p427_structured_edit_preservation import (
    apply_bounded_table_edit_with_preservation_atomic,
)
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic,
    build_advanced_table_map,
)
from test_p427_nested_table_in_cell import HP, make_nested_fixture, raw_nested_table_count


def rewrite_table_anchor(path, section_path, change):
    staged = path.with_suffix(".rewritten.hwpx")
    with zipfile.ZipFile(path) as original, zipfile.ZipFile(staged, "w") as result:
        for info in original.infolist():
            data = original.read(info)
            if info.filename == section_path:
                root = ET.fromstring(data)
                paragraph = next(p for p in root.findall(HP + "p")
                                 if p.find(".//" + HP + "tbl") is not None)
                run = next(r for r in paragraph.findall(HP + "run")
                           if r.find(".//" + HP + "tbl") is not None)
                change(run)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            result.writestr(info, data)
    staged.replace(path)


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
        self.assertEqual(receipt["unrelated_cells_verified"], 7)
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

    def test_mixed_content_table_anchor_survives_nested_cell_edit(self):
        child = build_advanced_table_map(self.path)["tables"][1]

        def add_anchor_text(run):
            text = ET.Element(HP + "t")
            text.text = "Text before the table"
            run.insert(0, text)
            ET.SubElement(run, HP + "t").text = "Text after the table"

        rewrite_table_anchor(self.path, child["section_path"], add_anchor_text)
        receipt = self.edit({
            "op": "set_cell_text", "table": child["locator"],
            "cell": child["cells"][0]["locator"], "text": "Nested edit",
        })
        self.assertEqual(receipt["table_anchor_paragraphs_verified"], 1)
        self.assertEqual(receipt["nested_table_anchor_paragraphs_verified"], 1)
        self.assertEqual(raw_nested_table_count(self.path), 1)
        self.assertEqual(build_advanced_table_map(self.path)["tables"][1]["cells"][0]["text"],
                         "Nested edit")

    def test_table_anchor_text_or_run_style_drift_rejects_without_committing(self):
        def add_anchor_text(run):
            ET.SubElement(run, HP + "t").text = "Keep this text"

        def change_text(run):
            run.findall(HP + "t")[-1].text = "Undeclared text change"

        def change_style(run):
            run.set("charPrIDRef", "1" if run.get("charPrIDRef") == "0" else "0")

        for change in (change_text, change_style):
            with self.subTest(change=change.__name__):
                make_nested_fixture(self.path)
                child = build_advanced_table_map(self.path)["tables"][1]
                rewrite_table_anchor(self.path, child["section_path"], add_anchor_text)
                original = self.path.read_bytes()
                with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_TABLE_ANCHOR_PARAGRAPH_DRIFT"):
                    self.edit({
                        "op": "set_table_page_break", "table": child["locator"], "mode": "TABLE",
                    }, candidate_validator=lambda candidate: rewrite_table_anchor(
                        candidate, child["section_path"], change,
                    ))
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(list(self.path.parent.glob("*.p427-preserved-*.hwpx")), [])

    def test_nested_table_host_run_format_is_preserved(self):
        child = build_advanced_table_map(self.path)["tables"][1]
        original = self.path.read_bytes()

        def change_nested_run(outer_run):
            nested_run = next(run for run in outer_run.iter(HP + "run")
                              if run is not outer_run and run.find(HP + "tbl") is not None)
            nested_run.set("charPrIDRef", "1" if nested_run.get("charPrIDRef") == "0" else "0")

        with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_NESTED_TABLE_ANCHOR_DRIFT"):
            self.edit({
                "op": "set_table_page_break", "table": child["locator"], "mode": "TABLE",
            }, candidate_validator=lambda candidate: rewrite_table_anchor(
                candidate, child["section_path"], change_nested_run,
            ))
        self.assertEqual(self.path.read_bytes(), original)

    def test_target_cell_edit_preserves_native_equation_and_rejects_script_drift(self):
        document = HwpxDocument.open(str(self.path))
        try:
            table = _collect_document_tables(document)[1].table
            table.cell(0, 0).paragraphs[0].add_equation("x + y")
            document.save_to_path(str(self.path))
        finally:
            document.close()

        child = build_advanced_table_map(self.path)["tables"][1]
        operation = {
            "op": "set_cell_text", "table": child["locator"],
            "cell": child["cells"][0]["locator"], "text": "교정한 설명",
        }
        original = self.path.read_bytes()

        def change_script(outer_run):
            outer_run.find(".//" + HP + "script").text = "x - y"

        def change_equation_run_style(outer_run):
            run = next(item for item in outer_run.iter(HP + "run")
                       if item.find(HP + "equation") is not None)
            run.set("charPrIDRef", "1" if run.get("charPrIDRef") == "0" else "0")

        for change in (change_script, change_equation_run_style):
            with self.subTest(change=change.__name__):
                with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_TARGET_CELL_OBJECT_DRIFT"):
                    self.edit(operation, candidate_validator=lambda candidate: rewrite_table_anchor(
                        candidate, child["section_path"], change,
                    ))
                self.assertEqual(self.path.read_bytes(), original)

        result = self.edit(operation)
        self.assertEqual(result["target_cell_inline_objects_verified"], 1)
        with zipfile.ZipFile(self.path) as archive:
            root = ET.fromstring(archive.read(child["section_path"]))
        self.assertEqual(root.findtext(".//" + HP + "script"), "x + y")
        self.assertEqual(build_advanced_table_map(self.path)["tables"][1]["cells"][0]["text"],
                         operation["text"])

    def test_target_cell_edit_preserves_run_style_and_allows_native_reflow(self):
        child = build_advanced_table_map(self.path)["tables"][1]

        def target_sublist(outer_run):
            table = outer_run.findall(".//" + HP + "tbl")[-1]
            return table.find(f"{HP}tr/{HP}tc/{HP}subList")

        def squeeze(outer_run):
            target_sublist(outer_run).set("lineWrap", "SQUEEZE")

        rewrite_table_anchor(self.path, child["section_path"], squeeze)
        original = self.path.read_bytes()
        operation = {
            "op": "set_cell_text", "table": child["locator"],
            "cell": child["cells"][0]["locator"], "text": "새 글",
        }

        def change_style(outer_run):
            target_sublist(outer_run).find(f"{HP}p/{HP}run").set("charPrIDRef", "1")

        with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_TARGET_CELL_FORMAT_DRIFT:first_run"):
            self.edit(operation, candidate_validator=lambda candidate: rewrite_table_anchor(
                candidate, child["section_path"], change_style,
            ))
        self.assertEqual(self.path.read_bytes(), original)

        self.edit(operation)
        with zipfile.ZipFile(self.path) as archive:
            root = ET.fromstring(archive.read(child["section_path"]))
        outer_run = next(run for run in root.iter(HP + "run") if run.find(HP + "tbl") is not None)
        self.assertEqual(target_sublist(outer_run).get("lineWrap"), "BREAK")
        self.assertEqual(target_sublist(outer_run).find(f"{HP}p/{HP}run").get("charPrIDRef"), "0")

    def test_target_cell_replacement_can_change_text_spacing_controls(self):
        child = build_advanced_table_map(self.path)["tables"][1]

        def add_line_break(outer_run):
            table = outer_run.findall(".//" + HP + "tbl")[-1]
            text = table.find(f"{HP}tr/{HP}tc/{HP}subList/{HP}p/{HP}run/{HP}t")
            ET.SubElement(text, HP + "lineBreak").tail = "다음 줄"

        rewrite_table_anchor(self.path, child["section_path"], add_line_break)
        replacement = "항목\t한글 값"
        result = self.edit({
            "op": "set_cell_text", "table": child["locator"],
            "cell": child["cells"][0]["locator"], "text": replacement,
        })
        self.assertEqual(result["target_cell_inline_objects_verified"], 0)
        self.assertEqual(build_advanced_table_map(self.path)["tables"][1]["cells"][0]["text"],
                         replacement)

    def test_phrase_edit_preserves_both_styled_runs_and_rejects_late_drift(self):
        document = HwpxDocument.open(str(self.path))
        try:
            paragraph = _collect_document_tables(document)[1].table.cell(0, 0).paragraphs[0]
            paragraph.add_run(" / 교정 전", char_pr_id_ref="1")
            paragraph.add_equation("a + b")
            document.save_to_path(str(self.path))
        finally:
            document.close()

        child = build_advanced_table_map(self.path)["tables"][1]
        operation = {
            "op": "replace_cell_phrase", "table": child["locator"],
            "cell": child["cells"][0]["locator"], "paragraph_index": 0,
            "old_text": "교정 전", "new_text": "교정 완료",
        }
        original = self.path.read_bytes()

        def change_style(outer_run):
            run = next(run for run in outer_run.iter(HP + "run")
                       if run.findtext(HP + "t") == " / 교정 완료")
            run.set("charPrIDRef", "0")

        with self.assertRaisesRegex(ValueError, "P427_UNDECLARED_PHRASE_CELL_DRIFT"):
            self.edit(operation, candidate_validator=lambda candidate: rewrite_table_anchor(
                candidate, child["section_path"], change_style,
            ))
        self.assertEqual(self.path.read_bytes(), original)

        receipt = self.edit(operation)
        self.assertEqual(receipt["target_cell_inline_objects_verified"], 1)
        with zipfile.ZipFile(self.path) as archive:
            root = ET.fromstring(archive.read(child["section_path"]))
        runs = {run.findtext(HP + "t"): run.get("charPrIDRef") for run in root.iter(HP + "run")}
        self.assertEqual(runs["Inner unique anchor"], "0")
        self.assertEqual(runs[" / 교정 완료"], "1")
        self.assertEqual(root.findtext(".//" + HP + "script"), "a + b")

    def test_phrase_index_selects_second_paragraph_with_the_same_words(self):
        document = HwpxDocument.open(str(self.path))
        try:
            cell = _collect_document_tables(document)[1].table.cell(0, 0)
            cell.add_paragraph("Inner unique anchor")
            document.save_to_path(str(self.path))
        finally:
            document.close()
        child = build_advanced_table_map(self.path)["tables"][1]
        self.edit({
            "op": "replace_cell_phrase", "table": child["locator"],
            "cell": child["cells"][0]["locator"], "paragraph_index": 1,
            "old_text": "Inner", "new_text": "Updated",
        })
        edited = build_advanced_table_map(self.path)["tables"][1]["cells"][0]
        self.assertEqual(edited["text"], "Inner unique anchor\nUpdated unique anchor")

    def test_phrase_edit_rejects_out_of_range_paragraph_without_committing(self):
        child = build_advanced_table_map(self.path)["tables"][1]
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "P427_CELL_PARAGRAPH_INDEX_INVALID"):
            self.edit({
                "op": "replace_cell_phrase", "table": child["locator"],
                "cell": child["cells"][0]["locator"], "paragraph_index": 1,
                "old_text": "Inner", "new_text": "Updated",
            })
        self.assertEqual(self.path.read_bytes(), original)

    def test_unrelated_cell_run_style_change_preserves_original(self):
        child = build_advanced_table_map(self.path)["tables"][1]
        original = self.path.read_bytes()

        def change_peer_style(outer_run):
            peer_text = next(text for text in outer_run.iter(HP + "t")
                             if text.text == "Inner peer")
            peer_run = next(run for run in outer_run.iter(HP + "run")
                            if peer_text in list(run))
            peer_run.set("charPrIDRef", "1" if peer_run.get("charPrIDRef") == "0" else "0")

        with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_CELL_XML_DRIFT"):
            self.edit({
                "op": "set_cell_text", "table": child["locator"],
                "cell": child["cells"][0]["locator"], "text": "Declared edit",
            }, candidate_validator=lambda candidate: rewrite_table_anchor(
                candidate, child["section_path"], change_peer_style,
            ))
        self.assertEqual(self.path.read_bytes(), original)

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

    def test_unrelated_body_text_and_inline_markup_are_preserved_atomically(self):
        source_digest = self.digest()
        child = build_advanced_table_map(self.path)["tables"][1]

        def corrupt_intro(candidate, change):
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
                                    change(first_text)
                                    changed = True
                                    break
                        if changed:
                            data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    result.writestr(info, data)
            staged.replace(candidate)

        def change_text(text):
            text.text = "UNDECLARED BODY CHANGE"

        def insert_line_break(text):
            ET.SubElement(text, HP + "lineBreak")

        for change in (change_text, insert_line_break):
            with self.subTest(change=change.__name__):
                with self.assertRaisesRegex(ValueError, "R3_UNDECLARED_BODY_PARAGRAPH_DRIFT"):
                    self.edit({
                        "op": "set_table_page_break",
                        "table": child["locator"], "mode": "TABLE",
                    }, candidate_validator=lambda candidate: corrupt_intro(candidate, change))
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

    def test_both_edit_operations_reject_shared_header_drift(self):
        original = self.path.read_bytes()
        child = build_advanced_table_map(self.path)["tables"][1]

        def rewrite_header(candidate):
            staged = candidate.with_suffix(".rewritten.hwpx")
            with zipfile.ZipFile(candidate) as source, zipfile.ZipFile(staged, "w") as result:
                for info in source.infolist():
                    data = source.read(info)
                    if info.filename == "Contents/header.xml":
                        data += b"\n<!-- unexpected header rewrite -->"
                    result.writestr(info, data)
            staged.replace(candidate)

        operations = [
            {"op": "set_table_page_break", "table": child["locator"], "mode": "TABLE"},
            {"op": "set_cell_text", "table": child["locator"],
             "cell": child["cells"][0]["locator"], "text": "새 값"},
        ]
        for operation in operations:
            with self.subTest(operation=operation["op"]):
                with self.assertRaisesRegex(ValueError, "PRESERVATION_GRADE_NOT_MET"):
                    self.edit(operation, candidate_validator=rewrite_header)
                self.assertEqual(self.path.read_bytes(), original)

    def test_validation_receipt_must_identify_the_candidate_bytes(self):
        original = self.path.read_bytes()
        child = build_advanced_table_map(self.path)["tables"][1]
        operation = {"op": "set_table_page_break", "table": child["locator"], "mode": "TABLE"}

        with self.assertRaisesRegex(ValueError, "R3_PACKAGE_VALIDATION_SHA256_MISMATCH"):
            self.edit(operation, candidate_validator=lambda _: {"sha256": self.digest()})
        self.assertEqual(self.path.read_bytes(), original)

        result = self.edit(operation, candidate_validator=lambda candidate: {
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        })
        self.assertEqual(result["committed_sha256"], self.digest())
        self.assertEqual(result["package_validation"]["sha256"], self.digest())
        self.assertEqual(result["mutation_footprint"]["after"]["package_sha256"], self.digest())

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

    def test_malformed_operation_names_are_rejected_before_staging(self):
        original = self.path.read_bytes()
        for name in (None, 7, [], {}):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "R3_EDIT_OPERATION_NOT_ADMITTED"):
                    self.edit({"op": name})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.p427-preserved-*.hwpx")), [])


if __name__ == "__main__":
    unittest.main()
