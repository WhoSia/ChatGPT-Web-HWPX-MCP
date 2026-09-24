from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from p24_inline import apply_inline_edits_atomic, build_inline_map
from p2_document import build_document_map


SCHEMA = "chatgpt-web-hwpx-mcp/p3.37/product-workflow/v1"
HWP5_CFBF_MAGIC = bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")
HWPX_REQUIRED = {
    "mimetype",
    "version.xml",
    "META-INF/container.xml",
    "Contents/content.hpf",
    "Contents/header.xml",
    "Contents/section0.xml",
}
MAX_FILL_KEYS = 50
MAX_FILL_OPERATIONS = 100


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _declared_format(filename: str) -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix == ".hwpx":
        return "HWPX"
    if suffix == ".hwp":
        return "HWP5"
    return "UNKNOWN"


def sniff_hangul_payload(payload: bytes, filename: str = "") -> dict:
    """Classify Hangul-family bytes from signatures/package structure, never the extension alone."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    raw = bytes(payload)
    declared = _declared_format(filename)
    actual = "UNKNOWN"
    evidence: dict[str, Any] = {
        "prefix_hex": raw[:16].hex(),
        "zip_entries": None,
        "mimetype": None,
    }

    if raw.startswith(HWP5_CFBF_MAGIC):
        actual = "HWP5"
        evidence["signature"] = "OLE_CFBF_D0CF11E0A1B11AE1"
    elif raw.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
                names = set(archive.namelist())
                evidence["zip_entries"] = len(names)
                if "mimetype" in names:
                    info = archive.getinfo("mimetype")
                    if info.file_size <= 512:
                        evidence["mimetype"] = archive.read("mimetype").decode(
                            "utf-8", errors="replace"
                        ).strip()
                if HWPX_REQUIRED.issubset(names) or evidence["mimetype"] == "application/hwp+zip":
                    actual = "HWPX"
                    evidence["signature"] = "ZIP_WITH_HWPX_PACKAGE_EVIDENCE"
                else:
                    actual = "ZIP_OTHER"
                    evidence["signature"] = "ZIP_WITHOUT_HWPX_PACKAGE_EVIDENCE"
        except zipfile.BadZipFile:
            actual = "INVALID_ZIP"
            evidence["signature"] = "PK_PREFIX_BUT_INVALID_ZIP"
    else:
        evidence["signature"] = "NO_HWPX_OR_HWP5_SIGNATURE"

    extension_match = None
    if declared != "UNKNOWN" and actual in {"HWPX", "HWP5"}:
        extension_match = declared == actual

    routes = {
        "HWPX": "HWPX_NATIVE_EDIT_AND_DELIVERY",
        "HWP5": "HWP5_READ_OR_DERIVATIVE_BRIDGE",
        "ZIP_OTHER": "REJECT_NON_HWPX_ZIP",
        "INVALID_ZIP": "REJECT_INVALID_ZIP",
        "UNKNOWN": "REJECT_UNKNOWN_FORMAT",
    }
    return {
        "schema": SCHEMA,
        "filename": Path(str(filename or "document")).name[:160],
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "declared_format": declared,
        "actual_format": actual,
        "extension_match": extension_match,
        "format_mismatch": bool(extension_match is False),
        "evidence": evidence,
        "recommended_route": routes[actual],
        "authority": "BYTE_SIGNATURE_AND_PACKAGE_STRUCTURE_NOT_FILENAME_EXTENSION",
    }


def product_workflow_contract() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "P3.37",
        "product_goal": "REQUEST_TO_VALIDATED_NATIVE_HWPX_RESOURCE_IN_ONE_PRIMARY_CALL",
        "primary_tools": [
            "create_and_deliver_document",
            "edit_and_deliver_document",
            "fill_template_and_deliver",
            "ingest_hangul_document",
        ],
        "compatibility_tools": [
            "generate_document",
            "edit_document_and_deliver",
            "deliver_document",
        ],
        "intake": {
            "classification": "bytes first; extension is provenance only",
            "formats": ["HWPX", "HWP5", "ZIP_OTHER", "INVALID_ZIP", "UNKNOWN"],
            "hwp5_default": "read-only inspection; derivative creation requires explicit TEXT or RICH mode",
            "source_mutation": "never mutate HWP5 bytes",
        },
        "template_fill": {
            "p337_lane": "literal placeholders across editable inline text, atomic clone-before-commit",
            "strictness": "missing placeholders fail by default; optional uniqueness gate",
            "operation_cap": MAX_FILL_OPERATIONS,
            "future_harvest": (
                "mixed nativeField/labelCell/canonicalPath/bodyAnchor analysis may be adapted "
                "from python-hwpx-automation after dependency-boundary review"
            ),
        },
        "delivery": {
            "native_type": ".hwpx",
            "resource_link": True,
            "signed_revision_bound_download": True,
            "validation_before_handoff": True,
            "recovery": (
                "renew delivery only after a committed mutation; never replay the mutation "
                "merely to refresh a link"
            ),
        },
        "upstream_harvest": [
            {
                "repo": "airmang/python-hwpx",
                "head": "189a8b2f622d29ec93230fbd70203946d89a4f19",
                "license": "Apache-2.0",
                "decision": (
                    "KEEP_AS_CORE_DEPENDENCY; prefer stable public primitives over local XML "
                    "reinvention where parity is demonstrated"
                ),
            },
            {
                "repo": "airmang/python-hwpx-automation",
                "head": "8e8b95a8adff5d6a86e853a119a081c3c410512a",
                "license": "Apache-2.0",
                "decision": (
                    "HARVEST_WORKFLOW_DESIGN_NOW; defer direct dependency until overlapping "
                    "custody/OAuth semantics are reconciled"
                ),
            },
            {
                "repo": "treesoop/hwp-mcp",
                "head": "4a93489d4f7dd316279b5f6f5d83014d9a8063f4",
                "license": "MIT",
                "decision": (
                    "REFERENCE_RHWP_HWP5_READ_RENDER_AS_ALTERNATE_ORACLE; do not replace "
                    "the existing bounded HWP5 reader without measured gain"
                ),
            },
            {
                "repo": "deoksangcho/hwpx-mcp-server",
                "head": "92cd24f5c18fbcc1a4a20cc3447e761d2bf8c1c5",
                "license": "MIT",
                "decision": "HARVEST_SMALL_PUBLIC_SURFACE_AND_STATELESS_TOOL_SHAPE",
            },
            {
                "repo": "Topabaem05/hwpx-mcp",
                "head": "5993e014dd5bec68770379f2532ed0c1502a9952",
                "license": "UNVERIFIED_IN_P3.37_RECEIPT",
                "decision": (
                    "HARVEST_GATEWAY_PATTERN_FOR_FUTURE_TOOL_SEARCH_DESCRIBE_CALL_ROUTING; "
                    "no code copied"
                ),
            },
        ],
        "license_policy": (
            "No wholesale copying. Dependency/adapter/interface reuse must retain upstream "
            "license and NOTICE obligations."
        ),
    }


def _validate_fill_values(values: dict[str, str]) -> dict[str, str]:
    if not isinstance(values, dict) or not values:
        raise ValueError("template fill values must be a non-empty object")
    if len(values) > MAX_FILL_KEYS:
        raise ValueError(f"template fill exceeds {MAX_FILL_KEYS} keys")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        key = str(raw_key)
        value = str(raw_value)
        if not key or len(key) > 256:
            raise ValueError("placeholder keys must be 1..256 characters")
        if len(value) > 10000:
            raise ValueError("replacement values exceed 10000 characters")
        if key in normalized:
            raise ValueError("duplicate placeholder key")
        normalized[key] = value
    return normalized


def plan_literal_placeholder_fill(
    path: Path | str,
    values: dict[str, str],
    *,
    require_each: bool = True,
    require_unique: bool = False,
) -> dict:
    """Plan exact literal placeholder replacements over the current inline-text coordinate map."""
    path = Path(path)
    normalized_values = _validate_fill_values(values)
    inline = build_inline_map(path)
    operations: list[dict] = []
    matches: dict[str, int] = {}

    for placeholder, replacement in normalized_values.items():
        count = 0
        for paragraph in inline.get("paragraphs", []):
            text = str(paragraph.get("inline_text") or "")
            start = 0
            while True:
                index = text.find(placeholder, start)
                if index < 0:
                    break
                operations.append({
                    "op": "replace_inline_text",
                    "target": paragraph["locator"],
                    "start": index,
                    "end": index + len(placeholder),
                    "text": replacement,
                    "expected_text": placeholder,
                })
                count += 1
                start = index + len(placeholder)
        matches[placeholder] = count

    missing = [key for key, count in matches.items() if count == 0]
    ambiguous = [key for key, count in matches.items() if count != 1]
    if require_each and missing:
        raise ValueError("template placeholders not found: " + ", ".join(missing[:10]))
    if require_unique and ambiguous:
        raise ValueError("template placeholders are not unique: " + ", ".join(ambiguous[:10]))
    if not operations:
        raise ValueError("template fill produced no editable matches")
    if len(operations) > MAX_FILL_OPERATIONS:
        raise ValueError(f"template fill exceeds {MAX_FILL_OPERATIONS} operations")

    by_target: dict[str, list[tuple[int, int, str]]] = {}
    for op in operations:
        by_target.setdefault(str(op["target"]), []).append(
            (int(op["start"]), int(op["end"]), str(op["expected_text"]))
        )
    for ranges in by_target.values():
        ranges.sort()
        for left, right in zip(ranges, ranges[1:]):
            if right[0] < left[1]:
                raise ValueError(
                    f"overlapping placeholders are not admitted: {left[2]!r} / {right[2]!r}"
                )

    payload = {
        "values": normalized_values,
        "matches": matches,
        "operations": operations,
        "inline_structure_sha256_before": inline["inline_structure_sha256"],
    }
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.37/template-fill-plan/v1",
        "plan_sha256": _sha(payload),
        "operation_count": len(operations),
        "placeholder_count": len(normalized_values),
        "matches": matches,
        "operations": operations,
        "inline_structure_sha256_before": inline["inline_structure_sha256"],
        "authority": "EXACT_LITERAL_PLACEHOLDER_MATCHES_ONLY",
    }


def fill_template_atomic(
    template_path: Path | str,
    destination: Path | str,
    values: dict[str, str],
    *,
    require_each: bool = True,
    require_unique: bool = False,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    """Clone one HWPX template, fill exact placeholders atomically, and commit destination only on success."""
    template_path = Path(template_path)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=destination.stem + ".p337-fill-",
        suffix=".hwpx",
        dir=str(destination.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    try:
        shutil.copy2(template_path, candidate)
        plan = plan_literal_placeholder_fill(
            candidate,
            values,
            require_each=require_each,
            require_unique=require_unique,
        )
        transaction = apply_inline_edits_atomic(
            candidate,
            plan["operations"],
            expected_revision=1,
            current_revision=1,
            validator=validator,
        )
        after_inline = build_inline_map(candidate)
        after_document = build_document_map(candidate)
        receipt = {
            "schema": "chatgpt-web-hwpx-mcp/p3.37/template-fill-receipt/v1",
            "plan_sha256": plan["plan_sha256"],
            "operation_count": plan["operation_count"],
            "placeholder_count": plan["placeholder_count"],
            "matches": plan["matches"],
            "inline_structure_sha256_before": plan["inline_structure_sha256_before"],
            "inline_structure_sha256_after": after_inline["inline_structure_sha256"],
            "semantic_sha256_after": after_document["semantic_sha256"],
            "structure_sha256_after": after_document["structure_sha256"],
            "validation": transaction.get("validation"),
            "atomic_commit": True,
            "source_template_mutated": False,
            "authority": "LITERAL_PLACEHOLDER_FILL_WITH_INLINE_STRUCTURE_PRESERVATION_GATE",
        }
        receipt["fill_sha256"] = _sha(receipt)
        os.replace(candidate, destination)
        return receipt
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
