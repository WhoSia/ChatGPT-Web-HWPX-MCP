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
            result = server.materialize_hwpx(path, "첫 번째 문단\n두 번째 문단", "P1.2 최소 HWPX")
            self.assertTrue(result["valid"])
            self.assertGreater(result["bytes"], 0)
            self.assertEqual(len(result["sha256"]), 64)
            with zipfile.ZipFile(path, "r") as archive:
                infos = archive.infolist()
                self.assertEqual(infos[0].filename, "mimetype")
                self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
                self.assertEqual(archive.read("mimetype"), b"application/hwp+zip")
                self.assertTrue(server.REQUIRED_HWPX_ENTRIES.issubset(set(archive.namelist())))

    def test_existing_ingress_accepts_known_good_generated_hwpx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "known-good.hwpx"
            server.materialize_hwpx(path, "bounded ingress", "P1.2")
            result = server.validate_hwpx_package(path, ingress=True)
            self.assertTrue(result["valid"])
            self.assertEqual(result["ingress_profile"], "bounded-existing-hwpx")

    def test_ingress_rejects_zip_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unsafe.hwpx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("mimetype", b"application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                archive.writestr("../escape.xml", b"<x/>")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP entry path"):
                server.validate_hwpx_package(path, ingress=True)

    def test_ingress_rejects_dtd_or_entity_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.hwpx"
            bad = Path(tmp) / "bad.hwpx"
            server.materialize_hwpx(good, "safe", "P1.2")
            with zipfile.ZipFile(good, "r") as source, zipfile.ZipFile(bad, "w") as target:
                for info in source.infolist():
                    payload = source.read(info.filename)
                    if info.filename == "Contents/section0.xml":
                        payload = b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>'
                    target.writestr(info, payload)
            with self.assertRaisesRegex(ValueError, "DTD/entity declarations"):
                server.validate_hwpx_package(bad, ingress=True)

    def test_document_id_shape(self) -> None:
        document_id = server._new_document_id()
        self.assertRegex(document_id, server.DOC_ID_RE)


if __name__ == "__main__":
    unittest.main()
