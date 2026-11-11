"""P4.26 opt-in long-table segmentation into small native HWPX tables.

Designed as an alternative to continuous OWPML pageBreak=CELL when
actual layout engines clip long cell text. The mode preserves all data
rows and the logical caption number, with explicit page breaks between
segments. It is not a guarantee of Windows Hancom pixel parity.
"""
from __future__ import annotations

from copy import deepcopy


def segment_native_long_tables(
    blocks: list[dict],
    *,
    max_rows_per_segment: int = 20,
    page_break_before_each: bool = True,
) -> dict:
    if not isinstance(blocks, list):
        raise ValueError("TABLE_SEGMENT_BLOCKS_INVALID")
    if (type(max_rows_per_segment) is not int
            or not 5 <= max_rows_per_segment <= 60):
        raise ValueError("TABLE_SEGMENT_ROWS_INVALID")
    if type(page_break_before_each) is not bool:
        raise ValueError("TABLE_SEGMENT_PAGE_BREAK_INVALID")

    result: list[dict] = []
    summaries = []
    for index, source in enumerate(blocks):
        if not isinstance(source, dict):
            raise ValueError("TABLE_SEGMENT_BLOCK_INVALID")
        if source.get("type") != "table":
            result.append(deepcopy(source))
            continue
        grid = source.get("cells")
        if not isinstance(grid, list) or not grid or len(grid) != source.get("rows"):
            raise ValueError("TABLE_SEGMENT_GRID_INVALID")
        if len(grid) <= max_rows_per_segment:
            result.append(deepcopy(source))
            continue

        table_format = source.get("table_format") or {}
        if not isinstance(table_format, dict):
            raise ValueError("TABLE_SEGMENT_FORMAT_INVALID")
        if not (source.get("first_row_header") or table_format.get("first_row_header")):
            raise ValueError("TABLE_SEGMENT_REQUIRES_HEADER")
        if len(grid[0]) != source.get("cols") or any(
            not isinstance(row, list) or len(row) != source.get("cols")
            for row in grid
        ):
            raise ValueError("TABLE_SEGMENT_GRID_WIDTH_INVALID")
        raw_id = source.get("id")
        if raw_id is not None and (not isinstance(raw_id, str) or len(raw_id) > 75):
            raise ValueError("TABLE_SEGMENT_BLOCK_ID_INVALID")
        logical_key = raw_id or f"p426_table_{index + 1}"
        rows_per_chunk = max_rows_per_segment - 1
        content_rows = grid[1:]
        segments = [
            content_rows[i:i + rows_per_chunk]
            for i in range(0, len(content_rows), rows_per_chunk)
        ]
        if not segments:
            raise ValueError("TABLE_SEGMENT_NO_DATA")
        for part_index, part in enumerate(segments):
            if page_break_before_each:
                result.append({
                    "type": "page_break",
                    "_p426_table_break": logical_key,
                })
            item = deepcopy(source)
            item["cells"] = [deepcopy(grid[0])] + deepcopy(part)
            item["rows"] = len(item["cells"])
            item["first_row_header"] = True
            item["table_format"] = {
                **table_format, "page_break": "CELL",
                "repeat_header": True, "first_row_header": True,
            }
            item["_p426_logical_table"] = logical_key
            item["_p426_segment_index"] = part_index + 1
            item["_p426_segment_total"] = len(segments)
            if part_index > 0:
                if raw_id:
                    item["id"] = f"{raw_id}_segment_{part_index + 1}"
                item.pop("bookmark", None)
                if item.get("caption"):
                    item["caption"] += " (계속)"
            result.append(item)
        summaries.append({
            "logical_table": logical_key,
            "original_rows": len(grid),
            "data_rows": len(content_rows),
            "generated_segments": len(segments),
            "header_rows_repeated": len(segments) - 1,
            "max_rows_per_segment": max_rows_per_segment,
            "page_breaks_inserted": len(segments) if page_break_before_each else 0,
        })
    return {
        "blocks": result,
        "segment_summaries": summaries,
        "segmented_table_count": len(summaries),
        "authority": "EXPLICIT_NATIVE_TABLE_SEGMENTATION_NOT_RENDERER_VERIFIED",
    }
