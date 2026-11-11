"""R2: genuinely nested HWPX table inside another table cell.

This is not two adjacent tables. Build authentic native table structures using
python-hwpx, then relocate the existing inner hp:tbl inside a native hp:tc
subList paragraph without adding any new table or binary resource.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from hwpx import HwpxDocument
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic, build_advanced_table_map,
)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def make_nested_fixture(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P4.27 nested table regression intro")
    outer = doc.add_table(rows=2, cols=2)
    outer.set_cell_text(0, 0, "Outer host")
    outer.set_cell_text(0, 1, "Outer peer")
    outer.set_cell_text(1, 0, "Outer lower")
    outer.set_cell_text(1, 1, "Outer final")
    doc.add_paragraph("Paragraph between original native table anchors")
    inner = doc.add_table(rows=2, cols=2)
    inner.set_cell_text(0, 0, "Inner unique anchor")
    inner.set_cell_text(0, 1, "Inner peer")
    inner.set_cell_text(1, 0, "Inner lower")
    inner.set_cell_text(1, 1, "Inner final")
    doc.add_paragraph("P4.27 nested table regression outro")
    doc.save_to_path(str(path))
    doc.close()

    replacement = path.with_name("nested-patched.hwpx")
    modified = False
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(replacement, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                root = ET.fromstring(data)
                tables = root.findall(f".//{HP}tbl")
                if len(tables) == 2:
                    outer_node, inner_node = tables
                    host_cell = outer_node.find(f".//{HP}tc")
                    if host_cell is None:
                        raise AssertionError("NESTED_FIXTURE_MISSING_CELL")
                    host_paragraph = host_cell.find(f"{HP}subList/{HP}p")
                    if host_paragraph is None:
                        raise AssertionError("NESTED_FIXTURE_MISSING_CELL_PARAGRAPH")
                    host_run = host_paragraph.find(f"{HP}run")
                    if host_run is None:
                        raise AssertionError("NESTED_FIXTURE_MISSING_CELL_RUN")
                    parents = {child: parent for parent in root.iter() for child in parent}
                    parents[inner_node].remove(inner_node)
                    host_run.append(inner_node)
                    assert host_cell in list(_ancestors(root, inner_node))
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    modified = True
            target.writestr(info, data)
    if not modified:
        raise AssertionError("NESTED_FIXTURE_REQUIRES_TWO_NATIVE_TABLES")
    replacement.replace(path)


def _ancestors(root: ET.Element, child: ET.Element):
    parents = {sub: par for par in root.iter() for sub in par}
    node = child
    while node in parents:
        node = parents[node]
        yield node


def raw_nested_table_count(path: Path) -> int:
    for_section = []
    with zipfile.ZipFile(path) as container:
        for name in container.namelist():
            if name.startswith("Contents/section") and name.endswith(".xml"):
                root = ET.fromstring(container.read(name))
                for table in root.findall(f".//{HP}tbl"):
                    if any(ancestor.tag == HP + "tc" for ancestor in _ancestors(root, table)):
                        for_section.append(table)
    return len(for_section)


class ActualNestedTableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p427-r2-nested-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "actual-nested.hwpx"
        make_nested_fixture(self.path)

    def test_nested_table_is_inside_cell_and_reader_finds_both(self):
        self.assertEqual(raw_nested_table_count(self.path), 1)
        table_map = build_advanced_table_map(self.path)
        self.assertEqual(table_map["table_count"], 2)
        self.assertEqual([table["table_index"] for table in table_map["tables"]], [0, 1])
        self.assertTrue(any(cell["text"] == "Inner unique anchor"
                            for cell in table_map["tables"][1]["cells"]))

    def test_edit_inner_table_native_metadata_preserves_outer_and_nesting(self):
        before = build_advanced_table_map(self.path)
        self.assertEqual(raw_nested_table_count(self.path), 1)
        outer_before = [(c["row"], c["col"], c["text"], c["row_span"], c["col_span"])
                        for c in before["tables"][0]["cells"]]
        inner_locator = before["tables"][1]["locator"]
        result = apply_advanced_table_edits_atomic(
            self.path,
            [{"op": "set_table_page_break", "table": inner_locator, "mode": "TABLE"}],
            expected_revision=1, current_revision=1,
        )
        self.assertEqual(result["operation_count"], 1)
        self.assertEqual(raw_nested_table_count(self.path), 1)
        after = build_advanced_table_map(self.path)
        self.assertEqual(after["tables"][1]["page_break"], "TABLE")
        outer_after = [(c["row"], c["col"], c["text"], c["row_span"], c["col_span"])
                       for c in after["tables"][0]["cells"]]
        self.assertEqual(outer_after, outer_before)


    def test_nested_child_cell_text_edit_preserves_parent_cell_values(self):
        before = build_advanced_table_map(self.path)
        parent, child = before["tables"]
        parent_cells = [
            (c["row"], c["col"], c["text"], c["row_span"], c["col_span"])
            for c in parent["cells"]
        ]
        unchanged_child_cells = {
            (c["row"], c["col"]): c["text"]
            for c in child["cells"] if (c["row"], c["col"]) != (0, 0)
        }
        child_anchor = next(
            c for c in child["cells"] if c["row"] == 0 and c["col"] == 0
        )
        self.assertEqual(child_anchor["text"], "Inner unique anchor")
        self.assertEqual(raw_nested_table_count(self.path), 1)
        apply_advanced_table_edits_atomic(
            self.path,
            [{"op": "set_cell_text", "table": child["locator"],
              "cell": child_anchor["locator"],
              "text": "Inner edited in nested cell"}],
            expected_revision=1, current_revision=1,
        )
        after = build_advanced_table_map(self.path)
        self.assertEqual(raw_nested_table_count(self.path), 1)
        self.assertEqual(
            [(c["row"], c["col"], c["text"], c["row_span"], c["col_span"])
             for c in after["tables"][0]["cells"]],
            parent_cells,
        )
        updated = next(
            c for c in after["tables"][1]["cells"] if c["row"] == 0 and c["col"] == 0
        )
        self.assertEqual(updated["text"], "Inner edited in nested cell")
        for c in after["tables"][1]["cells"]:
            if (c["row"], c["col"]) != (0, 0):
                self.assertEqual(c["text"], unchanged_child_cells[(c["row"], c["col"])])


    def test_rejects_replacing_nested_table_host_cell_without_data_loss(self):
        before_bytes = self.path.read_bytes()
        before_sha = hashlib.sha256(before_bytes).hexdigest()
        parent = build_advanced_table_map(self.path)["tables"][0]
        host_cell = next(c for c in parent["cells"]
                         if (c["row"], c["col"]) == (0, 0))
        with self.assertRaisesRegex(ValueError, "NESTED_TABLE_HOST_CELL_TEXT_EDIT_DEFERRED"):
            apply_advanced_table_edits_atomic(
                self.path,
                [{"op": "set_cell_text", "table": parent["locator"],
                  "cell": host_cell["locator"], "text": "would delete inner table"}],
                expected_revision=1, current_revision=1,
            )
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before_sha)
        self.assertEqual(raw_nested_table_count(self.path), 1)


if __name__ == "__main__":
    unittest.main()
