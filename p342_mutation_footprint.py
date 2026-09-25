from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from p2_document import build_document_map
from p28_tables import build_table_map
from p340_feedback_loop import apply_document_design_repairs_atomic

SCHEMA = "chatgpt-web-hwpx-mcp/p3.42/mutation-footprint-certificate/v1"
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.42/mutation-footprint-contract/v1"
HEADER_PART = "Contents/header.xml"
MAX_PARTS = 2048
MAX_EXPANDED_BYTES = 128_000_000
MAX_SINGLE_PART_BYTES = 64_000_000
MAX_EXPANSION_RATIO = 200

GRADE_ORDER = {
    "PACKAGE_VALID_ONLY": 0,
    "TARGETED_PARTS_ONLY": 1,
    "PACKAGE_IDENTICAL": 2,
}
EXPECTED_SCOPE_FIELDS = {
    "changed_parts",
    "added_parts",
    "removed_parts",
    "required_changed_parts",
    "require_untouched_record_metadata",
    "label",
}


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def mutation_footprint_contract() -> dict:
    return {
        "schema": CONTRACT_SCHEMA,
        "phase": "P3.42",
        "purpose": "MEASURE_EXPECTED_VS_ACTUAL_HWPX_PACKAGE_PART_MUTATION_AND_FAIL_CLOSED_ON_DIVERGENCE",
        "grades_strongest_first": [
            "PACKAGE_IDENTICAL",
            "TARGETED_PARTS_ONLY",
            "PACKAGE_VALID_ONLY",
        ],
        "grade_semantics": {
            "PACKAGE_IDENTICAL": (
                "Whole HWPX container bytes are identical. This is normally a no-op result."
            ),
            "TARGETED_PARTS_ONLY": (
                "All observed payload changes/additions/removals are inside the declared exact scope; "
                "every untouched common part payload is byte-identical."
            ),
            "PACKAGE_VALID_ONLY": (
                "The before/after archives were inspectable, but the declared mutation footprint was "
                "missing or diverged. No targeted-preservation claim is authorized."
            ),
        },
        "evidence_layers": [
            "WHOLE_PACKAGE_SHA256",
            "PER_PART_UNCOMPRESSED_PAYLOAD_SHA256",
            "UNTOUCHED_RECORD_METADATA_SIGNATURE",
            "EXPECTED_VS_OBSERVED_PART_SET",
            "PRESERVATION_GRADE_ENFORCEMENT",
        ],
        "scope_policy": {
            "exact_paths_only": True,
            "wildcards": False,
            "implicit_add_remove_permission": False,
            "missing_required_change_is_divergence": True,
        },
        "non_claims": [
            "No unchanged byte claim inside a changed part.",
            "No visual fidelity claim without render evidence.",
            "No semantic correctness claim from ZIP-part locality alone.",
            "ZIP record metadata identity is reported separately from payload identity.",
        ],
    }


def classify_footprint_grade(
    *,
    package_identical: bool,
    expected_declared: bool,
    unexpected_changed: int,
    unexpected_added: int,
    unexpected_removed: int,
    missing_required: int,
    untouched_record_metadata_changed: int = 0,
    require_untouched_record_metadata: bool = False,
) -> str:
    if package_identical:
        return "PACKAGE_IDENTICAL"
    diverged = bool(
        unexpected_changed
        or unexpected_added
        or unexpected_removed
        or missing_required
        or (require_untouched_record_metadata and untouched_record_metadata_changed)
    )
    if expected_declared and not diverged:
        return "TARGETED_PARTS_ONLY"
    return "PACKAGE_VALID_ONLY"


def _canonical_part_name(value: str) -> str:
    name = str(value or "").strip()
    if (
        not name
        or len(name) > 512
        or name.startswith("/")
        or "\\" in name
        or any(ch in name for ch in "*?[]")
        or any(piece in {"", ".", ".."} for piece in name.split("/"))
    ):
        raise ValueError(f"invalid HWPX part path: {value!r}")
    return name


def _normalize_part_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_PARTS:
        raise ValueError(f"{field} must be a bounded list")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        name = _canonical_part_name(str(item))
        if name in seen:
            raise ValueError(f"duplicate part in {field}: {name}")
        seen.add(name)
        out.append(name)
    return sorted(out)


