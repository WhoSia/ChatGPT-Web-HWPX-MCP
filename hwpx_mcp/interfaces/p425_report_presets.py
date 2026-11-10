"""Practical P4.25 native HWPX report presets and one-call report authoring.

No separate renderer or table implementation. Produces the existing P3.38
rich-plan schema and delegates final composition to the registered tool.
"""
from __future__ import annotations

from copy import deepcopy

PRESETS = {
    "science-report": {
        "native_preset": "academic-report",
        "label": "과학 탐구·실험 보고서",
        "default_sections": ["연구 배경", "연구 방법", "결과", "논의", "결론"],
    },
    "school-report": {
        "native_preset": "school-report",
        "label": "학교 수행평가 보고서",
        "default_sections": ["탐구 동기", "이론적 배경", "탐구 과정", "결과 및 고찰"],
    },
    "institutional-report": {
        "native_preset": "institutional-report",
        "label": "공식 기관·행정 보고서",
        "default_sections": ["개요", "현황", "분석", "제언"],
    },
    "polished-report": {
        "native_preset": "polished-report",
        "label": "일반 전문 보고서",
        "default_sections": ["요약", "본문", "결론"],
    },
}


def build_report_plan(
    *, title: str,
    sections: list[dict],
    preset: str = "science-report",
    subtitle: str = "",
    author: str = "",
    page_numbers: bool = True,
) -> dict:
    if preset not in PRESETS:
        raise ValueError("UNKNOWN_REPORT_PRESET")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise ValueError("REPORT_TITLE_INVALID")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 32:
        raise ValueError("REPORT_SECTIONS_INVALID")
    if not isinstance(subtitle, str) or len(subtitle) > 500:
        raise ValueError("REPORT_SUBTITLE_INVALID")
    if not isinstance(author, str) or len(author) > 200:
        raise ValueError("REPORT_AUTHOR_INVALID")
    if type(page_numbers) is not bool:
        raise ValueError("REPORT_PAGE_NUMBER_SETTING_INVALID")

    blocks = [{"type": "title", "text": title.strip()}]
    if subtitle.strip():
        blocks.append({"type": "paragraph", "text": subtitle.strip()})
    if author.strip():
        blocks.append({"type": "paragraph", "text": author.strip()})

    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("REPORT_SECTION_INVALID")
        heading = section.get("heading")
        if not isinstance(heading, str) or not heading.strip() or len(heading) > 200:
            raise ValueError("REPORT_HEADING_INVALID")
        blocks.append({"type": "heading", "level": 1, "text": heading.strip()})
        paragraphs = section.get("paragraphs", [])
        if not isinstance(paragraphs, list) or len(paragraphs) > 100:
            raise ValueError("REPORT_PARAGRAPHS_INVALID")
        for paragraph in paragraphs:
            if not isinstance(paragraph, str) or len(paragraph) > 10000:
                raise ValueError("REPORT_PARAGRAPH_INVALID")
            if paragraph.strip():
                blocks.append({"type": "paragraph", "text": paragraph})
        tables = section.get("tables", [])
        if not isinstance(tables, list) or len(tables) > 20:
            raise ValueError("REPORT_TABLES_INVALID")
        for table in tables:
            if not isinstance(table, dict):
                raise ValueError("REPORT_TABLE_INVALID")
            grid = table.get("cells")
            if not isinstance(grid, list) or not grid or len(grid) > 200:
                raise ValueError("REPORT_TABLE_CELLS_INVALID")
            if not all(isinstance(row, list) for row in grid):
                raise ValueError("REPORT_TABLE_ROW_INVALID")
            width = len(grid[0])
            if not 1 <= width <= 100 or any(len(row) != width for row in grid):
                raise ValueError("REPORT_TABLE_WIDTH_INVALID")
            if any(not isinstance(value, (str, int, float)) or isinstance(value, bool)
                   for row in grid for value in row):
                raise ValueError("REPORT_TABLE_VALUE_INVALID")
            block = {
                "type": "table", "rows": len(grid), "cols": width,
                "cells": [[str(value) for value in row] for row in grid],
            }
            caption = table.get("caption")
            if caption is not None:
                if not isinstance(caption, str) or len(caption) > 500:
                    raise ValueError("REPORT_CAPTION_INVALID")
                block["caption"] = caption
            blocks.append(block)

    # Existing P3.21 composer has a 240-block limit. Validate here too,
    # before invoking native authoring or producing any bytes.
    if len(blocks) > 240:
        raise ValueError("REPORT_TOO_MANY_BLOCKS")
    return {
        "preset": PRESETS[preset]["native_preset"],
        "document": {"title": title.strip()},
        "sections": [{"blocks": blocks, "page_numbers": page_numbers}],
    }


def register_report_preset_tools(core):
    @core.mcp.tool()
    def list_report_presets() -> dict:
        """Discover ready-to-use native HWPX report styles and section examples."""
        core._caller_subject()
        return {
            "ok": True,
            "presets": [
                {"id": name, **deepcopy(details)}
                for name, details in PRESETS.items()
            ],
            "next_tool": "create_report_from_sections_and_deliver",
        }

    @core.mcp.tool()
    def create_report_from_sections_and_deliver(
        title: str, sections: list[dict],
        preset: str = "science-report",
        subtitle: str = "", author: str = "",
        filename: str = "report.hwpx",
        page_numbers: bool = True,
    ):
        """One-call report authoring with native headings, tables and styles."""
        core._caller_subject()
        plan = build_report_plan(
            title=title, sections=sections, preset=preset,
            subtitle=subtitle, author=author, page_numbers=page_numbers,
        )
        # Delegate to the registered P4.25 rich native authoring tool.
        # This callback is defined on the same MCP core by the previous
        # registration module. No new XML serializer is introduced.
        return core.create_rich_document_and_deliver(plan, filename)
