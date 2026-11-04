import tempfile
import unittest
import zipfile
from pathlib import Path

from hwpx_mcp.document.p423_document_shell import (
    inspect_document_shell, compare_document_shell,
)


def make_hwpx(xml: str):
    temp = tempfile.TemporaryDirectory()
    path = Path(temp.name) / "fixture.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)
    return temp, path


class P423DocumentShellTests(unittest.TestCase):
    def test_script_change_preserves_text_digest(self):
        a, first = make_hwpx('<s><p><t>Report</t><equation><script>rm A</script></equation></p></s>')
        b, second = make_hwpx('<s><p><t>Report</t><equation><script>rm A it</script></equation></p></s>')
        try:
            comparison = compare_document_shell(
                inspect_document_shell(first), inspect_document_shell(second)
            )
            self.assertTrue(all(comparison.values()))
        finally:
            a.cleanup()
            b.cleanup()

    def test_plain_text_change_changes_digest(self):
        a, first = make_hwpx('<s><p><t>Initial</t></p></s>')
        b, second = make_hwpx('<s><p><t>Revised</t></p></s>')
        try:
            diff = compare_document_shell(inspect_document_shell(first), inspect_document_shell(second))
            self.assertFalse(diff["text_exact_fragment_digest_preserved"])
            self.assertTrue(diff["paragraph_count_preserved"])
        finally:
            a.cleanup()
            b.cleanup()
    def test_extra_paragraph_changes_shell_count(self):
        a, first = make_hwpx('<s><p><t>A</t></p></s>')
        b, second = make_hwpx('<s><p><t>A</t></p><p/></s>')
        try:
            diff = compare_document_shell(inspect_document_shell(first), inspect_document_shell(second))
            self.assertFalse(diff["paragraph_count_preserved"])
        finally:
            a.cleanup()
            b.cleanup()
    def test_equation_count_change_is_detected(self):
        a, first = make_hwpx('<s><p><t>A</t></p></s>')
        b, second = make_hwpx('<s><p><t>A</t><equation><script>x</script></equation></p></s>')
        try:
            diff = compare_document_shell(inspect_document_shell(first), inspect_document_shell(second))
            self.assertFalse(diff["equation_count_preserved"])
        finally:
            a.cleanup()
            b.cleanup()

if __name__ == "__main__":
    unittest.main()
