from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import server


class P1HwpxTests(unittest.TestCase):
    def test_filename_sanitization(self) -> None:
        self.assertEqual(server.sanitize_filename("../../my report?.hwpx"), "my report_.hwpx")
        self.assertEqual(server.sanitize_filename("문서"), "문서.hwpx")

    def test_materialize_and_validate_minimal_hwpx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.hwpx"
            result = server.materialize_hwpx(
                path,
                "첫 번째 문단\n두 번째 문단",
                "P1 최소 HWPX",
            )
            self.assertTrue(result["valid"])
            self.assertGreater(result["bytes"], 0)
            self.assertEqual(len(result["sha256"]), 64)

            with zipfile.ZipFile(path, "r") as archive:
                infos = archive.infolist()
                self.assertEqual(infos[0].filename, "mimetype")
                self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
                self.assertEqual(archive.read("mimetype"), b"application/hwp+zip")
                self.assertTrue(server.REQUIRED_HWPX_ENTRIES.issubset(set(archive.namelist())))

    def test_document_id_shape(self) -> None:
        document_id = server._new_document_id()
        self.assertRegex(document_id, server.DOC_ID_RE)


if __name__ == "__main__":
    unittest.main()
