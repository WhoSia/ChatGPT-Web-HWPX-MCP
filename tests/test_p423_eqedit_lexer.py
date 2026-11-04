import json
import unittest
from pathlib import Path
from hwpx_mcp.document.p423_eqedit_lexer import scan_eqedit

class P423EqEditLexerTests(unittest.TestCase):
    def test_braces_do_not_reset_font(self):
        self.assertEqual(scan_eqedit('M _{rm perp} (0)').final_font, 'upright')

    def test_explicit_it_restores_italic(self):
        self.assertEqual(scan_eqedit("M _{rm perp} it (0)").final_font, "italic")

    def test_quote_excludes_font_switch(self):
        report = scan_eqedit('M_{"rm"} it')
        self.assertEqual([t.value for t in report.tokens if t.kind == "font"], ["it"])

    def test_unclosed_brace_reports_issue(self):
        self.assertIn("unclosed_group", scan_eqedit("M _{rm perp").issues)

    def test_extra_brace_reports_issue(self):
        self.assertIn("extra_closing_brace", scan_eqedit("M}").issues)

    def test_uppercase_structure_commands_from_hancom(self):
        report = scan_eqedit("BOX{ M } LEFT( a RIGHT)")
        self.assertEqual(
            [token.value for token in report.tokens if token.kind == "structure"],
            ["box", "left", "right"],
        )

    def test_human_corrected_fixture_is_lexable(self):
        source = Path(__file__).parent / "fixtures" / "p423_mri_human_corrected_eqedit.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(len(data["examples"]), 6)
        for example in data["examples"]:
            report = scan_eqedit(example["script"])
            self.assertEqual(report.issues, (), example["id"])

if __name__ == '__main__':
    unittest.main()
