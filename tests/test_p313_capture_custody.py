from __future__ import annotations

import unittest

from p313_capture_custody import (
    CAPTURE_SCHEMA,
    RUNNER_SCHEMA,
    adjudicate_cross_version_replay,
    adjudicate_sensitivity_controls,
    near_wrap_positive_sensitivity_spec,
    validate_artifact_custody,
    validate_runner_identity,
    verify_custody_chain,
)


def runner(version="2024"):
    return {
        "schema": RUNNER_SCHEMA,
        "os": "Windows 11",
        "os_version": "24H2",
        "machine_id": "runner-a",
        "hancom_version": version,
        "hancom_executable_sha256": "a" * 64,
        "harness_sha256": "b" * 64,
        "capture_user": "ci",
        "locale": "ko-KR",
        "display_scale_percent": 100,
    }


def bundle(previous="", fixture="f1"):
    roles = [
        "source-document", "target-document", "source-raster", "target-raster",
        "line-box-capture", "font-inventory", "render-receipt",
    ]
    return {
        "schema": CAPTURE_SCHEMA,
        "fixture_id": fixture,
        "captured_at": "2026-09-20T00:00:00Z",
        "previous_bundle_sha256": previous,
        "runner": runner(),
        "artifacts": [
            {
                "path": f"{role}.bin",
                "sha256": f"{i+1:064x}"[-64:],
                "bytes": i + 1,
                "role": role,
            }
            for i, role in enumerate(roles)
        ],
    }


def world_packet(version="2024"):
    return {
        "schema": "chatgpt-web-hwpx-mcp/render-receipt/p3.12/v1",
        "fixture_id": "plain",
        "source_sha256": "c" * 64,
        "target_sha256": "d" * 64,
        "renderer": {
            "name": "Hancom Hangul",
            "version": version,
            "hancom_native": True,
            "executable_sha256": "e" * 64,
            "os": "Windows 11",
            "dpi": 144,
            "pdf_backend": "Hancom PDF",
            "rasterizer": "controlled",
            "rasterizer_version": "1",
        },
        "source_environment": {
            "fonts": [{"family": "HCR Batang", "file_sha256": "1" * 64}]
        },
        "target_environment": {
            "fonts": [{"family": "HCR Batang", "file_sha256": "1" * 64}]
        },
        "source_capture": {
            "pages": [{
                "page_index": 0, "width_px": 1000, "height_px": 1400,
                "raster_sha256": "2" * 64,
                "line_boxes": [{"x": 1, "y": 1, "width": 10, "height": 10, "baseline": 9}],
            }]
        },
        "target_capture": {
            "pages": [{
                "page_index": 0, "width_px": 1000, "height_px": 1400,
                "raster_sha256": "2" * 64,
                "line_boxes": [{"x": 1, "y": 1, "width": 10, "height": 10, "baseline": 9}],
            }]
        },
        "metrics": {
            "exact_pixel_match": True,
            "pixel_diff_ratio": 0.0,
            "mae": 0.0,
            "edge_disagreement": 0.0,
            "bbox_max_displacement_px": 0.0,
            "glyph_advance_max_delta_px": 0.0,
            "inline_baseline_max_delta_px": 0.0,
            "border_paint_diff_ratio": 0.0,
        },
        "calibration": {},
    }


STRUCTURAL = {
    "page_section_geometry_sha256": "g",
    "hard_break_receipt": {"sha256": "h"},
    "font_inventory_sha256": "i",
}


class P313CaptureCustodyTests(unittest.TestCase):
    def test_windows_runner_required(self):
        good = validate_runner_identity(runner())
        self.assertEqual(good["hancom_version"], "2024")
        bad = runner()
        bad["os"] = "Linux"
        with self.assertRaises(ValueError):
            validate_runner_identity(bad)

    def test_artifact_custody_bundle(self):
        result = validate_artifact_custody(bundle())
        self.assertTrue(result["custody_complete"])
        self.assertEqual(result["authority"], "ARTIFACT_CUSTODY_CHAIN_RECEIPT")

    def test_append_only_chain(self):
        first = validate_artifact_custody(bundle())
        second = bundle(previous=first["bundle_sha256"], fixture="f2")
        chain = verify_custody_chain([bundle(), second])
        self.assertTrue(chain["chain_valid"])
        self.assertEqual(chain["bundle_count"], 2)

    def test_chain_break_rejected(self):
        second = bundle(previous="f" * 64, fixture="f2")
        with self.assertRaises(ValueError):
            verify_custody_chain([bundle(), second])

    def test_sensitivity_spec_has_two_positive_controls(self):
        spec = near_wrap_positive_sensitivity_spec()
        self.assertEqual(spec["required_positive_controls"], 2)
        self.assertEqual(len(spec["fixtures"]), 3)

    def test_sensitivity_controls(self):
        base = {"adjudication": {"promotion_gate": {"line_break_exact": True}}}
        div = {"adjudication": {"promotion_gate": {"line_break_exact": False}}}
        result = adjudicate_sensitivity_controls({
            "near-wrap-base": base,
            "near-wrap-plus-advance": div,
            "near-wrap-minus-frame": div,
        })
        self.assertTrue(result["positive_sensitivity_pass"])

    def test_cross_version_exact_candidate_requires_sensitivity(self):
        result = adjudicate_cross_version_replay(
            STRUCTURAL,
            [world_packet("2024"), world_packet("2026")],
            {"positive_sensitivity_pass": True},
        )
        self.assertEqual(
            result["verdict"], "CROSS_VERSION_EXACT_PIXEL_PROMOTION_CANDIDATE"
        )

    def test_cross_version_without_sensitivity_holds(self):
        result = adjudicate_cross_version_replay(
            STRUCTURAL,
            [world_packet("2024"), world_packet("2026")],
            None,
        )
        self.assertEqual(
            result["verdict"], "CROSS_VERSION_PIXEL_FIDELITY_HOLD"
        )


if __name__ == "__main__":
    unittest.main()
