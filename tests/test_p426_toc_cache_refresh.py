"""Real HWPX TOC cached pages corrected using renderer-derived page evidence."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from hwpx_mcp.render.p426_toc_cache_refresh import (
    discover_native_toc_headings,
    refresh_native_toc_cache_from_svg, _native_toc_entry, HP,
)
from scripts.p426_generate_native_showcase import create_showcase
from lxml import etree


HEADINGS = ["연구 배경", "이론적 분석", "합성 실험 결과", "결론 및 한계"]


def _svg(*lines: str) -> bytes:
    rows = "".join(
        f'<text x="25" y="{100 + idx * 25}">{line}</text>'
        for idx, line in enumerate(lines)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg">' + rows + '</svg>'
    ).encode("utf-8")


def _pages() -> list[bytes]:
    return [
        _svg("목차", "1.연구배경1", "2.이론적분석1",
             "3.합성실험결과1", "4.결론및한계1",
             "1.연구배경", "2.이론적분석", "3.합성실험결과"),
        _svg("그림1"),
        _svg("전압전류표"),
        _svg("전압전류표"),
        _svg("4.결론및한계"),
    ]


def _toc_pages(path: Path) -> dict[str, int]:
    result = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("Contents/section") or not name.endswith(".xml"):
                continue
            root = etree.fromstring(archive.read(name))
            for p in root.iter(f"{HP}p"):
                entry = _native_toc_entry(p)
                if entry is not None:
                    title, tab = entry
                    result[title] = int((tab.tail or "").strip())
    return result


class NativeTOCRefreshTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="p426-toc-refresh-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        output = create_showcase(self.folder, table_segment_rows=28)
        self.source = self.folder / output["filename"]
        self.refreshed = self.folder / "refreshed.hwpx"

    def test_discovers_actual_numbered_toc_titles_without_hardcoding(self):
        observed = discover_native_toc_headings(self.source)
        self.assertEqual(observed, HEADINGS)

    def test_real_hwpx_cached_pages_updated_from_visual_evidence_only(self):
        before = _toc_pages(self.source)
        self.assertEqual(before["4. 결론 및 한계"], 1)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        result = refresh_native_toc_cache_from_svg(
            self.source, self.refreshed, _pages(), HEADINGS,
        )
        after = _toc_pages(self.refreshed)
        self.assertEqual(after, {
            "1. 연구 배경": 1,
            "2. 이론적 분석": 1,
            "3. 합성 실험 결과": 1,
            "4. 결론 및 한계": 5,
        })
        self.assertEqual(result["changed_entry_count"], 1)
        self.assertEqual(result["source_sha256"], digest)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), digest)
        self.assertTrue(result["re_render_required"])
        self.assertFalse(result["native_hancom_pagination_verified"])
        with zipfile.ZipFile(self.source) as a, zipfile.ZipFile(self.refreshed) as b:
            self.assertEqual(set(a.namelist()), set(b.namelist()))
            changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
            self.assertEqual(changed, ["Contents/section0.xml"])

    def test_incomplete_visual_evidence_never_creates_output(self):
        pages = _pages()[:2]
        with self.assertRaisesRegex(ValueError, "LOCATION_INCOMPLETE"):
            refresh_native_toc_cache_from_svg(
                self.source, self.refreshed, pages, HEADINGS,
            )
        self.assertFalse(self.refreshed.exists())

    def test_source_cannot_be_overwritten(self):
        with self.assertRaises(FileExistsError):
            refresh_native_toc_cache_from_svg(
                self.source, self.source, _pages(), HEADINGS,
            )


if __name__ == "__main__":
    unittest.main()
