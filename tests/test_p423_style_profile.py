"""User-facing P4.23 style profiles are portable, explicit and validated."""
import unittest

from hwpx_mcp.document.p423_style_profile import (
    normalize_style_profile, profile_fingerprint, style_for_block,
    PROFILE_SCHEMA,
)


class P423StyleProfileTests(unittest.TestCase):
    def test_profile_normalization_preserves_allowed_roles(self):
        profile = normalize_style_profile({
            "schema": PROFILE_SCHEMA, "name": "Lab report",
            "roles": {"body": {"run": {"size": 11}, "paragraph": {"line_spacing_percent": 155}}},
        })
        self.assertEqual(profile["roles"]["body"]["run"]["size"], 11)
        self.assertEqual(style_for_block(profile, "paragraph")["paragraph"]["line_spacing_percent"], 155)


if __name__ == "__main__":
    unittest.main()
