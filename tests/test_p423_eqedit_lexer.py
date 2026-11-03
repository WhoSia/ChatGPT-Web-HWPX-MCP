import unittest
from hwpx_mcp.document.p423_eqedit_lexer import scan_eqedit

class P423EqEditLexerTests(unittest.TestCase):
    def test_braces_do_not_reset_font(self):
        self.assertEqual(scan_eqedit('M _{rm perp} (0)').final_font, 'upright')

if __name__ == '__main__':
    unittest.main()
