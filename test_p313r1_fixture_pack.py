from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import server
from p313r1_fixture_pack import materialize_pre_hancom_pack, select_boundary_candidate


class P313R1FixturePackTests(unittest.TestCase):
    def test_boundary_selector_picks_smallest_observed_transition(self):
        result = select_boundary_candidate([
            {"candidate_id": "b", "magnitude": 4, "line_break_diverged": True},
            {"candidate_id": "a", "magnitude": 2, "line_break_diverged": True},
            {"candidate_id": "z", "magnitude": 1, "line_break_diverged": False},
        ])
        self.assertEqual(result["selected"]["candidate_id"], "a")

    def test_boundary_selector_holds_without_transition(self):
        result = select_boundary_candidate([
            {"candidate_id": "a", "magnitude": 1, "line_break_diverged": False},
        ])
        self.assertIsNone(result["selected"])
        self.assertEqual(result["authority"], "BOUNDARY_SELECTION_HOLD")

    def test_materialized_pack_is_capture_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            result = materialize_pre_hancom_pack(root)

            self.assertEqual(result["fixture_count"], 3)
            self.assertFalse(result["manual_fixture_authoring_required"])
            self.assertTrue(result["hancom_step_remaining"])

            manifest = json.loads((root / "capture-ready-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "chatgpt-web-hwpx-mcp/pre-hancom-pack/p3.13-r1/v1")
            self.assertEqual(len(manifest["boundary_calibration_ladder"]["advance"]), 8)
            self.assertEqual(len(manifest["boundary_calibration_ladder"]["frame"]), 8)

            for fixture in manifest["fixtures"]:
                source = root / fixture["source"]
                target = root / fixture["target"]
                self.assertTrue(server.validate_hwpx_package(source)["valid"])
                self.assertTrue(server.validate_hwpx_package(target)["valid"])

            base = next(x for x in manifest["fixtures"] if x["fixture_id"] == "near-wrap-base")
            plus = next(x for x in manifest["fixtures"] if x["fixture_id"] == "near-wrap-plus-advance")
            minus = next(x for x in manifest["fixtures"] if x["fixture_id"] == "near-wrap-minus-frame")
            self.assertEqual(base["source_sha256"], base["target_sha256"])
            self.assertNotEqual(plus["source_sha256"], plus["target_sha256"])
            self.assertNotEqual(minus["source_sha256"], minus["target_sha256"])

            zip_path = Path(result["pack_zip"])
            self.assertTrue(zip_path.is_file())
            with zipfile.ZipFile(zip_path, "r") as archive:
                names = set(archive.namelist())
                self.assertIn("pack/capture-ready-manifest.json", names)
                self.assertIn("pack/near-wrap-base/source.hwpx", names)
                self.assertIn("pack/near-wrap-base/target.hwpx", names)


if __name__ == "__main__":
    unittest.main()
