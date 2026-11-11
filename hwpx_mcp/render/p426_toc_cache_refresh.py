"""Refresh an HWPX native TOC's *cached* page numbers from actual rhwp SVG evidence.

This updates only TOC entry tab tails inside a copied HWPX ZIP. The native
hyperlinks, outline/bookmarks and other OWPML objects are preserved. A later
Hancom/rhwp renderer may repaginate, so the final rendered output must be
rechecked independently; this is not native Hancom PAGE-field recalculation.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from lxml import etree

from scripts.p426_visual_toc_audit import audit_toc_page_cache

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _native_toc_entry(paragraph: etree._Element) -> tuple[str, ElementTree.Element] | None:
    """Find only the TOC-generated HYPERLINK→OUTLINE, never arbitrary tabs."""
    fields = paragraph.findall(f".//{HP}fieldBegin")
    if not any(
        field.get("type") == "HYPERLINK" and any(
            item.get("name") == "TargetType"
            and item.text == "HWPHYPERLINK_TARGET_OUTLINE"
            for item in field.findall(f".//{HP}stringParam")
        )
        for field in fields
    ):
        return None
    matches = []
    for t in paragraph.findall(f".//{HP}t"):
        tab = t.find(f"{HP}tab")
        if tab is not None and (t.text or "").strip():
            matches.append(((t.text or "").strip(), tab))
    if len(matches) != 1:
        raise ValueError("TOC_NATIVE_ENTRY_AMBIGUOUS")
    return matches[0]


def refresh_native_toc_cache_from_svg(
    source: Path, destination: Path,
    svg_pages: list[bytes], headings: list[str],
) -> dict:
    """Require complete 1-indexed page evidence before copying and patching.

    Invalid/ambiguous heading detection fails closed: no output is produced.
    """
    source, destination = Path(source), Path(destination)
    if not source.is_file() or source.suffix.lower() != ".hwpx":
        raise ValueError("TOC_SOURCE_HWPX_INVALID")
    if source.resolve() == destination.resolve() or destination.exists():
        raise FileExistsError("TOC_REFRESH_REQUIRES_NEW_DESTINATION")
    audit = audit_toc_page_cache(svg_pages, headings)
    if audit["unresolved_heading_count"] != 0:
        raise ValueError("TOC_RENDERED_HEADING_LOCATION_INCOMPLETE")
    expected = {
        f"{idx}. {heading.strip()}": item["rendered_heading_page"]
        for idx, (heading, item) in enumerate(zip(headings, audit["headings"]), 1)
    }
    if len(expected) != len(headings) or not all(type(v) is int and v >= 1 for v in expected.values()):
        raise ValueError("TOC_RENDERED_PAGE_MAPPING_INVALID")

    source_bytes = source.read_bytes()
    changes = []
    with zipfile.ZipFile(source, "r") as archive:
        member_names = archive.namelist()
        if archive.testzip() is not None:
            raise ValueError("TOC_SOURCE_ZIP_INVALID")
        xml_updates = {}
        seen = set()
        for member in member_names:
            if not member.startswith("Contents/section") or not member.endswith(".xml"):
                continue
            root = etree.fromstring(archive.read(member))
            touched = False
            for paragraph in root.iter(f"{HP}p"):
                entry = _native_toc_entry(paragraph)
                if entry is None:
                    continue
                title, tab = entry
                if title not in expected or title in seen:
                    raise ValueError("TOC_UNEXPECTED_OR_DUPLICATE_ENTRY")
                seen.add(title)
                previous = (tab.tail or "").strip()
                if not previous.isdecimal():
                    raise ValueError("TOC_CACHED_PAGE_NOT_NUMERIC")
                requested = str(expected[title])
                if previous != requested:
                    tab.tail = requested
                    changes.append({
                        "heading": title, "previous_cached_page": int(previous),
                        "rendered_page": expected[title],
                    })
                    touched = True
            if touched:
                xml_updates[member] = etree.tostring(
                    root, encoding="utf-8", xml_declaration=True,
                )
        if seen != set(expected):
            raise ValueError("TOC_NATIVE_ENTRIES_MISSING")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(
            prefix="p426-toc-candidate-", suffix=".hwpx", dir=destination.parent
        )
        os.close(fd)
        try:
            with zipfile.ZipFile(temp, "w") as target:
                for entry in archive.infolist():
                    target.writestr(entry, xml_updates.get(entry.filename, archive.read(entry.filename)))
            with zipfile.ZipFile(temp, "r") as completed:
                if completed.testzip() is not None:
                    raise ValueError("TOC_REFRESHED_ZIP_INVALID")
            os.replace(temp, destination)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return {
        "ok": True, "source_sha256": _sha(source_bytes),
        "refreshed_sha256": _sha(destination.read_bytes()),
        "changed_entry_count": len(changes),
        "entry_count": len(expected),
        "changes": changes,
        "source_unchanged": _sha(source.read_bytes()) == _sha(source_bytes),
        "authority": "RHWP_RENDERED_PAGE_TO_NATIVE_TOC_CACHE_NOT_HANCOM_ORACLE",
        "re_render_required": True,
        "native_hancom_pagination_verified": False,
    }
