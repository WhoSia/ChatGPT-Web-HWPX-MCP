from __future__ import annotations

import os
from pathlib import Path

import server as core
from p2_document import apply_edits_atomic, build_document_map
from p22_formatting import build_formatting_map
from p23_richtext import apply_rich_formatting_atomic
from p24_inline import apply_inline_edits_atomic, build_inline_map
from p26_controls import apply_control_edits_atomic

P2_VERSION = "0.3.6-p2.6"
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
    core._write_metadata(document_id, metadata)
    return metadata


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
def apply_inline_edits(document_id: str, expected_revision: int, operations: list[dict]) -> dict:
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
def apply_control_edits(document_id: str, expected_revision: int, operations: list[dict]) -> dict:
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
def apply_formatting(document_id: str, expected_revision: int, operations: list[dict]) -> dict:
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
def apply_edits(document_id: str, expected_revision: int, operations: list[dict]) -> dict:
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
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "current": {
            "semantic_sha256": current_semantic,
            "structure_sha256": current_structure,
            "formatting_sha256": current_formatting,
            "inline_structure_sha256": current_inline_structure,
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
        },
    }


@core.mcp.tool()
def p2_capabilities() -> dict:
    subject = core._caller_subject()
    return {
        "project": core.PROJECT,
        "version": core.VERSION,
        "phase": "P2.6",
        "authenticated_subject": subject,
        "tools_added": [
            "get_document_map",
            "get_text",
            "apply_edits",
            "compare_document",
            "get_formatting",
            "apply_formatting",
            "get_inline_map",
            "apply_inline_edits",
            "apply_control_edits",
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
        "tables_images_equations": False,
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
