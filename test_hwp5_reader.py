from __future__ import annotations

import io
import struct
import unittest
import zlib

from PIL import Image

from hwp5_reader import (
    HWP5_SIGNATURE,
    HWPTAG_PARA_TEXT,
    Hwp5ReadError,
    _clean_para_text,
    _decompress_stream,
    _iter_records,
    _parse_header,
    _parse_table_record,
    _parse_equation_record,
    _parse_para_header,
    _parse_para_char_shapes,
    _parse_docinfo_char_shape,
    _build_run_receipts,
    _parse_ctrl_header,
    _parse_list_header,
    _parse_table_cell_from_list_header,
    _parse_picture_record,
    _parse_bindata_record,
    _parent_indexes,
    prepare_hwp5_image_for_hwpx,
)


class Hwp5ReaderPrimitiveTests(unittest.TestCase):
    def test_header_version_and_flags(self):
        raw = bytearray(256)
        raw[:32] = HWP5_SIGNATURE
        raw[32:36] = bytes([7, 1, 0, 5])  # 5.0.1.7
        struct.pack_into("<I", raw, 36, (1 << 0) | (1 << 6))
        header = _parse_header(bytes(raw))
        self.assertEqual(header.version, (5, 0, 1, 7))
        self.assertTrue(header.compressed)
        self.assertTrue(header.public_flags()["history"])
        self.assertFalse(header.password)

    def test_bad_signature_rejected(self):
        with self.assertRaises(Hwp5ReadError):
            _parse_header(b"x" * 256)

    def test_record_header_and_para_text(self):
        payload = "가나다".encode("utf-16le")
        header = HWPTAG_PARA_TEXT | (2 << 10) | (len(payload) << 20)
        stream = struct.pack("<I", header) + payload
        records = list(_iter_records(stream))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], HWPTAG_PARA_TEXT)
        self.assertEqual(records[0][1], 2)
        self.assertEqual(_clean_para_text(records[0][2]), "가나다")

    def test_raw_deflate_decompression(self):
        data = b"BodyText payload" * 20
        compressor = zlib.compressobj(wbits=-15)
        compressed = compressor.compress(data) + compressor.flush()
        self.assertEqual(_decompress_stream(compressed), data)

    def test_table_record_structural_decode(self):
        rows = 2
        payload = (
            struct.pack("<IHHH", 0b100, rows, 3, 120)
            + struct.pack("<HHHH", 10, 20, 30, 40)
            + struct.pack("<HH", 500, 600)
            + struct.pack("<H", 7)
        )
        table = _parse_table_record(payload)
        self.assertEqual(table["fidelity"], "structural")
        self.assertEqual(table["row_count"], 2)
        self.assertEqual(table["col_count"], 3)
        self.assertEqual(table["cell_spacing"], 120)
        self.assertEqual(table["row_sizes"], [500, 600])
        self.assertEqual(table["border_fill_id"], 7)
        self.assertTrue(table["repeat_header"])

    def test_equation_record_semantic_decode(self):
        script = "x^2+y^2"
        raw_script = script.encode("utf-16le")
        payload = (
            struct.pack("<IH", 1, len(script))
            + raw_script
            + struct.pack("<IIh", 1200, 0x00AA33, -7)
        )
        eq = _parse_equation_record(payload)
        self.assertEqual(eq["fidelity"], "semantic")
        self.assertEqual(eq["script"], script)
        self.assertEqual(eq["font_size"], 1200)
        self.assertEqual(eq["baseline"], -7)

    def test_paragraph_header_and_char_shape_runs(self):
        raw = bytearray(22)
        struct.pack_into("<II", raw, 0, 6, 0)
        struct.pack_into("<H", raw, 8, 12)
        raw[10] = 3
        raw[11] = 0
        struct.pack_into("<HHH", raw, 12, 2, 0, 1)
        struct.pack_into("<I", raw, 18, 77)
        header = _parse_para_header(bytes(raw))
        self.assertEqual(header["para_shape_id"], 12)
        self.assertEqual(header["para_style_id"], 3)
        self.assertEqual(header["char_shape_count"], 2)
        self.assertEqual(header["instance_id"], 77)

        changes = _parse_para_char_shapes(
            struct.pack("<IIII", 0, 0, 2, 1)
        )
        shape0 = {
            "char_shape_id": 0,
            "fidelity": "semantic",
            "bold": False,
        }
        shape1 = {
            "char_shape_id": 1,
            "fidelity": "semantic",
            "bold": True,
        }
        receipts = _build_run_receipts(
            "abcdef",
            header,
            changes,
            [shape0, shape1],
        )
        self.assertEqual(receipts["visible_span_fidelity"], "semantic")
        self.assertEqual(receipts["runs"][0]["text"], "ab")
        self.assertEqual(receipts["runs"][1]["text"], "cdef")
        self.assertTrue(receipts["runs"][1]["char_shape"]["bold"])

    def test_controlled_paragraph_keeps_source_coordinate_only(self):
        header = {
            "char_count": 8,
            "control_mask": 1,
        }
        receipts = _build_run_receipts(
            "abcd",
            header,
            [{"source_position": 0, "char_shape_id": 0}],
            [{"char_shape_id": 0, "fidelity": "semantic"}],
        )
        self.assertEqual(
            receipts["visible_span_fidelity"],
            "source-coordinate-only",
        )
        self.assertFalse(receipts["runs"][0]["visible_span_certified"])

    def test_docinfo_char_shape_semantic_decode(self):
        raw = bytearray(74)
        struct.pack_into("<7H", raw, 0, 1, 2, 3, 4, 5, 6, 7)
        raw[14:21] = bytes([100] * 7)
        struct.pack_into("<7b", raw, 21, *([0] * 7))
        raw[28:35] = bytes([100] * 7)
        struct.pack_into("<7b", raw, 35, *([0] * 7))
        struct.pack_into("<I", raw, 42, 1200)
        struct.pack_into("<I", raw, 46, 0b11)
        struct.pack_into("<bb", raw, 50, 1, -1)
        struct.pack_into("<IIII", raw, 52, 0x00112233, 0, 0x00FFFFFF, 0)
        struct.pack_into("<H", raw, 68, 9)
        struct.pack_into("<I", raw, 70, 0x00010203)
        shape = _parse_docinfo_char_shape(bytes(raw), 4)
        self.assertEqual(shape["char_shape_id"], 4)
        self.assertEqual(shape["height"], 1200)
        self.assertTrue(shape["italic"])
        self.assertTrue(shape["bold"])
        self.assertEqual(shape["face_ids"][0], 1)
        self.assertEqual(shape["border_fill_id"], 9)

    def test_ctrl_header_geometry_decode(self):
        ctrl_id = (ord("e") << 24) | (ord("q") << 16) | (ord("e") << 8) | ord("d")
        raw = bytearray(46)
        struct.pack_into("<I", raw, 0, ctrl_id)
        struct.pack_into("<I", raw, 4, 1 | (2 << 3) | (3 << 8))
        struct.pack_into("<iiiii", raw, 8, 120, 340, 5000, 2100, -2)
        struct.pack_into("<HHHH", raw, 28, 1, 2, 3, 4)
        struct.pack_into("<I", raw, 36, 77)
        struct.pack_into("<i", raw, 40, 1)
        struct.pack_into("<H", raw, 44, 0)
        ctrl = _parse_ctrl_header(bytes(raw))
        self.assertEqual(ctrl["ctrl_id"], "eqed")
        self.assertEqual(ctrl["width"], 5000)
        self.assertEqual(ctrl["height"], 2100)
        self.assertEqual(ctrl["instance_id"], 77)
        self.assertTrue(ctrl["treat_as_char"])

    def test_table_cell_list_header_decode(self):
        raw = bytearray(32)
        struct.pack_into("<hI", raw, 0, 2, 0)
        struct.pack_into("<HHHH", raw, 6, 3, 4, 2, 1)
        struct.pack_into("<ii", raw, 14, 7200, 1800)
        struct.pack_into("<HHHH", raw, 22, 10, 20, 30, 40)
        struct.pack_into("<H", raw, 30, 9)
        header = _parse_list_header(bytes(raw))
        cell = _parse_table_cell_from_list_header(bytes(raw))
        self.assertEqual(header["paragraph_count"], 2)
        self.assertEqual(cell["column"], 3)
        self.assertEqual(cell["row"], 4)
        self.assertEqual(cell["col_span"], 2)
        self.assertEqual(cell["width"], 7200)
        self.assertEqual(cell["border_fill_id"], 9)

    def test_picture_bindata_reference_decode(self):
        raw = bytearray(78)
        struct.pack_into("<I", raw, 0, 0x112233)
        struct.pack_into("<i", raw, 4, 20)
        struct.pack_into("<I", raw, 8, 0)
        struct.pack_into("<iiii", raw, 12, 0, 100, 100, 0)
        struct.pack_into("<iiii", raw, 28, 0, 0, 100, 100)
        struct.pack_into("<iiii", raw, 44, 1, 2, 90, 80)
        struct.pack_into("<HHHH", raw, 60, 0, 0, 0, 0)
        struct.pack_into("<bbB", raw, 68, 5, -3, 0)
        struct.pack_into("<H", raw, 71, 12)
        raw[73] = 7
        struct.pack_into("<I", raw, 74, 99)
        pic = _parse_picture_record(bytes(raw))
        self.assertEqual(pic["bin_item_id"], 12)
        self.assertEqual(pic["instance_id"], 99)
        self.assertEqual(pic["crop"]["right"], 90)

    def test_bindata_embedding_metadata_decode(self):
        ext = "png"
        raw = struct.pack("<HHH", 0x0011, 5, len(ext)) + ext.encode("utf-16le")
        item = _parse_bindata_record(raw)
        self.assertEqual(item["data_type"], 1)
        self.assertEqual(item["compression"], 0x0010)
        self.assertEqual(item["storage_id"], 5)
        self.assertEqual(item["extension"], "png")

    def test_record_parent_graph(self):
        def rec(tag, level, payload=b"x"):
            return (tag, level, payload)
        records = [
            rec(0x42, 0),
            rec(0x47, 1),
            rec(0x48, 2),
            rec(0x42, 3),
            rec(0x43, 4),
            rec(0x4D, 2),
        ]
        parents = _parent_indexes(records)
        self.assertEqual(parents, [None, 0, 1, 2, 3, 1])

    def test_bmp_to_png_promotion_receipt_and_pixel_bound(self):
        output = io.BytesIO()
        Image.new("RGB", (2, 2), (12, 34, 56)).save(output, format="BMP")
        raw = output.getvalue()
        prepared = prepare_hwp5_image_for_hwpx({
            "data": raw,
            "format": "bmp",
        })
        self.assertEqual(prepared["transform"], "bmp-to-png")
        self.assertEqual(prepared["format"], "png")
        self.assertTrue(prepared["data"].startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(prepared["width"], 2)
        self.assertEqual(prepared["height"], 2)
        self.assertNotEqual(prepared["source_sha256"], prepared["output_sha256"])
        with self.assertRaises(Hwp5ReadError):
            prepare_hwp5_image_for_hwpx(
                {"data": raw, "format": "bmp"},
                max_pixels=3,
            )

    def test_p38_id_mappings_face_name_and_font_resolution(self):
        counts = [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0]
        mappings = _parse_id_mappings(struct.pack("<18i", *counts))
        self.assertEqual(mappings["font_counts"]["hangul"], 1)
        self.assertEqual(mappings["font_counts"]["latin"], 1)
        self.assertEqual(mappings["char_shape"], 1)
        self.assertEqual(mappings["para_shape"], 1)

        name = "함초롬바탕"
        face = _parse_face_name(
            bytes([0]) + struct.pack("<H", len(name)) + name.encode("utf-16le")
        )
        self.assertEqual(face["fidelity"], "semantic")
        self.assertEqual(face["face"], name)

        shape = {
            "fidelity": "semantic",
            "face_ids": [0, 0, 0, 0, 0, 0, 0],
        }
        resolved = _resolve_char_shape_faces(
            shape,
            {
                "hangul": [{"face": name}],
                "latin": [{"face": "Arial"}],
                "hanja": [],
                "japanese": [],
                "other": [],
                "symbol": [],
                "user": [],
            },
        )
        self.assertEqual(resolved["primary_font_face"], name)
        self.assertEqual(resolved["font_faces"]["latin"], "Arial")

    def test_p38_para_shape_semantics(self):
        attributes = 3 << 2  # CENTER in the P3.8 canonical mapping.
        payload = (
            struct.pack("<I", attributes)
            + struct.pack("<iiiiii", 720, 360, -180, 100, 200, 160)
            + struct.pack("<HHH", 2, 0, 7)
        )
        shape = _parse_docinfo_para_shape(payload, 4)
        self.assertEqual(shape["fidelity"], "semantic")
        self.assertEqual(shape["para_shape_id"], 4)
        self.assertEqual(shape["alignment"], "CENTER")
        self.assertEqual(shape["left_margin_hwpunit"], 720)
        self.assertEqual(shape["spacing_after_hwpunit"], 200)
        self.assertEqual(shape["border_fill_id"], 7)

    def test_p38_header_footer_scope_and_note_control(self):
        ctrl_value = int.from_bytes(b"head", "big")
        payload = (
            struct.pack("<I", ctrl_value)
            + struct.pack("<IiiBB", 2, 7200, 900, 0x03, 0x01)
        )
        header = _parse_ctrl_header(payload)
        self.assertEqual(header["ctrl_id"], "head")
        self.assertEqual(header["fidelity"], "semantic")
        self.assertEqual(header["apply_page_type"], "ODD")
        self.assertEqual(header["text_width"], 7200)

        note_value = int.from_bytes(b"fn  ", "big")
        note = _parse_ctrl_header(struct.pack("<I", note_value) + b"\x00" * 8)
        self.assertEqual(note["ctrl_id"], "fn  ")
        self.assertEqual(note["fidelity"], "structural")
        self.assertEqual(note["note_payload_bytes"], 8)

    def test_control_units_are_not_exposed_as_visible_text(self):
        payload = "앞".encode("utf-16le") + b"\x01\x00" + "뒤".encode("utf-16le")
        self.assertEqual(_clean_para_text(payload), "앞뒤")


if __name__ == "__main__":
    unittest.main()
