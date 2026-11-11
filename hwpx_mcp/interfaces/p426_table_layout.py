"""P4.26 native long-table pagination policy inspection for owned HWPX.

This tool reports persistent OWPML table geometry, header flags and
pageBreak attributes, not inferred renderer page boundaries.
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def register_table_layout_tools(core):
    @core.mcp.tool()
    def inspect_document_table_layout(
        document_id: str, offset: int = 0, limit: int = 20,
    ) -> dict:
        """Read saved HWPX table header repetition and native break policy."""
        if type(offset) is not int or offset < 0:
            raise ValueError("TABLE_LAYOUT_OFFSET_INVALID")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("TABLE_LAYOUT_LIMIT_INVALID")
        subject = core._caller_subject()
        core._paths(document_id)
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row.get("owner_subject") != subject:
            raise FileNotFoundError("OWNED_TABLE_DOCUMENT_NOT_FOUND")
        from hwpx_mcp.document.p323_advanced_tables import build_advanced_table_map
        with tempfile.TemporaryDirectory(prefix="p426-table-inspect-") as tmp:
            source = Path(tmp) / "owned.hwpx"
            source.write_bytes(row["bytes"])
            mapped = build_advanced_table_map(source)
        tables = mapped["tables"]
        selected = tables[offset:offset + limit]
        return {
            "ok": True, "document_id": document_id, "revision": row["revision"],
            "table_count": len(tables),
            "tables": [
                {
                    "locator": item["locator"],
                    "rows": item["rows"], "cols": item["cols"],
                    "repeat_header": item["repeat_header"],
                    "page_break": item["page_break"],
                    "first_row_marked_header": bool(
                        item["row_geometry"] and item["row_geometry"][0]["all_header"]
                    ),
                    "row_geometry": item["row_geometry"],
                } for item in selected
            ],
            "next_offset": offset + limit if offset + limit < len(tables) else None,
            "layout_authority": "SAVED_HWPX_TABLE_PROPERTIES_NOT_RENDERED_PAGES",
            "page_boundary_verified": False,
        }
