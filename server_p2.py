from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

import server as core
from hwpx import HwpxDocument
from p2_document import apply_edits_atomic, build_document_map
from p22_formatting import build_formatting_map
from p23_richtext import apply_rich_formatting_atomic
from p24_inline import apply_inline_edits_atomic, build_inline_map
from p26_controls import apply_control_edits_atomic
from p28_tables import apply_table_edits_atomic, build_table_map
from p29_objects import apply_object_edits_atomic, build_object_map
from p210_equations import (
    apply_equation_edits_atomic,
    build_equation_map,
    _resolve_paragraph as _resolve_hwpx_paragraph,
)
from hwp5_reader import (
    Hwp5ReadError,
    extract_hwp5_binary_assets,
    parse_hwp5_bytes,
    prepare_hwp5_image_for_hwpx,
)
from common_ir import (
    hwp5_to_common_ir,
    hwpx_to_common_ir,
    extract_common_ir,
    search_common_ir,
    slice_common_ir,
)

P2_VERSION = "0.6.0-p3.6"
core.VERSION = P2_VERSION

_original_metadata = core._metadata


def _p2_metadata(*args, **kwargs) -> dict:
    metadata = _original_metadata(*args, **kwargs)
    metadata.setdefault("revision", 1)
    return metadata


# Existing P1.2 create/ingest tools resolve this global at call time, so new
# documents start with revision=1 without duplicating the tool definitions.
core._metadata = _p2_metadata


def _owned_document(document_id: str) -> tuple[dict, Path]:
    metadata = core._load_metadata(document_id)
    core._require_owner(metadata)
    path, _ = core._paths(document_id)
    if "revision" not in metadata:
        metadata["revision"] = 1
        core._write_metadata(document_id, metadata)
    return metadata, path


def _refresh_metadata(
    document_id: str,
    metadata: dict,
    validation: dict,
    document_map: dict,
    formatting_map: dict | None = None,
    inline_map: dict | None = None,
    table_map: dict | None = None,
    object_map: dict | None = None,
    equation_map: dict | None = None,
) -> dict:
    metadata["sha256"] = validation["sha256"]
    metadata["bytes"] = validation["bytes"]
    metadata["semantic_sha256"] = document_map["semantic_sha256"]
    metadata["structure_sha256"] = document_map["structure_sha256"]
    if formatting_map is not None:
        metadata["formatting_sha256"] = formatting_map["formatting_sha256"]
    if inline_map is not None:
        metadata["inline_text_sha256"] = inline_map["inline_text_sha256"]
        metadata["inline_structure_sha256"] = inline_map["inline_structure_sha256"]
    if table_map is not None:
        metadata["table_structure_sha256"] = table_map["table_structure_sha256"]
        metadata["table_format_sha256"] = table_map["table_format_sha256"]
        if "table_object_sha256" in table_map:
            metadata["table_object_sha256"] = table_map["table_object_sha256"]
    if object_map is not None:
        metadata["object_structure_sha256"] = object_map["object_structure_sha256"]
        metadata["object_geometry_sha256"] = object_map["object_geometry_sha256"]
        metadata["media_custody_sha256"] = object_map["media_custody_sha256"]
    if equation_map is not None:
        metadata["equation_structure_sha256"] = equation_map["equation_structure_sha256"]
        metadata["equation_geometry_sha256"] = equation_map["equation_geometry_sha256"]
        metadata["equation_script_custody_sha256"] = equation_map["equation_script_custody_sha256"]
    core._write_metadata(document_id, metadata)
    return metadata


@core.mcp.tool()
def acquire_document_lease(
    document_id: str,
    expected_revision: int,
    ttl_seconds: int = 30,
    holder_id: str = "mcp-client",
) -> dict:
    """Acquire a short durable coordination lease for one revision."""
    metadata, _path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    if int(expected_revision) != current_revision:
        raise ValueError(
            f"Stale revision: expected {expected_revision}, current {current_revision}"
        )
    token = secrets.token_urlsafe(32)
    receipt = core.DOCUMENT_STORE.acquire_lease(
        document_id,
        holder_id=holder_id,
        expected_revision=current_revision,
        lease_token=token,
        ttl_seconds=ttl_seconds,
    )
    return {
        "ok": True,
        **receipt,
        "lease_token": token,
        "lease_semantics": "coordination layer; CAS remains final authority",
    }


@core.mcp.tool()
def release_document_lease(document_id: str, lease_token: str) -> dict:
    """Release a durable document lease held by its opaque token."""
    metadata, _path = _owned_document(document_id)
    released = core.DOCUMENT_STORE.release_lease(
        document_id,
        lease_token=lease_token,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "released": released,
    }


@core.mcp.tool()
def get_document_commit_receipt(document_id: str, revision: int = 0) -> dict:
    """Return the deterministic durable commit receipt for one revision."""
    metadata, _path = _owned_document(document_id)
    target_revision = int(revision) or int(metadata["revision"])
    receipt = core.DOCUMENT_STORE.get_commit_receipt(document_id, target_revision)
    if receipt is None:
        raise FileNotFoundError("Commit receipt not found")
    return {"ok": True, **receipt}


@core.mcp.tool()
def get_document_versions(document_id: str) -> dict:
    """Return durable revision history for one owned document."""
    metadata, _path = _owned_document(document_id)
    versions = core.DOCUMENT_STORE.list_revisions(document_id)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "storage": core.DOCUMENT_STORE.mode,
        "versions": versions,
        "version_count": len(versions),
    }


