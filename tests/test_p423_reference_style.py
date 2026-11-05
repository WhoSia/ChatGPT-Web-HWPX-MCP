"""Reference-to-style extraction is opt in, lossy only with explicit warnings."""
import unittest
from unittest.mock import patch

from hwpx_mcp.document.p423_reference_style import profile_from_reference


class P423ReferenceStyleTests(unittest.TestCase):
    @patch("hwpx_mcp.document.p423_reference_style.build_role_aware_style_exemplars")
    def test_reference_body_typography_becomes_portable_profile(self, reader):
        reader.return_value = {
            "profile_sha256": "source-certificate",
            "roles": [
                {"role": "body", "authoring_preset": {
                    "run_format": {"size": 11, "font_by_script": {"hangul": "함초롬바탕"}},
                    "paragraph_format": {"alignment": "justify", "line_spacing_percent": 160},
                }},
            ],
        }
        result = profile_from_reference("reference.hwpx", name="school-example")
        self.assertEqual(result["style_profile"]["roles"]["body"]["run"]["size"], 11)
        self.assertEqual(result["style_profile"]["roles"]["body"]["paragraph"]["alignment"], "JUSTIFY")
        self.assertEqual(result["status"], "CANDIDATE_REQUIRES_USER_APPROVAL")
        self.assertFalse(result["source_text_included"])
        self.assertEqual(result["reference_exemplar_sha256"], "source-certificate")

    def test_unsupported_reference_fields_return_warning(self):
        with patch("hwpx_mcp.document.p423_reference_style.build_role_aware_style_exemplars") as reader:
            reader.return_value = {"roles": [{"role": "body", "authoring_preset": {
                "run_format": {"size": 11, "letter_spacing_by_script_readback_only": {"hangul": -3}},
                "paragraph_format": {"indent_left_mm": 5},
            }}]}
            result = profile_from_reference("ref.hwpx")
        self.assertGreaterEqual(len(result["warnings"]), 2)
        self.assertEqual(result["style_profile"]["roles"]["body"]["run"]["size"], 11)

    def test_unknown_reference_roles_are_not_assigned_to_body(self):
        with patch("hwpx_mcp.document.p423_reference_style.build_role_aware_style_exemplars") as reader:
            reader.return_value = {"roles": [
                {"role": "footer", "authoring_preset": {"run_format": {"size": 9}}},
                {"role": "body", "authoring_preset": {"run_format": {"size": 11}}},
            ]}
            result = profile_from_reference("ref.hwpx")
        self.assertIn("body", result["style_profile"]["roles"])
        self.assertEqual(set(result["style_profile"]["roles"]), {"body"})
        self.assertTrue(any("footer" in warning for warning in result["warnings"]))

    def test_unportable_reference_cannot_be_silently_accepted(self):
        with patch("hwpx_mcp.document.p423_reference_style.build_role_aware_style_exemplars") as reader:
            reader.return_value = {"roles": [{"role": "table_cell", "authoring_preset": {"run_format": {"size": 9}}}]}
            with self.assertRaisesRegex(ValueError, "no portable"):
                profile_from_reference("ref.hwpx")

    def test_reference_profile_does_not_include_private_text_or_locators(self):
        with patch("hwpx_mcp.document.p423_reference_style.build_role_aware_style_exemplars") as reader:
            reader.return_value = {"profile_sha256": "abc", "roles": [{
                "role": "body", "authoring_preset": {"run_format": {"size": 11}},
                "assignments": [{"locator": "secret_document_id", "text": "PRIVATE_REPORT_TEXT"}],
            }]}
            result = profile_from_reference("ref.hwpx")
        self.assertNotIn("PRIVATE_REPORT_TEXT", repr(result))
        self.assertNotIn("secret_document_id", repr(result))


if __name__ == "__main__":
    unittest.main()
