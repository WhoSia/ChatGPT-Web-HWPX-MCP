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


def _paragraph_geometry_profile_from_paragraphs(paragraphs: list[dict]) -> dict:
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


def build_paragraph_geometry_profile(path: Path) -> dict:
    mapped = build_formatting_map(path)
    return _paragraph_geometry_profile_from_paragraphs(mapped.get("paragraphs", []))


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


def build_style_transfer_operations(
    exemplar: dict,
    targets: list[str],
    *,
    include_typography: bool = True,
    include_paragraph: bool = True,
) -> list[dict]:
    """Compile one extracted exemplar into existing atomic formatting operations.

    This intentionally reuses the already-productionized set_run_format and
    set_paragraph_format primitives. Native-only/readback-only dimensions are
    never promoted into mutation keys here.
    """
    if not isinstance(exemplar, dict):
        raise TypeError("exemplar must be a dict")
    clean_targets = [str(target).strip() for target in targets if str(target).strip()]
    if not clean_targets:
        raise ValueError("At least one target paragraph locator is required")
    if len(set(clean_targets)) != len(clean_targets):
        raise ValueError("Duplicate target paragraph locator")

    preset = exemplar.get("authoring_preset") or {}
    run_format = dict(preset.get("run_format") or {})
    paragraph_format = dict(preset.get("paragraph_format") or {})
    run_format = {
        key: value for key, value in run_format.items()
        if not str(key).endswith("_readback_only")
    }

    operations: list[dict] = []
    for target in clean_targets:
        if include_typography and run_format:
            operations.append({
                "op": "set_run_format",
                "target": target,
                "format": dict(run_format),
            })
        if include_paragraph and paragraph_format:
            operations.append({
                "op": "set_paragraph_format",
                "target": target,
                "format": dict(paragraph_format),
            })
    if not operations:
        raise ValueError("Exemplar contains no safely reusable authoring dimensions")
    return operations


def _infer_paragraph_role(para: dict) -> dict:
    """Assign a conservative document role from explicit HWPX evidence only."""
    container = str(para.get("container") or "unknown").lower()
    style = para.get("style_property") or {}
    style_name = " ".join(
        str(value or "").lower()
        for value in (style.get("name"), style.get("eng_name"))
    )
    named_roles = (
        ("caption", ("캡션", "caption")),
        ("footnote", ("각주", "footnote")),
        ("header", ("머리말", "header")),
        ("footer", ("꼬리말", "footer")),
        ("title", ("제목", "title")),
    )
    for role, tokens in named_roles:
        if any(token in style_name for token in tokens):
            return {"role": role, "basis": "named_style", "evidence": style_name.strip()}

    if container != "section-body":
        table_tokens = ("tc", "cell", "table", "tbl")
        role = "table_cell" if any(token in container for token in table_tokens) else "embedded"
        return {"role": role, "basis": "container", "evidence": container}

    heading = (para.get("paragraph_property") or {}).get("heading") or {}
    heading_type = str(heading.get("type") or "").upper()
    if heading and heading_type not in ("", "NONE"):
        return {"role": "heading", "basis": "paragraph_heading", "evidence": dict(heading)}

    return {
        "role": "body",
        "basis": "conservative_fallback",
        "evidence": {
            "style_id_ref": para.get("style_id_ref"),
            "style_name": style.get("name"),
        },
    }


def _run_authoring_preset_from_paragraphs(paragraphs: list[dict]) -> dict:
    font_counters = {script: Counter() for script in SCRIPTS}
    size_counter = Counter()
    spacing_counters = {script: Counter() for script in SCRIPTS}
    for para in paragraphs:
        for run in para.get("runs", []):
            text = str(run.get("text") or "")
            if not text:
                continue
            weight = max(1, len(text))
            style = run.get("style") or {}
            for script in SCRIPTS:
                face = (style.get("font_faces") or {}).get(script)
                if face:
                    font_counters[script][str(face)] += weight
                spacing = (style.get("letter_spacing_by_script") or {}).get(script)
                if spacing is not None:
                    try:
                        spacing_counters[script][int(spacing)] += weight
                    except (TypeError, ValueError):
                        pass
            size = style.get("size_pt")
            if size is not None:
                try:
                    size_counter[float(size)] += weight
                except (TypeError, ValueError):
                    pass

    result: dict = {}
    fonts = {
        script: counter.most_common(1)[0][0]
        for script, counter in font_counters.items()
        if counter
    }
    if fonts:
        result["font_by_script"] = fonts
    if size_counter:
        result["size"] = size_counter.most_common(1)[0][0]

    spacing = {
        script: counter.most_common(1)[0][0]
        for script, counter in spacing_counters.items()
        if counter
    }
    if spacing and len(set(spacing.values())) == 1:
        value = next(iter(spacing.values()))
        if -50 <= value <= 50:
            result["letter_spacing"] = value
    return result


def build_role_aware_style_exemplars(path: Path) -> dict:
    """Extract multiple evidence-bounded style presets instead of one document-wide dominant preset."""
    mapped = build_formatting_map(path)
    paragraphs = mapped.get("paragraphs", [])
    grouped: dict[str, list[dict]] = {}
    evidence = Counter()
    assignments = []

    for para in paragraphs:
        inferred = _infer_paragraph_role(para)
        role = inferred["role"]
        # Empty structural anchors (including HwpxDocument.new's initial
        # paragraph) are not evidence for a textual role's style. Retain the
        # assignment for geometry/custody, but exclude it from exemplar support.
        included = any(str(run.get("text") or "").strip() for run in para.get("runs", []))
        if included:
            grouped.setdefault(role, []).append(para)
        evidence[(role, inferred["basis"])] += 1
        assignments.append({
            "locator": para.get("locator"),
            "role": role,
            "basis": inferred["basis"],
            "evidence": inferred["evidence"],
            "included_in_exemplar": included,
            "exclusion_reason": None if included else "EMPTY_OR_WHITESPACE_STRUCTURAL_PARAGRAPH",
        })

    roles = []
    for role in sorted(grouped):
        group = grouped[role]
        paragraph_profile = _paragraph_geometry_profile_from_paragraphs(group)
        text_weight = sum(max(1, int(para.get("direct_text_length") or 0)) for para in group)
        roles.append({
            "role": role,
            "paragraph_count": len(group),
            "weighted_characters_or_empty_paragraphs": text_weight,
            "authoring_preset": {
                "run_format": _run_authoring_preset_from_paragraphs(group),
                "paragraph_format": _paragraph_authoring_preset(paragraph_profile),
            },
            "native_readback": {
                "dominant_paragraph_style": (
                    None if not paragraph_profile.get("dominant_paragraph_styles")
                    else paragraph_profile["dominant_paragraph_styles"][0]["style"]
                ),
                "dominant_tab_property": _dominant(paragraph_profile.get("tab_properties", [])),
            },
            "paragraph_profile_sha256": paragraph_profile.get("profile_sha256"),
        })

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/role-aware-style-exemplars/v1",
        "classification_policy": (
            "explicit named style and structural container evidence first; "
            "paragraph heading metadata second; otherwise conservative body fallback"
        ),
        "roles": roles,
        "structural_paragraph_count": len(paragraphs),
        "excluded_empty_paragraph_count": sum(not row["included_in_exemplar"] for row in assignments),
        "assignments": assignments,
        "evidence_counts": [
            {"role": role, "basis": basis, "paragraphs": count}
            for (role, basis), count in sorted(evidence.items())
        ],
    }
    result["profile_sha256"] = hashlib.sha256(_stable(result).encode("utf-8")).hexdigest()
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