@core.mcp.tool()
def restore_document_revision(
    document_id: str,
    revision: int,
    expected_revision: int,
    lease_token: str = "",
) -> dict:
    """Promote one durable historical snapshot as a new monotonic revision."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    if int(expected_revision) != current_revision:
        raise ValueError(
            f"Stale revision: expected {expected_revision}, current {current_revision}"
        )
    source_revision = int(revision)
    if source_revision < 1 or source_revision > current_revision:
        raise ValueError("Recovery source revision is outside durable history")
    historical = core.DOCUMENT_STORE.load_revision(document_id, source_revision)
    if historical is None:
        raise FileNotFoundError("Durable revision not found")
    if historical["owner_subject"] != metadata.get("owner_subject"):
        raise PermissionError("Durable revision owner mismatch")

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p30-restore-",
        suffix=".hwpx",
        dir=str(path.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(historical["bytes"])
    try:
        validation = core.validate_hwpx_package(
            candidate,
            ingress=metadata.get("source") == "existing-ingress",
        )
        new_revision = current_revision + 1
        restored = dict(metadata)
        restored["revision"] = new_revision
        restored["sha256"] = validation["sha256"]
        restored["bytes"] = validation["bytes"]
        restored["recovered_from_revision"] = source_revision
        restored["recovered_at"] = core._utc_iso()
        if lease_token:
            restored["_commit_lease_token"] = lease_token
        os.replace(candidate, path)
        core._write_metadata(document_id, restored)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": new_revision,
        "recovered_from_revision": source_revision,
        "sha256": validation["sha256"],
        "bytes": validation["bytes"],
        "storage": core.DOCUMENT_STORE.mode,
        "transaction": "RECOVERED_AS_NEW_REVISION",
    }


@core.mcp.tool()
def set_document_retention(document_id: str, retention_seconds: int) -> dict:
    """Extend or shorten durable retention under a revision CAS guard."""
    metadata, _path = _owned_document(document_id)
    revision = int(metadata["revision"])
    seconds = max(3600, min(int(retention_seconds), 2_592_000))
    expires = time.time() + seconds
    core.DOCUMENT_STORE.update_retention(
        document_id,
        expected_revision=revision,
        expires_at_epoch=expires,
    )
    metadata["expires_at_epoch"] = expires
    metadata["expires_at"] = core._utc_iso(expires)
    metadata["retention_seconds"] = seconds
    _hwpx_path, metadata_path = core._paths(document_id)
    metadata_path.write_text(
        __import__("json").dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": revision,
        "retention_seconds": seconds,
        "expires_at": metadata["expires_at"],
        "storage": core.DOCUMENT_STORE.mode,
    }


@core.mcp.tool()
def pin_document_revision(
    document_id: str,
    revision: int,
    reason: str = "restore-anchor",
) -> dict:
    """Protect one retained historical revision from compaction."""
    metadata, _path = _owned_document(document_id)
    receipt = core.DOCUMENT_STORE.pin_revision(
        document_id,
        int(revision),
        reason=reason,
    )
    return {
        "ok": True,
        **receipt,
        "current_revision": int(metadata["revision"]),
        "semantics": "pinned revision remains restore-reachable and DB-protected from byte-snapshot GC",
    }


@core.mcp.tool()
def unpin_document_revision(document_id: str, revision: int) -> dict:
    """Remove a historical restore-anchor pin; current revision remains protected independently."""
    metadata, _path = _owned_document(document_id)
    released = core.DOCUMENT_STORE.unpin_revision(document_id, int(revision))
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(revision),
        "current_revision": int(metadata["revision"]),
        "unpinned": released,
    }


@core.mcp.tool()
def compact_document_history(
    document_id: str,
    expected_revision: int,
    keep_last: int = 3,
    dry_run: bool = True,
) -> dict:
    """Prune unpinned historical byte snapshots without deleting the commit audit ledger."""
    metadata, _path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    if int(expected_revision) != current_revision:
        raise ValueError(
            f"Stale revision: expected {expected_revision}, current {current_revision}"
        )
    receipt = core.DOCUMENT_STORE.compact_revisions(
        document_id,
        expected_revision=current_revision,
        keep_last=keep_last,
        dry_run=dry_run,
    )
    lineage = core.DOCUMENT_STORE.verify_audit_chain(document_id)
    if not lineage["audit_chain_valid"] or not lineage["restore_reachability_valid"]:
        raise RuntimeError("Post-compaction lineage verification failed")
    return {
        "ok": True,
        **receipt,
        "audit_head": lineage["audit_head"],
        "audit_chain_valid": lineage["audit_chain_valid"],
        "restore_reachability_valid": lineage["restore_reachability_valid"],
    }


@core.mcp.tool()
def verify_document_lineage(document_id: str) -> dict:
    """Verify commit hash-chain integrity and restore reachability of current/pinned snapshots."""
    metadata, _path = _owned_document(document_id)
    report = core.DOCUMENT_STORE.verify_audit_chain(document_id)
    return {
        "ok": bool(report["audit_chain_valid"] and report["restore_reachability_valid"]),
        **report,
        "metadata_revision": int(metadata["revision"]),
        "audit_semantics": "commit ledger is append-only authority; byte-snapshot compaction does not erase commit receipts",
    }


@core.mcp.tool()
def get_document_map(document_id: str) -> dict:
    """Return revision-bound structural addresses for sections and paragraphs."""
    metadata, path = _owned_document(document_id)
    document_map = build_document_map(path)
    formatting_map = build_formatting_map(path)
    inline_map = build_inline_map(path)
    validation = core.validate_hwpx_package(
        path,
        ingress=metadata.get("source") == "existing-ingress",
    )
    _refresh_metadata(
        document_id, metadata, validation, document_map, formatting_map, inline_map
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "semantic_sha256": document_map["semantic_sha256"],
        "structure_sha256": document_map["structure_sha256"],
        "formatting_sha256": formatting_map["formatting_sha256"],
        "inline_text_sha256": inline_map["inline_text_sha256"],
        "inline_structure_sha256": inline_map["inline_structure_sha256"],
        "sections": document_map["sections"],
        "paragraphs": document_map["paragraphs"],
        "address_contract": {
            "intrinsic-id": "stable across text edits and same-section moves while the paragraph intrinsic id survives",
            "revision-bound-ordinal": "valid only for the current structural revision; reacquire after structural edits",
        },
    }


@core.mcp.tool()
def inspect_hwp5_document(
    content_base64: str,
    filename: str = "document.hwp",
    include_text: bool = True,
    include_paragraphs: bool = True,
    max_text_chars: int = 100000,
) -> dict:
    """Read one bounded legacy HWP 5.x payload without converting or editing the original file."""
    encoded_limit = ((core.MAX_INGEST_BYTES + 2) // 3) * 4 + 16
    if len(content_base64) > encoded_limit:
        raise ValueError("Encoded HWP exceeds the bounded ingress limit")
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if len(payload) > core.MAX_INGEST_BYTES:
        raise ValueError(f"HWP ingress exceeds {core.MAX_INGEST_BYTES} bytes")

    result = parse_hwp5_bytes(
        payload,
        max_text_chars=max(1000, min(int(max_text_chars), 500000)),
    )
    safe_name = Path(filename or "document.hwp").name[:128]
    response = {
        "ok": True,
        "filename": safe_name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "format": result["format"],
        "version": result["version"],
        "flags": result["flags"],
        "readable": result["readable"],
        "block_reason": result["block_reason"],
        "section_count": result.get("section_count", 0),
        "paragraph_count": result.get("paragraph_count", 0),
        "text_chars": result.get("text_chars", 0),
        "table_count": len(result.get("tables", [])),
        "equation_count": len(result.get("equations", [])),
        "object_count": len(result.get("objects", [])),
        "binary_item_count": len(result.get("binary_items", [])),
        "fidelity": result.get("fidelity", {}),
        "tables": result.get("tables", []),
        "equations": result.get("equations", []),
        "objects": result.get("objects", []),
        "binary_items": result.get("binary_items", []),
        "preview_text": result.get("preview_text", ""),
        "preview_text_truncated": result.get("preview_text_truncated", False),
        "warnings": result.get("warnings", []),
        "authority": result.get("authority", "READ_ONLY_LOSS_AWARE"),
        "edit_authority": "NONE_FOR_HWP_BINARY",
        "recommended_successor": "materialize a provenance-marked HWPX derivative before using HWPX edit tools",
    }
    if include_text:
        response["text"] = result.get("text", "")
    if include_paragraphs:
        response["paragraphs"] = result.get("paragraphs", [])
    return response


@core.mcp.tool()
def materialize_hwp5_text_derivative(
    content_base64: str,
    filename: str = "document.hwp",
    title: str = "",
    request_id: str = "",
    max_text_chars: int = 500000,
) -> dict:
    """Create an editable HWPX text derivative from one readable HWP 5.x source without mutating the source."""
    owner_subject = core._caller_subject()
    encoded_limit = ((core.MAX_INGEST_BYTES + 2) // 3) * 4 + 16
    if len(content_base64) > encoded_limit:
        raise ValueError("Encoded HWP exceeds the bounded ingress limit")
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if len(payload) > core.MAX_INGEST_BYTES:
        raise ValueError(f"HWP ingress exceeds {core.MAX_INGEST_BYTES} bytes")

    parsed = parse_hwp5_bytes(
        payload,
        max_text_chars=max(1000, min(int(max_text_chars), 500000)),
    )
    if not parsed.get("readable"):
        raise ValueError(
            f"HWP source is not readable by the native lane: {parsed.get('block_reason')}"
        )
    text = parsed.get("text", "")
    if not text.strip():
        raise ValueError("HWP source yielded no readable body text")

    source_sha256 = hashlib.sha256(payload).hexdigest()
    source_name = Path(filename or "document.hwp").name[:128]
    normalized_request_id = str(request_id or "").strip()
    derivative_request = (
        f"hwp5-derivative:{source_sha256}:{normalized_request_id}"
        if normalized_request_id
        else ""
    )
    document_id = (
        core._idempotent_document_id(owner_subject, derivative_request)
        if derivative_request
        else core._new_document_id()
    )
    if derivative_request:
        try:
            existing = core._load_metadata(document_id)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            core._require_owner(existing)
            if existing.get("source_hwp_sha256") != source_sha256:
                raise RuntimeError("Derivative request id conflicts with a different HWP source")
            return {
                "ok": True,
                **existing,
                "idempotent_replay": True,
                "source_hwp_sha256": source_sha256,
                "fidelity": existing.get("hwp_derivative_fidelity", "text-only"),
            }

    hwpx_path, _ = core._paths(document_id)
    derivative_title = title or Path(source_name).stem
    validation = core.materialize_hwpx(hwpx_path, text, derivative_title)
    metadata = core._metadata(
        document_id,
        filename=core.sanitize_filename(Path(source_name).stem + ".hwpx"),
        owner_subject=owner_subject,
        validation=validation,
        title=derivative_title,
        source="hwp5-text-derivative",
    )
    metadata.update({
        "source_hwp_filename": source_name,
        "source_hwp_sha256": source_sha256,
        "source_hwp_version": parsed.get("version"),
        "source_hwp_flags": parsed.get("flags", {}),
        "source_hwp_paragraph_count": parsed.get("paragraph_count", 0),
        "source_hwp_table_count": len(parsed.get("tables", [])),
        "source_hwp_equation_count": len(parsed.get("equations", [])),
        "source_hwp_object_count": len(parsed.get("objects", [])),
        "source_hwp_binary_item_count": len(parsed.get("binary_items", [])),
        "hwp_derivative_fidelity": "text-semantic / object-families-provenance-only",
        "hwp_fidelity_grades": parsed.get("fidelity", {}),
        "hwp_derivative_warnings": parsed.get("warnings", []),
        "hwp_original_mutated": False,
    })
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        **metadata,
        "validation": validation,
        "idempotent_replay": False,
        "source_hwp_sha256": source_sha256,
        "fidelity": {
            "derivative_text": "editable-native",
            "source_families": parsed.get("fidelity", {}),
            "tables_promoted": False,
            "equations_promoted": False,
            "pictures_promoted": False,
        },
        "promotion_report": {
            "paragraph_text": "PROMOTED",
            "tables": "PROVENANCE_ONLY",
            "equations": "PROVENANCE_ONLY",
            "pictures": "PROVENANCE_ONLY",
            "reason": "P3.5 does not synthesize richer HWPX objects until position/cell/media linkage is independently verified.",
        },
        "authority": "EDITABLE_HWPX_DERIVATIVE / ORIGINAL_HWP_READ_ONLY",
        "next": "Use HWPX navigation/edit/export tools on this derivative document_id.",
    }


def _hwp_rel_to_horizontal(value: object) -> str:
    return {0: "PAGE", 1: "PAGE", 2: "COLUMN", 3: "PARA"}.get(int(value or 0), "COLUMN")


def _hwp_rel_to_vertical(value: object) -> str:
    return {0: "PAPER", 1: "PAGE", 2: "PARA"}.get(int(value or 0), "PARA")


@core.mcp.tool()
def get_hwp5_control_graph(
    content_base64: str,
    filename: str = "document.hwp",
) -> dict:
    """Return the reconstructed HWP5 control/cell/object graph without mutating the source."""
    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    if not parsed.get("readable"):
        return {
            "ok": True,
            "filename": Path(filename or "document.hwp").name[:128],
            "sha256": hashlib.sha256(payload).hexdigest(),
            "readable": False,
            "block_reason": parsed.get("block_reason"),
            "controls": [],
            "edges": [],
        }
    pictures = [
        item for item in parsed.get("objects", [])
        if item.get("kind") == "picture"
    ]
    return {
        "ok": True,
        "filename": Path(filename or "document.hwp").name[:128],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "readable": True,
        "controls": parsed.get("controls", []),
        "edges": parsed.get("control_edges", []),
        "tables": parsed.get("tables", []),
        "equations": parsed.get("equations", []),
        "pictures": pictures,
        "receipts": {
            "table_cell_binding_closed": bool(parsed.get("tables")) and all(
                bool(item.get("cells")) for item in parsed.get("tables", [])
            ),
            "equation_anchor_binding_closed": bool(parsed.get("equations")) and all(
                item.get("anchor_paragraph_ordinal") is not None
                and item.get("position_fidelity") == "structural"
                for item in parsed.get("equations", [])
            ),
            "picture_bindata_binding_closed": bool(pictures) and all(
                item.get("binary_link") is not None for item in pictures
            ),
        },
        "authority": "READ_ONLY_CONTROL_GRAPH",
    }


@core.mcp.tool()
def materialize_hwp5_rich_derivative(
    content_base64: str,
    filename: str = "document.hwp",
    title: str = "",
    request_id: str = "",
    promote_tables: bool = True,
    promote_equations: bool = True,
    promote_pictures: bool = True,
) -> dict:
    """Create an HWPX derivative and promote only HWP object families whose bindings are independently closed."""
    owner_subject = core._caller_subject()
    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    if not parsed.get("readable"):
        raise ValueError(
            f"HWP source is not readable by the native lane: {parsed.get('block_reason')}"
        )

    source_sha256 = hashlib.sha256(payload).hexdigest()
    source_name = Path(filename or "document.hwp").name[:128]
    normalized_request_id = str(request_id or "").strip()
    if normalized_request_id and len(normalized_request_id) > 160:
        raise ValueError("request_id exceeds 160 characters")
    derivative_request = (
        f"hwp5-rich-v1:{source_sha256}:{normalized_request_id}"
        if normalized_request_id else ""
    )
    document_id = (
        core._idempotent_document_id(owner_subject, derivative_request)
        if derivative_request else core._new_document_id()
    )
    if derivative_request:
        try:
            existing = core._load_metadata(document_id)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            core._require_owner(existing)
            if existing.get("source_hwp_sha256") != source_sha256:
                raise RuntimeError("Derivative request id conflicts with a different HWP source")
            return {
                "ok": True,
                **existing,
                "idempotent_replay": True,
                "promotion_report": existing.get("hwp_rich_promotion_report", {}),
            }

    # Cell-owned paragraphs are materialized inside promoted tables rather than
    # duplicated into the top-level text stream.
    top_level = [
        item for item in parsed.get("paragraphs", [])
        if item.get("list_header_record_index") is None
    ]
    if not top_level:
        top_level = list(parsed.get("paragraphs", []))
    base_text = "\n".join(str(item.get("text", "")) for item in top_level)
    if not base_text:
        base_text = " "

    hwpx_path, _ = core._paths(document_id)
    derivative_title = title or Path(source_name).stem
    core.materialize_hwpx(hwpx_path, base_text, derivative_title)

    promotion_report = {
        "paragraph_text": {"status": "PROMOTED", "count": len(top_level)},
        "tables": {"promoted": 0, "deferred": []},
        "equations": {"promoted": 0, "deferred": []},
        "pictures": {"promoted": 0, "deferred": []},
    }

    document = HwpxDocument.open(str(hwpx_path))
    try:
        mapped = build_document_map(hwpx_path)
        target_paragraphs = mapped.get("paragraphs", [])
        anchor_map: dict[tuple[int, int], str] = {}
        for source_para, target_para in zip(top_level, target_paragraphs):
            ordinal = source_para.get("source_paragraph_ordinal")
            if ordinal is None:
                continue
            anchor_map[
                (int(source_para.get("section_index", 0)), int(ordinal))
            ] = target_para["locator"]

        controls = {
            int(item["control_index"]): item
            for item in parsed.get("controls", [])
            if item.get("control_index") is not None
        }

        if promote_tables:
            for table_index, source_table in enumerate(parsed.get("tables", [])):
                cells = source_table.get("cells", [])
                anchor_key = (
                    int(source_table.get("section_index", 0)),
                    int(source_table.get("anchor_paragraph_ordinal", -1)),
                )
                anchor_locator = anchor_map.get(anchor_key)
                rows = int(source_table.get("row_count", 0) or 0)
                cols = int(source_table.get("col_count", 0) or 0)
                if not anchor_locator or not cells or rows <= 0 or cols <= 0:
                    promotion_report["tables"]["deferred"].append({
                        "table_index": table_index,
                        "reason": "anchor_or_cell_binding_incomplete",
                    })
                    continue
                created_table = None
                try:
                    normalized_cells: list[dict] = []
                    anchors_seen: set[tuple[int, int]] = set()
                    for cell in sorted(
                        cells,
                        key=lambda item: (int(item["row"]), int(item["column"])),
                    ):
                        row = int(cell["row"])
                        col = int(cell["column"])
                        row_span = max(1, int(cell.get("row_span", 1) or 1))
                        col_span = max(1, int(cell.get("col_span", 1) or 1))
                        if row < 0 or col < 0 or row >= rows or col >= cols:
                            raise ValueError("source cell address exceeds table geometry")
                        if row + row_span > rows or col + col_span > cols:
                            raise ValueError("source cell span exceeds table geometry")
                        if (row, col) in anchors_seen:
                            raise ValueError("duplicate source cell anchor")
                        anchors_seen.add((row, col))
                        normalized_cells.append({
                            "row": row,
                            "col": col,
                            "row_span": row_span,
                            "col_span": col_span,
                            "text": "\n".join(
                                str(value) for value in cell.get("paragraph_text", [])
                            ),
                        })

                    # HWP may retain physical cell records that are covered by a
                    # spanning anchor. Treat them as subordinate storage, not as
                    # independent logical cells. Any visible subordinate text is
                    # an ambiguity and therefore blocks promotion.
                    coverage_owner: dict[tuple[int, int], tuple[int, int]] = {}
                    for cell in normalized_cells:
                        if cell["row_span"] == 1 and cell["col_span"] == 1:
                            continue
                        anchor = (cell["row"], cell["col"])
                        for r in range(cell["row"], cell["row"] + cell["row_span"]):
                            for col in range(cell["col"], cell["col"] + cell["col_span"]):
                                coord = (r, col)
                                if coord == anchor:
                                    continue
                                previous = coverage_owner.get(coord)
                                if previous is not None and previous != anchor:
                                    raise ValueError("overlapping merged-cell anchors")
                                coverage_owner[coord] = anchor

                    material_cells: list[dict] = []
                    for cell in normalized_cells:
                        coord = (cell["row"], cell["col"])
                        if coord in coverage_owner:
                            if cell["text"].strip():
                                raise ValueError(
                                    "covered subordinate cell contains visible text"
                                )
                            continue
                        material_cells.append(cell)

                    paragraph, _target = _resolve_hwpx_paragraph(
                        document, hwpx_path, anchor_locator
                    )
                    control = controls.get(int(source_table.get("control_index", -1)))
                    width = None if not control else int(control.get("width") or 0)
                    height = None if not control else int(control.get("height") or 0)
                    created_table = paragraph.add_table(
                        rows,
                        cols,
                        width=width if width and width > 0 else None,
                        height=height if height and height > 0 else None,
                    )

                    for cell in material_cells:
                        created_table.set_cell_text(
                            cell["row"],
                            cell["col"],
                            cell["text"],
                            logical=False,
                        )

                    for cell in material_cells:
                        if cell["row_span"] == 1 and cell["col_span"] == 1:
                            continue
                        created_table.merge_cells(
                            cell["row"],
                            cell["col"],
                            cell["row"] + cell["row_span"] - 1,
                            cell["col"] + cell["col_span"] - 1,
                        )
                    promotion_report["tables"]["promoted"] += 1
                except Exception as exc:
                    if created_table is not None:
                        try:
                            element = created_table.element
                            parent = element.getparent()
                            if parent is not None:
                                parent.remove(element)
                                paragraph.section.mark_dirty()
                        except Exception:
                            pass
                    promotion_report["tables"]["deferred"].append({
                        "table_index": table_index,
                        "reason": f"promotion_refused:{type(exc).__name__}",
                        "detail": str(exc)[:240],
                    })

        if promote_equations:
            for equation_index, equation in enumerate(parsed.get("equations", [])):
                anchor_ordinal = equation.get("anchor_paragraph_ordinal")
                anchor_key = (
                    int(equation.get("section_index", 0)),
                    int(anchor_ordinal if anchor_ordinal is not None else -1),
                )
                anchor_locator = anchor_map.get(anchor_key)
                script = str(equation.get("script", ""))
                if (
                    not anchor_locator
                    or not script
                    or equation.get("position_fidelity") != "structural"
                ):
                    promotion_report["equations"]["deferred"].append({
                        "equation_index": equation_index,
                        "reason": "anchor_position_or_script_incomplete",
                    })
                    continue
                try:
                    paragraph, _target = _resolve_hwpx_paragraph(
                        document, hwpx_path, anchor_locator
                    )
                    position = equation.get("position") or {}
                    width = int(position.get("width") or 0)
                    height = int(position.get("height") or 0)
                    size = (width, height) if width > 0 and height > 0 else None
                    base_unit = max(1, int(equation.get("font_size") or 1100))
                    document.shapes.add_equation(
                        script,
                        paragraph=paragraph,
                        base_unit=base_unit,
                        size=size,
                    )
                    promotion_report["equations"]["promoted"] += 1
                except Exception as exc:
                    promotion_report["equations"]["deferred"].append({
                        "equation_index": equation_index,
                        "reason": f"promotion_refused:{type(exc).__name__}",
                        "detail": str(exc)[:240],
                    })

        if promote_pictures:
            assets = extract_hwp5_binary_assets(payload)
            pictures = [
                item for item in parsed.get("objects", [])
                if item.get("kind") == "picture"
            ]
            for picture_index, picture in enumerate(pictures):
                anchor_ordinal = picture.get("anchor_paragraph_ordinal")
                anchor_key = (
                    int(picture.get("section_index", 0)),
                    int(anchor_ordinal if anchor_ordinal is not None else -1),
                )
                anchor_locator = anchor_map.get(anchor_key)
                bin_item_id = picture.get("bin_item_id")
                asset = (
                    None if bin_item_id is None
                    else assets.get(int(bin_item_id))
                )
                if not anchor_locator or asset is None:
                    promotion_report["pictures"]["deferred"].append({
                        "picture_index": picture_index,
                        "reason": "anchor_or_media_link_incomplete",
                        "bin_item_id": bin_item_id,
                    })
                    continue
                try:
                    prepared_asset = prepare_hwp5_image_for_hwpx(asset)
                    paragraph, _target = _resolve_hwpx_paragraph(
                        document, hwpx_path, anchor_locator
                    )
                    media_item = document.media.add_image(
                        prepared_asset["data"], str(prepared_asset["format"])
                    )
                    geometry = picture.get("control_geometry") or {}
                    width = max(1, int(geometry.get("width") or 14400))
                    height = max(1, int(geometry.get("height") or 14400))
                    treat_as_char = bool(geometry.get("treat_as_char", True))
                    pos_overrides = None
                    if not treat_as_char:
                        pos_overrides = {
                            "horzRelTo": _hwp_rel_to_horizontal(
                                controls.get(
                                    int(picture.get("control_index", -1)), {}
                                ).get("horz_rel_to")
                            ),
                            "vertRelTo": _hwp_rel_to_vertical(
                                controls.get(
                                    int(picture.get("control_index", -1)), {}
                                ).get("vert_rel_to")
                            ),
                            "horzAlign": "LEFT",
                            "vertAlign": "TOP",
                            "horzOffset": int(geometry.get("horizontal_offset") or 0),
                            "vertOffset": int(geometry.get("vertical_offset") or 0),
                        }
                    paragraph.add_picture(
                        str(media_item),
                        width=width,
                        height=height,
                        treat_as_char=treat_as_char,
                        pos_overrides=pos_overrides,
                    )
                    promotion_report["pictures"].setdefault("media_transforms", []).append({
                        "picture_index": picture_index,
                        "bin_item_id": bin_item_id,
                        "transform": prepared_asset["transform"],
                        "source_format": prepared_asset["source_format"],
                        "target_format": prepared_asset["format"],
                        "source_sha256": prepared_asset["source_sha256"],
                        "output_sha256": prepared_asset["output_sha256"],
                        "width": prepared_asset.get("width"),
                        "height": prepared_asset.get("height"),
                    })
                    promotion_report["pictures"]["promoted"] += 1
                except Exception as exc:
                    promotion_report["pictures"]["deferred"].append({
                        "picture_index": picture_index,
                        "reason": f"promotion_refused:{type(exc).__name__}",
                        "bin_item_id": bin_item_id,
                    })

        fd, tmp_name = tempfile.mkstemp(
            prefix=hwpx_path.stem + ".p36-rich-",
            suffix=".hwpx",
            dir=str(hwpx_path.parent),
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            document.save_to_path(str(tmp_path))
            os.replace(tmp_path, hwpx_path)
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
    finally:
        document.close()

    validation = core.validate_hwpx_package(hwpx_path, ingress=False)
    final_map = build_document_map(hwpx_path)
    final_tables = build_table_map(hwpx_path)
    final_equations = build_equation_map(hwpx_path)
    final_objects = build_object_map(hwpx_path)
    metadata = core._metadata(
        document_id,
        filename=core.sanitize_filename(Path(source_name).stem + ".hwpx"),
        owner_subject=owner_subject,
        validation=validation,
        title=derivative_title,
        source="hwp5-rich-derivative",
    )
    metadata.update({
        "source_hwp_filename": source_name,
        "source_hwp_sha256": source_sha256,
        "source_hwp_version": parsed.get("version"),
        "source_hwp_flags": parsed.get("flags", {}),
        "hwp_derivative_fidelity": "family-graded-rich",
        "hwp_fidelity_grades": parsed.get("fidelity", {}),
        "hwp_rich_promotion_report": promotion_report,
        "hwp_control_graph_edge_count": len(parsed.get("control_edges", [])),
        "hwp_original_mutated": False,
        "semantic_sha256": final_map["semantic_sha256"],
        "structure_sha256": final_map["structure_sha256"],
        "table_structure_sha256": final_tables["table_structure_sha256"],
        "equation_structure_sha256": final_equations["equation_structure_sha256"],
        "object_structure_sha256": final_objects["object_structure_sha256"],
    })
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        **metadata,
        "validation": validation,
        "idempotent_replay": False,
        "promotion_report": promotion_report,
        "final_inventory": {
            "tables": final_tables["table_count"],
            "equations": final_equations["equation_count"],
            "pictures": final_objects["picture_count"],
            "media_items": final_objects["media_item_count"],
        },
        "authority": "FIDELITY_GRADED_RICH_HWPX_DERIVATIVE / ORIGINAL_HWP_READ_ONLY",
    }


def _decode_hwp5_payload(content_base64: str) -> bytes:
    encoded_limit = ((core.MAX_INGEST_BYTES + 2) // 3) * 4 + 16
    if len(content_base64) > encoded_limit:
        raise ValueError("Encoded HWP exceeds the bounded ingress limit")
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if len(payload) > core.MAX_INGEST_BYTES:
        raise ValueError(f"HWP ingress exceeds {core.MAX_INGEST_BYTES} bytes")
    return payload


def _common_ir_from_source(
    document_id: str = "",
    content_base64: str = "",
    filename: str = "document.hwp",
) -> dict:
    has_hwpx = bool(str(document_id or "").strip())
    has_hwp = bool(str(content_base64 or "").strip())
    if has_hwpx == has_hwp:
        raise ValueError("Provide exactly one of document_id or content_base64")

    if has_hwpx:
        metadata, path = _owned_document(document_id)
        document_map = build_document_map(path)
        table_map = build_table_map(path)
        equation_map = build_equation_map(path)
        object_map = build_object_map(path)
        return hwpx_to_common_ir(
            document_id=document_id,
            revision=int(metadata["revision"]),
            semantic_sha256=document_map["semantic_sha256"],
            paragraphs=document_map["paragraphs"],
            tables=table_map.get("tables", []),
            equations=equation_map.get("equations", []),
            pictures=object_map.get("pictures", []),
            media_items=object_map.get("media_items", []),
        )

    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    if not parsed.get("readable"):
        raise ValueError(
            f"HWP source is not readable by the native lane: {parsed.get('block_reason')}"
        )
    return hwp5_to_common_ir(
        parsed,
        source_sha256=hashlib.sha256(payload).hexdigest(),
        filename=Path(filename or "document.hwp").name[:128],
    )


@core.mcp.tool()
def get_common_document_ir(
    document_id: str = "",
    content_base64: str = "",
    filename: str = "document.hwp",
    include_blocks: bool = True,
    max_blocks: int = 200,
) -> dict:
    """Return one format-neutral IR for either an owned HWPX document or one bounded HWP 5.x payload."""
    ir = _common_ir_from_source(document_id, content_base64, filename)
    limit = max(1, min(int(max_blocks), 1000))
    response = {key: value for key, value in ir.items() if key != "blocks"}
    response["ok"] = True
    if include_blocks:
        blocks = ir.get("blocks", [])
        response["blocks"] = blocks[:limit]
        response["blocks_truncated"] = len(blocks) > limit
    return response


@core.mcp.tool()
def extract_common_document(
    document_id: str = "",
    content_base64: str = "",
    filename: str = "document.hwp",
    kinds: list[str] = [],
    minimum_fidelity: str = "inventory",
    include_text: bool = True,
    include_data: bool = True,
    max_blocks: int = 200,
) -> dict:
    """Extract only common-IR blocks meeting an explicit minimum fidelity grade."""
    ir = _common_ir_from_source(document_id, content_base64, filename)
    result = extract_common_ir(
        ir,
        kinds=kinds or None,
        minimum_fidelity=minimum_fidelity,
        include_text=include_text,
        include_data=include_data,
        max_blocks=max_blocks,
    )
    return {
        "ok": True,
        "source_format": ir["source_format"],
        "ir_sha256": ir["ir_sha256"],
        "inventory": ir["inventory"],
        **result,
    }


@core.mcp.tool()
def search_common_document(
    query: str,
    document_id: str = "",
    content_base64: str = "",
    filename: str = "document.hwp",
    case_sensitive: bool = False,
    kinds: list[str] = [],
    max_results: int = 100,
) -> dict:
    """Search paragraph, table, equation, and other textual IR blocks across HWPX or HWP 5.x."""
    ir = _common_ir_from_source(document_id, content_base64, filename)
    result = search_common_ir(
        ir,
        query,
        case_sensitive=case_sensitive,
        kinds=kinds or None,
        max_results=max_results,
    )
    return {
        "ok": True,
        "source_format": ir["source_format"],
        "ir_sha256": ir["ir_sha256"],
        "inventory": ir["inventory"],
        **result,
    }


@core.mcp.tool()
def get_common_document_slice(
    document_id: str = "",
    content_base64: str = "",
    filename: str = "document.hwp",
    start_block: int = 0,
    block_count: int = 50,
    kinds: list[str] = [],
) -> dict:
    """Return one bounded block window from the common IR for HWPX or HWP 5.x."""
    ir = _common_ir_from_source(document_id, content_base64, filename)
    result = slice_common_ir(
        ir,
        start_block=start_block,
        block_count=block_count,
        kinds=kinds or None,
    )
    return {
        "ok": True,
        "source_format": ir["source_format"],
        "ir_sha256": ir["ir_sha256"],
        "inventory": ir["inventory"],
        **result,
    }


@core.mcp.tool()
def assess_hwp5_promotion(
    content_base64: str,
    filename: str = "document.hwp",
) -> dict:
    """Grade HWP5 object families from observed control/linkage closure rather than format-wide defaults."""
    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    if not parsed.get("readable"):
        return {
            "ok": True,
            "filename": Path(filename or "document.hwp").name[:128],
            "sha256": hashlib.sha256(payload).hexdigest(),
            "readable": False,
            "block_reason": parsed.get("block_reason"),
            "promotion_allowed": False,
            "grades": parsed.get("fidelity", {}),
        }

    tables = parsed.get("tables", [])
    equations = parsed.get("equations", [])
    pictures = [
        item for item in parsed.get("objects", [])
        if item.get("kind") == "picture"
    ]
    assets = extract_hwp5_binary_assets(payload)

    table_closed = bool(tables) and all(
        item.get("cells")
        and all(
            cell.get("paragraph_indexes") is not None
            for cell in item.get("cells", [])
        )
        for item in tables
    )
    equation_closed = bool(equations) and all(
        item.get("anchor_paragraph_ordinal") is not None
        and item.get("position_fidelity") == "structural"
        and bool(item.get("script"))
        for item in equations
    )
    picture_prepared: dict[int, dict] = {}
    picture_closed = bool(pictures)
    if picture_closed:
        for item in pictures:
            bin_item_id = int(item.get("bin_item_id") or -1)
            asset = assets.get(bin_item_id)
            if (
                item.get("anchor_paragraph_ordinal") is None
                or item.get("binary_link") is None
                or item.get("control_geometry") is None
                or asset is None
            ):
                picture_closed = False
                break
            try:
                picture_prepared[bin_item_id] = prepare_hwp5_image_for_hwpx(asset)
            except Hwp5ReadError:
                picture_closed = False
                break

    return {
        "ok": True,
        "filename": Path(filename or "document.hwp").name[:128],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "version": parsed.get("version"),
        "readable": True,
        "promotion_allowed": True,
        "grades": parsed.get("fidelity", {}),
        "inventory": {
            "paragraphs": len(parsed.get("paragraphs", [])),
            "tables": len(tables),
            "equations": len(equations),
            "pictures": len(pictures),
            "objects": len(parsed.get("objects", [])),
            "binary_items": len(parsed.get("binary_items", [])),
        },
        "closure": {
            "table_cell_paragraph_binding": table_closed,
            "equation_anchor_position_binding": equation_closed,
            "picture_bindata_geometry_binding": picture_closed,
        },
        "promotion": {
            "paragraph_text": {
                "grade": "A",
                "authority": "PROMOTE_TO_EDITABLE_HWPX_TEXT",
            },
            "tables": {
                "grade": "A-" if table_closed else ("C" if tables else "N/A"),
                "authority": (
                    "RICH_PROMOTION_ELIGIBLE"
                    if table_closed else "STRUCTURAL_PROVENANCE_ONLY"
                ),
                "reason": (
                    "cell addresses, spans, and paragraph ownership are bound"
                    if table_closed
                    else "cell/paragraph binding is incomplete"
                ),
            },
            "equations": {
                "grade": "A-" if equation_closed else ("B" if equations else "N/A"),
                "authority": (
                    "RICH_PROMOTION_ELIGIBLE"
                    if equation_closed
                    else "SEMANTIC_SCRIPT_RECOVERED / POSITION_PROMOTION_DEFERRED"
                ),
                "reason": (
                    "EqEdit script and control-derived anchor/geometry are bound"
                    if equation_closed
                    else "script is available but positioned control binding is incomplete"
                ),
            },
            "pictures": {
                "grade": "A-" if picture_closed else ("D" if pictures else "N/A"),
                "authority": (
                    "RICH_PROMOTION_ELIGIBLE"
                    if picture_closed else "INVENTORY_OR_PARTIAL_LINKAGE"
                ),
                "reason": (
                    "picture record, unique BinData asset, bounded promotable media transform, and control geometry are bound"
                    if picture_closed
                    else "one or more media/anchor/geometry links remain incomplete"
                ),
            },
        },
        "recommended_mode": (
            "FIDELITY_GRADED_RICH_DERIVATIVE"
            if any([table_closed, equation_closed, picture_closed])
            else "TEXT_DERIVATIVE_WITH_OBJECT_PROVENANCE"
        ),
    }


@core.mcp.tool()
def search_document_text(
    document_id: str,
    query: str,
    case_sensitive: bool = False,
    max_results: int = 50,
    context_chars: int = 120,
) -> dict:
    """Search paragraph text and return compact revision-bound hits without emitting the full document."""
    metadata, path = _owned_document(document_id)
    needle = str(query)
    if not needle:
        raise ValueError("query must not be empty")
    limit = max(1, min(int(max_results), 200))
    context = max(0, min(int(context_chars), 500))
    document_map = build_document_map(path)
    hits = []
    folded_needle = needle if case_sensitive else needle.casefold()
    for index, paragraph in enumerate(document_map["paragraphs"]):
        text_value = paragraph.get("text", "")
        haystack = text_value if case_sensitive else text_value.casefold()
        start = 0
        while len(hits) < limit:
            pos = haystack.find(folded_needle, start)
            if pos < 0:
                break
            left = max(0, pos - context)
            right = min(len(text_value), pos + len(needle) + context)
            hits.append({
                "paragraph_index": index,
                "locator": paragraph["locator"],
                "address_stability": paragraph["address_stability"],
                "match_start": pos,
                "match_end": pos + len(needle),
                "text_sha256": paragraph["text_sha256"],
                "context": text_value[left:right],
                "context_start": left,
            })
            start = pos + max(1, len(folded_needle))
        if len(hits) >= limit:
            break
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "query": needle,
        "case_sensitive": bool(case_sensitive),
        "match_count": len(hits),
        "truncated": len(hits) >= limit,
        "semantic_sha256": document_map["semantic_sha256"],
        "hits": hits,
    }


@core.mcp.tool()
def get_document_slice(
    document_id: str,
    start_paragraph: int = 0,
    paragraph_count: int = 20,
    include_locators: bool = True,
) -> dict:
    """Return a bounded paragraph window for large-document reading and agent navigation."""
    metadata, path = _owned_document(document_id)
    document_map = build_document_map(path)
    total = len(document_map["paragraphs"])
    start = max(0, int(start_paragraph))
    count = max(1, min(int(paragraph_count), 200))
    end = min(total, start + count)
    paragraphs = []
    for absolute_index, paragraph in enumerate(document_map["paragraphs"][start:end], start=start):
        item = {
            "paragraph_index": absolute_index,
            "text": paragraph.get("text", ""),
            "text_sha256": paragraph["text_sha256"],
        }
        if include_locators:
            item["locator"] = paragraph["locator"]
            item["address_stability"] = paragraph["address_stability"]
        paragraphs.append(item)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "semantic_sha256": document_map["semantic_sha256"],
        "start_paragraph": start,
        "end_paragraph_exclusive": end,
        "returned_paragraphs": len(paragraphs),
        "paragraph_count": total,
        "has_more": end < total,
        "next_start_paragraph": end if end < total else None,
        "paragraphs": paragraphs,
    }


def _literal_matches(text: str, query: str, case_sensitive: bool) -> list[tuple[int, int, str]]:
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    return [(match.start(), match.end(), match.group(0)) for match in pattern.finditer(text)]


def _bulk_plan(
    document_id: str,
    metadata: dict,
    path: Path,
    query: str,
    replacement: str,
    case_sensitive: bool,
    max_operations: int,
    selected_hit_indexes: list[int],
) -> dict:
    needle = str(query)
    if not needle:
        raise ValueError("query must not be empty")
    if len(replacement) > 100_000:
        raise ValueError("replacement is too large")
    limit = max(1, min(int(max_operations), 100))
    document_map = build_document_map(path)
    all_hits: list[dict] = []
    for paragraph_index, paragraph in enumerate(document_map["paragraphs"]):
        text_value = paragraph.get("text", "")
        for start, end, matched_text in _literal_matches(text_value, needle, case_sensitive):
            all_hits.append({
                "hit_index": len(all_hits),
                "paragraph_index": paragraph_index,
                "locator": paragraph["locator"],
                "address_stability": paragraph["address_stability"],
                "start": start,
                "end": end,
                "expected_text": matched_text,
                "text_sha256": paragraph["text_sha256"],
            })

    if selected_hit_indexes:
        requested = [int(item) for item in selected_hit_indexes]
        if len(set(requested)) != len(requested):
            raise ValueError("selected_hit_indexes must not contain duplicates")
        by_index = {item["hit_index"]: item for item in all_hits}
        missing = [item for item in requested if item not in by_index]
        if missing:
            raise ValueError(f"Unknown selected hit indexes: {missing[:10]}")
        selected = [by_index[item] for item in requested]
    else:
        selected = all_hits[:limit]

    if len(selected) > limit:
        raise ValueError(f"Selected hits exceed max_operations={limit}")
    if not selected:
        raise ValueError("No text matches selected for bulk replacement")

    # Apply from right to left within each paragraph so earlier offsets stay valid.
    operations = [
        {
            "op": "replace_inline_text",
            "target": hit["locator"],
            "start": hit["start"],
            "end": hit["end"],
            "text": replacement,
            "expected_text": hit["expected_text"],
        }
        for hit in sorted(
            selected,
            key=lambda item: (item["paragraph_index"], item["start"]),
            reverse=True,
        )
    ]

    ingress = metadata.get("source") == "existing-ingress"
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p34-preview-",
        suffix=".hwpx",
        dir=str(path.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    try:
        preview = apply_inline_edits_atomic(
            candidate,
            operations,
            expected_revision=int(metadata["revision"]),
            current_revision=int(metadata["revision"]),
            validator=lambda item: core.validate_hwpx_package(item, ingress=ingress),
        )
        after_map = build_document_map(candidate)
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass

    canonical = {
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "semantic_sha256": document_map["semantic_sha256"],
        "query": needle,
        "replacement": replacement,
        "case_sensitive": bool(case_sensitive),
        "selected": [
            {
                "hit_index": item["hit_index"],
                "locator": item["locator"],
                "start": item["start"],
                "end": item["end"],
                "expected_text": item["expected_text"],
                "text_sha256": item["text_sha256"],
            }
            for item in selected
        ],
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    plan_id = hmac.new(core._download_secret(), b"p3.4-bulk-plan\0" + payload, hashlib.sha256).hexdigest()
    return {
        "plan_id": plan_id,
        "revision": int(metadata["revision"]),
        "semantic_sha256": document_map["semantic_sha256"],
        "query": needle,
        "replacement": replacement,
        "case_sensitive": bool(case_sensitive),
        "total_hits": len(all_hits),
        "selected_hit_count": len(selected),
        "selected_hits": selected,
        "truncated": not selected_hit_indexes and len(all_hits) > len(selected),
        "operations": operations,
        "preview": preview,
        "after_semantic_sha256": after_map["semantic_sha256"],
    }


@core.mcp.tool()
def plan_bulk_text_replace(
    document_id: str,
    query: str,
    replacement: str,
    case_sensitive: bool = False,
    max_operations: int = 100,
    selected_hit_indexes: list[int] = [],
) -> dict:
    """Build and validate a revision-bound multi-hit inline replacement plan without committing it."""
    metadata, path = _owned_document(document_id)
    plan = _bulk_plan(
        document_id,
        metadata,
        path,
        query,
        replacement,
        case_sensitive,
        max_operations,
        selected_hit_indexes,
    )
    return {
        "ok": True,
        "document_id": document_id,
        **plan,
        "authority": "preview only; commit requires the same plan_id against the same revision",
    }


@core.mcp.tool()
def commit_bulk_text_replace(
    document_id: str,
    expected_revision: int,
    plan_id: str,
    query: str,
    replacement: str,
    case_sensitive: bool = False,
    max_operations: int = 100,
    selected_hit_indexes: list[int] = [],
    lease_token: str = "",
) -> dict:
    """Commit one previously previewed multi-hit inline replacement as a single CAS-guarded revision."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    if int(expected_revision) != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    plan = _bulk_plan(
        document_id,
        metadata,
        path,
        query,
        replacement,
        case_sensitive,
        max_operations,
        selected_hit_indexes,
    )
    if not hmac.compare_digest(str(plan_id), plan["plan_id"]):
        raise ValueError("Bulk edit plan no longer matches the current document or selection")

    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_inline_edits_atomic(
        path,
        plan["operations"],
        expected_revision=current_revision,
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
    )

    changed_locators = sorted({item["locator"] for item in plan["selected_hits"]})
    after_index = {item["locator"]: item for item in after_document["paragraphs"]}
    verification = [
        {
            "locator": locator,
            "text_sha256": after_index[locator]["text_sha256"],
            "text": after_index[locator]["text"][:1000],
            "text_truncated": len(after_index[locator]["text"]) > 1000,
        }
        for locator in changed_locators
        if locator in after_index
    ][:50]
    return {
        "ok": True,
        "document_id": document_id,
        "plan_id": plan["plan_id"],
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "operation_count": len(plan["operations"]),
        "changed_paragraph_count": len(changed_locators),
        "semantic_sha256_before": plan["semantic_sha256"],
        "semantic_sha256_after": after_document["semantic_sha256"],
        "inline_structure_sha256_after": after_inline["inline_structure_sha256"],
        "verification": verification,
        "verification_truncated": len(changed_locators) > len(verification),
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def get_table_map(document_id: str, table_locator: str = "") -> dict:
    """Return table/cell semantic addresses, merge geometry and table receipts."""
    metadata, path = _owned_document(document_id)
    table_map = build_table_map(path)
    if table_locator:
        table = next(
            (item for item in table_map["tables"] if item["locator"] == table_locator),
            None,
        )
        if table is None:
            raise ValueError("Unknown table locator")
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "table_structure_sha256": table_map["table_structure_sha256"],
            "table_format_sha256": table_map["table_format_sha256"],
            "table_object_sha256": table_map.get("table_object_sha256"),
            "table": table,
        }
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **table_map,
    }


