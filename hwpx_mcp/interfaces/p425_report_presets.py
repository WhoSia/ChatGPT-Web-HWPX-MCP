"""Practical P4.25 native HWPX report presets and one-call report authoring.

No separate renderer or table implementation. Produces the existing P3.38
rich-plan schema and delegates final composition to the registered tool.
"""
from __future__ import annotations

import base64
import binascii
import re
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


def _as_native_table(table: dict) -> dict:
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
    if "first_row_header" in table:
        if type(table["first_row_header"]) is not bool:
            raise ValueError("REPORT_TABLE_HEADER_INVALID")
        block["first_row_header"] = table["first_row_header"]
    return block


def _as_native_equation(equation: str | dict) -> dict:
    if isinstance(equation, str):
        latex, caption = equation, None
    elif isinstance(equation, dict):
        latex, caption = equation.get("latex"), equation.get("caption")
    else:
        raise ValueError("REPORT_EQUATION_INVALID")
    if not isinstance(latex, str) or not latex.strip() or len(latex) > 4000:
        raise ValueError("REPORT_EQUATION_LATEX_INVALID")
    block = {"type": "equation", "latex": latex.strip()}
    if caption is not None:
        if not isinstance(caption, str) or len(caption) > 500:
            raise ValueError("REPORT_EQUATION_CAPTION_INVALID")
        block["caption"] = caption
    return block


def _as_native_figure(figure: dict) -> dict:
    """Validate an in-memory PNG/JPEG and reuse the P3.21 native picture object."""
    if not isinstance(figure, dict):
        raise ValueError("REPORT_FIGURE_INVALID")
    fmt = figure.get("image_format", "png")
    if not isinstance(fmt, str) or fmt.lower() not in ("png", "jpg", "jpeg"):
        raise ValueError("REPORT_FIGURE_FORMAT_INVALID")
    encoded = figure.get("content_base64")
    if not isinstance(encoded, str) or not encoded or len(encoded) > 12_000_000:
        raise ValueError("REPORT_FIGURE_PAYLOAD_INVALID")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("REPORT_FIGURE_BASE64_INVALID") from error
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError("REPORT_FIGURE_BYTES_INVALID")
    is_png = raw.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = raw.startswith(b"\xff\xd8\xff")
    if not (is_png if fmt.lower() == "png" else is_jpeg):
        raise ValueError("REPORT_FIGURE_SIGNATURE_MISMATCH")
    width, height = figure.get("width", 10000), figure.get("height", 8000)
    if (type(width) is not int or type(height) is not int
            or not 100 <= width <= 100000 or not 100 <= height <= 100000):
        raise ValueError("REPORT_FIGURE_SIZE_INVALID")
    caption = figure.get("caption")
    if caption is not None and (not isinstance(caption, str) or len(caption) > 500):
        raise ValueError("REPORT_FIGURE_CAPTION_INVALID")
    inline = figure.get("inline", True)
    if type(inline) is not bool:
        raise ValueError("REPORT_FIGURE_INLINE_INVALID")
    return {
        "type": "picture", "content_base64": encoded,
        "image_format": fmt.lower(), "width": width, "height": height,
        "inline": inline, **({"caption": caption} if caption else {}),
    }


def _as_ordered_block(item: dict) -> dict:
    """Transform a small semantic report DSL into existing native block types."""
    if not isinstance(item, dict):
        raise ValueError("REPORT_CONTENT_BLOCK_INVALID")
    kind = item.get("type")
    if kind == "paragraph":
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError("REPORT_PARAGRAPH_INVALID")
        return {"type": "paragraph", "text": text}
    if kind == "heading":
        text, level = item.get("text"), item.get("level", 2)
        if not isinstance(text, str) or not text.strip() or len(text) > 200:
            raise ValueError("REPORT_HEADING_INVALID")
        if type(level) is not int or not 1 <= level <= 6:
            raise ValueError("REPORT_HEADING_LEVEL_INVALID")
        return {"type": "heading", "level": level, "text": text.strip()}
    if kind == "list_item":
        text, level, style = item.get("text"), item.get("level", 1), item.get("kind", "bullet")
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError("REPORT_LIST_TEXT_INVALID")
        if type(level) is not int or not 1 <= level <= 3 or style not in ("bullet", "number"):
            raise ValueError("REPORT_LIST_FORMAT_INVALID")
        return {"type": "list_item", "text": text, "level": level, "kind": style}
    if kind == "equation":
        return _as_native_equation(item)
    if kind == "table":
        return _as_native_table(item)
    if kind in ("figure", "picture", "image"):
        return _as_native_figure(item)
    if kind == "page_break":
        return {"type": "page_break"}
    raise ValueError("REPORT_CONTENT_TYPE_UNSUPPORTED")


