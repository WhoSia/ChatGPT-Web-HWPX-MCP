import unittest
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

if __name__ == '__main__':
    unittest.main()