@core.mcp.tool()
def get_object_map(document_id: str, object_locator: str = "") -> dict:
    """Return picture objects, package-owned media items, geometry and custody receipts."""
    metadata, path = _owned_document(document_id)
    object_map = build_object_map(path)
    if object_locator:
        picture = next(
            (item for item in object_map["pictures"] if item["locator"] == object_locator),
            None,
        )
        if picture is None:
            raise ValueError("Unknown picture locator")
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "object_structure_sha256": object_map["object_structure_sha256"],
            "object_geometry_sha256": object_map["object_geometry_sha256"],
            "media_custody_sha256": object_map["media_custody_sha256"],
            "picture": picture,
        }
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **object_map,
    }


@core.mcp.tool()
def get_equation_map(document_id: str, equation_locator: str = "") -> dict:
    """Return equation identities, EqEdit scripts, geometry and custody receipts."""
    metadata, path = _owned_document(document_id)
    equation_map = build_equation_map(path)
    if equation_locator:
        equation = next(
            (item for item in equation_map["equations"] if item["locator"] == equation_locator),
            None,
        )
        if equation is None:
            raise ValueError("Unknown equation locator")
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "equation_structure_sha256": equation_map["equation_structure_sha256"],
            "equation_geometry_sha256": equation_map["equation_geometry_sha256"],
            "equation_script_custody_sha256": equation_map["equation_script_custody_sha256"],
            "equation": equation,
        }
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **equation_map,
    }


