from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from p22_formatting import build_formatting_map
from p335_typography import SCRIPTS, build_typography_profile


def paragraph_geometry_contract() -> dict:
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/paragraph-geometry-contract/v1",
        "phase": "P3.35",
        "subphase": "P3.35-R2",
        "strategy": "FEATURE_FIRST_EXISTING_PRIMITIVE_REPROMOTION",
        "authoring_keys": [
            "alignment",
            "line_spacing_percent",
            "indent_left_mm",
            "indent_right_mm",
            "first_line_indent_mm",
            "spacing_before_pt",
            "spacing_after_pt",
            "tab_stops",
            "auto_tab_left",
            "auto_tab_right",
            "outline_level",
            "keep_with_next",
            "keep_lines",
            "page_break_before",
            "column_break",
            "bottom_border",
            "border_color",
            "border_width",
        ],
        "readback": {
            "alignment": "hh:paraPr/hh:align attributes",
            "line_spacing": "hh:paraPr/hh:lineSpacing attributes",
            "margins": "hh:margin hc:intent/left/right/prev/next value+unit",
            "tabs": "paraPr@tabPrIDRef plus resolved hh:tabPr snapshot when present",
            "break_setting": "hh:breakSetting attributes",
            "style": "styleIDRef resolved through header style table",
        },
        "units": {
            "HWPUNIT_per_inch": 7200,
            "HWPUNIT_per_point": 100,
            "profile_policy": "retain native raw values; expose authoring preset only for invertible dimensions",
        },
        "evidence_policy": (
            "reuse existing production paragraph primitives and native XML readback; "
            "open a new Hancom probe only when corpus/readback leaves semantics ambiguous"
        ),
    }


def _stable(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _inc(counter: Counter, value, weight: int) -> None:
    if value is None:
        return
    counter[_stable(value)] += max(1, int(weight))


def _rows(counter: Counter, total_weight: int, limit: int = 20) -> list[dict]:
    rows = []
    denominator = max(1, int(total_weight))
    for payload, weight in counter.most_common(limit):
        rows.append({
            "value": json.loads(payload),
            "weight": int(weight),
            "share": round(weight / denominator, 6),
        })
    return rows


def _dominant(rows: list[dict]):
    return None if not rows else rows[0].get("value")


def _margin_dimension(profile: dict, key: str):
    return _dominant(profile.get("margins", {}).get(key, []))


def build_paragraph_geometry_profile(path: Path) -> dict:
    mapped = build_formatting_map(path)
    counters = {
        "alignment": Counter(),
        "line_spacing": Counter(),
        "break_setting": Counter(),
        "heading": Counter(),
        "border": Counter(),
        "style": Counter(),
        "tab_property": Counter(),
        "page_break": Counter(),
        "column_break": Counter(),
    }
    margins = {key: Counter() for key in ("intent", "left", "right", "prev", "next")}
    fingerprints = Counter()
    total_weight = 0
    paragraphs = mapped.get("paragraphs", [])

    for para in paragraphs:
        weight = max(1, int(para.get("direct_text_length") or 0))
        total_weight += weight
        prop = para.get("paragraph_property") or {}
        style = para.get("style_property") or {}

        _inc(counters["alignment"], prop.get("alignment"), weight)
        _inc(counters["line_spacing"], prop.get("line_spacing"), weight)
        _inc(counters["break_setting"], prop.get("break_setting"), weight)
        _inc(counters["heading"], prop.get("heading"), weight)
        _inc(counters["border"], prop.get("border"), weight)
        _inc(counters["tab_property"], prop.get("tab_property"), weight)
        _inc(counters["page_break"], para.get("page_break"), weight)
        _inc(counters["column_break"], para.get("column_break"), weight)

        style_payload = {
            "style_id_ref": para.get("style_id_ref"),
            "name": style.get("name"),
            "eng_name": style.get("eng_name"),
            "type": style.get("type"),
            "para_pr_id_ref": style.get("para_pr_id_ref"),
        }
        _inc(counters["style"], style_payload, weight)

        margin_values = prop.get("margin_values") or {}
        for key in margins:
            _inc(margins[key], margin_values.get(key), weight)

        fingerprint_payload = {
            "alignment": prop.get("alignment"),
            "line_spacing": prop.get("line_spacing"),
            "margin_values": margin_values,
            "tab_pr_id_ref": prop.get("tab_pr_id_ref"),
            "tab_property": prop.get("tab_property"),
            "break_setting": prop.get("break_setting"),
            "page_break": para.get("page_break"),
            "column_break": para.get("column_break"),
            "style": style_payload,
        }
        fingerprint = hashlib.sha256(_stable(fingerprint_payload).encode("utf-8")).hexdigest()[:16]
        fingerprints[(fingerprint, _stable(fingerprint_payload))] += weight

    dominant_paragraph_styles = []
    for (fingerprint, payload), weight in fingerprints.most_common(20):
        dominant_paragraph_styles.append({
            "fingerprint": fingerprint,
            "weight": int(weight),
            "share": round(weight / max(1, total_weight), 6),
            "style": json.loads(payload),
        })

    profile = {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/paragraph-geometry-profile/v1",
        "paragraph_count": len(paragraphs),
        "weighted_characters_or_empty_paragraphs": total_weight,
        "alignment": _rows(counters["alignment"], total_weight),
        "line_spacing": _rows(counters["line_spacing"], total_weight),
        "margins": {key: _rows(counter, total_weight) for key, counter in margins.items()},
        "tab_properties": _rows(counters["tab_property"], total_weight),
        "break_settings": _rows(counters["break_setting"], total_weight),
        "headings": _rows(counters["heading"], total_weight),
        "borders": _rows(counters["border"], total_weight),
        "styles": _rows(counters["style"], total_weight),
        "page_break": _rows(counters["page_break"], total_weight),
        "column_break": _rows(counters["column_break"], total_weight),
        "dominant_paragraph_styles": dominant_paragraph_styles,
    }
    profile["profile_sha256"] = hashlib.sha256(_stable(profile).encode("utf-8")).hexdigest()
    return profile


def compare_paragraph_geometry_profiles(left: dict, right: dict) -> dict:
    dimensions = [
        ("alignment", _dominant(left.get("alignment", [])), _dominant(right.get("alignment", []))),
        ("line_spacing", _dominant(left.get("line_spacing", [])), _dominant(right.get("line_spacing", []))),
        ("tab_property", _dominant(left.get("tab_properties", [])), _dominant(right.get("tab_properties", []))),
        ("style", _dominant(left.get("styles", [])), _dominant(right.get("styles", []))),
        ("page_break", _dominant(left.get("page_break", [])), _dominant(right.get("page_break", []))),
        ("column_break", _dominant(left.get("column_break", [])), _dominant(right.get("column_break", []))),
    ]
    for key in ("intent", "left", "right", "prev", "next"):
        dimensions.append((f"margin.{key}", _margin_dimension(left, key), _margin_dimension(right, key)))

    differences = [
        {"dimension": name, "left": lvalue, "right": rvalue}
        for name, lvalue, rvalue in dimensions
        if lvalue != rvalue
    ]
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/paragraph-geometry-profile-comparison/v1",
        "left_profile_sha256": left.get("profile_sha256"),
        "right_profile_sha256": right.get("profile_sha256"),
        "dominant_differences": differences,
    }


