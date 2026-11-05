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


if __name__ == "__main__":
    unittest.main()