@core.mcp.tool()
def get_text(document_id: str, locator: str = "") -> dict:
    """Return whole-document text or the text of one paragraph locator."""
    metadata, path = _owned_document(document_id)
    document_map = build_document_map(path)
    if locator:
        target = next((p for p in document_map["paragraphs"] if p["locator"] == locator), None)
        if target is None:
            raise ValueError("Unknown paragraph locator")
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "locator": locator,
            "kind": "paragraph",
            "text": target["text"],
            "text_sha256": target["text_sha256"],
            "address_stability": target["address_stability"],
        }
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "text": document_map["text"],
        "text_chars": document_map["text_chars"],
        "paragraph_count": document_map["paragraph_count"],
        "semantic_sha256": document_map["semantic_sha256"],
    }


@core.mcp.tool()
def get_inline_map(document_id: str, locator: str = "") -> dict:
    """Return direct inline text spans, controls, fields and structure receipts."""
    metadata, path = _owned_document(document_id)
    inline_map = build_inline_map(path)
    if locator:
        paragraph = next(
            (item for item in inline_map["paragraphs"] if item["locator"] == locator),
            None,
        )
        if paragraph is None:
            raise ValueError("Unknown paragraph locator")
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "inline_text_sha256": inline_map["inline_text_sha256"],
            "inline_structure_sha256": inline_map["inline_structure_sha256"],
            "paragraph": paragraph,
        }
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **inline_map,
    }


