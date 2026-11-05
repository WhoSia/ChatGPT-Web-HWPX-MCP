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

    def test_unknown_top_level_key_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            normalize_style_profile({"execute": "anything"})

    def test_style_profile_rejects_bad_page_margin(self):
        with self.assertRaisesRegex(ValueError, "margin"):
            normalize_style_profile({"page": {"margin_left_mm": -5}})

    def test_equation_size_cannot_be_boolean(self):
        with self.assertRaisesRegex(ValueError, "equation_base_unit"):
            normalize_style_profile({"equation_base_unit": True})

    def test_heading_role_is_scoped_to_level(self):
        p = normalize_style_profile({"roles": {"heading_2": {"run": {"size": 13}}}})
        self.assertEqual(style_for_block(p, "heading", 2)["run"]["size"], 13)
        self.assertEqual(style_for_block(p, "heading", 1), {})

    def test_profile_rejects_execution_payloads(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            normalize_style_profile({"roles": {"body": {"run": {"__import__": "os"}}}})

    def test_profile_accepts_korean_font_name(self):
        p = normalize_style_profile({"roles": {"body": {"run": {"font_by_script": {"hangul": "함초롬바탕", "latin": "Malgun Gothic"}}}}})
        self.assertEqual(p["roles"]["body"]["run"]["font_by_script"]["hangul"], "함초롬바탕")

    def test_bad_table_color_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "border_color"):
            normalize_style_profile({"table": {"border_color": "blue"}})

    def test_inherited_body_style_flows_into_heading(self):
        p = normalize_style_profile({"roles": {
            "body": {"run": {"font_by_script": {"hangul": "함초롬바탕", "latin": "Malgun Gothic"}, "size": 11}},
            "heading_1": {"inherits": "body", "run": {"size": 15, "bold": True}},
        }})
        heading = style_for_block(p, "heading", 1)["run"]
        self.assertEqual(heading["size"], 15)
        self.assertTrue(heading["bold"])
        self.assertEqual(heading["font_by_script"]["hangul"], "함초롬바탕")


if __name__ == "__main__":
    unittest.main()
