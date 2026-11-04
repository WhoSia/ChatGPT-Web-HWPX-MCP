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


if __name__ == "__main__":
    unittest.main()
