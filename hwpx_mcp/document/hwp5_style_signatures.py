"""HWP5 and HWPX presentation-signature canonicalization.

Extracted from the P2 facade without changing its public tool registration.
Pure functions, no repository state, storage or MCP dependencies.
"""
from __future__ import annotations

import re
import unicodedata

def _canonical_font_face(value: object) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = " ".join(text.split()).strip()
    return text.casefold() or None


def _canonical_color(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text.startswith("#"):
        text = text[1:]
    if re.fullmatch(r"[0-9A-F]{6}", text):
        return f"#{text}"
    return text or None


def _hwp_colorref_to_hex(value: object) -> str:
    raw = int(value or 0)
    red = raw & 0xFF
    green = (raw >> 8) & 0xFF
    blue = (raw >> 16) & 0xFF
    return f"#{red:02X}{green:02X}{blue:02X}"


def _hwp_run_format_subset(run: dict) -> dict:
    shape = run.get("char_shape") or {}
    if not shape or shape.get("fidelity") != "semantic":
        return {}
    fmt = {
        "bold": bool(shape.get("bold")),
        "italic": bool(shape.get("italic")),
        "underline": int(shape.get("underline_type", 0) or 0) != 0,
        "strike": bool(shape.get("strikeout_color") is not None and (int(shape.get("attributes", 0)) >> 18) & 0b111),
    }
    height = int(shape.get("height", 0) or 0)
    if height > 0:
        fmt["size"] = height / 100.0
    if shape.get("text_color") is not None:
        fmt["color"] = _hwp_colorref_to_hex(shape.get("text_color"))
    primary_font = shape.get("primary_font_face")
    if primary_font:
        fmt["font"] = str(primary_font)
    if shape.get("superscript"):
        fmt["script"] = "sup"
    elif shape.get("subscript"):
        fmt["script"] = "sub"
    return fmt


def _hwp_paragraph_format_subset(paragraph: dict) -> dict:
    shape = (paragraph.get("paragraph_style") or {}).get("resolved_para_shape") or {}
    if shape.get("fidelity") != "semantic":
        return {}
    fmt: dict = {}
    alignment = str(shape.get("alignment") or "")
    if alignment in {"LEFT", "RIGHT", "CENTER", "JUSTIFY", "DISTRIBUTE"}:
        fmt["alignment"] = alignment
    def mm(value: object) -> float:
        return round(float(value or 0) * 25.4 / 7200.0, 4)
    def pt(value: object) -> float:
        return round(float(value or 0) / 100.0, 4)
    left = int(shape.get("left_margin_hwpunit", 0) or 0)
    right = int(shape.get("right_margin_hwpunit", 0) or 0)
    indent = int(shape.get("indent_hwpunit", 0) or 0)
    before = int(shape.get("spacing_before_hwpunit", 0) or 0)
    after = int(shape.get("spacing_after_hwpunit", 0) or 0)
    if left:
        fmt["indent_left_mm"] = mm(left)
    if right:
        fmt["indent_right_mm"] = mm(right)
    if indent:
        fmt["first_line_indent_mm"] = mm(indent)
    if before:
        fmt["spacing_before_pt"] = pt(before)
    if after:
        fmt["spacing_after_pt"] = pt(after)
    return fmt


def _hwp_style_signature(run: dict) -> dict:
    fmt = _hwp_run_format_subset(run)
    return {
        "text": str(run.get("text", "")),
        "bold": fmt.get("bold"),
        "italic": fmt.get("italic"),
        "underline": fmt.get("underline"),
        "strike": fmt.get("strike"),
        "size": fmt.get("size"),
        "color": _canonical_color(fmt.get("color")),
        "font": _canonical_font_face(fmt.get("font")),
        "script": fmt.get("script"),
    }


def _hwp_paragraph_style_signature(paragraph: dict) -> dict:
    fmt = _hwp_paragraph_format_subset(paragraph)
    def zero_default(name: str) -> float:
        value = fmt.get(name)
        return 0.0 if value is None else round(float(value), 4)
    return {
        "alignment": fmt.get("alignment"),
        "indent_left_mm": zero_default("indent_left_mm"),
        "indent_right_mm": zero_default("indent_right_mm"),
        "first_line_indent_mm": zero_default("first_line_indent_mm"),
        "spacing_before_pt": zero_default("spacing_before_pt"),
        "spacing_after_pt": zero_default("spacing_after_pt"),
    }


def _hwpx_paragraph_style_signature(paragraph: dict) -> dict:
    prop = paragraph.get("paragraph_property") or {}
    alignment = (prop.get("alignment") or {}).get("horizontal")
    margin_values = prop.get("margin_values") or {}

    def hwpunit_value(name: str) -> float | None:
        item = margin_values.get(name) or {}
        raw = item.get("value")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        unit = str(item.get("unit") or "HWPUNIT").upper()
        if unit != "HWPUNIT":
            return None
        return value

    left = hwpunit_value("left")
    right = hwpunit_value("right")
    intent = hwpunit_value("intent")
    prev = hwpunit_value("prev")
    next_value = hwpunit_value("next")

    def mm(value: float | None) -> float | None:
        return None if value is None else round(value * 25.4 / 7200.0, 4)

    def pt(value: float | None) -> float | None:
        return None if value is None else round(value / 100.0, 4)

    return {
        "alignment": alignment,
        "indent_left_mm": 0.0 if left is None else mm(left),
        "indent_right_mm": 0.0 if right is None else mm(right),
        "first_line_indent_mm": 0.0 if intent is None else mm(intent),
        "spacing_before_pt": 0.0 if prev is None else pt(prev),
        "spacing_after_pt": 0.0 if next_value is None else pt(next_value),
    }


def _hwp_rel_to_horizontal(value: object) -> str:
    return {0: "PAGE", 1: "PAGE", 2: "COLUMN", 3: "PARA"}.get(int(value or 0), "COLUMN")


def _hwp_rel_to_vertical(value: object) -> str:
    return {0: "PAPER", 1: "PAGE", 2: "PARA"}.get(int(value or 0), "PARA")


