"""Frozen A1 baseline provenance: human review is not a static detector."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "benchmarks/authorbench_a1_human_review.json"


class TestAuthorBenchA1EvidenceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = json.loads(REVIEW.read_text(encoding="utf-8"))

    def test_frozen_human_evidence_has_independent_authority(self):
        self.assertEqual(self.review["benchmark"], "A1")
        self.assertEqual(
            self.review["specimen"],
            "artifacts/authorbench-a1-generative-ai-science.hwpx",
        )
        self.assertEqual(
            self.review["authority"],
            "HUMAN_VISUAL_REVIEW_GROUND_TRUTH_NOT_AUTOMATIC_AESTHETIC_NORM",
        )

    def test_observed_section_weakness_is_not_relabelled_static(self):
        findings = {f["code"]: f for f in self.review["findings"]}
        self.assertIn("SECTION_SEPARATION_WEAK", findings)
        self.assertEqual(findings["SECTION_SEPARATION_WEAK"]["severity"], "MEDIUM")
        self.assertIn("NARRATIVE_ORDER_CONCLUSION_EARLY", findings)
        self.assertEqual(
            findings["NARRATIVE_ORDER_CONCLUSION_EARLY"]["automatic_static_detection"],
            "NOT_SUPPORTED_WITHOUT_SEMANTIC_MANIFEST",
        )

    def test_frozen_review_covers_distinct_design_defect_families(self):
        codes = {f["code"] for f in self.review["findings"]}
        self.assertTrue({
            "SECTION_SEPARATION_WEAK",
            "TABLE_HEADER_CONTRAST_WEAK",
            "HIERARCHY_CONTRAST_WEAK",
            "TABLE_READING_ERGONOMICS_WEAK",
        }.issubset(codes))


if __name__ == "__main__":
    unittest.main()
