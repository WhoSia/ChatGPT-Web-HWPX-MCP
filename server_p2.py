from __future__ import annotations

import os
import secrets
import tempfile
import time
from pathlib import Path

import server as core
from p2_document import apply_edits_atomic, build_document_map
from p22_formatting import build_formatting_map
from p23_richtext import apply_rich_formatting_atomic
from p24_inline import apply_inline_edits_atomic, build_inline_map
from p26_controls import apply_control_edits_atomic
from p28_tables import apply_table_edits_atomic, build_table_map
from p29_objects import apply_object_edits_atomic, build_object_map
from p210_equations import apply_equation_edits_atomic, build_equation_map

P2_VERSION = "0.4.1-p3.1"
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
        "phase": "P3.1",
        "authenticated_subject": subject,
        "tools_added": [
            "acquire_document_lease",
            "release_document_lease",
            "get_document_commit_receipt",
            "get_document_versions",
            "restore_document_revision",
            "set_document_retention",
            "get_document_map",
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
        "durable_document_storage": {
            "authority": "encrypted Postgres revision snapshots; local filesystem is a rehydratable execution cache",
            "versioning": "every committed content revision is stored by document_id + monotonic revision",
            "restart_recovery": "local cache miss or mismatch rehydrates current durable revision automatically",
            "historical_recovery": "restore historical bytes only by promoting them as current_revision+1",
            "retention": "bounded 1 hour..30 days; default 7 days unless configured",
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
