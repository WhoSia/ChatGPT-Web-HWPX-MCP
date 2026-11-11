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
    if "width" in table:
        native_width = table["width"]
        if type(native_width) is not int or not 100 <= native_width <= 200000:
            raise ValueError("REPORT_TABLE_NATIVE_WIDTH_INVALID")
        block["width"] = native_width
    if "table_format" in table:
        requested = table["table_format"]
        if not isinstance(requested, dict) or set(requested) - {
            "page_break", "repeat_header", "first_row_header", "border_color"
        }:
            raise ValueError("REPORT_TABLE_FORMAT_INVALID")
        normalized = {}
        if "page_break" in requested:
            mode = requested["page_break"]
            if not isinstance(mode, str) or mode.upper() not in {"CELL", "TABLE", "NONE"}:
                raise ValueError("REPORT_TABLE_PAGE_BREAK_INVALID")
            normalized["page_break"] = mode.upper()
        for key in ("repeat_header", "first_row_header"):
            if key in requested:
                if type(requested[key]) is not bool:
                    raise ValueError("REPORT_TABLE_HEADER_POLICY_INVALID")
                normalized[key] = requested[key]
        if "border_color" in requested:
            color = requested["border_color"]
            if not isinstance(color, str) or not re.fullmatch(r"#?[A-Fa-f0-9]{6}", color):
                raise ValueError("REPORT_TABLE_BORDER_COLOR_INVALID")
            normalized["border_color"] = "#" + color.lstrip("#").upper()
        block["table_format"] = normalized
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
    from hwpx_mcp.equations.p426_latex_compatibility import normalize_equation_latex
    policy = equation.get("policy", "strict") if isinstance(equation, dict) else "strict"
    compatibility = normalize_equation_latex(latex, policy)
    block = {"type": "equation", "latex": compatibility["normalized_latex"]}
    if compatibility["spacing_adjusted"]:
        block["source_latex_sha256"] = compatibility["original_sha256"]
        block["spacing_normalization"] = compatibility["removed_spacing_commands"]
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
        block = {"type": "paragraph", "text": text}
        if "paragraph_format" in item:
            requested = item["paragraph_format"]
            if (not isinstance(requested, dict) or
                    set(requested) - {"spacing_before_pt", "spacing_after_pt",
                                      "keep_with_next", "keep_lines"}):
                raise ValueError("REPORT_PARAGRAPH_FORMAT_INVALID")
            for key in ("spacing_before_pt", "spacing_after_pt"):
                if key in requested and (
                    type(requested[key]) not in (int, float)
                    or not 0 <= requested[key] <= 72
                ):
                    raise ValueError("REPORT_PARAGRAPH_SPACING_INVALID")
            for key in ("keep_with_next", "keep_lines"):
                if key in requested and type(requested[key]) is not bool:
                    raise ValueError("REPORT_PARAGRAPH_KEEP_INVALID")
            block["paragraph_format"] = dict(requested)
        return block
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
    layout: dict | str | None = None,
    fit_figures_to_page: bool = False,
    segment_long_tables: bool = False,
    table_segment_rows: int = 20,
    caption_clearance_pt: float = 0.0,
    equation_caption_mode: str = "native",
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
    if type(fit_figures_to_page) is not bool:
        raise ValueError("REPORT_FIGURE_FIT_INVALID")
    if type(segment_long_tables) is not bool:
        raise ValueError("REPORT_TABLE_SEGMENT_SETTING_INVALID")
    if type(table_segment_rows) is not int or not 5 <= table_segment_rows <= 60:
        raise ValueError("REPORT_TABLE_SEGMENT_ROWS_INVALID")
    if type(caption_clearance_pt) not in (int, float) or not 0 <= caption_clearance_pt <= 36:
        raise ValueError("REPORT_CAPTION_CLEARANCE_INVALID")
    if equation_caption_mode not in ("native", "visible-paragraph"):
        raise ValueError("REPORT_EQUATION_CAPTION_MODE_INVALID")

    notes: list[dict] = []
    crossrefs: list[dict] = []
    explicit_ids: set[str] = set()
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
                # Stable native paragraph identity is used by bookmarks,
                # footnotes and page crossrefs in the P3.19/P3.20 engines.
                requested_id = item.get("id")
                if requested_id is not None:
                    if (not isinstance(requested_id, str) or
                            re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", requested_id) is None):
                        raise ValueError("REPORT_BLOCK_ID_INVALID")
                    if requested_id in explicit_ids:
                        raise ValueError("REPORT_BLOCK_ID_DUPLICATE")
                    explicit_ids.add(requested_id)
                    block["id"] = requested_id
                if "bookmark" in item:
                    bookmark = item["bookmark"]
                    if (not isinstance(bookmark, str) or
                            not 1 <= len(bookmark.strip()) <= 80):
                        raise ValueError("REPORT_BOOKMARK_INVALID")
                    block["bookmark"] = bookmark.strip()
                if "page_ref_target" in item:
                    if block["type"] != "paragraph":
                        raise ValueError("REPORT_PAGE_REFERENCE_REQUIRES_PARAGRAPH")
                    target = item["page_ref_target"]
                    if not isinstance(target, str) or not target:
                        raise ValueError("REPORT_PAGE_REFERENCE_TARGET_INVALID")
                    if "id" not in block:
                        ref_id = f"p426_ref_{len(crossrefs) + 1}"
                        if ref_id in explicit_ids:
                            raise ValueError("REPORT_BLOCK_ID_DUPLICATE")
                        block["id"] = ref_id
                        explicit_ids.add(ref_id)
                    crossrefs.append({"paragraph": block["id"], "target": target})
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
                    block_id = block.get("id") or f"p425_note_{len(notes) + 1}"
                    if block_id in explicit_ids and "id" not in block:
                        raise ValueError("REPORT_BLOCK_ID_DUPLICATE")
                    block["id"] = block_id
                    explicit_ids.add(block_id)
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

    if segment_long_tables:
        from hwpx_mcp.orchestration.p426_table_pagination import segment_native_long_tables
        segmented = segment_native_long_tables(
            blocks, max_rows_per_segment=table_segment_rows,
            page_break_before_each=True,
        )
        blocks = segmented["blocks"]
        # Generated continuation IDs and explicit author IDs must never
        # collide in the downstream native composer.
        block_ids = [b["id"] for b in blocks if "id" in b]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("REPORT_BLOCK_ID_DUPLICATE")

    # P3.19 resolves $block: identities after paragraph materialization,
    # and inserts actual native page-reference fields before TOC generation.
    if crossrefs:
        available = {b.get("id") for b in blocks if b.get("id")}
        for ref in crossrefs:
            if ref["target"] not in available:
                raise ValueError("REPORT_PAGE_REFERENCE_TARGET_MISSING")
    post_operations = [
        {"op": "add_page_crossref",
         "paragraph": "$block:" + ref["paragraph"],
         "target_paragraph": "$block:" + ref["target"],
         "cached_page": 1}
        for ref in crossrefs
    ]

    # P4.26 actual SVG showed that a picture caption can be rendered
    # dangerously close to the following body paragraph. The opt-in
    # clearance applies to the next paragraph, never to the image binary.
    if caption_clearance_pt:
        for i in range(1, len(blocks)):
            previous, current = blocks[i - 1], blocks[i]
            if (previous.get("type") == "picture"
                    and previous.get("caption")
                    and current.get("type") == "paragraph"):
                fmt = dict(current.get("paragraph_format") or {})
                fmt["spacing_before_pt"] = max(
                    float(fmt.get("spacing_before_pt", 0)),
                    float(caption_clearance_pt),
                )
                current["paragraph_format"] = fmt

    if number_captions:
        counters = {"picture": 0, "table": 0, "equation": 0}
        names = {"picture": "그림", "table": "표", "equation": "식"}
        seen_logical_tables: set[str] = set()
        for block in blocks:
            kind = block["type"]
            if kind not in counters:
                continue
            logical = block.get("_p426_logical_table") if kind == "table" else None
            if logical is None or logical not in seen_logical_tables:
                counters[kind] += 1
            if logical is not None:
                seen_logical_tables.add(logical)
            caption = block.get("caption")
            if not caption:
                continue
            label = names[kind]
            if not re.match(r"^(?:그림|표|식)\s*\d+[.．:\s]", caption):
                block["caption"] = f"{label} {counters[kind]}. {caption}"

    if equation_caption_mode == "visible-paragraph":
        visible_blocks = []
        for block in blocks:
            if block.get("type") != "equation" or not block.get("caption"):
                visible_blocks.append(block)
                continue
            equation = dict(block)
            rendered_caption = str(equation.pop("caption"))
            # Keeping native+printed captions simultaneously can create
            # duplicates in Hancom, so only one representation is chosen.
            # The native HWPX equation anchor has no text run; P2.3
            # paragraph formatting currently requires a text run.
            # Keep the equation untouched and format the visible caption only.
            visible_blocks.append(equation)
            visible_blocks.append({
                "type": "paragraph",
                "text": rendered_caption,
                "paragraph_format": {
                    "spacing_before_pt": 4,
                    "spacing_after_pt": 8,
                    "keep_lines": True,
                },
                "_p426_visible_math_caption": True,
            })
        blocks = visible_blocks

    # Existing P3.21 composer has a 240-block limit. Validate here too,
    # before invoking native authoring or producing any bytes.
    if len(blocks) > 240:
        raise ValueError("REPORT_TOO_MANY_BLOCKS")
    if fit_figures_to_page:
        from hwpx_mcp.orchestration.p426_layout_preflight import fit_native_pictures_to_body
        fitted = fit_native_pictures_to_body(blocks, layout or "science-lab")
        blocks = fitted["blocks"]
    result = {
        "preset": PRESETS[preset]["native_preset"],
        "document": {"title": title.strip()},
        "sections": [{"blocks": blocks, "page_numbers": page_numbers}],
        **({"publishing": {"toc": {"at_index": 1, "title": "목차", "level": 3}}}
           if table_of_contents else {}),
        **({"annotations": notes} if notes else {}),
        **({"post_operations": post_operations} if post_operations else {}),
    }
    if layout is not None:
        from hwpx_mcp.orchestration.p426_layout_tokens import compile_layout_tokens
        design = compile_layout_tokens(layout)
        result["style_profile"] = design["style_profile"]
    return result


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
        layout: dict | str | None = None,
        fit_figures_to_page: bool = False,
        segment_long_tables: bool = False,
        table_segment_rows: int = 20,
        caption_clearance_pt: float = 0.0,
        equation_caption_mode: str = "native",
    ) -> dict:
        """Preview the exact native report composition plan without writing a file."""
        core._caller_subject()
        from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
        requested = build_report_plan(
            title=title, sections=sections, preset=preset,
            subtitle=subtitle, author=author, page_numbers=page_numbers,
            table_of_contents=table_of_contents,
            number_captions=number_captions,
            layout=layout,
            fit_figures_to_page=fit_figures_to_page,
            segment_long_tables=segment_long_tables,
            table_segment_rows=table_segment_rows,
            caption_clearance_pt=caption_clearance_pt,
            equation_caption_mode=equation_caption_mode,
        )
        compiled = compile_rich_document_plan(requested)
        from hwpx_mcp.orchestration.p426_layout_preflight import assess_native_layout
        fit = assess_native_layout(compiled["plan"], layout or "science-lab")
        return {
            "ok": True, "committed": False, "native_pdf_created": False,
            "layout_preflight": fit,
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
        filename: str = "",
        page_numbers: bool = True,
        table_of_contents: bool = False,
        number_captions: bool = False,
        layout: dict | str | None = None,
        fit_figures_to_page: bool = False,
        segment_long_tables: bool = False,
        table_segment_rows: int = 20,
        caption_clearance_pt: float = 0.0,
        equation_caption_mode: str = "native",
    ):
        """One-call native report with headings, tables, equations and styles."""
        core._caller_subject()
        plan = build_report_plan(
            title=title, sections=sections, preset=preset,
            subtitle=subtitle, author=author, page_numbers=page_numbers,
            table_of_contents=table_of_contents,
            number_captions=number_captions,
            layout=layout,
            fit_figures_to_page=fit_figures_to_page,
            segment_long_tables=segment_long_tables,
            table_segment_rows=table_segment_rows,
            caption_clearance_pt=caption_clearance_pt,
            equation_caption_mode=equation_caption_mode,
        )
        if not filename:
            # Human-readable default without requiring a document ID.
            # The shared file-delivery layer performs final filename
            # sanitization and owns download/attachment semantics.
            filename = title.strip()[:80] + ".hwpx"
        # Delegate to the registered P4.25 rich native authoring tool.
        # This callback is defined on the same MCP core by the previous
        # registration module. No new XML serializer is introduced.
        return core._p425_create_rich_document_and_deliver(plan, filename)
