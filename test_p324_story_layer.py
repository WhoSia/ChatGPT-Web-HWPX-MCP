from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p324_story_layer import (
    apply_story_layer_atomic,
    build_story_layer_map,
    story_layer_contract,
)


class P324StoryLayerTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        path = root / "story-layer.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.24 story layer")
        doc.add_paragraph("body")
        doc.save_to_path(str(path))
        doc.close()
        return path

    def test_odd_even_and_first_page_policy_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            result = apply_story_layer_atomic(
                path,
                [
                    {
                        "op": "set_story_variant",
                        "section_index": 0,
                        "kind": "header",
                        "page_type": "ODD",
                        "text": "Odd Header",
                    },
                    {
                        "op": "set_story_variant",
                        "section_index": 0,
                        "kind": "header",
                        "page_type": "EVEN",
                        "text": "Even Header",
                    },
                    {
                        "op": "set_page_number_variant",
                        "section_index": 0,
                        "target": "footer",
                        "page_type": "ODD",
                        "prefix": "O-",
                    },
                    {
                        "op": "set_first_page_policy",
                        "section_index": 0,
                        "hide_header": True,
                        "hide_footer": False,
                        "hide_page_number": True,
                    },
                ],
                expected_revision=2,
                current_revision=2,
            )
            self.assertTrue(result["story_layer_changed"])

            reopened = HwpxDocument.open(str(path))
            reopened.close()
            mapped = build_story_layer_map(path)
            section = mapped["sections"][0]
            self.assertEqual(
                section["first_page_policy"],
                {"hide_header": True, "hide_footer": False, "hide_page_number": True},
            )
            stories = {(s["kind"], s["page_type"]): s for s in section["stories"]}
            self.assertEqual(stories[("header", "ODD")]["text"], "Odd Header")
            self.assertEqual(stories[("header", "EVEN")]["text"], "Even Header")
            self.assertTrue(stories[("header", "ODD")]["linkage_exact"])
            self.assertTrue(stories[("header", "EVEN")]["linkage_exact"])
            self.assertIn(("footer", "ODD"), stories)
            self.assertGreaterEqual(len(stories[("footer", "ODD")]["page_number_fields"]), 1)

    def test_section_boundary_story_configuration_is_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            apply_story_layer_atomic(
                path,
                [{
                    "op": "add_section_boundary",
                    "after": 0,
                    "text": "section two",
                    "first_page_policy": {
                        "hide_header": True,
                        "hide_footer": True,
                        "hide_page_number": False,
                    },
                    "stories": [
                        {"kind": "header", "page_type": "BOTH", "text": "Section 2 Header"},
                        {"kind": "footer", "page_type": "EVEN", "text": "Section 2 Even"},
                    ],
                }],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_story_layer_map(path)
            self.assertEqual(mapped["section_count"], 2)
            second = mapped["sections"][1]
            stories = {(s["kind"], s["page_type"]): s for s in second["stories"]}
            self.assertEqual(stories[("header", "BOTH")]["text"], "Section 2 Header")
            self.assertEqual(stories[("footer", "EVEN")]["text"], "Section 2 Even")
            self.assertTrue(second["first_page_policy"]["hide_header"])
            self.assertTrue(second["first_page_policy"]["hide_footer"])

    def test_first_story_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, "EVIDENCE_GATE_CLOSED"):
                apply_story_layer_atomic(
                    path,
                    [{
                        "op": "set_first_page_story",
                        "section_index": 0,
                        "kind": "header",
                        "text": "invented",
                    }],
                    expected_revision=1,
                    current_revision=1,
                )

    def test_contract_declares_p318_ancestry(self):
        contract = story_layer_contract()
        self.assertEqual(contract["phase"], "P3.24")
        self.assertIn("P3.18", contract["ancestry"])
        self.assertEqual(contract["native_page_types"], ["BOTH", "EVEN", "ODD"])
        self.assertIn("set_first_page_story", contract["deferred_operations"])


if __name__ == "__main__":
    unittest.main()
