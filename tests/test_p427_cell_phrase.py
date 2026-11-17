"""Native XML contract for an unambiguous phrase correction."""
import unittest
from xml.etree import ElementTree as ET

from hwpx_mcp.document.p427_cell_phrase import (
    HP, replace_phrase_in_plain_node, validate_phrase_operation,
)


class CellPhraseTests(unittest.TestCase):
    def paragraph(self):
        paragraph = ET.Element(HP + "p")
        bold = ET.SubElement(paragraph, HP + "run", {"charPrIDRef": "4"})
        ET.SubElement(bold, HP + "t").text = "결과: "
        normal = ET.SubElement(paragraph, HP + "run", {"charPrIDRef": "0"})
        ET.SubElement(normal, HP + "t").text = "값을 교정한다"
        equation = ET.SubElement(normal, HP + "equation")
        ET.SubElement(equation, HP + "script").text = "x+y"
        return paragraph

    def test_updates_one_text_node_and_invalidates_layout(self):
        paragraph = self.paragraph()
        ET.SubElement(paragraph, HP + "linesegarray")
        replace_phrase_in_plain_node(paragraph, "교정", "비교")
        self.assertEqual([node.text for node in paragraph.iter(HP + "t")],
                         ["결과: ", "값을 비교한다"])
        self.assertEqual([run.get("charPrIDRef") for run in paragraph.findall(HP + "run")],
                         ["4", "0"])
        self.assertEqual(paragraph.findtext(".//" + HP + "script"), "x+y")
        self.assertIsNone(paragraph.find(HP + "linesegarray"))

    def test_rejects_ambiguous_and_cross_run_phrases_without_mutation(self):
        for old, code in (("과: 값", "CROSSES_RUNS"), ("을", "NOT_UNIQUE")):
            with self.subTest(old=old):
                paragraph = self.paragraph()
                paragraph[0][0].text += "을 "
                if old == "과: 값":
                    paragraph[0][0].text = "결과: "
                original = ET.tostring(paragraph)
                with self.assertRaisesRegex(ValueError, code):
                    replace_phrase_in_plain_node(paragraph, old, "수정")
                self.assertEqual(ET.tostring(paragraph), original)

    def test_rejects_both_native_tab_forms_without_mutation(self):
        for tag, attributes in (("tab", {}), ("ctrl", {"id": "tab"})):
            with self.subTest(tag=tag):
                paragraph = self.paragraph()
                paragraph[1].insert(0, ET.Element(HP + tag, attributes))
                original = ET.tostring(paragraph)
                with self.assertRaisesRegex(ValueError, "P427_CELL_MIXED_TEXT_UNSUPPORTED"):
                    replace_phrase_in_plain_node(paragraph, "교정", "비교")
                self.assertEqual(ET.tostring(paragraph), original)

    def test_rejects_invalid_indices_and_replacements(self):
        for args in ({"paragraph_index": True}, {"old_text": ""},
                     {"new_text": "\t"}, {"new_text": "기존"}):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    validate_phrase_operation({
                        "paragraph_index": 0, "old_text": "기존", "new_text": "", **args,
                    })