def normalize_expected_scope(scope: Mapping[str, Any] | None) -> dict:
    if scope is None:
        return {
            "declared": False,
            "changed_parts": [],
            "added_parts": [],
            "removed_parts": [],
            "required_changed_parts": [],
            "require_untouched_record_metadata": False,
            "label": None,
        }
    if not isinstance(scope, Mapping) or set(scope) - EXPECTED_SCOPE_FIELDS:
        raise ValueError("invalid expected mutation scope fields")
    changed = _normalize_part_list(scope.get("changed_parts"), "changed_parts")
    added = _normalize_part_list(scope.get("added_parts"), "added_parts")
    removed = _normalize_part_list(scope.get("removed_parts"), "removed_parts")
    required = _normalize_part_list(
        scope.get("required_changed_parts"), "required_changed_parts"
    )
    if set(required) - set(changed):
        raise ValueError("required_changed_parts must be a subset of changed_parts")
    label = scope.get("label")
    if label is not None and (not isinstance(label, str) or len(label) > 240):
        raise ValueError("expected scope label is invalid")
    return {
        "declared": True,
        "changed_parts": changed,
        "added_parts": added,
        "removed_parts": removed,
        "required_changed_parts": required,
        "require_untouched_record_metadata": bool(
            scope.get("require_untouched_record_metadata", False)
        ),
        "label": label,
    }


def _record_signature(info: zipfile.ZipInfo) -> dict:
    # Content-derived fields (CRC, compressed size, uncompressed size) are deliberately
    # excluded. This is a metadata signal, not a byte-for-byte local-record oracle.
    return {
        "compress_type": int(info.compress_type),
        "flag_bits": int(info.flag_bits),
        "date_time": list(info.date_time),
        "external_attr": int(info.external_attr),
        "internal_attr": int(info.internal_attr),
        "create_system": int(info.create_system),
        "create_version": int(info.create_version),
        "extract_version": int(info.extract_version),
        "extra_sha256": _sha_bytes(bytes(info.extra or b"")),
        "comment_sha256": _sha_bytes(bytes(info.comment or b"")),
    }


def _package_inventory(path: Path) -> dict:
    path = Path(path)
    raw = path.read_bytes()
    try:
        archive = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid HWPX ZIP container") from exc
    with archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in infos]
        if len(infos) > MAX_PARTS:
            raise ValueError("HWPX part-count limit exceeded")
        if len(names) != len(set(names)):
            raise ValueError("duplicate HWPX part names are not admitted")
        expanded = sum(int(item.file_size) for item in infos)
        if expanded > MAX_EXPANDED_BYTES:
            raise ValueError("HWPX expanded-size limit exceeded")
        parts: dict[str, dict] = {}
        for info in infos:
            name = _canonical_part_name(info.filename)
            if int(info.file_size) > MAX_SINGLE_PART_BYTES:
                raise ValueError(f"HWPX part too large: {name}")
            ratio = int(info.file_size) / max(1, int(info.compress_size))
            if ratio > MAX_EXPANSION_RATIO:
                raise ValueError(f"HWPX part expansion ratio too high: {name}")
            payload = archive.read(info)
            parts[name] = {
                "sha256": _sha_bytes(payload),
                "bytes": len(payload),
                "record": _record_signature(info),
            }
    return {
        "path": str(path),
        "package_sha256": _sha_bytes(raw),
        "package_bytes": len(raw),
        "part_count": len(parts),
        "expanded_bytes": sum(item["bytes"] for item in parts.values()),
        "parts": parts,
    }


