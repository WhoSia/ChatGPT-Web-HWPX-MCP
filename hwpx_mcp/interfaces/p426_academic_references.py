"""Native academic references, bookmarks and page fields from retained HWPX.

Unlike a list of printed citation strings, these are actual P3.19
bookmarks and cross-reference fields. Cached page numbers remain
renderer-dependent until the document is repaginated.
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def register_academic_reference_tools(core):
    @core.mcp.tool()
    def inspect_document_references(
        document_id: str,
        limit: int = 100,
    ) -> dict:
        """Inspect actual native HWPX bookmarks, TOC and crossref fields."""
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("REFERENCE_LIMIT_INVALID")
        owner = core._caller_subject()
        core._paths(document_id)
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row.get("owner_subject") != owner:
            raise FileNotFoundError("OWNED_REFERENCE_DOCUMENT_NOT_FOUND")
        from hwpx_mcp.document.p319_structured_publishing import (
            build_structured_publishing_map,
        )
        with tempfile.TemporaryDirectory(prefix="p426-references-") as tmp:
            source = Path(tmp) / "source.hwpx"
            source.write_bytes(row["bytes"])
            mapped = build_structured_publishing_map(source)
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "bookmarks": mapped["bookmarks"][:limit],
            "fields": mapped["fields"][:limit],
            "captions": mapped["captions"][:limit],
            "bookmark_count": len(mapped["bookmarks"]),
            "field_count": len(mapped["fields"]),
            "crossref_field_count": mapped["crossref_field_count"],
            "toc_field_count": mapped["toc_field_count"],
            "caption_count": len(mapped["captions"]),
            "truncated": any(
                len(mapped[key]) > limit for key in ("bookmarks", "fields", "captions")
            ),
            "structured_publishing_sha256": mapped["structured_publishing_sha256"],
            "page_reference_authority": "NATIVE_FIELD_WITH_CACHED_PAGE_REPAGINATION_REQUIRED",
        }
