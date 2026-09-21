from __future__ import annotations

import copy
import unittest

from p315_cross_version import adjudicate_cross_version_replay


def version_record(version: str, exe: str, *, baseline_raster: str = "a" * 64) -> dict:
    return {
        "world_contact_pass": True,
        "baseline_exact_pixel_pass": True,
        "positive_sensitivity_pass": True,
        "renderer_version": version,
        "renderer_executable_sha256": exe,
        "os_name": "Windows 11",
        "os_version": "10.0.26100",
        "machine_id": "runner-a",
        "locale": "ko-KR",
        "dpi": 144,
        "rasterizer": "PyMuPDF",
        "rasterizer_version": "1.28.2",
        "fixture_set_sha256": "f" * 64,
        "font_file_custody_sha256": "c" * 64,
        "baseline_source_raster_sha256": baseline_raster,
        "baseline_target_raster_sha256": baseline_raster,
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


class P315CrossVersionTests(unittest.TestCase):
    def test_exact_cross_version_pixel_stability_reopens_strong_candidate(self):
        packet = {
            "schema": "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1",
            "versions": [
                version_record("13.0.0.3622", "1" * 64),
                version_record("14.0.0.1000", "2" * 64),
            ],
        }
        result = adjudicate_cross_version_replay(packet)
        self.assertTrue(result["promotion_reopened"])
        self.assertTrue(result["cross_version_baseline_pixel_stable"])
        self.assertEqual(
            result["verdict"],
            "CROSS_VERSION_NATIVE_PIXEL_STABILITY_PROMOTION_CANDIDATE",
        )

    def test_version_indexed_reopens_when_native_pixels_shift(self):
        packet = {
            "schema": "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1",
            "versions": [
                version_record("13.0.0.3622", "1" * 64, baseline_raster="a" * 64),
                version_record("14.0.0.1000", "2" * 64, baseline_raster="b" * 64),
            ],
        }
        result = adjudicate_cross_version_replay(packet)
        self.assertTrue(result["promotion_reopened"])
        self.assertFalse(result["cross_version_baseline_pixel_stable"])
        self.assertEqual(
            result["verdict"],
            "VERSION_INDEXED_PIXEL_FIDELITY_PROMOTION_CANDIDATE",
        )

    def test_font_environment_delta_keeps_hold(self):
        second = version_record("14.0.0.1000", "2" * 64)
        second["font_file_custody_sha256"] = "d" * 64
        packet = {
            "schema": "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1",
            "versions": [version_record("13.0.0.3622", "1" * 64), second],
        }
        result = adjudicate_cross_version_replay(packet)
        self.assertFalse(result["promotion_reopened"])
        self.assertEqual(result["verdict"], "CROSS_VERSION_PIXEL_FIDELITY_HOLD")

    def test_same_version_is_not_cross_version_evidence(self):
        packet = {
            "schema": "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1",
            "versions": [
                version_record("13.0.0.3622", "1" * 64),
                version_record("13.0.0.3622", "2" * 64),
            ],
        }
        result = adjudicate_cross_version_replay(packet)
        self.assertFalse(result["promotion_reopened"])
        self.assertFalse(result["distinct_versions"])

    def test_dead_positive_control_is_rejected(self):
        bad = version_record("14.0.0.1000", "2" * 64)
        bad["boundaries"]["advance"]["selected_line_break_equal"] = True
        packet = {
            "schema": "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1",
            "versions": [version_record("13.0.0.3622", "1" * 64), bad],
        }
        with self.assertRaises(ValueError):
            adjudicate_cross_version_replay(packet)


if __name__ == "__main__":
    unittest.main()
