import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from hwpx_mcp.document.p423_equation_corpus import extract_equations, pair_equations


def fixture(section_xml: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("Contents/section0.xml", section_xml)
    return stream.getvalue()


def read_fixture(payload: bytes):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.hwpx"
        path.write_bytes(payload)
        return extract_equations(path)


class P423EquationCorpusTests(unittest.TestCase):
    def test_extracts_scripts_but_not_prose(self):
        records = read_fixture(fixture(
            '<section><p>Private prose</p><equation><script>M_{rm perp} it</script></equation></section>'
        ))
        self.assertEqual([row.script for row in records], ["M_{rm perp} it"])
        self.assertNotIn("Private prose", str(records))

    def test_empty_section_has_no_equations(self):
        self.assertEqual(read_fixture(fixture("<section><p>text</p></section>")), ())
    def test_preserves_equation_order(self):
        rows = read_fixture(fixture("<section><equation><script>a</script></equation><equation><script>b</script></equation></section>"))
        self.assertEqual([(r.index, r.script) for r in rows], [(0, "a"), (1, "b")])
    def test_missing_section_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "none.hwpx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("Contents/header.xml", "<header/>")
            with self.assertRaises(ValueError):
                extract_equations(path)
    def test_missing_script_fails_closed(self):
        with self.assertRaises(ValueError):
            read_fixture(fixture("<section><equation/></section>"))
    def test_pair_reports_hashes_without_scripts(self):
        a = read_fixture(fixture("<section><equation><script>a</script></equation></section>"))
        b = read_fixture(fixture("<section><equation><script>b</script></equation></section>"))
        pairs = pair_equations(a, b)
        self.assertTrue(pairs[0]["changed"])
        self.assertNotIn("script", pairs[0])
        self.assertNotEqual(pairs[0]["before_sha256"], pairs[0]["after_sha256"])
    def test_identical_pair_is_unchanged(self):
        a = read_fixture(fixture("<section><equation><script>a</script></equation></section>"))
        self.assertFalse(pair_equations(a, a)[0]["changed"])
    def test_changed_equation_count_requires_review(self):
        a = read_fixture(fixture("<section><equation><script>a</script></equation></section>"))
        b = read_fixture(fixture("<section></section>"))
        with self.assertRaises(ValueError):
            pair_equations(a, b)
    def test_doctype_is_rejected(self):
        xml = '<!DOCTYPE section [<!ENTITY x "unsafe">]><section/>'
        with self.assertRaises(ValueError):
            read_fixture(fixture(xml))
    def test_namespaced_native_equations(self):
        xml = '<sec xmlns:hp="urn:hp"><hp:equation><hp:script>it M</hp:script></hp:equation></sec>'
        rows = read_fixture(fixture(xml))
        self.assertEqual(rows[0].script, "it M")
    def test_duplicate_zip_members_are_rejected(self):
        import warnings
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "duplicate.hwpx"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "w") as z:
                    z.writestr("Contents/section0.xml", "<section/>")
                    z.writestr("Contents/section0.xml", "<section/>")
            with self.assertRaises(ValueError):
                extract_equations(path)

if __name__ == "__main__":
    unittest.main()