def build_mutation_footprint(
    before: Path | str,
    after: Path | str,
    expected_scope: Mapping[str, Any] | None = None,
) -> dict:
    before_inv = _package_inventory(Path(before))
    after_inv = _package_inventory(Path(after))
    expected = normalize_expected_scope(expected_scope)

    before_names = set(before_inv["parts"])
    after_names = set(after_inv["parts"])
    common = before_names & after_names
    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    changed = sorted(
        name
        for name in common
        if before_inv["parts"][name]["sha256"] != after_inv["parts"][name]["sha256"]
    )
    unchanged = sorted(common - set(changed))
    record_drift = sorted(
        name
        for name in unchanged
        if before_inv["parts"][name]["record"] != after_inv["parts"][name]["record"]
    )

    expected_changed = set(expected["changed_parts"])
    expected_added = set(expected["added_parts"])
    expected_removed = set(expected["removed_parts"])
    required_changed = set(expected["required_changed_parts"])

    unexpected_changed = sorted(set(changed) - expected_changed)
    unexpected_added = sorted(set(added) - expected_added)
    unexpected_removed = sorted(set(removed) - expected_removed)
    missing_required = sorted(required_changed - set(changed))

    package_identical = (
        before_inv["package_sha256"] == after_inv["package_sha256"]
    )
    actual_grade = classify_footprint_grade(
        package_identical=package_identical,
        expected_declared=bool(expected["declared"]),
        unexpected_changed=len(unexpected_changed),
        unexpected_added=len(unexpected_added),
        unexpected_removed=len(unexpected_removed),
        missing_required=len(missing_required),
        untouched_record_metadata_changed=len(record_drift),
        require_untouched_record_metadata=bool(
            expected["require_untouched_record_metadata"]
        ),
    )

    certificate = {
        "schema": SCHEMA,
        "phase": "P3.42",
        "before": {
            "package_sha256": before_inv["package_sha256"],
            "package_bytes": before_inv["package_bytes"],
            "part_count": before_inv["part_count"],
            "expanded_bytes": before_inv["expanded_bytes"],
        },
        "after": {
            "package_sha256": after_inv["package_sha256"],
            "package_bytes": after_inv["package_bytes"],
            "part_count": after_inv["part_count"],
            "expanded_bytes": after_inv["expanded_bytes"],
        },
        "expected_scope": expected,
        "observed": {
            "changed_parts": changed,
            "added_parts": added,
            "removed_parts": removed,
            "unchanged_common_parts": len(unchanged),
            "untouched_record_metadata_changed_parts": record_drift,
        },
        "divergence": {
            "unexpected_changed_parts": unexpected_changed,
            "unexpected_added_parts": unexpected_added,
            "unexpected_removed_parts": unexpected_removed,
            "missing_required_changed_parts": missing_required,
            "count": (
                len(unexpected_changed)
                + len(unexpected_added)
                + len(unexpected_removed)
                + len(missing_required)
                + (
                    len(record_drift)
                    if expected["require_untouched_record_metadata"]
                    else 0
                )
            ),
        },
        "preservation": {
            "actual_grade": actual_grade,
            "whole_package_identical": package_identical,
            "untouched_part_payloads": {
                "verified": len(unchanged),
                "changed": 0,
            },
            "untouched_record_metadata": {
                "verified": len(unchanged) - len(record_drift),
                "changed": len(record_drift),
                "required_for_grade": bool(
                    expected["require_untouched_record_metadata"]
                ),
            },
            "changed_part_payloads": {
                name: {
                    "before_sha256": before_inv["parts"][name]["sha256"],
                    "after_sha256": after_inv["parts"][name]["sha256"],
                    "before_bytes": before_inv["parts"][name]["bytes"],
                    "after_bytes": after_inv["parts"][name]["bytes"],
                }
                for name in changed
            },
            "added_part_payloads": {
                name: {
                    "after_sha256": after_inv["parts"][name]["sha256"],
                    "after_bytes": after_inv["parts"][name]["bytes"],
                }
                for name in added
            },
            "removed_part_payloads": {
                name: {
                    "before_sha256": before_inv["parts"][name]["sha256"],
                    "before_bytes": before_inv["parts"][name]["bytes"],
                }
                for name in removed
            },
        },
        "authority": (
            "MEASURED_PACKAGE_PART_FOOTPRINT_NOT_VISUAL_OR_SEMANTIC_CORRECTNESS"
        ),
    }
    certificate["certificate_sha256"] = _sha(certificate)
    return certificate


def enforce_preservation_grade(certificate: Mapping[str, Any], required_grade: str) -> dict:
    required = str(required_grade or "").upper()
    if required not in GRADE_ORDER:
        raise ValueError(f"unsupported preservation grade: {required_grade}")
    actual = str(
        (certificate.get("preservation") or {}).get("actual_grade") or ""
    ).upper()
    if actual not in GRADE_ORDER:
        raise ValueError("certificate has no valid preservation grade")
    passed = GRADE_ORDER[actual] >= GRADE_ORDER[required]
    receipt = {
        "required_grade": required,
        "actual_grade": actual,
        "passed": passed,
        "certificate_sha256": certificate.get("certificate_sha256"),
    }
    if not passed:
        divergence = certificate.get("divergence") or {}
        raise ValueError(
            "PRESERVATION_GRADE_NOT_MET:"
            f"{actual}<{required}:"
            + _stable(
                {
                    "unexpected_changed_parts": divergence.get(
                        "unexpected_changed_parts", []
                    ),
                    "unexpected_added_parts": divergence.get(
                        "unexpected_added_parts", []
                    ),
                    "unexpected_removed_parts": divergence.get(
                        "unexpected_removed_parts", []
                    ),
                    "missing_required_changed_parts": divergence.get(
                        "missing_required_changed_parts", []
                    ),
                }
            )
        )
    return receipt


