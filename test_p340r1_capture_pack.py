from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from p340r1_capture_pack import deterministic_zip, sha256_file, validate_complete, verify_fixture, write_json


class P340R1CapturePackTests(unittest.TestCase):
    def test_fixture_hash_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp); fixture_path = pack / "fixtures" / "A" / "input.hwpx"
            fixture_path.parent.mkdir(parents=True); fixture_path.write_bytes(b"frozen")
            fixture = {"fixture_id": "A", "path": "fixtures/A/input.hwpx", "sha256": sha256_file(fixture_path)}
            self.assertEqual(verify_fixture(pack, fixture), fixture_path)
            fixture_path.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"): verify_fixture(pack, fixture)

    def test_incomplete_pack_does_not_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp); input_path = pack / "fixtures" / "A" / "input.hwpx"
            input_path.parent.mkdir(parents=True); input_path.write_bytes(b"fixture")
            write_json(pack / "capture-ready-manifest.json", {"fixtures": [{"fixture_id": "A", "path": "fixtures/A/input.hwpx", "sha256": sha256_file(input_path)}]})
            result = validate_complete(pack)
            self.assertFalse(result["complete"]); self.assertEqual(result["failures"][0]["fixture_id"], "A")

    def test_deterministic_zip_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pack = root / "pack"; pack.mkdir()
            (pack / "b.txt").write_text("b", encoding="utf-8"); (pack / "a.txt").write_text("a", encoding="utf-8")
            first, second = root / "one.zip", root / "two.zip"
            self.assertEqual(deterministic_zip(pack, first), deterministic_zip(pack, second))
            with zipfile.ZipFile(first) as archive: self.assertEqual(archive.namelist(), ["a.txt", "b.txt"])
            with self.assertRaises(FileExistsError): deterministic_zip(pack, first)


if __name__ == "__main__": unittest.main()
