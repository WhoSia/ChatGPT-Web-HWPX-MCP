"""P4.23 explicit, reusable *per-plan* user style profiles.

This is a portable declarative profile, not a server-stored personal memory.
A caller must opt in by supplying it. Precedence:
built-in preset < style_profile < per-block explicit overrides.
Unsupported keys fail closed to prevent a saved profile becoming an arbitrary
edit-program or a silent formatting downgrade.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

PROFILE_SCHEMA = "chatgpt-web-hwpx-mcp/p423/document-style-profile/v1"
MAX_PROFILE_BYTES = 8192
RUN_KEYS = frozenset({"bold", "italic", "size", "letter_spacing", "font_by_script"})
PARA_KEYS = frozenset({"alignment", "line_spacing_percent", "spacing_before_pt", "spacing_after_pt", "keep_with_next"})
PAGE_KEYS = frozenset({
    "margin_left_mm", "margin_right_mm", "margin_top_mm", "margin_bottom_mm"
})
ROLE_KEYS = frozenset({"title", "body", "heading_1", "heading_2", "heading_3"})
TABLE_KEYS = frozenset({"page_break", "border_color", "repeat_header", "first_row_header"})


def _format_profile_field(value: object, *, category: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(category + " must be an object")
    allowed = RUN_KEYS if category == "run" else PARA_KEYS
    if set(value) - allowed:
        raise ValueError(category + " contains unknown style keys")
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"bold", "italic", "keep_with_next"}:
            if type(item) is not bool:
                raise ValueError(key + " must be boolean")
        elif key == "font_by_script":
            if not isinstance(item, dict) or not item or set(item) - {"hangul", "latin", "hanja", "japanese", "other"}:
                raise ValueError("font_by_script must contain allowed script names")
            if any(not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 for name in item.values()):
                raise ValueError("font names must contain 1..80 characters")
            item = dict(item)
        elif key == "alignment":
            if item not in ("LEFT", "CENTER", "RIGHT", "JUSTIFY"):
                raise ValueError("alignment must be LEFT, CENTER, RIGHT, or JUSTIFY")
        elif key == "size":
            if type(item) not in (int, float) or not 4 <= item <= 72:
                raise ValueError("font size must be between 4 and 72 pt")
        elif key == "line_spacing_percent":
            if type(item) is not int or not 80 <= item <= 300:
                raise ValueError("line spacing must be between 80 and 300 percent")
        elif key == "letter_spacing":
            if type(item) is not int or not -15 <= item <= 15:
                raise ValueError("letter spacing must be between -15 and 15")
        else:
            if type(item) not in (int, float) or not 0 <= item <= 72:
                raise ValueError(key + " must be between 0 and 72 pt")
        clean[key] = item
    return clean


def normalize_style_profile(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("style_profile must be an object")
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("style_profile must be JSON-compatible") from exc
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("style_profile exceeds 8192 bytes")
    if set(value) - {"schema", "name", "roles", "page", "table", "equation_base_unit"}:
        raise ValueError("style_profile contains unknown fields")
    if value.get("schema", PROFILE_SCHEMA) != PROFILE_SCHEMA:
        raise ValueError("unsupported style_profile schema")
    name = value.get("name", "")
    if not isinstance(name, str) or len(name) > 80:
        raise ValueError("profile name must be at most 80 characters")
    roles = value.get("roles", {})
    if not isinstance(roles, dict) or set(roles) - ROLE_KEYS:
        raise ValueError("style_profile.roles contains unsupported roles")
    clean_roles = {}
    for role, style in roles.items():
        if not isinstance(style, dict) or set(style) - {"run", "paragraph", "inherits"}:
            raise ValueError("style role must contain run, paragraph and/or inherits")
        parent = style.get("inherits")
        if parent is not None and (not isinstance(parent, str) or parent not in ROLE_KEYS):
            raise ValueError("style inherits must name a supported role")
        clean_roles[role] = {
            key: _format_profile_field(item, category=key)
            for key, item in style.items() if key != "inherits"
        }
        if parent is not None:
            clean_roles[role]["inherits"] = parent
    # Reject missing parents and cycles before any document is modified.
    for role in clean_roles:
        current = role
        seen: set[str] = set()
        while current in clean_roles:
            if current in seen:
                raise ValueError("style inheritance cycle")
            seen.add(current)
            parent = clean_roles[current].get("inherits")
            if parent is None:
                break
            if parent not in clean_roles:
                raise ValueError("style inherited role is not defined")
            current = parent
    page = value.get("page", {})
    if not isinstance(page, dict) or set(page) - PAGE_KEYS:
        raise ValueError("style_profile.page contains unknown fields")
    for key, number in page.items():
        if type(number) not in (int, float) or not 5 <= number <= 60:
            raise ValueError(key + " must be between 5 and 60 mm")
    table = value.get("table", {})
    if not isinstance(table, dict) or set(table) - TABLE_KEYS:
        raise ValueError("style_profile.table contains unknown fields")
    if "page_break" in table and table["page_break"] not in ("CELL", "TABLE", "NONE"):
        raise ValueError("table page_break unsupported")
    if "border_color" in table:
        import re
        if not isinstance(table["border_color"], str) or re.fullmatch(r"#?[0-9A-Fa-f]{6}", table["border_color"]) is None:
            raise ValueError("table border_color must be hex")
    for key in ("repeat_header", "first_row_header"):
        if key in table and type(table[key]) is not bool:
            raise ValueError(key + " must be boolean")
    unit = value.get("equation_base_unit", 1100)
    if type(unit) is not int or not 500 <= unit <= 2400:
        raise ValueError("equation_base_unit must be an integer from 500 to 2400")
    return {
        "schema": PROFILE_SCHEMA,
        "name": name,
        "roles": clean_roles,
        "page": dict(page),
        "table": dict(table),
        "equation_base_unit": unit,
    }


def profile_fingerprint(profile: dict[str, Any]) -> str:
    normalized = normalize_style_profile(profile)
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def style_for_block(profile: dict[str, Any], kind: str, level: int = 1) -> dict[str, Any]:
    role = "heading_" + str(level) if kind == "heading" else ("body" if kind in ("paragraph", "list_item", "equation", "piecewise", "equation_line") else kind)
    roles = profile.get("roles", {})
    if role not in roles:
        return {}
    chain: list[dict] = []
    visited: set[str] = set()
    current = role
    while current in roles:
        if current in visited:
            raise ValueError("style inheritance cycle")
        visited.add(current)
        definition = roles[current]
        chain.append(definition)
        current = definition.get("inherits")
        if current is None:
            break
    out: dict[str, Any] = {}
    for definition in reversed(chain):
        for area in ("run", "paragraph"):
            incoming = definition.get(area, {})
            merged = dict(out.get(area, {}))
            for key, value in incoming.items():
                if key == "font_by_script":
                    fonts = dict(merged.get(key, {}))
                    fonts.update(value)
                    merged[key] = fonts
                else:
                    merged[key] = value
            if incoming:
                out[area] = merged
    return out
