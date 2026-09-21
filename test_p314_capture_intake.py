from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from p314_capture_intake import adjudicate_first_hancom_world_contact


ROOT = Path(__file__).resolve().parent
RECEIPT = json.loads(
    (ROOT / "fixtures" / "p314_first_hancom_capture_receipt.json").read_text(encoding="utf-8")
)


class P314CaptureIntakeTests(unittest.TestCase):
    def test_first_world_contact_passes_but_cross_version_holds(self):
        result = adjudicate_first_hancom_world_contact(RECEIPT)
        self.assertTrue(result["world_contact_pass"])
        self.assertTrue(result["baseline_exact_pixel_pass"])
        self.assertTrue(result["positive_sensitivity_pass"])
        self.assertFalse(result["cross_version_pass"])
        self.assertEqual(
            result["verdict"],
            "FIRST_HANCOM_WORLD_CONTACT_PASS_CROSS_VERSION_HOLD",
        )
        self.assertEqual(result["promotion_ceiling"], "CROSS_VERSION_REPLAY_REQUIRED")

    def test_dead_oracle_baseline_only_cannot_pass_sensitivity(self):
        bad = copy.deepcopy(RECEIPT)
        bad["positive_controls"]["advance"]["selected_line_break_equal"] = True
        result = adjudicate_first_hancom_world_contact(bad)
        self.assertFalse(result["positive_sensitivity_pass"])
        self.assertFalse(result["world_contact_pass"])

    def test_integrity_mismatch_is_fatal(self):
        bad = copy.deepcopy(RECEIPT)
        bad["integrity"]["manifest_document_hashes_matched"] = 37
        with self.assertRaises(ValueError):
            adjudicate_first_hancom_world_contact(bad)

    def test_second_version_reopens_promotion_candidate(self):
        promoted = copy.deepcopy(RECEIPT)
        promoted["cross_version"]["distinct_hancom_versions"] = 2
        promoted["cross_version"]["versions"] = ["13.0.0.3622", "second-version"]
        result = adjudicate_first_hancom_world_contact(promoted)
        self.assertTrue(result["cross_version_pass"])
        self.assertEqual(
            result["verdict"],
            "CONDITIONAL_PIXEL_FIDELITY_PROMOTION_CANDIDATE",
        )


if __name__ == "__main__":
    unittest.main()
