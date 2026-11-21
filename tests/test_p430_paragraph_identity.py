import tempfile
import unittest
import zipfile
from pathlib import Path

from hwpx_mcp.document.p2_document import apply_edits_atomic, build_document_map


class ParagraphIdentityTests(unittest.TestCase):
    def test_repeated_ids_and_nested_text_have_independent_edit_targets(self):
        xml = """<section><p id="0"><run><t>outer</t><tbl><tc><p id="0">
        <run><t>cell</t></run></p></tc></tbl></run></p><p id="9">
        <run><t>last</t></run></p></section>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.hwpx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Contents/section0.xml", xml)
            before = build_document_map(path)["paragraphs"]
            self.assertEqual(len({p["locator"] for p in before}), 3)
            self.assertEqual([p["address_stability"] for p in before],
                             ["revision-bound-ordinal", "revision-bound-ordinal", "intrinsic-id"])
            receipt = apply_edits_atomic(path, [
                {"op": "replace_paragraph_text", "target": before[0]["locator"], "text": "edited"}
            ], expected_revision=1, current_revision=1)
            after = build_document_map(path)["paragraphs"]
            self.assertEqual([p["text"] for p in after], ["edited", "cell", "last"])
            self.assertEqual(receipt["locator_rebinding"]["invalidated_revision_bound_locators"],
                             [p["locator"] for p in before[:2]])

    def test_spine_order_precedes_numeric_fallback_for_unlisted_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ordered.hwpx"
            with zipfile.ZipFile(path, "w") as archive:
                for n in (0, 1, 10, 2):
                    archive.writestr(f"Contents/section{n}.xml", f"<s><p><t>{n}</t></p></s>")
                archive.writestr("Contents/content.hpf", """<package xmlns="urn:opf"><manifest>
                    <item id="a" href="Contents/section1.xml"/><item id="b" href="section0.xml"/>
                    </manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>""")
            self.assertEqual(build_document_map(path)["text"].splitlines(), ["1", "0", "2", "10"])
