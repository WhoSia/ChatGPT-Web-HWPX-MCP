from __future__ import annotations

import unittest

from p312_render_harness import (
    RECEIPT_SCHEMA,
    adjudicate_fixture_set,
    adjudicate_fixture_world_contact,
    normalize_render_receipt,
    seal_font_environment,
)


def packet(*, same_raster=True, same_fonts=True, executable=True):
    source_raster = "1" * 64
    target_raster = source_raster if same_raster else "2" * 64
    source_font = "a" * 64
    target_font = source_font if same_fonts else "b" * 64
    return {
        "schema": RECEIPT_SCHEMA,
        "fixture_id": "plain-paragraph",
        "source_sha256": "c" * 64,
        "target_sha256": "d" * 64,
        "renderer": {
            "name": "Hancom Hangul",
            "version": "2026",
            "hancom_native": True,
            "executable_sha256": ("e" * 64) if executable else "",
            "os": "Windows",
            "dpi": 144,
            "pdf_backend": "Hancom PDF",
            "rasterizer": "controlled",
            "rasterizer_version": "1",
        },
        "source_environment": {
            "fonts": [{
                "family": "HCR Batang",
                "style": "Regular",
                "version": "1",
                "file_sha256": source_font,
            }]
        },
        "target_environment": {
            "fonts": [{
                "family": "HCR Batang",
                "style": "Regular",
                "version": "1",
                "file_sha256": target_font,
            }]
        },
        "source_capture": {
            "pages": [{
                "page_index": 0,
                "width_px": 1000,
                "height_px": 1400,
                "raster_sha256": source_raster,
                "line_boxes": [{
                    "x": 100, "y": 100, "width": 500, "height": 30,
                    "baseline": 125, "text_sha256": "f" * 64,
                    "paragraph_locator": "p1",
                }],
            }]
        },
        "target_capture": {
            "pages": [{
                "page_index": 0,
                "width_px": 1000,
                "height_px": 1400,
                "raster_sha256": target_raster,
                "line_boxes": [{
                    "x": 100, "y": 100, "width": 500, "height": 30,
                    "baseline": 125, "text_sha256": "f" * 64,
                    "paragraph_locator": "p1",
                }],
            }]
        },
        "metrics": {
            "exact_pixel_match": same_raster,
            "pixel_diff_ratio": 0.0 if same_raster else 0.001,
            "mae": 0.0 if same_raster else 0.001,
            "edge_disagreement": 0.0 if same_raster else 0.001,
            "bbox_max_displacement_px": 0.0,
            "glyph_advance_max_delta_px": 0.0,
            "inline_baseline_max_delta_px": 0.0,
            "border_paint_diff_ratio": 0.0,
        },
        "calibration": {
            "pixel_diff_tolerance_ratio": 0.01,
            "mae_tolerance": 0.01,
            "edge_disagreement_tolerance": 0.01,
            "bbox_displacement_tolerance_px": 0.1,
            "glyph_advance_tolerance_px": 0.1,
            "inline_baseline_tolerance_px": 0.1,
            "border_paint_tolerance_ratio": 0.01,
        },
    }


STRUCTURAL = {
    "page_section_geometry_sha256": "g",
    "hard_break_receipt": {"sha256": "h"},
    "font_inventory_sha256": "i",
}


class P312RenderHarnessTests(unittest.TestCase):
    def test_font_seal_order_independent(self):
        a = seal_font_environment([
            {"family": "B", "file_sha256": "2" * 64},
            {"family": "A", "file_sha256": "1" * 64},
        ])
        b = seal_font_environment([
            {"family": "A", "file_sha256": "1" * 64},
            {"family": "B", "file_sha256": "2" * 64},
        ])
        self.assertEqual(a["font_inventory_sha256"], b["font_inventory_sha256"])

    def test_exact_world_contact_promotes(self):
        result = adjudicate_fixture_world_contact(STRUCTURAL, packet())
        self.assertTrue(result["world_contact_valid"])
        self.assertTrue(result["raster"]["exact_hashes"])
        self.assertEqual(
            result["adjudication"]["verdict"], "PIXEL_RENDER_FIDELITY_PASS"
        )

    def test_missing_executable_seal_downgrades(self):
        result = adjudicate_fixture_world_contact(
            STRUCTURAL, packet(executable=False)
        )
        self.assertFalse(result["world_contact_valid"])
        self.assertEqual(
            result["adjudication"]["verdict"], "PIXEL_RENDER_FIDELITY_HOLD"
        )
        self.assertIn(
            "HANCOM_WORLD_CONTACT_SEAL_INCOMPLETE",
            result["adjudication"]["reason_chain"],
        )

    def test_font_mismatch_holds(self):
        result = adjudicate_fixture_world_contact(
            STRUCTURAL, packet(same_fonts=False)
        )
        self.assertEqual(
            result["adjudication"]["verdict"], "PIXEL_RENDER_FIDELITY_HOLD"
        )
        self.assertFalse(result["font_seal"]["exact"])

    def test_capture_contradiction_is_rejected(self):
        value = packet()
        value["metrics"]["pagination_equal"] = False
        with self.assertRaises(ValueError):
            adjudicate_fixture_world_contact(STRUCTURAL, value)

    def test_exact_pixel_claim_requires_raster_hash_identity(self):
        value = packet(same_raster=False)
        value["metrics"]["exact_pixel_match"] = True
        with self.assertRaises(ValueError):
            adjudicate_fixture_world_contact(STRUCTURAL, value)

    def test_fixture_set_authority(self):
        p = packet()
        p2 = packet()
        p2["fixture_id"] = "near-wrap-boundary"
        result = adjudicate_fixture_set(
            {
                "plain-paragraph": STRUCTURAL,
                "near-wrap-boundary": STRUCTURAL,
            },
            [p, p2],
        )
        self.assertEqual(result["fixture_count"], 2)
        self.assertTrue(result["all_world_contact_valid"])
        self.assertTrue(result["all_exact_pixel"])
        self.assertEqual(
            result["authority"], "FIXTURE_SET_EXACT_PIXEL_AUTHORITY"
        )

    def test_receipt_hash_is_deterministic(self):
        left = normalize_render_receipt(packet())
        right = normalize_render_receipt(packet())
        self.assertEqual(left["receipt_sha256"], right["receipt_sha256"])


if __name__ == "__main__":
    unittest.main()
