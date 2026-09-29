from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import re
from typing import Any, Mapping

PRODUCT = "0.28.0-p4.2"
PHASE = "P4.2"
SOURCE_PIN = "6.5.0"
CANDIDATE = "6.6.0"

NUMBER_FORMATS = frozenset({
    "DIGIT", "CIRCLED_DIGIT", "ROMAN_CAPITAL", "ROMAN_SMALL", "LATIN_CAPITAL", "LATIN_SMALL",
    "CIRCLED_LATIN_CAPITAL", "CIRCLED_LATIN_SMALL", "HANGUL_SYLLABLE", "CIRCLED_HANGUL_SYLLABLE",
    "HANGUL_JAMO", "CIRCLED_HANGUL_JAMO", "HANGUL_PHONETIC", "IDEOGRAPH", "CIRCLED_IDEOGRAPH",
})
NUMBER_FORMAT_ALIASES = {
    "NUMBER": "DIGIT",
    "ROMAN": "ROMAN_CAPITAL",
    "ROMAN_UPPER": "ROMAN_CAPITAL",
    "ROMAN_LOWER": "ROMAN_SMALL",
    "ALPHA": "LATIN_CAPITAL",
    "ALPHA_UPPER": "LATIN_CAPITAL",
    "ALPHA_LOWER": "LATIN_SMALL",
    "HANGUL": "HANGUL_SYLLABLE",
}

def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()

def semantic_page_geometry(width: int, height: int, storage_orientation: str | None) -> dict:
    raw_width = int(width)
    raw_height = int(height)
    raw_orientation = str(storage_orientation or "").strip().upper() or None
    if raw_width <= 0 or raw_height <= 0:
        raise ValueError("page dimensions must be positive")

    source = "ORIENTATION_ATTRIBUTE"
    if raw_orientation in {"NARROWLY", "LANDSCAPE"}:
        semantic = "LANDSCAPE"
    elif raw_orientation in {"WIDELY", "PORTRAIT"}:
        # python-hwpx<=6.5 wrote LANDSCAPE as WIDELY and also swapped the
        # stored dimensions. Preserve those already-authored documents.
        if raw_orientation == "WIDELY" and raw_width > raw_height:
            semantic = "LANDSCAPE"
            source = "LEGACY_6_5_GEOMETRY_OVERRIDE"
        else:
            semantic = "PORTRAIT"
    else:
        semantic = "LANDSCAPE" if raw_width > raw_height else "PORTRAIT"
        source = "GEOMETRY_INFERENCE"

    short_side, long_side = sorted((raw_width, raw_height))
    drawn_width, drawn_height = (
        (long_side, short_side) if semantic == "LANDSCAPE" else (short_side, long_side)
    )
    return {
        "width": drawn_width,
        "height": drawn_height,
        "orientation": semantic,
        "storage_width": raw_width,
        "storage_height": raw_height,
        "storage_orientation": raw_orientation,
        "orientation_authority": source,
    }

def normalize_list_number_format(value: object | None, *, level: int = 1) -> tuple[str | None, dict]:
    if value is None:
        return None, {"status": "UNCHANGED", "input": None, "output": None}
    if int(level) < 1:
        raise ValueError("level must be >= 1")
    raw = str(value).strip()
    normalized = raw.upper()
    normalized = NUMBER_FORMAT_ALIASES.get(normalized, normalized)
    if normalized in NUMBER_FORMATS:
        return normalized, {
            "status": "CANONICAL",
            "input": raw,
            "output": normalized,
            "rule": "UPSTREAM_NUMBER_TYPE_ENUM",
        }

    expected_legacy = ".".join(f"^{part}" for part in range(1, int(level) + 1)) + "."
    if raw == expected_legacy:
        return "DIGIT", {
            "status": "MIGRATED",
            "input": raw,
            "output": "DIGIT",
            "rule": "LEGACY_DEFAULT_PATTERN_TO_DIGIT",
            "preserved_label_pattern": expected_legacy,
        }

    if re.fullmatch(r"(?:\^\d+\.)+", raw):
        raise ValueError(
            "legacy numbered-list pattern does not match the selected level; "
            f"expected {expected_legacy!r} for level {level}"
        )
    raise ValueError(
        f"unsupported numbered-list format {raw!r}; use a supported semantic number type"
    )

def migration_contract() -> dict:
    contract = {
        "schema": "chatgpt-web-hwpx-mcp/p4.2/migration-contract/v1",
        "phase": PHASE,
        "product": PRODUCT,
        "source_pin": SOURCE_PIN,
        "candidate": CANDIDATE,
        "adapters": [
            {
                "id": "PAGE_ORIENTATION_SEMANTIC_NORMALIZATION",
                "purpose": "separate drawn page geometry from raw OWPML storage geometry",
                "preserves": ["P3.18 page map", "P3.38 rich-builder page semantics"],
            },
            {
                "id": "LIST_NUMBER_FORMAT_SEMANTIC_NORMALIZATION",
                "purpose": "translate the legacy default ^N. pattern into the upstream number-type enum",
                "preserves": ["P3.19 numbered-list label semantics"],
            },
        ],
        "promotion_policy": "EVIDENCE_GATED_NO_AUTOMATIC_DEPENDENCY_PROMOTION",
        "rollback_policy": "EXACT_REQUIREMENTS_PIN_ROLLBACK",
    }
    return {**contract, "contract_sha256": _sha(contract)}

def current_runtime_state() -> dict:
    try:
        observed = md.version("python-hwpx")
    except md.PackageNotFoundError:
        observed = None
    if observed == CANDIDATE:
        state = "CANDIDATE_OR_PROMOTED_TARGET"
    elif observed == SOURCE_PIN:
        state = "SUPPORTED_SOURCE_PIN"
    else:
        state = "UNVALIDATED_RUNTIME"
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "observed_python_hwpx": observed,
        "state": state,
        "source_pin": SOURCE_PIN,
        "candidate": CANDIDATE,
    }

def adjudicate_upgrade(evidence: Mapping[str, Any]) -> dict:
    required = [
        "candidate_targeted_regressions",
        "real_document_matrix",
        "performance_budget",
        "candidate_docker",
        "rollback_rehearsal",
    ]
    normalized = {key: bool(evidence.get(key)) for key in required}
    missing = [key for key, ok in normalized.items() if not ok]
    verdict = "READY_FOR_PROMOTION_COMMIT" if not missing else "HOLD"
    payload = {
        "phase": PHASE,
        "product": PRODUCT,
        "candidate": CANDIDATE,
        "source_pin": SOURCE_PIN,
        "evidence": normalized,
        "missing_or_failed": missing,
        "verdict": verdict,
        "automatic_production_promotion": False,
    }
    return {**payload, "receipt_sha256": _sha(payload)}
