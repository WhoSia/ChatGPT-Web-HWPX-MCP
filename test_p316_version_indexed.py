from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from p313r1_fixture_pack import materialize_pre_hancom_pack
from p316_stability_builder import build_structural_consolidation
from p316_version_indexed import adjudicate_version_indexed_stability


def record(*, raster="a" * 64, font="c" * 64) -> dict:
    return {
        "world_contact_pass": True,
        "baseline_exact_pixel_pass": True,
        "positive_sensitivity_pass": True,
        "renderer_version": "13.0.0.3622",
        "renderer_executable_sha256": "1" * 64,
        "os_name": "Microsoft Windows 11",
        "os_version": "10.0.26100",
        "machine_id": "runner-a",
        "locale": "ko-KR",
        "dpi": 144,
        "rasterizer": "PyMuPDF",
        "rasterizer_version": "1.28.2",
        "fixture_set_sha256": "f" * 64,
        "font_file_custody_sha256": font,
        "baseline_source_raster_sha256": raster,
        "baseline_target_raster_sha256": raster,
        "boundaries": {
            "advance": {
                "candidate_id": "advance-10120",
                "magnitude": 120,
                "predecessor_candidate_id": "advance-10100",
                "predecessor_line_break_equal": True,
                "selected_line_break_equal": False,
            },
            "frame": {
                "candidate_id": "frame-283",
                "magnitude": 283,
                "predecessor_candidate_id": "frame-213",
                "predecessor_line_break_equal": True,
                "selected_line_break_equal": False,
            },
        },
    }


STRUCTURAL = {
    "baseline_structurally_identical": True,
    "advance_changed_dimensions": ["header_style"],
    "frame_changed_dimensions": ["page_geometry"],
}


class P316VersionIndexedTests(unittest.TestCase):
    def packet(self, reps):
        return {
            "schema": "chatgpt-web-hwpx-mcp/version-indexed-stability/p3.16/v1",
            "repetitions": reps,
            "structural_oracle": STRUCTURAL,
        }

    def test_three_exact_repetitions_earn_version_indexed_exact_authority(self):
        result = adjudicate_version_indexed_stability(
            self.packet([record(), record(), record()])
        )
        self.assertEqual(result["verdict"], "VERSION_INDEXED_EXACT_FIDELITY_AUTHORITY")
        self.assertTrue(result["baseline_raster_stable"])
        self.assertTrue(result["advance_boundary_stable"])
        self.assertTrue(result["frame_boundary_stable"])
        self.assertEqual(result["cross_version_state"], "DEFERRED_REOPENING_AVAILABLE")
        self.assertTrue(result["cross_version_required_for_global_authority"])

    def test_boundary_stability_survives_pixel_hash_drift(self):
        result = adjudicate_version_indexed_stability(
            self.packet([
                record(raster="a" * 64),
                record(raster="b" * 64),
                record(raster="c" * 64),
            ])
        )
        self.assertEqual(
            result["verdict"], "VERSION_INDEXED_BOUNDARY_STABILITY_AUTHORITY"
        )
        self.assertFalse(result["baseline_raster_stable"])

    def test_font_custody_delta_holds(self):
        result = adjudicate_version_indexed_stability(
            self.packet([record(), record(), record(font="d" * 64)])
        )
        self.assertEqual(result["verdict"], "SINGLE_VERSION_STABILITY_HOLD")
        self.assertIn("font_file_custody_sha256", result["identity_mismatches"])

    def test_boundary_drift_holds(self):
        third = record()
        third["boundaries"]["advance"]["candidate_id"] = "advance-10160"
        third["boundaries"]["advance"]["magnitude"] = 160
        result = adjudicate_version_indexed_stability(
            self.packet([record(), record(), third])
        )
        self.assertEqual(result["verdict"], "SINGLE_VERSION_STABILITY_HOLD")
        self.assertFalse(result["advance_boundary_stable"])

    def test_structural_oracle_localizes_fixture_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            materialize_pre_hancom_pack(pack)
            result = build_structural_consolidation(pack)
            self.assertTrue(result["baseline_structurally_identical"])
            self.assertEqual(result["advance_changed_dimensions"], ["header_style"])
            self.assertEqual(result["frame_changed_dimensions"], ["page_geometry"])


if __name__ == "__main__":
    unittest.main()
