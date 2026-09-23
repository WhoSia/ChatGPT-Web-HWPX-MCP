from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from p22_formatting import build_formatting_map

SCRIPTS = ("hangul","latin","hanja","japanese","other","symbol","user")


def typography_contract() -> dict:
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/typography-contract/v1",
        "phase": "P3.35",
        "subphase": "P3.35-R1",
        "character_spacing_percent": {
            "min": -50,
            "max": 50,
            "native_hancom_13_0_0_3622_verified": [-50, -20, 0, 20, 50],
            "out_of_range_behavior": "REJECT",
        },
        "font_model": {
            "scripts": list(SCRIPTS),
            "whole_run_face_key": "font",
            "script_specific_face_key": "font_by_script",
            "native_observation": (
                "representative font selection may set all seven fontRef scripts; "
                "language-specific selection updates only that script while preserving the others"
            ),
        },
        "font_size": {
            "unit": "pt",
            "native_verified_values": [9.0, 13.5],
            "encoding": "charPr@height = pt * 100",
        },
        "mixed_run": {
            "run_format_operation": "set_run_format",
            "range_format_operation": "set_range_format",
            "normalization_operation": "normalize_formatting",
        },
        "evidence_source": "Hancom 13.0.0.3622 native before/after HWPX capture",
    }


def _inc(counter: Counter, value, weight: int) -> None:
    if value is None:
        return
    counter[str(value)] += max(1, int(weight))


def _counter_rows(counter: Counter, limit: int = 20) -> list[dict]:
    total = sum(counter.values())
    rows = []
    for value, chars in counter.most_common(limit):
        rows.append({
            "value": value,
            "characters": int(chars),
            "share": 0.0 if total == 0 else round(chars / total, 6),
        })
    return rows


def build_typography_profile(path: Path) -> dict:
    mapped = build_formatting_map(path)

    size = Counter()
    spacing = {script: Counter() for script in SCRIPTS}
    ratio = {script: Counter() for script in SCRIPTS}
    fonts = {script: Counter() for script in SCRIPTS}
    emphasis = {
        "bold": 0,
        "italic": 0,
        "underline": 0,
        "strike": 0,
    }
    text_chars = 0
    text_runs = 0
    paragraphs_with_multiple_text_runs = 0
    style_fingerprints = Counter()

    for para in mapped.get("paragraphs", []):
        text_bearing = [run for run in para.get("runs", []) if run.get("text")]
        if len(text_bearing) > 1:
            paragraphs_with_multiple_text_runs += 1
        for run in text_bearing:
            text = str(run.get("text") or "")
            weight = len(text)
            if weight <= 0:
                continue
            text_chars += weight
            text_runs += 1
            style = run.get("style") or {}

            _inc(size, style.get("size_pt"), weight)
            faces = style.get("font_faces") or {}
            spaces = style.get("letter_spacing_by_script") or {}
            ratios = style.get("ratio_by_script") or {}

            for script in SCRIPTS:
                _inc(fonts[script], faces.get(script), weight)
                _inc(spacing[script], spaces.get(script), weight)
                _inc(ratio[script], ratios.get(script), weight)

            for key in emphasis:
                if style.get(key):
                    emphasis[key] += weight

            fingerprint_payload = {
                "font_faces": {k: faces.get(k) for k in SCRIPTS},
                "size_pt": style.get("size_pt"),
                "letter_spacing": {k: spaces.get(k) for k in SCRIPTS},
                "ratio": {k: ratios.get(k) for k in SCRIPTS},
                "bold": bool(style.get("bold")),
                "italic": bool(style.get("italic")),
                "underline": bool(style.get("underline")),
                "strike": bool(style.get("strike")),
                "script": style.get("script"),
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    fingerprint_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
            style_fingerprints[(fingerprint, json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True))] += weight

    dominant_styles = []
    for (fingerprint, payload), chars in style_fingerprints.most_common(20):
        dominant_styles.append({
            "fingerprint": fingerprint,
            "characters": int(chars),
            "share": 0.0 if text_chars == 0 else round(chars / text_chars, 6),
            "style": json.loads(payload),
        })

    profile = {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/typography-profile/v1",
        "text_characters": text_chars,
        "text_runs": text_runs,
        "paragraph_count": len(mapped.get("paragraphs", [])),
        "paragraphs_with_multiple_text_runs": paragraphs_with_multiple_text_runs,
        "font_faces_by_script": {script: _counter_rows(fonts[script]) for script in SCRIPTS},
        "font_sizes_pt": _counter_rows(size),
        "letter_spacing_by_script": {script: _counter_rows(spacing[script]) for script in SCRIPTS},
        "ratio_by_script": {script: _counter_rows(ratio[script]) for script in SCRIPTS},
        "emphasis_character_counts": emphasis,
        "dominant_run_styles": dominant_styles,
    }
    profile["profile_sha256"] = hashlib.sha256(
        json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return profile


def compare_typography_profiles(left: dict, right: dict) -> dict:
    def dominant(rows: list[dict]):
        return None if not rows else rows[0]["value"]

    differences = []
    for script in SCRIPTS:
        lf = dominant(left.get("font_faces_by_script", {}).get(script, []))
        rf = dominant(right.get("font_faces_by_script", {}).get(script, []))
        if lf != rf:
            differences.append({
                "dimension": f"font_face.{script}",
                "left": lf,
                "right": rf,
            })
        ls = dominant(left.get("letter_spacing_by_script", {}).get(script, []))
        rs = dominant(right.get("letter_spacing_by_script", {}).get(script, []))
        if ls != rs:
            differences.append({
                "dimension": f"letter_spacing.{script}",
                "left": ls,
                "right": rs,
            })

    lsize = dominant(left.get("font_sizes_pt", []))
    rsize = dominant(right.get("font_sizes_pt", []))
    if lsize != rsize:
        differences.append({"dimension": "font_size_pt", "left": lsize, "right": rsize})

    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/typography-profile-comparison/v1",
        "left_profile_sha256": left.get("profile_sha256"),
        "right_profile_sha256": right.get("profile_sha256"),
        "dominant_differences": differences,
        "left_mixed_run_paragraphs": left.get("paragraphs_with_multiple_text_runs", 0),
        "right_mixed_run_paragraphs": right.get("paragraphs_with_multiple_text_runs", 0),
    }
