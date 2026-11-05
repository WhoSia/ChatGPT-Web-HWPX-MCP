"""Opt-in HWPX reference → reusable, minimal style-profile extraction.

Reuses the existing P3.35 typography/paragraph exemplar subsystem.
Returns only portable formatting, source fingerprint and warnings; **never**
the document text or paragraph locators. User approval is required before
reusing inferred styles in other documents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_mcp.corpus.p335_paragraph import build_role_aware_style_exemplars
from hwpx_mcp.document.p423_style_profile import (
    RUN_KEYS, PARA_KEYS, normalize_style_profile, profile_fingerprint,
)

ROLE_ALIASES = {"body": "body", "title": "title", "heading": "heading_1"}


def profile_from_reference(path: str | Path, *, name: str = "reference-style") -> dict[str, Any]:
    """Extract a *candidate*, not automatic user preference or visual proof."""
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        raise ValueError("profile name must contain 1..80 characters")
    observations = build_role_aware_style_exemplars(Path(path))
    warnings: list[str] = []
    roles: dict[str, dict[str, Any]] = {}
    for entry in observations.get("roles", []):
        source_role = str(entry.get("role") or "")
        target_role = ROLE_ALIASES.get(source_role)
        if target_role is None:
            warnings.append(f"role {source_role!r} not transferred; unsupported destination role")
            continue
        if target_role in roles:
            warnings.append(f"role {source_role!r} duplicated; manual selection required")
            continue
        preset = entry.get("authoring_preset") or {}
        mapped = {}
        for input_key, output_key, allowed in (
            ("run_format", "run", RUN_KEYS),
            ("paragraph_format", "paragraph", PARA_KEYS),
        ):
            raw_style = preset.get(input_key) or {}
            if not isinstance(raw_style, dict):
                warnings.append(f"{source_role}.{input_key} is invalid and omitted")
                continue
            extra = sorted(set(raw_style) - allowed)
            if extra:
                warnings.append(f"{source_role}.{input_key} unportable dimensions: {', '.join(extra)}")
            portable = {k: v for k, v in raw_style.items() if k in allowed}
            if output_key == "run" and isinstance(portable.get("font_by_script"), dict):
                fonts = portable["font_by_script"]
                unsupported_scripts = sorted(set(fonts) - {"hangul", "latin", "hanja", "japanese", "other"})
                if unsupported_scripts:
                    warnings.append(f"{source_role}.font_by_script unsupported scripts: {', '.join(unsupported_scripts)}")
                allowed_fonts = {k: v for k, v in fonts.items() if k not in unsupported_scripts}
                if allowed_fonts:
                    portable["font_by_script"] = allowed_fonts
                else:
                    del portable["font_by_script"]
            if output_key == "paragraph" and "alignment" in portable:
                if isinstance(portable["alignment"], str):
                    portable["alignment"] = portable["alignment"].upper()
            accepted: dict[str, Any] = {}
            for field, field_value in portable.items():
                # Validate per field: an unportable spacing setting must not
                # discard an otherwise usable reference font.
                if field == "line_spacing_percent" and type(field_value) is float and field_value.is_integer():
                    field_value = int(field_value)
                try:
                    normalize_style_profile({
                        "name": name,
                        "roles": {target_role: {output_key: {field: field_value}}},
                    })
                except ValueError as exc:
                    warnings.append(f"{source_role}.{field} omitted: {exc}")
                else:
                    accepted[field] = field_value
            if accepted:
                mapped[output_key] = accepted
        if mapped:
            try:
                checked = normalize_style_profile({"name": name, "roles": {target_role: mapped}})
                roles[target_role] = checked["roles"][target_role]
            except ValueError as exc:
                warnings.append(f"{source_role} style rejected: {exc}")
    if not roles:
        raise ValueError("reference has no portable supported style roles")
    profile = normalize_style_profile({"name": name, "roles": roles})
    return {
        "style_profile": profile,
        "style_profile_sha256": profile_fingerprint(profile),
        "reference_exemplar_sha256": observations.get("profile_sha256"),
        "warnings": warnings,
        "status": "CANDIDATE_REQUIRES_USER_APPROVAL",
        "source_text_included": False,
    }