def build_report_plan(
    *, title: str,
    sections: list[dict],
    preset: str = "science-report",
    subtitle: str = "",
    author: str = "",
    page_numbers: bool = True,
    table_of_contents: bool = False,
    number_captions: bool = False,
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
    if type(table_of_contents) is not bool:
        raise ValueError("REPORT_TOC_SETTING_INVALID")
    if type(number_captions) is not bool:
        raise ValueError("REPORT_CAPTION_NUMBERING_INVALID")

    notes: list[dict] = []
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
        if "content" in section:
            if any(field in section for field in ("paragraphs", "equations", "tables", "figures")):
                raise ValueError("REPORT_ORDERED_CONTENT_CONFLICT")
            content = section["content"]
            if not isinstance(content, list) or len(content) > 240:
                raise ValueError("REPORT_CONTENT_INVALID")
            for item in content:
                block = _as_ordered_block(item)
                # Keep the note attached to the native paragraph identity,
                # not a printed superscript that loses HWPX semantics.
                if isinstance(item, dict) and "footnote" in item:
                    if block["type"] != "paragraph":
                        raise ValueError("REPORT_FOOTNOTE_REQUIRES_PARAGRAPH")
                    footnote = item["footnote"]
                    if (not isinstance(footnote, str) or not footnote.strip()
                            or len(footnote) > 4000):
                        raise ValueError("REPORT_FOOTNOTE_TEXT_INVALID")
                    if len(notes) >= 100:
                        raise ValueError("REPORT_FOOTNOTE_LIMIT_EXCEEDED")
                    block_id = f"p425_note_{len(notes) + 1}"
                    block["id"] = block_id
                    notes.append({
                        "op": "add_footnote",
                        "paragraph": "$block:" + block_id,
                        "text": footnote.strip(),
                    })
                blocks.append(block)
            continue
        paragraphs = section.get("paragraphs", [])
        if not isinstance(paragraphs, list) or len(paragraphs) > 100:
            raise ValueError("REPORT_PARAGRAPHS_INVALID")
        for paragraph in paragraphs:
            if not isinstance(paragraph, str) or len(paragraph) > 10000:
                raise ValueError("REPORT_PARAGRAPH_INVALID")
            if paragraph.strip():
                blocks.append({"type": "paragraph", "text": paragraph})
        equations = section.get("equations", [])
        if not isinstance(equations, list) or len(equations) > 40:
            raise ValueError("REPORT_EQUATIONS_INVALID")
        blocks.extend(_as_native_equation(value) for value in equations)
        tables = section.get("tables", [])
        if not isinstance(tables, list) or len(tables) > 20:
            raise ValueError("REPORT_TABLES_INVALID")
        blocks.extend(_as_native_table(value) for value in tables)
        figures = section.get("figures", [])
        if not isinstance(figures, list) or len(figures) > 20:
            raise ValueError("REPORT_FIGURES_INVALID")
        blocks.extend(_as_native_figure(value) for value in figures)

    if number_captions:
        counters = {"picture": 0, "table": 0, "equation": 0}
        names = {"picture": "그림", "table": "표", "equation": "식"}
        for block in blocks:
            kind = block["type"]
            if kind not in counters:
                continue
            counters[kind] += 1
            caption = block.get("caption")
            if not caption:
                continue
            label = names[kind]
            if not re.match(r"^(?:그림|표|식)\s*\d+[.．:\s]", caption):
                block["caption"] = f"{label} {counters[kind]}. {caption}"

    # Existing P3.21 composer has a 240-block limit. Validate here too,
    # before invoking native authoring or producing any bytes.
    if len(blocks) > 240:
        raise ValueError("REPORT_TOO_MANY_BLOCKS")
    return {
        "preset": PRESETS[preset]["native_preset"],
        "document": {"title": title.strip()},
        "sections": [{"blocks": blocks, "page_numbers": page_numbers}],
        **({"publishing": {"toc": {"at_index": 1, "title": "목차", "level": 3}}}
           if table_of_contents else {}),
        **({"annotations": notes} if notes else {}),
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
    def preview_report_plan(
        title: str, sections: list[dict],
        preset: str = "science-report",
        subtitle: str = "", author: str = "",
        page_numbers: bool = True,
        table_of_contents: bool = False,
        number_captions: bool = False,
    ) -> dict:
        """Preview the exact native report composition plan without writing a file."""
        core._caller_subject()
        from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
        requested = build_report_plan(
            title=title, sections=sections, preset=preset,
            subtitle=subtitle, author=author, page_numbers=page_numbers,
            table_of_contents=table_of_contents,
            number_captions=number_captions,
        )
        compiled = compile_rich_document_plan(requested)
        return {
            "ok": True, "committed": False, "native_pdf_created": False,
            "preset": requested["preset"],
            "block_count": compiled["block_count"],
            "block_counts": compiled["block_counts"],
            "section_count": compiled["section_count"],
            "setup_operation_count": compiled["setup_operation_count"],
            "plan_sha256": compiled["plan_sha256"],
            "table_of_contents_requested": table_of_contents,
            "page_numbers_requested": page_numbers,
            "number_captions_requested": number_captions,
            "next_tool": "create_report_from_sections_and_deliver",
        }

    @core.mcp.tool()
    def create_report_from_sections_and_deliver(
        title: str, sections: list[dict],
        preset: str = "science-report",
        subtitle: str = "", author: str = "",
        filename: str = "report.hwpx",
        page_numbers: bool = True,
        table_of_contents: bool = False,
        number_captions: bool = False,
    ):
        """One-call native report with headings, tables, equations and styles."""
        core._caller_subject()
        plan = build_report_plan(
            title=title, sections=sections, preset=preset,
            subtitle=subtitle, author=author, page_numbers=page_numbers,
            table_of_contents=table_of_contents,
            number_captions=number_captions,
        )
        # Delegate to the registered P4.25 rich native authoring tool.
        # This callback is defined on the same MCP core by the previous
        # registration module. No new XML serializer is introduced.
        return core._p425_create_rich_document_and_deliver(plan, filename)