def _number(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _hwpunit_to_mm(item: dict | None):
    if not item or str(item.get("unit") or "").upper() != "HWPUNIT":
        return None
    value = _number(item.get("value"))
    return None if value is None else round(value * 25.4 / 7200.0, 6)


def _hwpunit_to_pt(item: dict | None):
    if not item or str(item.get("unit") or "").upper() != "HWPUNIT":
        return None
    value = _number(item.get("value"))
    return None if value is None else round(value / 100.0, 6)


def _paragraph_authoring_preset(profile: dict) -> dict:
    result = {}
    alignment = _dominant(profile.get("alignment", []))
    if isinstance(alignment, dict) and alignment.get("horizontal"):
        result["alignment"] = str(alignment["horizontal"]).lower()

    line_spacing = _dominant(profile.get("line_spacing", []))
    if isinstance(line_spacing, dict) and str(line_spacing.get("type") or "").upper() == "PERCENT":
        value = _number(line_spacing.get("value"))
        if value is not None:
            result["line_spacing_percent"] = value

    left = _hwpunit_to_mm(_margin_dimension(profile, "left"))
    right = _hwpunit_to_mm(_margin_dimension(profile, "right"))
    intent = _hwpunit_to_mm(_margin_dimension(profile, "intent"))
    before = _hwpunit_to_pt(_margin_dimension(profile, "prev"))
    after = _hwpunit_to_pt(_margin_dimension(profile, "next"))
    if left is not None:
        result["indent_left_mm"] = left
    if right is not None:
        result["indent_right_mm"] = right
    if intent is not None:
        result["first_line_indent_mm"] = intent
    if before is not None:
        result["spacing_before_pt"] = before
    if after is not None:
        result["spacing_after_pt"] = after
    return result


def _typography_authoring_preset(profile: dict) -> dict:
    result = {}
    fonts = {}
    spacing = {}
    for script in SCRIPTS:
        face = _dominant(profile.get("font_faces_by_script", {}).get(script, []))
        if face is not None:
            fonts[script] = face
        space = _dominant(profile.get("letter_spacing_by_script", {}).get(script, []))
        if space is not None:
            try:
                spacing[script] = int(space)
            except (TypeError, ValueError):
                pass
    if fonts:
        result["font_by_script"] = fonts

    size = _dominant(profile.get("font_sizes_pt", []))
    if size is not None:
        try:
            result["size"] = float(size)
        except (TypeError, ValueError):
            pass

    if spacing and len(set(spacing.values())) == 1:
        value = next(iter(spacing.values()))
        if -50 <= value <= 50:
            result["letter_spacing"] = value
    elif spacing:
        result["letter_spacing_by_script_readback_only"] = spacing
    return result


def build_document_style_exemplar(path: Path) -> dict:
    typography = build_typography_profile(path)
    paragraph = build_paragraph_geometry_profile(path)
    exemplar = {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/document-style-exemplar/v1",
        "typography_profile_sha256": typography.get("profile_sha256"),
        "paragraph_profile_sha256": paragraph.get("profile_sha256"),
        "authoring_preset": {
            "run_format": _typography_authoring_preset(typography),
            "paragraph_format": _paragraph_authoring_preset(paragraph),
        },
        "native_readback": {
            "dominant_typography_style": (
                None if not typography.get("dominant_run_styles")
                else typography["dominant_run_styles"][0]["style"]
            ),
            "dominant_paragraph_style": (
                None if not paragraph.get("dominant_paragraph_styles")
                else paragraph["dominant_paragraph_styles"][0]["style"]
            ),
            "dominant_tab_property": _dominant(paragraph.get("tab_properties", [])),
        },
        "application_policy": (
            "preset contains only dimensions safely invertible through existing public authoring keys; "
            "native tab property remains readback-only until a corpus or targeted probe confirms exact reuse semantics"
        ),
    }
    exemplar["exemplar_sha256"] = hashlib.sha256(_stable(exemplar).encode("utf-8")).hexdigest()
    return exemplar
