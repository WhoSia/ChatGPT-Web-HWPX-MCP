"""P4.24 competitor benchmark must never fabricate matched PASS results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.p424_competitor_benchmark import (
    compare_matched, read_jsonl, validate_run,
)


FIXTURE = hashlib.sha256(b"synthetic public benchmark fixture").hexdigest()


def case(product: str, elapsed: int = 100, **override):
    record = {
        "product": product, "task": "report", "fixture_sha256": FIXTURE,
        "environment": "windows-hancom-build-1", "status": "PASS",
        "elapsed_ms": elapsed, "consumer_verified": True,
        "native_visual_accepted": True,
        "artifact_sha256": hashlib.sha256(product.encode()).hexdigest(),
    }
    record.update(override)
    return record


class P424CompetitorBenchmarkTests(unittest.TestCase):
    def test_matched_pair_delta_is_descriptive_not_ranked(self):
        result = compare_matched([case("ours", 120), case("other", 80)], "ours", "other")
        self.assertEqual(result["verified_matched_pairs"], 1)
        self.assertEqual(result["median_candidate_minus_baseline_ms"], -40)
        self.assertFalse(result["ranking_authorized"])

    def test_unmatched_hardware_cannot_be_paired(self):
        result = compare_matched([
            case("ours"), case("other", environment="linux-mock")
        ], "ours", "other")
        self.assertEqual(result["verified_matched_pairs"], 0)
        self.assertEqual(result["excluded"]["missing_comparator"], 2)
        self.assertIsNone(result["median_candidate_minus_baseline_ms"])

    def test_native_visual_hold_cannot_be_pass(self):
        with self.assertRaisesRegex(ValueError, "native visual"):
            validate_run(case("ours", native_visual_accepted=False))

    def test_consumer_hold_cannot_be_pass(self):
        with self.assertRaisesRegex(ValueError, "consumer verification"):
            validate_run(case("ours", consumer_verified=False))

    def test_non_pass_cannot_claim_completed_consumer(self):
        with self.assertRaisesRegex(ValueError, "non-PASS"):
            validate_run(case("ours", status="UNSUPPORTED"))

    def test_duplicate_product_task_fixture_environment_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate trial"):
            compare_matched([case("ours"), case("ours"), case("other")], "ours", "other")

    def test_bad_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "fixture_sha256"):
            validate_run(case("ours", fixture_sha256="a" * 63))

    def test_zero_or_nonfinite_time_rejected(self):
        for ms in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(ms=ms), self.assertRaisesRegex(ValueError, "elapsed_ms"):
                validate_run(case("ours", elapsed_ms=ms))

    def test_unverified_pairs_are_excluded(self):
        waiting = case("other", status="UNVERIFIED",
                       consumer_verified=False, native_visual_accepted=False)
        result = compare_matched([case("ours"), waiting], "ours", "other")
        self.assertEqual(result["excluded"]["not_both_verified_pass"], 1)
        self.assertEqual(result["verified_matched_pairs"], 0)

    def test_jsonl_rejects_corrupt_and_preserves_line_number(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "runs.jsonl"
            path.write_text(json.dumps(case("ours")) + "\n" + "{bad", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                read_jsonl(path)

    def test_no_leaderboard_without_matched_runs(self):
        r = compare_matched([], "ours", "other")
        self.assertEqual(r["verified_matched_pairs"], 0)
        self.assertFalse(r["ranking_authorized"])


if __name__ == "__main__":
    unittest.main()