def expected_scope_for_design_repair(
    path: Path | str,
    repair_plan: Mapping[str, Any],
) -> dict:
    path = Path(path)
    if not isinstance(repair_plan, Mapping):
        raise ValueError("repair_plan must be an object")
    actions = [
        item
        for item in (repair_plan.get("actions") or [])
        if isinstance(item, Mapping) and item.get("status") == "EXECUTABLE"
    ]
    if not actions:
        raise ValueError("repair plan contains no executable actions")

    document = build_document_map(path)
    paragraphs = {str(item.get("locator")): item for item in document["paragraphs"]}
    tables = build_table_map(path)
    table_index = {
        str(item.get("locator")): item for item in tables.get("tables", [])
    }

    expected: set[str] = {HEADER_PART}
    seen_target = False

    def add_table(locator: str) -> None:
        nonlocal seen_target
        table = table_index.get(str(locator))
        if table is None:
            raise ValueError(f"repair table locator unavailable: {locator}")
        expected.add(_canonical_part_name(str(table["section_path"])))
        seen_target = True

    def add_paragraph(locator: str) -> None:
        nonlocal seen_target
        paragraph = paragraphs.get(str(locator))
        if paragraph is None:
            raise ValueError(f"repair paragraph locator unavailable: {locator}")
        expected.add(_canonical_part_name(str(paragraph["section"])))
        seen_target = True

    for action in actions:
        operation = dict(action.get("operation") or {})
        name = str(operation.get("op") or "")
        if name in {
            "set_cell_margin",
            "set_cell_shading",
            "set_cell_borders",
            "set_cell_properties",
            "set_column_widths",
            "autofit_columns",
            "style_table_header",
            "set_table_padding",
            "rebalance_table_columns",
        }:
            add_table(str(operation.get("table") or ""))
        elif name == "style_semantic_callout":
            add_table(str(operation.get("table") or ""))
            for locator in operation.get("paragraph_targets") or []:
                add_paragraph(str(locator))
        elif name in {"align_nested_table_paragraphs", "style_section_headings"}:
            for locator in operation.get("targets") or []:
                add_paragraph(str(locator))
        else:
            raise ValueError(
                f"unsupported P3.42 expected-scope repair operation: {name}"
            )

    if not seen_target:
        raise ValueError("repair plan has no resolvable target parts")
    return {
        "changed_parts": sorted(expected),
        "added_parts": [],
        "removed_parts": [],
        "required_changed_parts": [],
        "require_untouched_record_metadata": False,
        "label": "P3.40_DESIGN_REPAIR_TARGET_PARTS",
    }


def apply_document_design_repairs_with_footprint_atomic(
    path: Path | str,
    repair_plan: dict,
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
    required_grade: str = "TARGETED_PARTS_ONLY",
) -> dict:
    path = Path(path)
    expected_scope = expected_scope_for_design_repair(path, repair_plan)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.stem + ".p342-footprint-",
        suffix=".hwpx",
        dir=str(path.parent),
    )
    os.close(fd)
    candidate = Path(temp_name)
    shutil.copy2(path, candidate)
    try:
        repair_receipt = apply_document_design_repairs_atomic(
            candidate,
            repair_plan,
            expected_revision=expected_revision,
            current_revision=current_revision,
            validator=validator,
        )
        certificate = build_mutation_footprint(
            path,
            candidate,
            expected_scope=expected_scope,
        )
        enforcement = enforce_preservation_grade(certificate, required_grade)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise
    result = {
        **repair_receipt,
        "schema": "chatgpt-web-hwpx-mcp/p3.42/design-repair-with-footprint-receipt/v1",
        "phase": "P3.42",
        "mutation_footprint": certificate,
        "preservation_enforcement": enforcement,
        "authority": (
            "EXECUTED_NATIVE_REPAIR_WITH_MEASURED_TARGETED_PART_FOOTPRINT"
            " / NOT_RENDERED_IMPROVEMENT_CLAIM"
        ),
    }
    result["p342_receipt_sha256"] = _sha(result)
    return result


__all__ = [
    "CONTRACT_SCHEMA",
    "EXPECTED_SCOPE_FIELDS",
    "GRADE_ORDER",
    "SCHEMA",
    "apply_document_design_repairs_with_footprint_atomic",
    "build_mutation_footprint",
    "classify_footprint_grade",
    "enforce_preservation_grade",
    "expected_scope_for_design_repair",
    "mutation_footprint_contract",
    "normalize_expected_scope",
]
