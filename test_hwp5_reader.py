from __future__ import annotations

import struct
import unittest
import zlib

from hwp5_reader import (
    HWP5_SIGNATURE,
    HWPTAG_PARA_TEXT,
    Hwp5ReadError,
    _clean_para_text,
    _decompress_stream,
    _iter_records,
    _parse_header,
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

    def test_control_units_are_not_exposed_as_visible_text(self):
        payload = "앞".encode("utf-16le") + b"\x01\x00" + "뒤".encode("utf-16le")
        self.assertEqual(_clean_para_text(payload), "앞뒤")


if __name__ == "__main__":
    unittest.main()
