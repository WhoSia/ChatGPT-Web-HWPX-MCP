"""Native report figure preflight: preserve bytes, reject corrupt PNG envelopes."""
from __future__ import annotations

import base64
import struct
import unittest
import zlib

from hwpx_mcp.interfaces.p425_report_presets import _as_native_figure


def chunk(tag: bytes, data: bytes) -> bytes:
    frame = tag + data
    return struct.pack(">I", len(data)) + frame + struct.pack(">I", zlib.crc32(frame) & 0xFFFFFFFF)


def tiny_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixel = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", pixel)
            + chunk(b"IEND", b""))


def figure(raw: bytes) -> dict:
    return {"image_format": "png", "content_base64": base64.b64encode(raw).decode("ascii"),
            "width": 10000, "height": 8000, "caption": "Original synthetic pixel"}


class FigureContainerIntegrityTests(unittest.TestCase):
    def test_valid_png_bytes_are_preserved_without_reencoding(self):
        source = tiny_png()
        block = _as_native_figure(figure(source))
        self.assertEqual(base64.b64decode(block["content_base64"]), source)
        self.assertEqual(block["caption"], "Original synthetic pixel")

    def test_rejects_mutated_idat_crc(self):
        source = bytearray(tiny_png())
        source[45] ^= 1
        with self.assertRaisesRegex(ValueError, "REPORT_FIGURE_PNG_CRC_INVALID"):
            _as_native_figure(figure(bytes(source)))

    def test_rejects_truncated_png(self):
        with self.assertRaisesRegex(ValueError, "REPORT_FIGURE_PNG_TRUNCATED|REPORT_FIGURE_PNG_INCOMPLETE"):
            _as_native_figure(figure(tiny_png()[:-4]))

    def test_rejects_trailing_bytes_after_iend(self):
        with self.assertRaisesRegex(ValueError, "REPORT_FIGURE_PNG_IEND_INVALID"):
            _as_native_figure(figure(tiny_png() + b"junk"))

    def test_rejects_png_without_idat(self):
        data = tiny_png()
        start = data.index(b"IDAT") - 4
        end = data.index(b"IEND") - 4
        with self.assertRaisesRegex(ValueError, "REPORT_FIGURE_PNG_IEND_INVALID"):
            _as_native_figure(figure(data[:start] + data[end:]))


if __name__ == "__main__":
    unittest.main()
