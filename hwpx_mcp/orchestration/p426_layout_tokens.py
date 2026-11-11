"""P4.26 design token compiler to native P4.23 style profiles and P3.18 setup.

Tokens use display-friendly units (pt and mm) but compile only to fields
actually supported by P3.21. The document is still rendered by its native
HWPX composer; these are not simulated HTML/CSS styles.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from hwpx_mcp.document.p423_style_profile import normalize_style_profile

SCHEMA = "chatgpt-web-hwpx-mcp/p426/layout-tokens/v1"

PROFILES = {
    "academic-journal": {
        "page": {"paper": "A4", "margins_mm": [25, 22, 23, 22]},
        "typography": {
            "korean_font": "함초롬바탕", "latin_font": "Times New Roman",
            "body_pt": 10.5, "body_line_percent": 155, "title_pt": 19,
            "heading_1_pt": 14, "heading_2_pt": 12, "heading_3_pt": 11,
        },
        "table": {"repeat_header": True, "page_break": "CELL", "border_color": "#555555"},
        "equations": {"base_unit": 1100},
    },
    "science-lab": {
        "page": {"paper": "A4", "margins_mm": [20, 20, 20, 20]},
        "typography": {
            "korean_font": "함초롬바탕", "latin_font": "Cambria",
            "body_pt": 10.5, "body_line_percent": 150, "title_pt": 18,
            "heading_1_pt": 14, "heading_2_pt": 12, "heading_3_pt": 11,
        },
        "table": {"repeat_header": True, "page_break": "CELL", "border_color": "#345C79"},
        "equations": {"base_unit": 1100},
    },
    "institutional-clean": {
        "page": {"paper": "A4", "margins_mm": [22, 22, 18, 18]},
        "typography": {
            "korean_font": "맑은 고딕", "latin_font": "Arial",
            "body_pt": 10, "body_line_percent": 145, "title_pt": 18,
            "heading_1_pt": 13, "heading_2_pt": 11.5, "heading_3_pt": 10.5,
        },
        "table": {"repeat_header": True, "page_break": "CELL", "border_color": "#666666"},
        "equations": {"base_unit": 1100},
    },
}

def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def normalize_layout_tokens(value: dict | str) -> dict:
    """Validate a named design system or user override before native setup."""
    if isinstance(value, str):
        if value not in PROFILES:
            raise ValueError("LAYOUT_PROFILE_UNKNOWN")
        tokens = deepcopy(PROFILES[value])
        name = value
    elif isinstance(value, dict):
        if set(value) - {"base", "page", "typography", "table", "equations"}:
            raise ValueError("LAYOUT_TOKENS_UNKNOWN_KEYS")
        name = value.get("base", "science-lab")
        if name not in PROFILES:
            raise ValueError("LAYOUT_PROFILE_UNKNOWN")
        tokens = deepcopy(PROFILES[name])
        for area, overrides in value.items():
            if area == "base":
                continue
            if not isinstance(overrides, dict) or set(overrides) - set(tokens[area]):
                raise ValueError("LAYOUT_TOKENS_INVALID_OVERRIDES")
            tokens[area].update(overrides)
    else:
        raise ValueError("LAYOUT_TOKENS_INVALID")

    page, typography, table, equations = (
        tokens["page"], tokens["typography"], tokens["table"], tokens["equations"]
    )
    if page["paper"] != "A4":
        raise ValueError("LAYOUT_PAPER_NOT_SUPPORTED")
    margins = page["margins_mm"]
    if not isinstance(margins, list) or len(margins) != 4 or any(
        type(x) not in (int, float) or not 5 <= x <= 60 for x in margins
    ):
        raise ValueError("LAYOUT_MARGINS_INVALID")
    if margins[0] + margins[1] >= 180 or margins[2] + margins[3] >= 257:
        raise ValueError("LAYOUT_BODY_GEOMETRY_INVALID")
    for field in ("korean_font", "latin_font"):
        font = typography[field]
        if not isinstance(font, str) or not 1 <= len(font.strip()) <= 80:
            raise ValueError("LAYOUT_FONT_INVALID")
    for key in ("body_pt", "title_pt", "heading_1_pt", "heading_2_pt", "heading_3_pt"):
        size = typography[key]
        if type(size) not in (int, float) or not 6 <= size <= 40:
            raise ValueError("LAYOUT_FONT_SIZE_INVALID")
    if type(typography["body_line_percent"]) is not int or not 90 <= typography["body_line_percent"] <= 250:
        raise ValueError("LAYOUT_LINE_SPACING_INVALID")
    if type(table["repeat_header"]) is not bool or table["page_break"] not in ("CELL", "TABLE", "NONE"):
        raise ValueError("LAYOUT_TABLE_POLICY_INVALID")
    if type(equations["base_unit"]) is not int or not 500 <= equations["base_unit"] <= 2400:
        raise ValueError("LAYOUT_EQUATION_BASE_UNIT_INVALID")
    return {"schema": SCHEMA, "name": name, **tokens}


def compile_layout_tokens(value: dict | str) -> dict:
    tokens = normalize_layout_tokens(value)
    page = tokens["page"]
    ty = tokens["typography"]
    table = tokens["table"]
    fonts = {"hangul": ty["korean_font"], "latin": ty["latin_font"]}
    style_profile = normalize_style_profile({
        "name": tokens["name"],
        "roles": {
            "body": {"run": {"size": ty["body_pt"], "font_by_script": fonts},
                     "paragraph": {"line_spacing_percent": ty["body_line_percent"]}},
            "title": {"run": {"size": ty["title_pt"], "bold": True, "font_by_script": fonts},
                      "paragraph": {"alignment": "CENTER", "keep_with_next": True,
                                    "spacing_after_pt": 12}},
            "heading_1": {"run": {"size": ty["heading_1_pt"], "bold": True, "font_by_script": fonts},
                          "paragraph": {"spacing_before_pt": 12, "spacing_after_pt": 6, "keep_with_next": True}},
            "heading_2": {"run": {"size": ty["heading_2_pt"], "bold": True, "font_by_script": fonts},
                          "paragraph": {"spacing_before_pt": 9, "spacing_after_pt": 4, "keep_with_next": True}},
            "heading_3": {"run": {"size": ty["heading_3_pt"], "bold": True, "font_by_script": fonts},
                          "paragraph": {"spacing_before_pt": 7, "spacing_after_pt": 3, "keep_with_next": True}},
        },
        "page": {
            "margin_left_mm": page["margins_mm"][0],
            "margin_right_mm": page["margins_mm"][1],
            "margin_top_mm": page["margins_mm"][2],
            "margin_bottom_mm": page["margins_mm"][3],
        },
        "table": table,
        "equation_base_unit": tokens["equations"]["base_unit"],
    })
    geometry = {
        "paper_width_mm": 210, "paper_height_mm": 297,
        "content_width_mm": 210 - page["margins_mm"][0] - page["margins_mm"][1],
        "content_height_mm": 297 - page["margins_mm"][2] - page["margins_mm"][3],
    }
    return {"tokens": tokens, "tokens_sha256": _sha(tokens),
            "style_profile": style_profile, "geometry": geometry}
