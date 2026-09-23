from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light
from p335_corpus import build_corpus_style_profile, build_style_library
from p335_paragraph import (
    build_document_style_exemplar,
    build_paragraph_geometry_profile,
    build_role_aware_style_exemplars,
    build_style_transfer_operations,
    compare_paragraph_geometry_profiles,
    paragraph_geometry_contract,
)


def _make(path: Path, text: str) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph(text)
    doc.save_to_path(str(path))
    doc.close()
    return next(
        p["locator"] for p in build_document_map(path)["paragraphs"]
        if p["text"] == text
    )


class P335ParagraphProfileTests(unittest.TestCase):
    def test_paragraph_contract_is_feature_first_and_exposes_tabs(self):
        contract = paragraph_geometry_contract()
        self.assertEqual(contract["strategy"], "FEATURE_FIRST_EXISTING_PRIMITIVE_REPROMOTION")
        self.assertIn("tab_stops", contract["authoring_keys"])
        self.assertIn("tabPrIDRef", contract["readback"]["tabs"])

    def test_formatting_map_resolves_tab_property_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "default.hwpx"
            loc = _make(path, "본문")
            para = next(p for p in build_formatting_map(path)["paragraphs"] if p["locator"] == loc)
            prop = para["paragraph_property"]
            self.assertIn("tab_pr_id_ref", prop)
            self.assertIn("tab_property", prop)
            if prop["tab_pr_id_ref"] is not None:
                self.assertTrue(prop["tab_property"] is None or prop["tab_property"]["tag"] == "tabPr")

    def test_paragraph_profile_and_exemplar_capture_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "geometry.hwpx"
            loc = _make(path, "문단 geometry")
            apply_formatting_atomic(
                path,
                [{
                    "op": "set_paragraph_format",
                    "target": loc,
                    "format": {
                        "alignment": "center",
                        "line_spacing_percent": 180,
                        "indent_left_mm": 5,
                        "indent_right_mm": 3,
                        "first_line_indent_mm": 2,
                        "spacing_before_pt": 6,
                        "spacing_after_pt": 4,
                    },
                }],
                expected_revision=1,
                current_revision=1,
                validator=validate_hwpx_package_light,
            )

            profile = build_paragraph_geometry_profile(path)
            alignment = profile["alignment"][0]["value"]
            self.assertEqual(str(alignment["horizontal"]).upper(), "CENTER")
            line = profile["line_spacing"][0]["value"]
            self.assertEqual(str(line["type"]).upper(), "PERCENT")
            self.assertEqual(float(line["value"]), 180)

            exemplar = build_document_style_exemplar(path)
            preset = exemplar["authoring_preset"]["paragraph_format"]
            self.assertEqual(preset["alignment"], "center")
            self.assertEqual(preset["line_spacing_percent"], 180)
            self.assertLess(abs(preset["indent_left_mm"] - 5), 0.02)
            self.assertLess(abs(preset["indent_right_mm"] - 3), 0.02)
            self.assertLess(abs(preset["first_line_indent_mm"] - 2), 0.02)
            self.assertLess(abs(preset["spacing_before_pt"] - 6), 0.02)
            self.assertLess(abs(preset["spacing_after_pt"] - 4), 0.02)

    def test_corpus_profile_preserves_provenance_and_builds_candidate_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.hwpx"
            b = root / "b.hwpx"
            _make(a, "기관 A 본문")
            _make(b, "기관 B 본문")
            profile = build_corpus_style_profile([
                {
                    "path": str(a),
                    "source_id": "a",
                    "institution": "기관A",
                    "provenance_url": "https://example.invalid/a",
                    "public_status": "PUBLIC_SOURCE",
                    "license_note": "fixture",
                },
                {
                    "path": str(b),
                    "source_id": "b",
                    "institution": "기관B",
                    "provenance_url": "https://example.invalid/b",
                    "public_status": "PUBLIC_SOURCE",
                    "license_note": "fixture",
                },
            ])
            self.assertEqual(profile["document_count"], 2)
            self.assertEqual({row["source_id"] for row in profile["source_receipts"]}, {"a", "b"})
            self.assertEqual({row["institution"] for row in profile["institution_summary"]}, {"기관A", "기관B"})
            library = build_style_library(profile, min_documents=2, min_share=0.5)
            self.assertTrue(all(entry["authority"].startswith("EVIDENCE_GUIDED") for entry in library["entries"]))

    def test_role_aware_exemplar_uses_conservative_body_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roles.hwpx"
            loc = _make(path, "일반 본문")
            profile = build_role_aware_style_exemplars(path)
            body = next(item for item in profile["roles"] if item["role"] == "body")
            self.assertEqual(body["paragraph_count"], 1)
            self.assertIn("paragraph_format", body["authoring_preset"])
            assignment = next(item for item in profile["assignments"] if item["locator"] == loc)
            self.assertEqual(assignment["role"], "body")
            self.assertEqual(assignment["basis"], "conservative_fallback")

    def test_style_exemplar_compiles_to_existing_atomic_formatting_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.hwpx"
            target = Path(tmp) / "target.hwpx"
            source_loc = _make(source, "스타일 원본")
            target_loc = _make(target, "스타일 대상")

            apply_formatting_atomic(
                source,
                [{
                    "op": "set_paragraph_format",
                    "target": source_loc,
                    "format": {
                        "alignment": "center",
                        "line_spacing_percent": 175,
                        "indent_left_mm": 4,
                        "first_line_indent_mm": 1.5,
                        "spacing_after_pt": 5,
                    },
                }],
                expected_revision=1,
                current_revision=1,
                validator=validate_hwpx_package_light,
            )

            exemplar = build_document_style_exemplar(source)
            operations = build_style_transfer_operations(
                exemplar,
                [target_loc],
                include_typography=False,
                include_paragraph=True,
            )
            self.assertEqual([op["op"] for op in operations], ["set_paragraph_format"])

            apply_formatting_atomic(
                target,
                operations,
                expected_revision=1,
                current_revision=1,
                validator=validate_hwpx_package_light,
            )
            preset = build_document_style_exemplar(target)["authoring_preset"]["paragraph_format"]
            self.assertEqual(preset["alignment"], "center")
            self.assertEqual(preset["line_spacing_percent"], 175)
            self.assertLess(abs(preset["indent_left_mm"] - 4), 0.02)
            self.assertLess(abs(preset["first_line_indent_mm"] - 1.5), 0.02)
            self.assertLess(abs(preset["spacing_after_pt"] - 5), 0.02)

    def test_paragraph_profile_comparison_reports_geometry_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left.hwpx"
            right = Path(tmp) / "right.hwpx"
            l = _make(left, "왼쪽")
            r = _make(right, "오른쪽")
            apply_formatting_atomic(
                left,
                [{"op": "set_paragraph_format", "target": l, "format": {"alignment": "left", "line_spacing_percent": 160}}],
                expected_revision=1,
                current_revision=1,
                validator=validate_hwpx_package_light,
            )
            apply_formatting_atomic(
                right,
                [{"op": "set_paragraph_format", "target": r, "format": {"alignment": "right", "line_spacing_percent": 190}}],
                expected_revision=1,
                current_revision=1,
                validator=validate_hwpx_package_light,
            )
            diff = compare_paragraph_geometry_profiles(
                build_paragraph_geometry_profile(left),
                build_paragraph_geometry_profile(right),
            )
            dims = {row["dimension"] for row in diff["dominant_differences"]}
            self.assertIn("alignment", dims)
            self.assertIn("line_spacing", dims)


if __name__ == "__main__":
    unittest.main()