@core.mcp.tool()
def get_formatting(document_id: str, locator: str = "") -> dict:
    """Inspect paragraph/run formatting refs and resolved property summaries."""
    metadata, path = _owned_document(document_id)
    formatting_map = build_formatting_map(path)
    if locator:
        paragraph = next(
            (item for item in formatting_map["paragraphs"] if item["locator"] == locator),
            None,
        )
        if paragraph is None:
            raise ValueError("Unknown paragraph locator")
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "formatting_sha256": formatting_map["formatting_sha256"],
            "paragraph": paragraph,
            "property_counts": formatting_map["property_counts"],
        }
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **formatting_map,
    }


@core.mcp.tool()
def apply_inline_edits(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded control-aware inline text transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_inline_edits_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "inline_diff": transaction,
        "semantic_changed": transaction["semantic_changed"],
        "structure_changed": transaction["structure_changed"],
        "inline_text_changed": transaction["inline_text_changed"],
        "inline_structure_changed": transaction["inline_structure_changed"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def apply_control_edits(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded field/hyperlink/special-atom transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_control_edits_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "control_diff": transaction,
        "semantic_changed": transaction["semantic_changed"],
        "structure_changed": transaction["structure_changed"],
        "inline_text_changed": transaction["inline_text_changed"],
        "inline_structure_changed": transaction["inline_structure_changed"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def apply_table_edits(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded table structure/geometry/cell-format transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_table_edits_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    after_tables = build_table_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
        after_tables,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "table_diff": transaction,
        "table_structure_changed": transaction["table_structure_changed"],
        "table_format_changed": transaction["table_format_changed"],
        "table_object_changed": transaction["table_object_changed"],
        "table_rebinding": transaction["table_object_rebinding"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def apply_object_edits(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded picture/media/geometry transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_object_edits_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    after_tables = build_table_map(path)
    after_objects = build_object_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
        after_tables,
        after_objects,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "object_diff": transaction,
        "object_structure_changed": transaction["object_structure_changed"],
        "object_geometry_changed": transaction["object_geometry_changed"],
        "media_custody_changed": transaction["media_custody_changed"],
        "object_rebinding": transaction["object_rebinding"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def apply_equation_edits(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded equation script/geometry/lifecycle transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_equation_edits_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    after_tables = build_table_map(path)
    after_objects = build_object_map(path)
    after_equations = build_equation_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
        after_tables,
        after_objects,
        after_equations,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "equation_diff": transaction,
        "equation_structure_changed": transaction["equation_structure_changed"],
        "equation_geometry_changed": transaction["equation_geometry_changed"],
        "equation_script_custody_changed": transaction["equation_script_custody_changed"],
        "equation_rebinding": transaction["equation_rebinding"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def apply_formatting(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded formatting-only transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_rich_formatting_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id,
        metadata,
        validation,
        after_document,
        after_formatting,
        after_inline,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "formatting_diff": transaction,
        "semantic_changed": transaction["semantic_changed"],
        "structure_changed": transaction["structure_changed"],
        "formatting_changed": transaction["formatting_changed"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def apply_edits(document_id: str, expected_revision: int, operations: list[dict], lease_token: str = "") -> dict:
    """Apply one revision-guarded atomic text/paragraph-structure transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = apply_edits_atomic(
        path,
        operations,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    after_map = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    metadata["revision"] = current_revision + 1
    metadata["last_edit_at"] = core._utc_iso()
    if lease_token:
        metadata["_commit_lease_token"] = lease_token
    _refresh_metadata(
        document_id, metadata, validation, after_map, after_formatting, after_inline
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "diff": transaction,
        "semantic_diff": transaction,
        "structure_diff": {
            "changed": transaction["structure_changed"],
            "before_sha256": transaction["before"]["structure_sha256"],
            "after_sha256": transaction["after"]["structure_sha256"],
            "paragraph_count_before": transaction["before"]["paragraph_count"],
            "paragraph_count_after": transaction["after"]["paragraph_count"],
        },
        "locator_rebinding": transaction["locator_rebinding"],
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def compare_document(
    document_id: str,
    semantic_sha256: str = "",
    structure_sha256: str = "",
    formatting_sha256: str = "",
    inline_structure_sha256: str = "",
    table_structure_sha256: str = "",
    table_format_sha256: str = "",
    table_object_sha256: str = "",
    object_structure_sha256: str = "",
    object_geometry_sha256: str = "",
    media_custody_sha256: str = "",
    equation_structure_sha256: str = "",
    equation_geometry_sha256: str = "",
    equation_script_custody_sha256: str = "",
) -> dict:
    """Compare semantic/structure/formatting/inline-structure receipts."""
    metadata, path = _owned_document(document_id)
    document_map = build_document_map(path)
    formatting_map = build_formatting_map(path)
    inline_map = build_inline_map(path)
    current_semantic = document_map["semantic_sha256"]
    current_structure = document_map["structure_sha256"]
    current_formatting = formatting_map["formatting_sha256"]
    current_inline_structure = inline_map["inline_structure_sha256"]
    table_map = build_table_map(path)
    current_table_structure = table_map["table_structure_sha256"]
    current_table_format = table_map["table_format_sha256"]
    current_table_object = table_map.get("table_object_sha256", "")
    object_map = build_object_map(path)
    current_object_structure = object_map["object_structure_sha256"]
    current_object_geometry = object_map["object_geometry_sha256"]
    current_media_custody = object_map["media_custody_sha256"]
    equation_map = build_equation_map(path)
    current_equation_structure = equation_map["equation_structure_sha256"]
    current_equation_geometry = equation_map["equation_geometry_sha256"]
    current_equation_script_custody = equation_map["equation_script_custody_sha256"]
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "current": {
            "semantic_sha256": current_semantic,
            "structure_sha256": current_structure,
            "formatting_sha256": current_formatting,
            "inline_structure_sha256": current_inline_structure,
            "table_structure_sha256": current_table_structure,
            "table_format_sha256": current_table_format,
            "table_object_sha256": current_table_object,
            "object_structure_sha256": current_object_structure,
            "object_geometry_sha256": current_object_geometry,
            "media_custody_sha256": current_media_custody,
            "equation_structure_sha256": current_equation_structure,
            "equation_geometry_sha256": current_equation_geometry,
            "equation_script_custody_sha256": current_equation_script_custody,
        },
        "matches": {
            "semantic": None if not semantic_sha256 else semantic_sha256 == current_semantic,
            "structure": None if not structure_sha256 else structure_sha256 == current_structure,
            "formatting": None if not formatting_sha256 else formatting_sha256 == current_formatting,
            "inline_structure": (
                None
                if not inline_structure_sha256
                else inline_structure_sha256 == current_inline_structure
            ),
            "table_structure": (
                None if not table_structure_sha256 else table_structure_sha256 == current_table_structure
            ),
            "table_format": (
                None if not table_format_sha256 else table_format_sha256 == current_table_format
            ),
            "table_object": (
                None if not table_object_sha256 else table_object_sha256 == current_table_object
            ),
            "object_structure": (
                None if not object_structure_sha256 else object_structure_sha256 == current_object_structure
            ),
            "object_geometry": (
                None if not object_geometry_sha256 else object_geometry_sha256 == current_object_geometry
            ),
            "media_custody": (
                None if not media_custody_sha256 else media_custody_sha256 == current_media_custody
            ),
            "equation_structure": (
                None if not equation_structure_sha256 else equation_structure_sha256 == current_equation_structure
            ),
            "equation_geometry": (
                None if not equation_geometry_sha256 else equation_geometry_sha256 == current_equation_geometry
            ),
            "equation_script_custody": (
                None
                if not equation_script_custody_sha256
                else equation_script_custody_sha256 == current_equation_script_custody
            ),
        },
    }


@core.mcp.tool()
def p2_capabilities() -> dict:
    subject = core._caller_subject()
    return {
        "project": core.PROJECT,
        "version": core.VERSION,
        "phase": "P3.6",
        "authenticated_subject": subject,
        "tools_added": [
            "acquire_document_lease",
            "release_document_lease",
            "get_document_commit_receipt",
            "get_document_versions",
            "restore_document_revision",
            "set_document_retention",
            "pin_document_revision",
            "unpin_document_revision",
            "compact_document_history",
            "verify_document_lineage",
            "get_document_map",
            "assess_hwp5_promotion",
            "get_common_document_slice",
            "search_common_document",
            "extract_common_document",
            "get_common_document_ir",
            "materialize_hwp5_text_derivative",
            "inspect_hwp5_document",
            "materialize_hwp5_rich_derivative",
            "get_hwp5_control_graph",
            "search_document_text",
            "get_document_slice",
            "plan_bulk_text_replace",
            "commit_bulk_text_replace",
            "get_text",
            "apply_edits",
            "compare_document",
            "get_formatting",
            "apply_formatting",
            "get_inline_map",
            "apply_inline_edits",
            "apply_control_edits",
            "get_table_map",
            "apply_table_edits",
            "get_object_map",
            "apply_object_edits",
            "get_equation_map",
            "apply_equation_edits",
        ],
        "operations": [
            "replace_paragraph_text",
            "insert_paragraph_before",
            "insert_paragraph_after",
            "delete_paragraph",
            "move_paragraph_before",
            "move_paragraph_after",
        ],
        "inline_operations": [
            "replace_inline_text",
        ],
        "control_operations": [
            "create_hyperlink",
            "retarget_hyperlink",
            "remove_hyperlink",
            "set_field_name",
            "insert_special_atom",
            "delete_special_atom",
            "create_bookmark",
            "rename_bookmark",
            "remove_bookmark",
            "create_bookmark_reference",
            "retarget_bookmark_reference",
            "set_date_field_properties",
            "set_path_field_properties",
            "set_mail_merge_field_properties",
        ],
        "formatting_operations": [
            "set_run_format",
            "set_range_format",
            "copy_run_format",
            "set_paragraph_format",
            "copy_paragraph_format",
            "normalize_formatting",
        ],
        "addressing": "intrinsic paragraph ids when present; revision-bound ordinal fallback otherwise",
        "edit_transaction": "exact expected_revision + candidate-package validation + atomic package replacement",
        "semantic_diff": True,
        "structure_diff": True,
        "locator_rebinding": True,
        "structural_edits": "paragraph insert/delete/same-container move",
        "formatting": {
            "introspection": "paragraph/run refs + resolved summaries + direct-text offsets",
            "range_selection": "[start,end) over paragraph direct_text",
            "run_mutation": "whole run(s) or split-safe character range",
            "paragraph_mutation": "section-body and nested paragraphs",
            "style_copy_reuse": "exact same-document charPr/paraPr reference reuse",
            "normalization": "coalesce adjacent split-safe runs with identical run attributes",
            "diff": "formatting_sha256",
            "semantic_structure_preservation": "fail-closed",
        },
        "inline_editing": {
            "coordinate": "[start,end) over direct inline_text",
            "cross_run": True,
            "hyperlink_field_cached_text": True,
            "field_wrapper_preservation": "required",
            "mixed_markup": "context-aware; preserved markers are hard internal boundaries",
            "special_atoms": "tab/lineBreak/nbSpace/fwSpace/soft-hyphen are visible but non-replaceable in P2.4",
            "replacement_style": "storage/run style at range start",
            "diff": "inline_structure_sha256",
        },
        "control_editing": {
            "hyperlink": "partial-span create + retarget/remove",
            "typed_fields": "DATE/PATH/MAILMERGE confirmed property lanes only",
            "bookmarks": "create/rename/remove + internal hyperlink reference lifecycle",
            "special_atoms": "insert/delete tab/lineBreak/nbSpace/fwSpace/soft-hyphen",
            "identity_rebinding": "intrinsic field ids where available; revision-scoped bookmark rebinding otherwise",
            "transaction": "paragraph structure invariant; inline/control structure may change intentionally",
            "diff": "inline_structure_sha256 + control_rebinding",
        },
        "table_editing": {
            "introspection": "table/cell semantic map + merge geometry + structure/format/object receipts",
            "table_address": "intrinsic hp:tbl id when present; revision-bound ordinal fallback",
            "cell_address": "revision-bound grid-anchor locator with rebinding receipts",
            "object_lifecycle": "create_table + delete_table",
            "row_structure": "insert_row_by_clone + delete_row",
            "column_structure": "delete_column + width/autofit; insert_column evidence gate closed",
            "merge_split": "rectangular merge + merged-cell split",
            "cell_content_format": "text, shading, borders, gradient, margins, size, header/protect/editable/name",
            "diff": "table_structure_sha256 + table_format_sha256 + table_object_sha256",
        },
        "object_editing": {
            "introspection": "picture objects + paragraph anchors + package-owned media items",
            "media_custody": "PNG/JPEG only, base64 ingress, 8 MiB per image, package BinData SHA-256 receipts",
            "placement": "inline or floating insertion",
            "replacement_removal": "asset replacement with optional orphan cleanup + picture removal",
            "geometry": "picture resize + floating offset mutation",
            "diff": "object_structure_sha256 + object_geometry_sha256 + media_custody_sha256",
        },
        "durable_transaction_concurrency": {
            "cas": "database row lock + expected_revision; only N->N+1 may advance current authority",
            "same_revision_replay": "same revision + same SHA-256 returns deterministic IDEMPOTENT_REPLAY",
            "conflicting_same_revision": "same revision + different SHA-256 is rejected",
            "lease": "optional 5..300 second durable TTL lease; active lease token is mandatory for revision advancement",
            "lease_failure": "lease expiry/release never weakens CAS authority",
            "crash_consistency": "durable commit precedes local-cache acceptance; cache is rehydrated after commit/cache crash windows",
            "receipt": "deterministic SHA-256 receipt_id over document_id/revision/content SHA",
        },
        "large_document_navigation": {
            "search": "case-sensitive/insensitive paragraph search with bounded result count and compact context windows",
            "slice": "bounded paragraph windows with continuation cursor and optional revision-bound locators",
            "token_economy": "agents can locate and read relevant regions without materializing the full document map",
            "revision_binding": "all search/slice receipts expose the current revision and semantic SHA-256",
            "create_replay": "optional request_id makes create_document recoverable after a lost response; payload mismatch is rejected",
        },
        "bulk_text_transactions": {
            "plan": "query-to-hit selection with optional hit indexes and exact inline-range validation",
            "preview": "candidate HWPX is validated without durable mutation and returns after-semantic receipt",
            "commit": "same plan id + same revision required; all selected spans commit in one CAS-guarded revision",
            "format_safety": "uses inline-range mutation instead of whole-paragraph replacement to preserve unaffected rich formatting",
            "verification": "bounded post-edit paragraph receipts are returned after commit",
        },
        "legacy_hwp5_read": {
            "container": "native OLE/CFB HWP 5.x reader; no Hancom desktop dependency",
            "scope": "bounded read-only header/body-text extraction",
            "security": "password/DRM/certificate-encrypted content is blocked rather than bypassed",
            "fidelity": "control-graph graded: paragraph semantic, table cell graph structural/semantic, equation positioned-semantic, picture media-link structural when closed",
            "edit_boundary": "legacy HWP binary is never mutated by the HWPX edit engine",
        },
        "hwp5_control_graph": {
            "controls": "CTRL_HEADER family/instance/geometry reconstruction",
            "tables": "TABLE → cell LIST_HEADER → paragraph ownership graph",
            "equations": "EqEdit family record bound to control anchor and object geometry",
            "pictures": "picture BinItem reference bound to DocInfo/BinData storage and media custody",
            "promotion": "only closed family bindings may synthesize native HWPX objects; ambiguous families remain provenance",
        },
        "common_document_ir": {
            "formats": ["hwpx", "hwp5"],
            "blocks": ["paragraph", "table", "equation", "picture", "shape", "binary"],
            "search": "one query contract across HWPX document custody and bounded HWP 5.x payloads",
            "extract": "kind-filtered blocks gated by an explicit minimum fidelity threshold",
            "fidelity": "every block carries source-native receipts and an explicit fidelity grade",
        },
        "hwp5_promotion": {
            "text": "promotable to editable HWPX derivative",
            "tables": "structural provenance only until cell association is certified",
            "equations": "semantic EqEdit script recovered; exact position synthesis deferred",
            "pictures": "inventory/BinData custody only until linkage and geometry are certified",
        },
        "durable_document_storage": {
            "authority": "encrypted Postgres revision snapshots; local filesystem is a rehydratable execution cache",
            "versioning": "every committed content revision receives an append-only commit receipt; byte snapshots may later compact",
            "restart_recovery": "local cache miss or mismatch rehydrates current durable revision automatically",
            "historical_recovery": "restore only retained historical bytes, promoted as current_revision+1",
            "retention": "document TTL bounded 1 hour..30 days; revision compaction separately retains current + pinned + recent K",
            "revision_pins": "DB-level restore anchors protected from snapshot deletion",
            "compaction": "active durable lease blocks maintenance; commit ledger is never removed by revision compaction",
            "audit_chain": "SHA-256 hash chain over ordered commit receipts; current pointer and pinned reachability are revalidated after compaction",
            "encryption": "AES-GCM with document-specific domain-separated key/AAD from OAuth-state secret",
            "oauth_separation": "separate tables, payload format, AAD, and derived key from OAuth authority",
        },
        "equation_editing": {
            "introspection": "EqEdit script + owning paragraph + intrinsic object identity + geometry",
            "authoring_input": "verified LaTeX token set only; converted by hwpx.equation.latex_to_eqedit",
            "raw_eqedit_authoring": "evidence gate closed",
            "lifecycle": "insert + verified-script replacement + removal",
            "geometry": "explicit hp:sz resize; replacement re-estimates size unless preserve_size=true",
            "diff": "equation_structure_sha256 + equation_geometry_sha256 + equation_script_custody_sha256",
        },
        "tables_images_equations": "tables=P2.8 active; images=P2.9 active; equations=P2.10 active",
    }


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8000")))
    path = os.environ.get("MCP_PATH", "/mcp")
    core.mcp.run(
        "streamable-http",
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=True,
        json_response=True,
        transport_security=core._transport_security(),
    )
