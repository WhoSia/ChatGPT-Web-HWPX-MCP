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

    def test_profile_fingerprint_is_order_independent(self):
        a = {"roles": {"body": {"run": {"size": 11, "bold": False}}}, "name": "lab"}
        b = {"name": "lab", "roles": {"body": {"run": {"bold": False, "size": 11}}}}
        self.assertEqual(profile_fingerprint(a), profile_fingerprint(b))

    def test_profile_fingerprint_changes_with_font_size(self):
        a = {"roles": {"body": {"run": {"size": 10}}}}
        b = {"roles": {"body": {"run": {"size": 11}}}}
        self.assertNotEqual(profile_fingerprint(a), profile_fingerprint(b))

    def test_unknown_style_key_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            normalize_style_profile({"roles": {"body": {"run": {"magic_font": "x"}}}})


if __name__ == "__main__":
    unittest.main()
