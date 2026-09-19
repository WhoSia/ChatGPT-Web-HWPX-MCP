from __future__ import annotations

import unittest

from common_ir import hwp5_to_common_ir, search_common_ir, slice_common_ir


class CommonIrTests(unittest.TestCase):
    def fixture(self):
        return {
            "version": "5.0.1.7",
            "flags": {"compressed": True},
            "readable": True,
            "paragraphs": [
                {
                    "paragraph_index": 0,
                    "section_index": 0,
                    "section_stream": "BodyText/Section0",
                    "record_index": 0,
                    "record_level": 0,
                    "tag_id": 0x43,
                    "text": "alpha beta",
                }
            ],
            "tables": [
                {
                    "kind": "table",
                    "fidelity": "structural",
                    "section_index": 0,
                    "section_stream": "BodyText/Section0",
                    "record_index": 3,
                    "record_level": 2,
                    "tag_id": 0x4D,
                    "row_count": 2,
                    "col_count": 3,
                    "payload_sha256": "a" * 64,
                }
            ],
            "equations": [
                {
                    "kind": "equation",
                    "fidelity": "semantic",
                    "section_index": 0,
                    "section_stream": "BodyText/Section0",
                    "record_index": 4,
                    "record_level": 2,
                    "tag_id": 0x58,
                    "script": "x^2",
                    "payload_sha256": "b" * 64,
                }
            ],
            "objects": [
                {
                    "kind": "picture",
                    "fidelity": "inventory",
                    "section_index": 0,
                    "section_stream": "BodyText/Section0",
                    "record_index": 5,
                    "record_level": 3,
                    "tag_id": 0x55,
                    "payload_sha256": "c" * 64,
                }
            ],
            "binary_items": [
                {"stream": "BinData/BIN0001.png", "bytes": 123, "sha256": "d" * 64}
            ],
            "fidelity": {
                "paragraph_text": "semantic",
                "tables": "structural",
                "equations": "semantic",
                "pictures": "inventory",
                "binary_items": "inventory",
            },
            "warnings": [],
        }

    def test_hwp5_ir_preserves_family_fidelity(self):
        ir = hwp5_to_common_ir(
            self.fixture(),
            source_sha256="e" * 64,
            filename="fixture.hwp",
        )
        self.assertEqual(ir["source_format"], "hwp5")
        self.assertEqual(ir["inventory"]["paragraph"], 1)
        self.assertEqual(ir["inventory"]["table"], 1)
        self.assertEqual(ir["inventory"]["equation"], 1)
        self.assertEqual(ir["inventory"]["picture"], 1)
        self.assertEqual(ir["inventory"]["binary"], 1)
        table = next(block for block in ir["blocks"] if block["kind"] == "table")
        equation = next(block for block in ir["blocks"] if block["kind"] == "equation")
        self.assertEqual(table["fidelity"], "structural")
        self.assertEqual(equation["fidelity"], "semantic")
        self.assertEqual(equation["text"], "x^2")
        self.assertEqual(len(ir["ir_sha256"]), 64)

    def test_search_spans_formats_without_losing_receipts(self):
        ir = hwp5_to_common_ir(
            self.fixture(),
            source_sha256="e" * 64,
            filename="fixture.hwp",
        )
        result = search_common_ir(ir, "beta", kinds=["paragraph"])
        self.assertEqual(result["match_count"], 1)
        hit = result["hits"][0]
        self.assertEqual(hit["kind"], "paragraph")
        self.assertEqual(hit["fidelity"], "semantic")
        self.assertEqual(hit["source"]["section_stream"], "BodyText/Section0")

        eq = search_common_ir(ir, "x^2", kinds=["equation"])
        self.assertEqual(eq["match_count"], 1)
        self.assertEqual(eq["hits"][0]["fidelity"], "semantic")

    def test_slice_is_bounded_and_filterable(self):
        ir = hwp5_to_common_ir(
            self.fixture(),
            source_sha256="e" * 64,
            filename="fixture.hwp",
        )
        result = slice_common_ir(ir, start_block=0, block_count=1, kinds=["equation"])
        self.assertEqual(result["returned_blocks"], 1)
        self.assertEqual(result["blocks"][0]["kind"], "equation")
        self.assertFalse(result["has_more"])


if __name__ == "__main__":
    unittest.main()
