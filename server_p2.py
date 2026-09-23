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
import unicodedata
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
from p39_textbox import build_textbox_map, inject_textbox
from p311_layout_fidelity import build_hwpx_layout_receipt
from p312_render_harness import adjudicate_fixture_world_contact
from p317_fidelity_envelope import (
    production_fidelity_contract,
    assess_edit_fidelity_envelope,
)
from p317_page_geometry import (
    build_page_geometry_map,
    apply_page_geometry_edits_atomic,
)
from p318_document_setup import (
    build_document_setup_map,
    apply_document_setup_atomic,
)
from p319_structured_publishing import (
    build_structured_publishing_map,
    apply_structured_publishing_atomic,
)
from p320_annotation_apparatus import (
    build_annotation_apparatus_map,
    apply_annotation_apparatus_atomic,
)
from p321_document_composer import (
    document_plan_contract,
    validate_document_plan as validate_composition_plan,
    compose_document_plan,
)
from p322_review_workflow import (
    build_review_workflow_map,
    apply_review_workflow_atomic,
)
from p323_advanced_tables import (
    advanced_table_contract,
    build_advanced_table_map,
    apply_advanced_table_edits_atomic,
)
from p324_story_layer import (
    story_layer_contract,
    build_story_layer_map,
    apply_story_layer_atomic,
)
from p325_drawing_layer import (
    drawing_layer_contract,
    build_drawing_layer_map,
    apply_drawing_layer_atomic,
)
from p326_drawing_style import (
    drawing_style_contract,
    build_drawing_style_map,
    apply_drawing_style_atomic,
)
from p327_diagram_composition import (
    diagram_composition_contract,
    build_diagram_composition_map,
    apply_diagram_composition_atomic,
)
from p328_high_level_diagrams import (
    high_level_diagram_contract,
    validate_diagram_plan as validate_p328_diagram_plan,
    build_high_level_diagram_map,
    apply_high_level_diagrams_atomic,
)
from p329_diagram_lifecycle import (
    diagram_lifecycle_contract,
    build_diagram_lifecycle_map,
    apply_diagram_lifecycle_atomic,
)
from p330_diagram_design_system import (
    diagram_design_system_contract,
    build_diagram_design_system_map,
    apply_diagram_design_system_atomic,
)
from p331_diagram_quality_assurance import (
    diagram_quality_assurance_contract,
    validate_diagram_quality as validate_p331_diagram_quality,
    build_diagram_quality_map,
    plan_diagram_repairs as plan_p331_diagram_repairs,
    apply_diagram_repairs_atomic,
)
from p332_brownfield_diagrams import (
    brownfield_diagram_contract,
    build_brownfield_diagram_map,
    plan_diagram_adoption as plan_p332_diagram_adoption,
    promote_diagram_candidate_atomic,
    plan_legacy_diagram_refactor as plan_p332_legacy_refactor,
    apply_legacy_diagram_refactor_atomic,
)
from p334_rare_feature_registry import (
    rare_feature_registry,
    evaluate_rare_feature as evaluate_p334_rare_feature,
    plan_rare_feature_promotion as plan_p334_rare_feature_promotion,
    ux_regression_contract as p334_ux_regression_contract,
)
from p335_typography import (
    typography_contract as p335_typography_contract,
    build_typography_profile,
    compare_typography_profiles,
)
from p335_paragraph import (
    paragraph_geometry_contract as p335_paragraph_geometry_contract,
    build_paragraph_geometry_profile,
    compare_paragraph_geometry_profiles,
    build_document_style_exemplar,
    build_role_aware_style_exemplars,
    build_style_transfer_operations,
)
from p335_corpus import build_corpus_style_profile, build_style_library
from p313_capture_custody import (
    near_wrap_positive_sensitivity_spec,
    validate_artifact_custody,
    verify_custody_chain,
    adjudicate_cross_version_replay,
)
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

P2_VERSION = "0.13.0-p3.35"
core.VERSION = P2_VERSION
core.PHASE = "P3.35"

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
def get_layout_fidelity_receipt(document_id: str) -> dict:
    """Return renderer-independent page/section, explicit-break and font receipts."""
    metadata, path = _owned_document(document_id)
    receipt = build_hwpx_layout_receipt(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **receipt,
    }


@core.mcp.tool()
def get_production_fidelity_contract() -> dict:
    """Return the current product-facing structural/render fidelity envelope."""
    return {"ok": True, **production_fidelity_contract()}


@core.mcp.tool()
def assess_edit_plan_fidelity(operations: list[dict]) -> dict:
    """Classify a proposed edit plan before mutation and expose its authority ceiling."""
    return {"ok": True, **assess_edit_fidelity_envelope(operations)}


@core.mcp.tool()
def get_document_fidelity_profile(document_id: str) -> dict:
    """Combine one owned document's structural layout receipt with the production fidelity contract."""
    metadata, path = _owned_document(document_id)
    structural = build_hwpx_layout_receipt(path)
    contract = production_fidelity_contract()
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "document_sha256": str(metadata.get("sha256") or ""),
        "structural_receipt": structural,
        "production_contract": contract,
        "authority_semantics": (
            "structural evidence is document-specific; native-render exactness is granted "
            "only to explicitly certified edit classes and the recorded renderer version"
        ),
    }


@core.mcp.tool()
def get_document_setup(document_id: str) -> dict:
    """Return section/page composition including paper, margins, stories, numbering, and columns."""
    metadata, path = _owned_document(document_id)
    setup = build_document_setup_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **setup,
    }


@core.mcp.tool()
def apply_document_setup(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded document-setup transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_document_setup_atomic(
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
        "document_setup_diff": transaction,
        "document_setup": build_document_setup_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def get_structured_publishing(document_id: str) -> dict:
    """Return styles, list/outline state, captions, bookmarks, TOC and cross-reference fields."""
    metadata, path = _owned_document(document_id)
    mapped = build_structured_publishing_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_structured_publishing(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded structured-publishing transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_structured_publishing_atomic(
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
        "structured_publishing_diff": transaction,
        "structured_publishing": build_structured_publishing_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def get_document_plan_contract() -> dict:
    """Return the declarative P3.21 one-shot composition contract for LLM clients."""
    core._caller_subject()
    return {"ok": True, **document_plan_contract()}


@core.mcp.tool()
def validate_document_plan(plan: dict) -> dict:
    """Validate one declarative HWPX plan without creating a document."""
    core._caller_subject()
    return validate_composition_plan(plan)


@core.mcp.tool()
def create_document_from_plan(
    plan: dict,
    filename: str = "document.hwpx",
    template_document_id: str = "",
    request_id: str = "",
) -> dict:
    """Compile one declarative plan into a validated HWPX in a single atomic creation call."""
    owner_subject = core._caller_subject()
    core._cleanup_expired()
    safe_filename = core.sanitize_filename(filename)
    normalized_request_id = str(request_id or "").strip()
    if normalized_request_id and len(normalized_request_id) > 160:
        raise ValueError("request_id exceeds 160 characters")

    template_document_id = str(template_document_id or "").strip()
    template_path = None
    template_metadata = None
    if template_document_id:
        template_metadata = core._load_metadata(template_document_id)
        core._require_owner(template_metadata)
        template_path, _ = core._paths(template_document_id)

    checked = validate_composition_plan(plan)
    fingerprint_payload = {
        "plan_sha256": checked["plan_sha256"],
        "filename": safe_filename,
        "template_document_id": template_document_id or None,
    }
    request_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    document_id = (
        core._idempotent_document_id(owner_subject, normalized_request_id)
        if normalized_request_id
        else core._new_document_id()
    )

    if normalized_request_id:
        try:
            existing = core._load_metadata(document_id)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            core._require_owner(existing)
            if existing.get("create_request_sha256") != request_fingerprint:
                raise RuntimeError(
                    "Idempotency conflict: request_id already used with different composition plan"
                )
            return {
                "ok": True,
                **existing,
                "composition": existing.get("composition_receipt"),
                "idempotent_replay": True,
                "request_id": normalized_request_id,
                "next": "Call export_document for a signed download URL.",
            }

    hwpx_path, _ = core._paths(document_id)
    try:
        composition = compose_document_plan(
            hwpx_path,
            plan,
            template_path=template_path,
            validator=lambda candidate: core.validate_hwpx_package(
                candidate,
                ingress=False,
            ),
        )
        validation = composition["validation"]
        logical_document = plan.get("document") if isinstance(plan, dict) else {}
        title = ""
        if isinstance(logical_document, dict):
            title = str(logical_document.get("title") or "")
        metadata = core._metadata(
            document_id,
            filename=safe_filename,
            owner_subject=owner_subject,
            validation=validation,
            title=title,
            source="generated-plan-template" if template_path is not None else "generated-plan",
        )
        metadata["composition_sha256"] = composition["composition_sha256"]
        metadata["composition_plan_sha256"] = composition["plan_sha256"]
        metadata["composition_block_count"] = int(composition["block_count"])
        metadata["composition_preset"] = composition["preset"]
        metadata["composition_template_document_id"] = template_document_id or None
        metadata["composition_receipt"] = composition
        document_map = build_document_map(hwpx_path)
        formatting_map = build_formatting_map(hwpx_path)
        inline_map = build_inline_map(hwpx_path)
        table_map = build_table_map(hwpx_path)
        object_map = build_object_map(hwpx_path)
        equation_map = build_equation_map(hwpx_path)
        metadata["semantic_sha256"] = document_map["semantic_sha256"]
        metadata["structure_sha256"] = document_map["structure_sha256"]
        metadata["formatting_sha256"] = formatting_map["formatting_sha256"]
        metadata["inline_text_sha256"] = inline_map["inline_text_sha256"]
        metadata["inline_structure_sha256"] = inline_map["inline_structure_sha256"]
        metadata["table_structure_sha256"] = table_map["table_structure_sha256"]
        metadata["table_format_sha256"] = table_map["table_format_sha256"]
        metadata["object_structure_sha256"] = object_map["object_structure_sha256"]
        metadata["object_geometry_sha256"] = object_map["object_geometry_sha256"]
        metadata["media_custody_sha256"] = object_map["media_custody_sha256"]
        metadata["equation_structure_sha256"] = equation_map["equation_structure_sha256"]
        metadata["equation_geometry_sha256"] = equation_map["equation_geometry_sha256"]
        metadata["equation_script_custody_sha256"] = equation_map["equation_script_custody_sha256"]
        if normalized_request_id:
            metadata["create_request_sha256"] = request_fingerprint
            metadata["create_request_id_sha256"] = hashlib.sha256(
                normalized_request_id.encode("utf-8")
            ).hexdigest()
        core._write_metadata(document_id, metadata)
    except Exception:
        core._delete_document_files(document_id)
        raise

    return {
        "ok": True,
        **metadata,
        "composition": composition,
        "idempotent_replay": False,
        "request_id": normalized_request_id or None,
        "next": "Call export_document for a signed download URL.",
    }


@core.mcp.tool()
def get_review_workflow(document_id: str) -> dict:
    """Return tracked changes, form controls, highlights, and document metadata."""
    metadata, path = _owned_document(document_id)
    mapped = build_review_workflow_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_review_workflow(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded native review/forms/metadata transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_review_workflow_atomic(
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
        "review_workflow_diff": transaction,
        "review_workflow": build_review_workflow_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "collaboration": {
            "native_review_marks": True,
            "server_revision_history": True,
            "cas_guarded": True,
            "lease_compatible": True,
        },
    }


@core.mcp.tool()
def get_annotation_apparatus(document_id: str) -> dict:
    """Return footnotes/endnotes, memos, index marks, bookmarks, hyperlinks, and rich fields."""
    metadata, path = _owned_document(document_id)
    mapped = build_annotation_apparatus_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_annotation_apparatus(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded academic/report annotation transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_annotation_apparatus_atomic(
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
        "annotation_apparatus_diff": transaction,
        "annotation_apparatus": build_annotation_apparatus_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def adjudicate_render_world_contact(
    document_id: str,
    render_receipt: dict,
) -> dict:
    """Validate one externally measured Hancom render receipt against the owned HWPX."""
    metadata, path = _owned_document(document_id)
    structural = build_hwpx_layout_receipt(path)
    result = adjudicate_fixture_world_contact(structural, render_receipt)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **result,
    }


@core.mcp.tool()
def get_near_wrap_sensitivity_spec() -> dict:
    """Return the canonical P3.13 positive-sensitivity corpus specification."""
    return {"ok": True, **near_wrap_positive_sensitivity_spec()}


@core.mcp.tool()
def validate_render_capture_custody(bundle: dict) -> dict:
    """Validate one externally produced Windows/Hancom capture custody bundle."""
    return {"ok": True, **validate_artifact_custody(bundle)}


@core.mcp.tool()
def verify_render_capture_chain(bundles: list[dict]) -> dict:
    """Verify an append-only sequence of Windows/Hancom capture bundles."""
    return {"ok": True, **verify_custody_chain(bundles)}


@core.mcp.tool()
def adjudicate_cross_version_render_replay(
    document_id: str,
    trials: list[dict],
    sensitivity: dict = {},
) -> dict:
    """Adjudicate at least two distinct Hancom render versions against one HWPX."""
    metadata, path = _owned_document(document_id)
    structural = build_hwpx_layout_receipt(path)
    result = adjudicate_cross_version_replay(
        structural,
        trials,
        sensitivity or None,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **result,
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


def _canonical_font_face(value: object) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = " ".join(text.split()).strip()
    return text.casefold() or None


def _canonical_color(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text.startswith("#"):
        text = text[1:]
    if re.fullmatch(r"[0-9A-F]{6}", text):
        return f"#{text}"
    return text or None


def _hwp_colorref_to_hex(value: object) -> str:
    raw = int(value or 0)
    red = raw & 0xFF
    green = (raw >> 8) & 0xFF
    blue = (raw >> 16) & 0xFF
    return f"#{red:02X}{green:02X}{blue:02X}"


def _hwp_run_format_subset(run: dict) -> dict:
    shape = run.get("char_shape") or {}
    if not shape or shape.get("fidelity") != "semantic":
        return {}
    fmt = {
        "bold": bool(shape.get("bold")),
        "italic": bool(shape.get("italic")),
        "underline": int(shape.get("underline_type", 0) or 0) != 0,
        "strike": bool(shape.get("strikeout_color") is not None and (int(shape.get("attributes", 0)) >> 18) & 0b111),
    }
    height = int(shape.get("height", 0) or 0)
    if height > 0:
        fmt["size"] = height / 100.0
    if shape.get("text_color") is not None:
        fmt["color"] = _hwp_colorref_to_hex(shape.get("text_color"))
    primary_font = shape.get("primary_font_face")
    if primary_font:
        fmt["font"] = str(primary_font)
    if shape.get("superscript"):
        fmt["script"] = "sup"
    elif shape.get("subscript"):
        fmt["script"] = "sub"
    return fmt


def _hwp_paragraph_format_subset(paragraph: dict) -> dict:
    shape = (paragraph.get("paragraph_style") or {}).get("resolved_para_shape") or {}
    if shape.get("fidelity") != "semantic":
        return {}
    fmt: dict = {}
    alignment = str(shape.get("alignment") or "")
    if alignment in {"LEFT", "RIGHT", "CENTER", "JUSTIFY", "DISTRIBUTE"}:
        fmt["alignment"] = alignment
    def mm(value: object) -> float:
        return round(float(value or 0) * 25.4 / 7200.0, 4)
    def pt(value: object) -> float:
        return round(float(value or 0) / 100.0, 4)
    left = int(shape.get("left_margin_hwpunit", 0) or 0)
    right = int(shape.get("right_margin_hwpunit", 0) or 0)
    indent = int(shape.get("indent_hwpunit", 0) or 0)
    before = int(shape.get("spacing_before_hwpunit", 0) or 0)
    after = int(shape.get("spacing_after_hwpunit", 0) or 0)
    if left:
        fmt["indent_left_mm"] = mm(left)
    if right:
        fmt["indent_right_mm"] = mm(right)
    if indent:
        fmt["first_line_indent_mm"] = mm(indent)
    if before:
        fmt["spacing_before_pt"] = pt(before)
    if after:
        fmt["spacing_after_pt"] = pt(after)
    return fmt


def _hwp_style_signature(run: dict) -> dict:
    fmt = _hwp_run_format_subset(run)
    return {
        "text": str(run.get("text", "")),
        "bold": fmt.get("bold"),
        "italic": fmt.get("italic"),
        "underline": fmt.get("underline"),
        "strike": fmt.get("strike"),
        "size": fmt.get("size"),
        "color": _canonical_color(fmt.get("color")),
        "font": _canonical_font_face(fmt.get("font")),
        "script": fmt.get("script"),
    }


def _hwp_paragraph_style_signature(paragraph: dict) -> dict:
    fmt = _hwp_paragraph_format_subset(paragraph)
    def zero_default(name: str) -> float:
        value = fmt.get(name)
        return 0.0 if value is None else round(float(value), 4)
    return {
        "alignment": fmt.get("alignment"),
        "indent_left_mm": zero_default("indent_left_mm"),
        "indent_right_mm": zero_default("indent_right_mm"),
        "first_line_indent_mm": zero_default("first_line_indent_mm"),
        "spacing_before_pt": zero_default("spacing_before_pt"),
        "spacing_after_pt": zero_default("spacing_after_pt"),
    }


def _hwpx_paragraph_style_signature(paragraph: dict) -> dict:
    prop = paragraph.get("paragraph_property") or {}
    alignment = (prop.get("alignment") or {}).get("horizontal")
    margin_values = prop.get("margin_values") or {}

    def hwpunit_value(name: str) -> float | None:
        item = margin_values.get(name) or {}
        raw = item.get("value")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        unit = str(item.get("unit") or "HWPUNIT").upper()
        if unit != "HWPUNIT":
            return None
        return value

    left = hwpunit_value("left")
    right = hwpunit_value("right")
    intent = hwpunit_value("intent")
    prev = hwpunit_value("prev")
    next_value = hwpunit_value("next")

    def mm(value: float | None) -> float | None:
        return None if value is None else round(value * 25.4 / 7200.0, 4)

    def pt(value: float | None) -> float | None:
        return None if value is None else round(value / 100.0, 4)

    return {
        "alignment": alignment,
        "indent_left_mm": 0.0 if left is None else mm(left),
        "indent_right_mm": 0.0 if right is None else mm(right),
        "first_line_indent_mm": 0.0 if intent is None else mm(intent),
        "spacing_before_pt": 0.0 if prev is None else pt(prev),
        "spacing_after_pt": 0.0 if next_value is None else pt(next_value),
    }


def _hwp_rel_to_horizontal(value: object) -> str:
    return {0: "PAGE", 1: "PAGE", 2: "COLUMN", 3: "PARA"}.get(int(value or 0), "COLUMN")


def _hwp_rel_to_vertical(value: object) -> str:
    return {0: "PAPER", 1: "PAGE", 2: "PARA"}.get(int(value or 0), "PARA")


@core.mcp.tool()
def get_hwp5_style_map(
    content_base64: str,
    filename: str = "document.hwp",
    start_paragraph: int = 0,
    paragraph_count: int = 100,
    include_face_catalog: bool = True,
) -> dict:
    """Return bounded canonical run/font/paragraph-style receipts for one HWP 5.x source."""
    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    safe_name = Path(filename or "document.hwp").name[:128]
    if not parsed.get("readable"):
        return {
            "ok": True,
            "filename": safe_name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "readable": False,
            "block_reason": parsed.get("block_reason"),
            "paragraphs": [],
        }

    all_paragraphs = parsed.get("paragraphs", [])
    start = max(0, int(start_paragraph))
    count = max(1, min(int(paragraph_count), 500))
    end = min(len(all_paragraphs), start + count)
    paragraphs = []
    for item in all_paragraphs[start:end]:
        runs = []
        for run in item.get("runs", []):
            runs.append({
                "start": run.get("start"),
                "end": run.get("end"),
                "text": run.get("text", ""),
                "char_shape_id": run.get("char_shape_id"),
                "visible_span_fidelity": run.get("visible_span_fidelity"),
                "style": _hwp_style_signature(run),
            })
        paragraphs.append({
            "paragraph_index": item.get("paragraph_index"),
            "section_index": item.get("section_index"),
            "source_paragraph_ordinal": item.get("source_paragraph_ordinal"),
            "flow_kind": item.get("flow_kind"),
            "control_index": item.get("control_index"),
            "text": item.get("text", ""),
            "para_shape_id": (item.get("paragraph_style") or {}).get("para_shape_id"),
            "para_style_id": (item.get("paragraph_style") or {}).get("para_style_id"),
            "paragraph_style": _hwp_paragraph_style_signature(item),
            "runs": runs,
        })

    face_catalog = None
    if include_face_catalog:
        face_catalog = {
            language: [
                {
                    "font_id": face.get("font_id"),
                    "face": face.get("face"),
                    "alternative_face": face.get("alternative_face"),
                    "default_face": face.get("default_face"),
                }
                for face in faces
            ]
            for language, faces in (parsed.get("face_names") or {}).items()
        }

    return {
        "ok": True,
        "filename": safe_name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "version": parsed.get("version"),
        "readable": True,
        "start_paragraph": start,
        "end_paragraph_exclusive": end,
        "returned_paragraphs": len(paragraphs),
        "paragraph_count": len(all_paragraphs),
        "has_more": end < len(all_paragraphs),
        "next_start_paragraph": end if end < len(all_paragraphs) else None,
        "font_faces": face_catalog,
        "paragraphs": paragraphs,
        "authority": "CANONICAL_HWP_STYLE_MAP",
        "canonicalization": {
            "font": "FaceName-resolved NFKC/casefold semantic name",
            "color": "canonical #RRGGBB",
            "paragraph_units": "HWPUNIT converted to mm/pt semantic coordinates",
        },
    }


@core.mcp.tool()
def get_paragraph_style_provenance(
    document_id: str = "",
    content_base64: str = "",
    filename: str = "document.hwp",
    max_paragraphs: int = 200,
) -> dict:
    """Return paragraph-style reference provenance for either HWP5 or owned HWPX."""
    limit = max(1, min(int(max_paragraphs), 1000))
    has_hwpx = bool(str(document_id or "").strip())
    has_hwp = bool(str(content_base64 or "").strip())
    if has_hwpx == has_hwp:
        raise ValueError("Provide exactly one of document_id or content_base64")
    if has_hwp:
        payload = _decode_hwp5_payload(content_base64)
        parsed = parse_hwp5_bytes(payload)
        if not parsed.get("readable"):
            raise ValueError(
                f"HWP source is not readable by the native lane: {parsed.get('block_reason')}"
            )
        paragraphs = []
        for item in parsed.get("paragraphs", [])[:limit]:
            style = item.get("paragraph_style") or {}
            resolved = style.get("resolved_style") or {}
            paragraphs.append({
                "paragraph_index": item.get("paragraph_index"),
                "flow_kind": item.get("flow_kind"),
                "para_shape_id": style.get("para_shape_id"),
                "para_style_id": style.get("para_style_id"),
                "direct_para_shape": style.get("resolved_para_shape"),
                "resolved_style": resolved,
                "style_para_shape": style.get("style_para_shape"),
                "style_char_shape": style.get("style_char_shape"),
                "provenance": {
                    "paragraph_header_para_shape_id": style.get("para_shape_id"),
                    "paragraph_header_style_id": style.get("para_style_id"),
                    "style_para_shape_id": resolved.get("para_shape_id"),
                    "style_char_shape_id": resolved.get("char_shape_id"),
                    "direct_matches_style_para_shape": (
                        style.get("para_shape_id") is not None
                        and resolved.get("para_shape_id") is not None
                        and int(style.get("para_shape_id")) == int(resolved.get("para_shape_id"))
                    ),
                },
            })
        return {
            "ok": True,
            "source_format": "hwp5",
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "paragraph_count": len(parsed.get("paragraphs", [])),
            "returned_paragraphs": len(paragraphs),
            "paragraphs": paragraphs,
            "authority": "STYLE_REFERENCE_PROVENANCE_GRAPH",
        }

    metadata, path = _owned_document(document_id)
    formatting = build_formatting_map(path)
    paragraphs = []
    for item in formatting.get("paragraphs", [])[:limit]:
        style = item.get("style_property") or {}
        paragraphs.append({
            "locator": item.get("locator"),
            "container": item.get("container"),
            "para_pr_id_ref": item.get("para_pr_id_ref"),
            "style_id_ref": item.get("style_id_ref"),
            "direct_para_property": item.get("paragraph_property"),
            "resolved_style": style,
            "provenance": {
                "paragraph_para_pr_id_ref": item.get("para_pr_id_ref"),
                "paragraph_style_id_ref": item.get("style_id_ref"),
                "style_para_pr_id_ref": style.get("para_pr_id_ref"),
                "style_char_pr_id_ref": style.get("char_pr_id_ref"),
                "direct_matches_style_para_pr": (
                    item.get("para_pr_id_ref") is not None
                    and style.get("para_pr_id_ref") is not None
                    and str(item.get("para_pr_id_ref")) == str(style.get("para_pr_id_ref"))
                ),
            },
        })
    return {
        "ok": True,
        "source_format": "hwpx",
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        "paragraph_count": len(formatting.get("paragraphs", [])),
        "returned_paragraphs": len(paragraphs),
        "paragraphs": paragraphs,
        "authority": "STYLE_REFERENCE_PROVENANCE_GRAPH",
    }


@core.mcp.tool()
def get_hwp5_text_flows(
    content_base64: str,
    filename: str = "document.hwp",
    include_paragraphs: bool = True,
) -> dict:
    """Return body/header/footer/footnote/endnote/object-text paragraph ownership from HWP5."""
    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    if not parsed.get("readable"):
        return {
            "ok": True,
            "filename": Path(filename or "document.hwp").name[:128],
            "readable": False,
            "block_reason": parsed.get("block_reason"),
            "flows": {},
        }
    grouped: dict[str, list[dict]] = {}
    for paragraph in parsed.get("paragraphs", []):
        flow = str(paragraph.get("flow_kind") or "body")
        item = {
            "paragraph_index": paragraph.get("paragraph_index"),
            "section_index": paragraph.get("section_index"),
            "source_paragraph_ordinal": paragraph.get("source_paragraph_ordinal"),
            "control_index": paragraph.get("control_index"),
            "control_id": paragraph.get("control_id"),
            "para_shape_id": (paragraph.get("paragraph_style") or {}).get("para_shape_id"),
            "para_style_id": (paragraph.get("paragraph_style") or {}).get("para_style_id"),
            "run_count": len(paragraph.get("runs", [])),
            "run_visible_span_fidelity": paragraph.get("run_visible_span_fidelity"),
            "text": paragraph.get("text", ""),
        }
        grouped.setdefault(flow, []).append(item)
    return {
        "ok": True,
        "filename": Path(filename or "document.hwp").name[:128],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "readable": True,
        "flow_counts": {key: len(value) for key, value in grouped.items()},
        "flows": grouped if include_paragraphs else {
            key: {"paragraph_count": len(value)}
            for key, value in grouped.items()
        },
        "authority": "STRUCTURAL_NESTED_TEXT_FLOW_GRAPH",
    }


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


def _apply_formatting_batched_atomic(
    path: Path,
    operations: list[dict],
    *,
    validator,
    batch_size: int = 100,
) -> dict:
    if not operations:
        return {
            "operation_count": 0,
            "batch_count": 0,
            "after": build_formatting_map(path),
        }
    size = max(1, min(int(batch_size), 100))
    original = path.read_bytes()
    batch_count = 0
    total = 0
    try:
        for start in range(0, len(operations), size):
            batch = operations[start:start + size]
            result = apply_rich_formatting_atomic(
                path,
                batch,
                expected_revision=1,
                current_revision=1,
                validator=validator,
            )
            total += int(result.get("operation_count", len(batch)))
            batch_count += 1
        return {
            "operation_count": total,
            "batch_count": batch_count,
            "after": build_formatting_map(path),
        }
    except Exception:
        path.write_bytes(original)
        raise


@core.mcp.tool()
def materialize_hwp5_rich_derivative(
    content_base64: str,
    filename: str = "document.hwp",
    title: str = "",
    request_id: str = "",
    promote_tables: bool = True,
    promote_equations: bool = True,
    promote_pictures: bool = True,
    promote_textboxes: bool = True,
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
        f"hwp5-rich-v3:{source_sha256}:{normalized_request_id}"
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
        if item.get("flow_kind") == "body"
        and item.get("list_header_record_index") is None
    ]
    if not top_level:
        top_level = list(parsed.get("paragraphs", []))
    base_text = "\n".join(str(item.get("text", "")) for item in top_level)
    if not base_text:
        base_text = " "

    hwpx_path, _ = core._paths(document_id)
    derivative_title = title or Path(source_name).stem
    core.materialize_hwpx(hwpx_path, base_text, "")

    promotion_report = {
        "paragraph_text": {"status": "PROMOTED", "count": len(top_level)},
        "run_styles": {"promoted_runs": 0, "deferred": []},
        "paragraph_styles": {"promoted_paragraphs": 0, "deferred": []},
        "nested_text_flows": {
            "recovered": sum(
                1 for item in parsed.get("paragraphs", [])
                if item.get("flow_kind") != "body"
            ),
            "promoted": 0,
            "authority": "RECOVERED_GRAPH / FAMILY_GRADED_PROMOTION",
            "families": {
                "object-text": {
                    "status": "DEFERRED",
                    "reason": "no_rectangle_certified_object_text_promoted_yet",
                    "promoted_controls": 0,
                    "deferred": [],
                }
            },
        },
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

        pending_textboxes: list[dict] = []

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
                            "width": max(1, int(cell.get("width", 0) or 0)),
                            "height": max(1, int(cell.get("height", 0) or 0)),
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

                    # HWP stores the material cell's visible span extent in
                    # width/height. paragraph.add_table starts from an even grid,
                    # and merge_cells may recompute the merged anchor extent.
                    # Restore the certified source geometry *after* merges.
                    for cell in material_cells:
                        created_table.cell(
                            cell["row"], cell["col"]
                        ).set_size(
                            width=cell["width"],
                            height=cell["height"],
                        )
                    promotion_report["tables"].setdefault(
                        "geometry_receipts", []
                    ).append({
                        "table_index": table_index,
                        "material_cell_count": len(material_cells),
                        "source_cell_sizes_applied": True,
                        "authority": "STRUCTURAL_HWPUNIT_CELL_GEOMETRY",
                    })
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
        nested_groups: dict[str, list[dict]] = {}
        for item in parsed.get("paragraphs", []):
            flow = str(item.get("flow_kind") or "body")
            if flow == "body":
                continue
            nested_groups.setdefault(flow, []).append(item)

        # Header/footer controls carry a page-scope code. Group paragraphs by
        # owning control so multiple stories (BOTH/EVEN/ODD) are not collapsed.
        for flow, setter_name in (("header", "set_header_text"), ("footer", "set_footer_text")):
            items = nested_groups.get(flow, [])
            if not items:
                continue
            by_control: dict[int, list[dict]] = {}
            unbound: list[dict] = []
            for item in items:
                control_index = item.get("control_index")
                if control_index is None:
                    unbound.append(item)
                    continue
                by_control.setdefault(int(control_index), []).append(item)
            promoted_controls = 0
            deferred: list[dict] = []
            for control_index, owned in sorted(by_control.items()):
                control = controls.get(control_index) or {}
                page_type = str(control.get("apply_page_type") or "")
                if page_type not in {"BOTH", "EVEN", "ODD"}:
                    deferred.append({
                        "control_index": control_index,
                        "reason": "page_scope_not_resolved",
                    })
                    continue
                section_indexes = {int(item.get("section_index", 0)) for item in owned}
                if len(section_indexes) != 1:
                    deferred.append({
                        "control_index": control_index,
                        "reason": "cross_section_story_ambiguous",
                    })
                    continue
                section_index = next(iter(section_indexes))
                try:
                    section = document.sections[section_index]
                    setter = getattr(section.properties, setter_name)
                    setter(
                        "\n".join(str(item.get("text", "")) for item in owned),
                        page_type=page_type,
                    )
                    promoted_controls += 1
                except Exception as exc:
                    deferred.append({
                        "control_index": control_index,
                        "reason": f"{type(exc).__name__}:{str(exc)[:180]}",
                    })
            if unbound:
                deferred.append({
                    "reason": "paragraph_without_owner_control",
                    "paragraph_count": len(unbound),
                })
            promoted_paragraphs = sum(
                len(by_control[index])
                for index in by_control
                if not any(
                    item.get("control_index") == index
                    for item in deferred
                )
            )
            promotion_report["nested_text_flows"]["promoted"] += promoted_paragraphs
            promotion_report["nested_text_flows"].setdefault("families", {})[flow] = {
                "status": (
                    "PROMOTED_NATIVE"
                    if promoted_controls and not deferred
                    else ("PARTIAL" if promoted_controls else "DEFERRED")
                ),
                "promoted_controls": promoted_controls,
                "paragraph_count": len(items),
                "deferred": deferred[:20],
            }

        # One HWP note control can own several paragraphs. Preserve that unit:
        # one recovered control becomes one native HWPX footnote/endnote.
        for flow, method_name in (("footnote", "add_footnote"), ("endnote", "add_endnote")):
            items = nested_groups.get(flow, [])
            if not items:
                continue
            by_control: dict[int, list[dict]] = {}
            unbound: list[dict] = []
            for item in items:
                control_index = item.get("control_index")
                if control_index is None:
                    unbound.append(item)
                    continue
                by_control.setdefault(int(control_index), []).append(item)
            promoted_controls = 0
            deferred: list[dict] = []
            for control_index, owned in sorted(by_control.items()):
                control = controls.get(control_index)
                ordinal = None if control is None else control.get("anchor_paragraph_ordinal")
                section_indexes = {int(item.get("section_index", 0)) for item in owned}
                locator = None
                if ordinal is not None and len(section_indexes) == 1:
                    locator = anchor_map.get((next(iter(section_indexes)), int(ordinal)))
                if not locator:
                    deferred.append({
                        "control_index": control_index,
                        "reason": "owner_anchor_missing",
                    })
                    continue
                try:
                    paragraph, _target = _resolve_hwpx_paragraph(
                        document, hwpx_path, locator
                    )
                    note_text = "\n".join(str(item.get("text", "")) for item in owned)
                    getattr(paragraph, method_name)(note_text)
                    promoted_controls += 1
                except Exception as exc:
                    deferred.append({
                        "control_index": control_index,
                        "reason": f"{type(exc).__name__}:{str(exc)[:180]}",
                    })
            if unbound:
                deferred.append({
                    "reason": "paragraph_without_owner_control",
                    "paragraph_count": len(unbound),
                })
            promotion_report["nested_text_flows"]["promoted"] += sum(
                len(value) for key, value in by_control.items()
                if not any(item.get("control_index") == key for item in deferred)
            )
            promotion_report["nested_text_flows"].setdefault("families", {})[flow] = {
                "status": (
                    "PROMOTED_NATIVE"
                    if promoted_controls and not deferred
                    else ("PARTIAL" if promoted_controls else "DEFERRED")
                ),
                "promoted_controls": promoted_controls,
                "source_paragraph_count": len(items),
                "deferred": deferred[:20],
            }

        object_items = nested_groups.get("object-text", [])
        object_by_control: dict[int, list[dict]] = {}
        object_deferred: list[dict] = []
        for item in object_items:
            control_index = item.get("control_index")
            if control_index is None:
                object_deferred.append({
                    "reason": "paragraph_without_owner_control",
                    "paragraph_index": item.get("paragraph_index"),
                })
                continue
            object_by_control.setdefault(int(control_index), []).append(item)
        if promote_textboxes:
            for control_index, owned in sorted(object_by_control.items()):
                control = controls.get(control_index) or {}
                if control.get("shape_family") != "rectangle":
                    object_deferred.append({
                        "control_index": control_index,
                        "reason": "source_shape_family_not_certified_rectangle",
                        "shape_family": control.get("shape_family"),
                    })
                    continue
                ordinal = control.get("anchor_paragraph_ordinal")
                section_indexes = {int(item.get("section_index", 0)) for item in owned}
                locator = None
                if ordinal is not None and len(section_indexes) == 1:
                    locator = anchor_map.get((next(iter(section_indexes)), int(ordinal)))
                width = int(control.get("width") or 0)
                height = int(control.get("height") or 0)
                if not locator or width <= 0 or height <= 0:
                    object_deferred.append({
                        "control_index": control_index,
                        "reason": "textbox_anchor_or_geometry_incomplete",
                        "anchor_resolved": bool(locator),
                        "width": width,
                        "height": height,
                    })
                    continue
                pending_textboxes.append({
                    "control_index": control_index,
                    "anchor_locator": locator,
                    "paragraphs": [str(item.get("text", "")) for item in owned],
                    "width": width,
                    "height": height,
                    "treat_as_char": bool(control.get("treat_as_char")),
                    "horizontal_offset": int(control.get("horizontal_offset") or 0),
                    "vertical_offset": int(control.get("vertical_offset") or 0),
                    "horz_rel_to": _hwp_rel_to_horizontal(control.get("horz_rel_to")),
                    "vert_rel_to": _hwp_rel_to_vertical(control.get("vert_rel_to")),
                    "z_order": int(control.get("z_order") or 0),
                })
        elif object_items:
            object_deferred.append({"reason": "textbox_promotion_disabled"})

        object_family = promotion_report["nested_text_flows"]["families"]["object-text"]
        object_family["source_paragraph_count"] = len(object_items)
        object_family["source_control_count"] = len(object_by_control)
        object_family["deferred"] = object_deferred[:20]
        object_family["status"] = "PENDING" if pending_textboxes else "DEFERRED"

        if promotion_report["nested_text_flows"]["promoted"] > 0:
            promotion_report["nested_text_flows"]["authority"] = (
                "FAMILY_GRADED_NATIVE_PROMOTION"
            )

    finally:
        document.close()

    textbox_family = promotion_report["nested_text_flows"]["families"]["object-text"]
    promoted_textbox_controls = 0
    textbox_receipts: list[dict] = []
    textbox_deferred = list(textbox_family.get("deferred") or [])
    for spec in pending_textboxes:
        try:
            receipt = inject_textbox(
                hwpx_path,
                anchor_locator=spec["anchor_locator"],
                paragraphs=spec["paragraphs"],
                width=spec["width"],
                height=spec["height"],
                treat_as_char=spec["treat_as_char"],
                horizontal_offset=spec["horizontal_offset"],
                vertical_offset=spec["vertical_offset"],
                horz_rel_to=spec["horz_rel_to"],
                vert_rel_to=spec["vert_rel_to"],
                z_order=spec["z_order"],
                shape_seed=f"{source_sha256}:{spec['control_index']}",
            )
            core.validate_hwpx_package(hwpx_path, ingress=False)
            mapped_boxes = build_textbox_map(hwpx_path)
            created = next(
                (
                    box for box in mapped_boxes.get("textboxes", [])
                    if box.get("shape_id") == receipt.get("shape_id")
                ),
                None,
            )
            if created is None:
                raise ValueError("native textbox could not be re-read after synthesis")
            receipt["verified_geometry"] = {
                "width": created.get("width"),
                "height": created.get("height"),
                "position": created.get("position"),
                "paragraphs": created.get("paragraphs"),
            }
            textbox_receipts.append(receipt)
            promoted_textbox_controls += 1
            promotion_report["nested_text_flows"]["promoted"] += len(spec["paragraphs"])
        except Exception as exc:
            textbox_deferred.append({
                "control_index": spec.get("control_index"),
                "reason": f"textbox_promotion_refused:{type(exc).__name__}",
                "detail": str(exc)[:240],
            })
    textbox_family["promoted_controls"] = promoted_textbox_controls
    textbox_family["receipts"] = textbox_receipts
    textbox_family["deferred"] = textbox_deferred[:20]
    textbox_family["reason"] = (
        None
        if promoted_textbox_controls
        else "no_rectangle_certified_object_text_promoted"
    )
    textbox_family["status"] = (
        "PROMOTED_NATIVE"
        if promoted_textbox_controls and not textbox_deferred
        else ("PARTIAL" if promoted_textbox_controls else "DEFERRED")
    )
    if promotion_report["nested_text_flows"]["promoted"] > 0:
        promotion_report["nested_text_flows"]["authority"] = "FAMILY_GRADED_NATIVE_PROMOTION"

    # Promote only source-coordinate-safe top-level run styles. Nested/control-bearing
    # flows remain provenance until a dedicated native HWPX control writer is certified.
    style_operations: list[dict] = []
    post_object_map = build_document_map(hwpx_path)
    post_top_level = [
        item for item in post_object_map.get("paragraphs", [])
        if item.get("container") == "section-body"
    ]
    for source_para, target_para in zip(top_level, post_top_level):
        for run in source_para.get("runs", []):
            if not run.get("visible_span_certified"):
                promotion_report["run_styles"]["deferred"].append({
                    "paragraph_index": source_para.get("paragraph_index"),
                    "char_shape_id": run.get("char_shape_id"),
                    "reason": "visible_span_not_certified",
                })
                continue
            start = int(run.get("visible_start", 0))
            end = int(run.get("visible_end", 0))
            fmt = _hwp_run_format_subset(run)
            if end <= start or not fmt:
                continue
            style_operations.append({
                "op": "set_range_format",
                "target": target_para["locator"],
                "start": start,
                "end": end,
                "format": fmt,
            })
    if style_operations:
        try:
            style_result = _apply_formatting_batched_atomic(
                hwpx_path,
                style_operations,
                validator=lambda candidate: core.validate_hwpx_package(
                    candidate, ingress=False
                ),
            )
            promotion_report["run_styles"]["promoted_runs"] = int(
                style_result.get("operation_count", 0)
            )
            promotion_report["run_styles"]["formatting_sha256_after"] = (
                style_result.get("after", {}).get("formatting_sha256")
            )
        except Exception as exc:
            promotion_report["run_styles"]["deferred"].append({
                "reason": f"formatting_promotion_refused:{type(exc).__name__}",
                "detail": str(exc)[:240],
            })

    paragraph_style_operations: list[dict] = []
    refreshed_map = build_document_map(hwpx_path)
    refreshed_top = [
        item for item in refreshed_map.get("paragraphs", [])
        if item.get("container") == "section-body"
    ]
    for source_para, target_para in zip(top_level, refreshed_top):
        fmt = _hwp_paragraph_format_subset(source_para)
        if not fmt:
            continue
        paragraph_style_operations.append({
            "op": "set_paragraph_format",
            "target": target_para["locator"],
            "format": fmt,
        })
    if paragraph_style_operations:
        try:
            para_result = _apply_formatting_batched_atomic(
                hwpx_path,
                paragraph_style_operations,
                validator=lambda candidate: core.validate_hwpx_package(
                    candidate, ingress=False
                ),
            )
            promotion_report["paragraph_styles"]["promoted_paragraphs"] = int(
                para_result.get("operation_count", 0)
            )
            promotion_report["paragraph_styles"]["formatting_sha256_after"] = (
                para_result.get("after", {}).get("formatting_sha256")
            )
        except Exception as exc:
            promotion_report["paragraph_styles"]["deferred"].append({
                "reason": f"paragraph_formatting_refused:{type(exc).__name__}",
                "detail": str(exc)[:240],
            })

    validation = core.validate_hwpx_package(hwpx_path, ingress=False)
    final_map = build_document_map(hwpx_path)
    final_tables = build_table_map(hwpx_path)
    final_equations = build_equation_map(hwpx_path)
    final_objects = build_object_map(hwpx_path)
    final_textboxes = build_textbox_map(hwpx_path)
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
        "textbox_geometry_sha256": final_textboxes["textbox_geometry_sha256"],
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
            "textboxes": final_textboxes["textbox_count"],
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
def get_page_geometry(document_id: str) -> dict:
    """Return section page-size/margin geometry for one owned HWPX document."""
    metadata, path = _owned_document(document_id)
    mapped = build_page_geometry_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
        "fidelity_ceiling": "VERSION_INDEXED_BOUNDARY",
        "renderer_scope": "Hancom Hangul 13.0.0.3622",
    }


@core.mcp.tool()
def apply_page_geometry(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply revision-guarded page-margin edits with P3.16 boundary authority."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_page_geometry_edits_atomic(
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
        "page_geometry_diff": transaction,
        "page_geometry": build_page_geometry_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
    }


@core.mcp.tool()
def get_advanced_table_contract() -> dict:
    """Return the admitted P3.23 advanced-table contract and explicit evidence gates."""
    core._caller_subject()
    return {"ok": True, **advanced_table_contract()}


@core.mcp.tool()
def get_advanced_tables(document_id: str) -> dict:
    """Return table geometry, repeat-header state, row geometry, and vertical alignment."""
    metadata, path = _owned_document(document_id)
    mapped = build_advanced_table_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_advanced_table_edits(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.23 advanced-table transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_advanced_table_edits_atomic(
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
    after_tables = build_advanced_table_map(path)
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
        "advanced_table_diff": transaction,
        "advanced_tables": build_advanced_table_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "collaboration": {
            "server_revision_history": True,
            "cas_guarded": True,
            "lease_compatible": True,
        },
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
def compare_hwp5_roundtrip_fidelity(
    content_base64: str,
    document_id: str,
    filename: str = "document.hwp",
    require_provenance: bool = True,
) -> dict:
    """Compare a source HWP5 payload with one owned promoted HWPX derivative by family."""
    payload = _decode_hwp5_payload(content_base64)
    parsed = parse_hwp5_bytes(payload)
    if not parsed.get("readable"):
        raise ValueError(
            f"HWP source is not readable by the native lane: {parsed.get('block_reason')}"
        )
    metadata, path = _owned_document(document_id)
    source_sha256 = hashlib.sha256(payload).hexdigest()
    provenance_match = metadata.get("source_hwp_sha256") == source_sha256
    if require_provenance and not provenance_match:
        return {
            "ok": False,
            "document_id": document_id,
            "source_filename": Path(filename or "document.hwp").name[:128],
            "source_sha256": source_sha256,
            "provenance_match": False,
            "authority": "SOURCE_PROVENANCE_MISMATCH",
            "families": {},
        }

    document_map = build_document_map(path)
    formatting_map = build_formatting_map(path)
    table_map = build_table_map(path)
    equation_map = build_equation_map(path)
    object_map = build_object_map(path)

    source_top = [
        item for item in parsed.get("paragraphs", [])
        if item.get("flow_kind") == "body"
        and item.get("list_header_record_index") is None
    ]
    target_top = [
        item for item in formatting_map.get("paragraphs", [])
        if item.get("container") == "section-body"
    ]
    source_text = [str(item.get("text", "")) for item in source_top]
    target_text_all = [
        str(item.get("direct_text", item.get("text", "")))
        for item in target_top
    ]
    target_text = target_text_all[:len(source_top)]
    strict_text_exact = source_text == target_text

    # HWP and HWPX may encode visually empty/space-only paragraphs differently.
    # Preserve that as a strict-structure diagnostic, but compare body-text
    # semantics on the nonblank paragraph stream without changing nonblank text.
    source_semantic_text = [item for item in source_text if item.strip()]
    target_semantic_text = [item for item in target_text_all if item.strip()]
    semantic_text_exact = source_semantic_text == target_semantic_text

    text_mismatches = []
    for paragraph_index, (left, right) in enumerate(zip(source_semantic_text, target_semantic_text)):
        if left == right:
            continue
        prefix = 0
        for a, b in zip(left, right):
            if a != b:
                break
            prefix += 1
        text_mismatches.append({
            "paragraph_index": paragraph_index,
            "source_chars": len(left),
            "target_chars": len(right),
            "common_prefix_chars": prefix,
            "source_excerpt": left[max(0, prefix - 40):prefix + 120],
            "target_excerpt": right[max(0, prefix - 40):prefix + 120],
            "source_sha256": hashlib.sha256(left.encode("utf-8")).hexdigest(),
            "target_sha256": hashlib.sha256(right.encode("utf-8")).hexdigest(),
        })
        if len(text_mismatches) >= 8:
            break

    source_style_runs = []
    for paragraph in [item for item in source_top if str(item.get("text", "")).strip()]:
        source_style_runs.append([
            _hwp_style_signature(run)
            for run in paragraph.get("runs", [])
            if run.get("visible_span_certified") and str(run.get("text", ""))
        ])
    target_style_runs = []
    for paragraph in [
        item for item in target_top
        if str(item.get("direct_text", item.get("text", ""))).strip()
    ][:len(source_style_runs)]:
        runs = []
        for run in paragraph.get("runs", []):
            if not str(run.get("text", "")):
                continue
            style = run.get("style") or {}
            runs.append({
                "text": str(run.get("text", "")),
                "bold": style.get("bold"),
                "italic": style.get("italic"),
                "underline": style.get("underline"),
                "strike": style.get("strike"),
                "size": style.get("size_pt"),
                "color": _canonical_color(style.get("text_color")),
                "font": _canonical_font_face(style.get("primary_font_face")),
                "script": style.get("script"),
            })
        target_style_runs.append(runs)

    comparable_style_paragraphs = 0
    exact_style_paragraphs = 0
    segmentation_exact_paragraphs = 0
    run_style_axis_matches = {
        "text": 0,
        "bold": 0,
        "italic": 0,
        "underline": 0,
        "strike": 0,
        "size": 0,
        "color": 0,
        "font": 0,
        "script": 0,
    }
    run_style_axis_comparisons = {key: 0 for key in run_style_axis_matches}
    for expected, observed in zip(source_style_runs, target_style_runs):
        if not expected:
            continue
        comparable_style_paragraphs += 1
        if len(expected) != len(observed):
            continue
        segmentation_exact_paragraphs += 1
        ok = True
        for left, right in zip(expected, observed):
            for key in ("text", "bold", "italic", "underline", "strike", "color", "font", "script"):
                run_style_axis_comparisons[key] += 1
                if left.get(key) == right.get(key):
                    run_style_axis_matches[key] += 1
                else:
                    ok = False
            left_size = left.get("size")
            right_size = right.get("size")
            if left_size is not None and right_size is not None:
                run_style_axis_comparisons["size"] += 1
                if abs(float(left_size) - float(right_size)) <= 0.02:
                    run_style_axis_matches["size"] += 1
                else:
                    ok = False
            elif left_size is None and right_size is None:
                run_style_axis_comparisons["size"] += 1
                run_style_axis_matches["size"] += 1
            else:
                run_style_axis_comparisons["size"] += 1
                ok = False
        if ok:
            exact_style_paragraphs += 1

    source_para_styles = [
        _hwp_paragraph_style_signature(item)
        for item in source_top
        if str(item.get("text", "")).strip()
    ]
    target_para_styles = [
        _hwpx_paragraph_style_signature(item)
        for item in target_top
        if str(item.get("direct_text", item.get("text", ""))).strip()
    ][:len(source_para_styles)]
    paragraph_style_comparable = 0
    paragraph_style_exact = 0
    paragraph_style_mismatches = []
    paragraph_style_axis_matches = {
        "alignment": 0,
        "indent_left_mm": 0,
        "indent_right_mm": 0,
        "first_line_indent_mm": 0,
        "spacing_before_pt": 0,
        "spacing_after_pt": 0,
    }
    for expected, observed in zip(source_para_styles, target_para_styles):
        paragraph_style_comparable += 1
        axes_ok = True
        for key in paragraph_style_axis_matches:
            left = expected.get(key)
            right = observed.get(key)
            if left is None and right is None:
                paragraph_style_axis_matches[key] += 1
                continue
            if key == "alignment":
                same = left == right
            else:
                same = (
                    left is not None and right is not None
                    and abs(float(left) - float(right)) <= 0.05
                )
            if same:
                paragraph_style_axis_matches[key] += 1
            else:
                axes_ok = False
        if axes_ok:
            paragraph_style_exact += 1
        elif len(paragraph_style_mismatches) < 8:
            source_para = [
                item for item in source_top if str(item.get("text", "")).strip()
            ][paragraph_style_comparable - 1]
            target_para = [
                item for item in target_top
                if str(item.get("direct_text", item.get("text", ""))).strip()
            ][paragraph_style_comparable - 1]
            source_style_meta = source_para.get("paragraph_style") or {}
            target_style_meta = target_para.get("style_property") or {}
            paragraph_style_mismatches.append({
                "paragraph_index": paragraph_style_comparable - 1,
                "source": expected,
                "target": observed,
                "source_provenance": {
                    "para_shape_id": source_style_meta.get("para_shape_id"),
                    "para_style_id": source_style_meta.get("para_style_id"),
                    "style_name": (source_style_meta.get("resolved_style") or {}).get("local_name"),
                    "style_para_shape_id": (source_style_meta.get("resolved_style") or {}).get("para_shape_id"),
                    "direct_matches_style_para_shape": (
                        source_style_meta.get("para_shape_id") is not None
                        and (source_style_meta.get("resolved_style") or {}).get("para_shape_id") is not None
                        and int(source_style_meta.get("para_shape_id"))
                        == int((source_style_meta.get("resolved_style") or {}).get("para_shape_id"))
                    ),
                },
                "target_provenance": {
                    "para_pr_id_ref": target_para.get("para_pr_id_ref"),
                    "style_id_ref": target_para.get("style_id_ref"),
                    "style_name": target_style_meta.get("name"),
                    "style_para_pr_id_ref": target_style_meta.get("para_pr_id_ref"),
                    "direct_matches_style_para_pr": (
                        target_para.get("para_pr_id_ref") is not None
                        and target_style_meta.get("para_pr_id_ref") is not None
                        and str(target_para.get("para_pr_id_ref"))
                        == str(target_style_meta.get("para_pr_id_ref"))
                    ),
                },
            })

    source_tables = parsed.get("tables", [])
    target_tables = table_map.get("tables", [])
    source_table_geometry = sorted(
        (int(item.get("row_count", 0)), int(item.get("col_count", 0)))
        for item in source_tables
    )
    target_table_geometry = sorted(
        (int(item.get("rows", 0)), int(item.get("cols", 0)))
        for item in target_tables
    )
    source_table_cells = [
        sorted(
            (
                int(cell.get("row", 0)),
                int(cell.get("column", 0)),
                int(cell.get("row_span", 1) or 1),
                int(cell.get("col_span", 1) or 1),
                int(cell.get("width", 0) or 0),
                int(cell.get("height", 0) or 0),
            )
            for cell in item.get("cells", [])
            if cell.get("row") is not None and cell.get("column") is not None
        )
        for item in source_tables
    ]
    target_table_cells = [
        sorted(
            (
                int(cell.get("row", 0)),
                int(cell.get("col", 0)),
                int(cell.get("row_span", 1) or 1),
                int(cell.get("col_span", 1) or 1),
                int(cell.get("width", 0) or 0),
                int(cell.get("height", 0) or 0),
            )
            for cell in item.get("cells", [])
        )
        for item in target_tables
    ]
    table_cell_geometry_exact = (
        len(source_table_cells) == len(target_table_cells)
        and source_table_cells == target_table_cells
    )

    source_equations = sorted(
        str(item.get("script", "")) for item in parsed.get("equations", [])
    )
    target_equations = sorted(
        str(item.get("script", "")) for item in equation_map.get("equations", [])
    )
    source_equation_geometry = sorted(
        (
            int((item.get("position") or {}).get("width", 0) or 0),
            int((item.get("position") or {}).get("height", 0) or 0),
        )
        for item in parsed.get("equations", [])
    )
    target_equation_geometry = sorted(
        (int(item.get("width", 0) or 0), int(item.get("height", 0) or 0))
        for item in equation_map.get("equations", [])
    )
    equation_geometry_exact = (
        len(source_equation_geometry) == len(target_equation_geometry)
        and source_equation_geometry == target_equation_geometry
    )

    source_pictures = [
        item for item in parsed.get("objects", [])
        if item.get("kind") == "picture"
    ]
    target_pictures = object_map.get("pictures", [])
    source_picture_geometry = sorted(
        (
            int((item.get("control_geometry") or {}).get("width", 0) or 0),
            int((item.get("control_geometry") or {}).get("height", 0) or 0),
            int((item.get("control_geometry") or {}).get("horizontal_offset", 0) or 0),
            int((item.get("control_geometry") or {}).get("vertical_offset", 0) or 0),
            bool((item.get("control_geometry") or {}).get("treat_as_char")),
        )
        for item in source_pictures
    )
    target_picture_geometry = sorted(
        (
            int(item.get("width", 0) or 0),
            int(item.get("height", 0) or 0),
            int((item.get("position") or {}).get("horzOffset", 0) or 0),
            int((item.get("position") or {}).get("vertOffset", 0) or 0),
            str((item.get("position") or {}).get("treatAsChar", "0")).lower()
            in {"1", "true"},
        )
        for item in target_pictures
    )
    picture_geometry_exact = (
        len(source_picture_geometry) == len(target_picture_geometry)
        and source_picture_geometry == target_picture_geometry
    )

    source_object_paragraphs = [
        item for item in parsed.get("paragraphs", [])
        if item.get("flow_kind") == "object-text"
    ]
    source_object_controls: dict[int, list[dict]] = {}
    for item in source_object_paragraphs:
        control_index = item.get("control_index")
        if control_index is not None:
            source_object_controls.setdefault(int(control_index), []).append(item)
    control_index_map = {
        int(item["control_index"]): item
        for item in parsed.get("controls", [])
        if item.get("control_index") is not None
    }
    source_textbox_geometry = []
    for control_index, owned in sorted(source_object_controls.items()):
        control = control_index_map.get(control_index) or {}
        if control.get("shape_family") != "rectangle":
            continue
        source_textbox_geometry.append({
            "control_index": control_index,
            "width": int(control.get("width") or 0),
            "height": int(control.get("height") or 0),
            "treat_as_char": bool(control.get("treat_as_char")),
            "horizontal_offset": int(control.get("horizontal_offset") or 0),
            "vertical_offset": int(control.get("vertical_offset") or 0),
            "paragraphs": [str(item.get("text", "")) for item in owned],
        })
    target_textbox_map = build_textbox_map(path)
    target_textboxes = target_textbox_map.get("textboxes", [])
    textbox_pairs = list(zip(source_textbox_geometry, target_textboxes))
    textbox_geometry_exact = (
        len(source_textbox_geometry) == len(target_textboxes)
        and all(
            left["width"] == int(right.get("width") or 0)
            and left["height"] == int(right.get("height") or 0)
            and left["horizontal_offset"] == int((right.get("position") or {}).get("horzOffset", 0) or 0)
            and left["vertical_offset"] == int((right.get("position") or {}).get("vertOffset", 0) or 0)
            and left["treat_as_char"] == (
                str((right.get("position") or {}).get("treatAsChar", "0")).lower()
                in {"1", "true"}
            )
            and left["paragraphs"] == list(right.get("paragraphs") or [])
            for left, right in textbox_pairs
        )
    )

    nested = [
        item for item in parsed.get("paragraphs", [])
        if item.get("flow_kind") != "body"
    ]
    result = {
        "ok": True,
        "document_id": document_id,
        "source_filename": Path(filename or "document.hwp").name[:128],
        "source_sha256": source_sha256,
        "provenance_match": provenance_match,
        "families": {
            "body_text": {
                "source_paragraphs": len(source_text),
                "target_paragraphs": len(target_text_all),
                "strict_paragraph_exact": strict_text_exact,
                "source_nonblank_paragraphs": len(source_semantic_text),
                "target_nonblank_paragraphs": len(target_semantic_text),
                "semantic_exact": semantic_text_exact,
                "exact": semantic_text_exact,
                "normalization": "drop whitespace-only paragraphs; preserve every nonblank code point exactly",
                "mismatch_count_bounded": len(text_mismatches),
                "mismatches": text_mismatches,
            },
            "run_style": {
                "comparable_paragraphs": comparable_style_paragraphs,
                "exact_paragraphs": exact_style_paragraphs,
                "segmentation_exact_paragraphs": segmentation_exact_paragraphs,
                "axis_match_counts": run_style_axis_matches,
                "axis_comparison_counts": run_style_axis_comparisons,
                "exact": (
                    comparable_style_paragraphs > 0
                    and comparable_style_paragraphs == exact_style_paragraphs
                ),
                "canonical_axes": [
                    "text", "bold", "italic", "underline", "strike",
                    "size", "color", "font", "script",
                ],
                "font_semantics": "FaceName-resolved rather than raw fontRef id",
            },
            "paragraph_style": {
                "comparable_paragraphs": paragraph_style_comparable,
                "exact_paragraphs": paragraph_style_exact,
                "exact": (
                    paragraph_style_comparable > 0
                    and paragraph_style_comparable == paragraph_style_exact
                ),
                "axis_match_counts": paragraph_style_axis_matches,
                "mismatches": paragraph_style_mismatches,
            },
            "tables": {
                "source_count": len(source_tables),
                "target_count": len(target_tables),
                "geometry_exact": source_table_geometry == target_table_geometry,
                "cell_geometry_exact": table_cell_geometry_exact,
                "source_cell_geometry": source_table_cells[:20],
                "target_cell_geometry": target_table_cells[:20],
                "geometry_authority": "STRUCTURAL_HWPUNIT_GEOMETRY / NOT_PIXEL_RENDERING",
            },
            "equations": {
                "source_count": len(source_equations),
                "target_count": len(target_equations),
                "script_exact": source_equations == target_equations,
                "geometry_exact": equation_geometry_exact,
                "source_geometry": source_equation_geometry[:50],
                "target_geometry": target_equation_geometry[:50],
                "geometry_authority": "STRUCTURAL_HWPUNIT_GEOMETRY / NOT_PIXEL_RENDERING",
            },
            "pictures": {
                "source_count": len(source_pictures),
                "target_count": len(target_pictures),
                "count_exact": len(source_pictures) == len(target_pictures),
                "geometry_exact": picture_geometry_exact,
                "source_geometry": source_picture_geometry[:50],
                "target_geometry": target_picture_geometry[:50],
                "geometry_authority": "STRUCTURAL_HWPUNIT_GEOMETRY / NOT_PIXEL_RENDERING",
            },
            "textboxes": {
                "source_rectangle_textbox_count": len(source_textbox_geometry),
                "target_native_textbox_count": len(target_textboxes),
                "structural_geometry_exact": textbox_geometry_exact,
                "authority": "STRUCTURAL_HWPUNIT_GEOMETRY / NOT_PIXEL_RENDERING",
                "source": source_textbox_geometry[:20],
                "target": target_textboxes[:20],
            },
            "nested_text_flows": {
                "source_count": len(nested),
                "source_flow_counts": {
                    kind: sum(1 for item in nested if item.get("flow_kind") == kind)
                    for kind in sorted({str(item.get("flow_kind")) for item in nested})
                },
                "native_promotion": "FAMILY_GRADED",
                "promotion_receipt": (
                    metadata.get("hwp_rich_promotion_report", {})
                    .get("nested_text_flows", {})
                ),
            },
        },
        "authority": (
            "ROUNDTRIP_FIDELITY_RECEIPT"
            if provenance_match
            else (
                "CROSS_FORMAT_EQUIVALENCE_RECEIPT"
                if not require_provenance
                else "SOURCE_PROVENANCE_MISMATCH"
            )
        ),
        "provenance_required": bool(require_provenance),
    }
    return result


@core.mcp.tool()
def get_textbox_map(document_id: str) -> dict:
    """Return native HWPX rectangle-textbox text, anchor and structural geometry receipts."""
    metadata, path = _owned_document(document_id)
    mapped = build_textbox_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
        "authority": "NATIVE_HWPX_TEXTBOX_MAP / STRUCTURAL_HWPUNIT_GEOMETRY",
    }


@core.mcp.tool()
def get_story_layer_contract() -> dict:
    """Return the admitted P3.24 section-story contract and evidence gates."""
    core._caller_subject()
    return {"ok": True, **story_layer_contract()}


@core.mcp.tool()
def get_story_layer(document_id: str) -> dict:
    """Return section-scoped header/footer story ownership, variants and first-page policy."""
    metadata, path = _owned_document(document_id)
    mapped = build_story_layer_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_story_layer(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.24 section-story transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_story_layer_atomic(
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
        "story_layer_diff": transaction,
        "story_layer": build_story_layer_map(path),
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_drawing_layer_contract() -> dict:
    """Return the admitted P3.25 drawing-layer contract and evidence gates."""
    core._caller_subject()
    return {"ok": True, **drawing_layer_contract()}


@core.mcp.tool()
def get_drawing_layer(document_id: str) -> dict:
    """Return anchored drawing objects, geometry, wrap/z-order and grouping inventory."""
    metadata, path = _owned_document(document_id)
    mapped = build_drawing_layer_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_drawing_layer(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.25 drawing-layer transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_drawing_layer_atomic(
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
    drawing = build_drawing_layer_map(path)
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "drawing_layer_diff": transaction,
        "drawing_layer": drawing,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_drawing_style_contract() -> dict:
    """Return the admitted P3.26 native shape/styling contract and evidence gates."""
    core._caller_subject()
    return {"ok": True, **drawing_style_contract()}


@core.mcp.tool()
def get_drawing_styles(document_id: str) -> dict:
    """Return native shape stroke/fill/shadow/arrowhead and geometry receipts."""
    metadata, path = _owned_document(document_id)
    mapped = build_drawing_style_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_drawing_styles(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.26 native shape/style transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_drawing_style_atomic(
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
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "drawing_style_diff": transaction,
        "drawing_styles": styles,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_diagram_composition_contract() -> dict:
    """Return the admitted P3.27 diagram-composition contract and evidence gates."""
    core._caller_subject()
    return {"ok": True, **diagram_composition_contract()}


@core.mcp.tool()
def get_diagram_composition(document_id: str) -> dict:
    """Return top-level drawing placement, group topology and composition receipts."""
    metadata, path = _owned_document(document_id)
    mapped = build_diagram_composition_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_diagram_composition(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.27 diagram-composition transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_diagram_composition_atomic(
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
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
    diagram = build_diagram_composition_map(path)
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    metadata["diagram_placement_sha256"] = diagram["diagram_placement_sha256"]
    metadata["group_topology_sha256"] = diagram["group_topology_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "diagram_composition_diff": transaction,
        "diagram_composition": diagram,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_high_level_diagram_contract() -> dict:
    """Return P3.28 labeled-node, plan, callout and macro contract."""
    core._caller_subject()
    return {"ok": True, **high_level_diagram_contract()}


@core.mcp.tool()
def validate_high_level_diagram_plan(plan: dict) -> dict:
    """Validate a declarative P3.28 diagram plan without mutating a document."""
    core._caller_subject()
    return validate_p328_diagram_plan(plan)


@core.mcp.tool()
def get_high_level_diagrams(document_id: str) -> dict:
    """Return native shape-label and high-level diagram receipts."""
    metadata, path = _owned_document(document_id)
    mapped = build_high_level_diagram_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_high_level_diagrams(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.28 high-level diagram transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_high_level_diagrams_atomic(
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
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
    diagram = build_diagram_composition_map(path)
    high_level = build_high_level_diagram_map(path)
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    metadata["diagram_placement_sha256"] = diagram["diagram_placement_sha256"]
    metadata["group_topology_sha256"] = diagram["group_topology_sha256"]
    metadata["shape_text_sha256"] = high_level["shape_text_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "high_level_diagram_diff": transaction,
        "high_level_diagrams": high_level,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_diagram_lifecycle_contract() -> dict:
    """Return P3.29 persistent semantic identity, patch, relayout and subgraph contract."""
    core._caller_subject()
    return {"ok": True, **diagram_lifecycle_contract()}


@core.mcp.tool()
def get_diagram_lifecycle(document_id: str) -> dict:
    """Return managed diagrams with durable node identities and reconstructed static relations."""
    metadata, path = _owned_document(document_id)
    mapped = build_diagram_lifecycle_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_diagram_lifecycle(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.29 managed-diagram lifecycle transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_diagram_lifecycle_atomic(
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
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
    diagram = build_diagram_composition_map(path)
    high_level = build_high_level_diagram_map(path)
    lifecycle = build_diagram_lifecycle_map(path)
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    metadata["diagram_placement_sha256"] = diagram["diagram_placement_sha256"]
    metadata["group_topology_sha256"] = diagram["group_topology_sha256"]
    metadata["shape_text_sha256"] = high_level["shape_text_sha256"]
    metadata["diagram_identity_sha256"] = lifecycle["diagram_identity_sha256"]
    metadata["diagram_relation_sha256"] = lifecycle["diagram_relation_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "diagram_lifecycle_diff": transaction,
        "diagram_lifecycle": lifecycle,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_diagram_design_system_contract() -> dict:
    """Return P3.30 themes, semantic roles, layout policies and parameterized-template contract."""
    core._caller_subject()
    return {"ok": True, **diagram_design_system_contract()}


@core.mcp.tool()
def get_diagram_design_system(document_id: str) -> dict:
    """Return managed diagrams with semantic roles and effective materialized native styles."""
    metadata, path = _owned_document(document_id)
    mapped = build_diagram_design_system_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def apply_diagram_design_system(
    document_id: str,
    expected_revision: int,
    operations: list[dict],
    lease_token: str = "",
) -> dict:
    """Apply one revision-guarded P3.30 diagram design-system transaction."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    fidelity = assess_edit_fidelity_envelope(operations)
    transaction = apply_diagram_design_system_atomic(
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
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
    diagram = build_diagram_composition_map(path)
    high_level = build_high_level_diagram_map(path)
    lifecycle = build_diagram_lifecycle_map(path)
    design = build_diagram_design_system_map(path)
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    metadata["diagram_placement_sha256"] = diagram["diagram_placement_sha256"]
    metadata["group_topology_sha256"] = diagram["group_topology_sha256"]
    metadata["shape_text_sha256"] = high_level["shape_text_sha256"]
    metadata["diagram_identity_sha256"] = lifecycle["diagram_identity_sha256"]
    metadata["diagram_relation_sha256"] = lifecycle["diagram_relation_sha256"]
    metadata["semantic_style_sha256"] = design["semantic_style_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "diagram_design_system_diff": transaction,
        "diagram_design_system": design,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def get_diagram_quality_assurance_contract() -> dict:
    """Return P3.31 structural QA profiles, checks, repair semantics and evidence gates."""
    core._caller_subject()
    return {"ok": True, **diagram_quality_assurance_contract()}


@core.mcp.tool()
def get_diagram_quality(
    document_id: str,
    profile: str = "baseline",
    constraints: dict | None = None,
    expected_theme: str = "",
) -> dict:
    """Validate every managed diagram under one bounded structural QA profile."""
    metadata, path = _owned_document(document_id)
    mapped = build_diagram_quality_map(
        path,
        profile=profile,
        constraints=constraints,
        expected_theme=expected_theme or None,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def validate_diagram_quality(
    document_id: str,
    diagram_id: str,
    profile: str = "baseline",
    constraints: dict | None = None,
    expected_theme: str = "",
) -> dict:
    """Validate one managed diagram using structural graph/style/readability checks."""
    metadata, path = _owned_document(document_id)
    report = validate_p331_diagram_quality(
        path,
        diagram_id,
        profile=profile,
        constraints=constraints,
        expected_theme=expected_theme or None,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **report,
    }


@core.mcp.tool()
def plan_diagram_repairs(
    document_id: str,
    diagram_id: str,
    profile: str = "baseline",
    constraints: dict | None = None,
    expected_theme: str = "",
    repair_theme: str = "",
    repair_layout_policy: str = "",
    layout: str = "LEFT_TO_RIGHT",
) -> dict:
    """Build a deterministic P3.31 safe structural repair plan without mutating bytes."""
    metadata, path = _owned_document(document_id)
    plan = plan_p331_diagram_repairs(
        path,
        diagram_id,
        profile=profile,
        constraints=constraints,
        expected_theme=expected_theme or None,
        repair_theme=repair_theme or None,
        repair_layout_policy=repair_layout_policy or None,
        layout=layout,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **plan,
    }


@core.mcp.tool()
def apply_diagram_repairs(
    document_id: str,
    expected_revision: int,
    repair_plan: dict,
    lease_token: str = "",
) -> dict:
    """Apply one stale-safe P3.31 repair plan restricted to meaning-preserving design/layout operations."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    operations = repair_plan.get("operations") if isinstance(repair_plan, dict) else []
    fidelity = assess_edit_fidelity_envelope(operations or [])
    transaction = apply_diagram_repairs_atomic(
        path,
        repair_plan,
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
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
    diagram = build_diagram_composition_map(path)
    high_level = build_high_level_diagram_map(path)
    lifecycle = build_diagram_lifecycle_map(path)
    design = build_diagram_design_system_map(path)
    quality = build_diagram_quality_map(path)
    diagram_id = str(repair_plan.get("diagram_id") or "")
    post_report = validate_p331_diagram_quality(
        path,
        diagram_id,
        profile=str(repair_plan.get("profile", "baseline")),
        constraints=repair_plan.get("constraints"),
        expected_theme=repair_plan.get("expected_theme"),
    )
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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    metadata["diagram_placement_sha256"] = diagram["diagram_placement_sha256"]
    metadata["group_topology_sha256"] = diagram["group_topology_sha256"]
    metadata["shape_text_sha256"] = high_level["shape_text_sha256"]
    metadata["diagram_identity_sha256"] = lifecycle["diagram_identity_sha256"]
    metadata["diagram_relation_sha256"] = lifecycle["diagram_relation_sha256"]
    metadata["semantic_style_sha256"] = design["semantic_style_sha256"]
    metadata["diagram_quality_sha256"] = quality["quality_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "diagram_repair_diff": transaction,
        "post_repair_report": post_report,
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def p2_capabilities() -> dict:
    subject = core._caller_subject()
    return {
        "project": core.PROJECT,
        "version": core.VERSION,
        "phase": core.PHASE,
        "authenticated_subject": subject,
        "tools_added": [
            "get_rare_feature_registry",
            "evaluate_rare_feature_lane",
            "plan_rare_feature_promotion",
            "get_product_ux_regression_contract",
            "get_document_delivery_contract",
            "generate_document",
            "edit_document_and_deliver",
            "deliver_document",
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
            "compare_hwp5_roundtrip_fidelity",
            "get_hwp5_style_map",
            "get_paragraph_style_provenance",
            "get_textbox_map",
            "get_hwp5_text_flows",
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
            "get_document_setup",
            "apply_document_setup",
            "get_structured_publishing",
            "apply_structured_publishing",
            "get_annotation_apparatus",
            "apply_annotation_apparatus",
            "get_document_plan_contract",
            "validate_document_plan",
            "create_document_from_plan",
            "get_review_workflow",
            "apply_review_workflow",
            "get_advanced_table_contract",
            "get_advanced_tables",
            "apply_advanced_table_edits",
            "get_story_layer_contract",
            "get_story_layer",
            "apply_story_layer",
            "get_drawing_layer_contract",
            "get_drawing_layer",
            "apply_drawing_layer",
            "get_drawing_style_contract",
            "get_drawing_styles",
            "apply_drawing_styles",
            "get_diagram_composition_contract",
            "get_diagram_composition",
            "apply_diagram_composition",
            "get_high_level_diagram_contract",
            "validate_high_level_diagram_plan",
            "get_high_level_diagrams",
            "apply_high_level_diagrams",
            "get_diagram_lifecycle_contract",
            "get_diagram_lifecycle",
            "apply_diagram_lifecycle",
            "get_diagram_design_system_contract",
            "get_diagram_design_system",
            "apply_diagram_design_system",
            "get_diagram_quality_assurance_contract",
            "get_diagram_quality",
            "validate_diagram_quality",
            "plan_diagram_repairs",
            "apply_diagram_repairs",
            "get_brownfield_diagram_contract",
            "recognize_existing_diagrams",
            "plan_diagram_adoption",
            "promote_diagram_candidate",
            "plan_legacy_diagram_refactor",
            "apply_legacy_diagram_refactor",
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
        "story_layer": {
            "ancestry": "P3.18 document-setup primitives re-promoted into P3.24 story ownership contract",
            "native_variants": ["BOTH", "EVEN", "ODD"],
            "first_page": "hp:visibility hideFirstHeader/hideFirstFooter/hideFirstPageNum",
            "section_boundary": "story policy is section-scoped and revision/CAS guarded",
            "synthetic_first_story": "EVIDENCE_GATE_CLOSED",
            "authority": "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY until native P3.24 render batch",
            "diff": "story_layer_sha256",
        },
        "drawing_layer": {
            "ancestry": "P2.9 picture/object primitives + P3.9 native textbox/geometry re-promoted into P3.25",
            "inventory": "pic/rect/ellipse/line/polygon/arc/container",
            "authoring": "textbox + rectangle only; generic raw shapes fail closed",
            "layout": "anchor position + wrap/text-flow + z-order + lock",
            "geometry": "rect/pic resize + rotation/flip when native elements exist",
            "grouping": "existing containers inventoried; group/ungroup authoring evidence gate closed",
            "authority": "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY until native P3.25 render batch",
            "diff": "drawing_structure_sha256 + drawing_geometry_sha256",
        },
        "drawing_style": {
            "ancestry": "P3.25 unified drawing layer + upstream dedicated shape helpers promoted into P3.26",
            "authoring": "line/ellipse/polygon/arc via dedicated python-hwpx helpers",
            "stroke": "color/width/style/end-cap/alpha",
            "fill": "solid hc:winBrush + alpha; gradient/pattern remain closed",
            "arrowheads": "head/tail style + size + fill",
            "shadow": "NONE/DROP/CONTINUOUS + color/offset/alpha",
            "geometry": "shape-specific native points + arc attributes are read back",
            "authority": "STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY until native P3.26 render batch",
            "diff": "drawing_style_sha256 + shape_geometry_sha256",
        },
        "diagram_composition": {
            "ancestry": "P3.25 layout + P3.26 shape authoring + upstream ContainerMember/add_container promoted into P3.27",
            "connector": "static line connector between current node centers; no subjectIDRef binding or automatic rerouting",
            "group": "new hp:container from explicit local rect/ellipse/polygon members + rigid translation",
            "alignment": "LEFT/CENTER/RIGHT/TOP/MIDDLE/BOTTOM over floating same-anchor top-level objects",
            "distribution": "equal-center HORIZONTAL/VERTICAL distribution",
            "blocks": "reusable bounded group presets: two_nodes/three_stage/decision_cluster",
            "deferred": "native smart connectLine + arbitrary existing-object group/ungroup + group scaling",
            "authority": "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY until native P3.27 render batch",
            "diff": "diagram_placement_sha256 + group_topology_sha256",
        },
        "high_level_diagram": {
            "ancestry": "P3.25 hp:drawText read-back + P3.26 native shapes + P3.27 composition promoted into P3.28",
            "shape_text": "native hp:drawText plain labels + bounded text margins",
            "labeled_nodes": "process/terminator/decision/data/node macros over rect/ellipse/polygon",
            "callout": "labeled node + static pointer line; no unmeasured native callout family",
            "plans": "validated deterministic LEFT_TO_RIGHT/TOP_DOWN compiler with bounded nodes/edges",
            "macros": "flowchart sequence + recursive org-chart tree",
            "deferred": "smart connector routing + rich mixed-run shape text + renderer-aware collision/page avoidance",
            "authority": "STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY until native P3.28 render batch",
            "diff": "shape_text_sha256 + diagram_placement_sha256",
        },
        "diagram_lifecycle": {
            "ancestry": "P3.28 semantic nodes + static edges promoted into persistent identity and patch lifecycle",
            "identity": "diagram_id/node_id/node_type persisted in native hp:drawText@name",
            "relations": "static center-to-center line relations reconstructed and regenerated after geometry changes",
            "patching": "node add/update/delete + edge add/remove + deterministic relayout/resize",
            "templates": "linear_process / decision_gate / org_triad",
            "subgraphs": "move / clone / remove with semantic identity preservation",
            "deferred": "smart connector binding + parallel managed edges + cross-anchor subgraphs + renderer-aware layout",
            "authority": "STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY until native P3.29 render batch",
            "diff": "diagram_identity_sha256 + diagram_relation_sha256",
        },
        "diagram_design_system": {
            "ancestry": "P3.29 persistent semantic identity + P3.26 native shape styling promoted into role-driven design systems",
            "themes": "classic / mono / presentation materialized into native fill/stroke/arrow attributes",
            "roles": "node role from persisted node_type; edge branch role iff source node is decision, otherwise flow",
            "layout_policies": "compact / standard / spacious deterministic HWPUNIT spacing",
            "templates": "linear_process / decision_gate / org_triad with bounded label/theme/layout parameters",
            "bulk": "theme application + node/edge restyle + combined layout/theme transaction",
            "deferred": "rich drawText typography + private theme registry + renderer-aware collision layout + smart connector style binding",
            "authority": "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY until native P3.30 render batch",
            "diff": "semantic_style_sha256 + inherited diagram identity/relation receipts",
        },
        "diagram_quality_assurance": {
            "ancestry": "P3.29 semantic graph + P3.30 effective native style map promoted into read-only validation and explicit safe repair",
            "profiles": "baseline / flow / presentation with caller-overridable bounded structural constraints",
            "graph_checks": "labels + weak connectivity + cycle + source/sink cardinality + in/out degree bounds",
            "style_checks": "exact semantic-role theme-token conformance against materialized native attributes",
            "readability_checks": "native bbox overlap + minimum center spacing + label-length budget; no renderer/pixel claims",
            "repair": "theme re-materialization + P3.30 collision-safe layout only; semantic graph mutations remain advisory",
            "deferred": "pixel overlap + color contrast + font legibility + subjective aesthetic score + semantic graph auto-repair",
            "authority": "STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY until native P3.31 render batch",
            "diff": "qa_sha256 / quality_sha256 + inherited identity/relation/style receipts",
        },
        "table_editing": {
            "introspection": "table/cell semantic map + merge geometry + structure/format/object + P3.23 advanced-layout receipts",
            "table_address": "intrinsic hp:tbl id when present; revision-bound ordinal fallback",
            "cell_address": "revision-bound grid-anchor locator with rebinding receipts",
            "object_lifecycle": "create_table + delete_table",
            "row_structure": "insert_row_by_clone + delete_row + explicit row-height/header properties",
            "column_structure": "delete_column + width/autofit; insert_column evidence gate closed",
            "merge_split": "rectangular merge + merged-cell split",
            "cell_content_format": "text, shading, borders, gradient, margins, size, header/protect/editable/name + vertical alignment",
            "repeating_headers": "hp:tbl repeatHeader + designated header-row hp:tc header semantics",
            "table_wide_format": "border/shading fan-out over anchor cells + CELL/TABLE/NONE page-break mode",
            "authority": "STRUCTURAL_AUTHORITY_ONLY until Hancom-native P3.23 render batch",
            "diff": "table_structure_sha256 + table_format_sha256 + table_object_sha256 + advanced_table_layout_sha256",
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
        "hwp5_run_style_and_flows": {
            "paragraph_style": "PARA_HEADER shape/style/control-mask/instance references",
            "run_style": "PARA_CHAR_SHAPE source-coordinate transitions resolved through DocInfo CHAR_SHAPE",
            "visible_span": "certified through source-WCHAR→visible mapping when control decoding closes; control-free paragraphs use identity coordinates",
            "nested_flows": "header/footer/footnote/endnote/object-text paragraph ownership is explicit in Common IR",
            "promotion": "body run/paragraph styles use semantic FaceName/ParaShape subsets; header/footer and anchored footnote/endnote families may promote natively",
            "oracle": "canonical FaceName/run emphasis/paragraph semantics are compared by meaning rather than source-local IDs",
        },
        "hwp5_style_canonicalization": {
            "font": "DocInfo ID_MAPPINGS + FACE_NAME resolves HWP face_ids; HWPX fontRef ids resolve through header.xml fontfaces",
            "style_map": "bounded MCP surface exposes canonical run/font/paragraph receipts before promotion",
            "paragraph": "PARA_SHAPE alignment/margin/spacing prefix semantics mapped to HWPX paragraph-format coordinates",
            "oracle": "run style reports semantic font/color/script/emphasis axes and paragraph-style axis matches",
            "nested_promotion": "header/footer native section stories; footnote/endnote require recovered owner anchors; object-text remains deferred",
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
            "blocks": ["paragraph", "header", "footer", "footnote", "endnote", "object-text", "table", "equation", "picture", "shape", "binary"],
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
        "p39_style_layout": {
            "style_provenance": "HWP STYLE→ParaShape/CharShape and HWPX styleIDRef→paraPr/charPr reference graphs",
            "textbox_promotion": "rectangle-certified object-text only; anchor/geometry must close before native hp:rect+drawText synthesis",
            "geometry_oracle": "structural HWPUNIT geometry receipts; does not claim pixel-rendered identity",
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


@core.mcp.tool()
def get_brownfield_diagram_contract() -> dict:
    """Return P3.32 brownfield recognition, adoption, promotion and refactor boundaries."""
    core._caller_subject()
    return {"ok": True, **brownfield_diagram_contract()}


@core.mcp.tool()
def recognize_existing_diagrams(document_id: str) -> dict:
    """Recognize evidence-backed unmanaged native diagrams without claiming ownership or mutating bytes."""
    metadata, path = _owned_document(document_id)
    mapped = build_brownfield_diagram_map(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **mapped,
    }


@core.mcp.tool()
def plan_diagram_adoption(
    document_id: str,
    candidate_id: str,
    diagram_id: str,
    node_bindings: dict | None = None,
) -> dict:
    """Build one stale-safe explicit adoption plan for a promotable brownfield candidate."""
    metadata, path = _owned_document(document_id)
    plan = plan_p332_diagram_adoption(
        path,
        candidate_id,
        diagram_id,
        node_bindings=node_bindings,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **plan,
    }


def _commit_p332_maps(
    document_id: str,
    metadata: dict,
    path: Path,
    validation: dict,
    *,
    current_revision: int,
    lease_token: str = "",
) -> dict:
    after_document = build_document_map(path)
    after_formatting = build_formatting_map(path)
    after_inline = build_inline_map(path)
    after_tables = build_table_map(path)
    after_objects = build_object_map(path)
    after_equations = build_equation_map(path)
    drawing = build_drawing_layer_map(path)
    styles = build_drawing_style_map(path)
    diagram = build_diagram_composition_map(path)
    high_level = build_high_level_diagram_map(path)
    lifecycle = build_diagram_lifecycle_map(path)
    design = build_diagram_design_system_map(path)
    quality = build_diagram_quality_map(path)
    brownfield = build_brownfield_diagram_map(path)

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
    metadata["drawing_structure_sha256"] = drawing["drawing_structure_sha256"]
    metadata["drawing_geometry_sha256"] = drawing["drawing_geometry_sha256"]
    metadata["drawing_style_sha256"] = styles["drawing_style_sha256"]
    metadata["shape_geometry_sha256"] = styles["shape_geometry_sha256"]
    metadata["diagram_placement_sha256"] = diagram["diagram_placement_sha256"]
    metadata["group_topology_sha256"] = diagram["group_topology_sha256"]
    metadata["shape_text_sha256"] = high_level["shape_text_sha256"]
    metadata["diagram_identity_sha256"] = lifecycle["diagram_identity_sha256"]
    metadata["diagram_relation_sha256"] = lifecycle["diagram_relation_sha256"]
    metadata["semantic_style_sha256"] = design["semantic_style_sha256"]
    metadata["diagram_quality_sha256"] = quality["quality_sha256"]
    metadata["brownfield_recognition_sha256"] = brownfield["recognition_sha256"]
    core._write_metadata(document_id, metadata)
    return {
        "drawing": drawing,
        "styles": styles,
        "diagram": diagram,
        "high_level": high_level,
        "lifecycle": lifecycle,
        "design": design,
        "quality": quality,
        "brownfield": brownfield,
    }


@core.mcp.tool()
def promote_diagram_candidate(
    document_id: str,
    expected_revision: int,
    adoption_plan: dict,
    lease_token: str = "",
) -> dict:
    """Promote one evidence-closed brownfield candidate by writing only P3.29 identity carriers."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    transaction = promote_diagram_candidate_atomic(
        path,
        adoption_plan,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    maps = _commit_p332_maps(
        document_id,
        metadata,
        path,
        validation,
        current_revision=current_revision,
        lease_token=lease_token,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "promotion": transaction,
        "diagram_lifecycle": maps["lifecycle"],
        "brownfield": maps["brownfield"],
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }


@core.mcp.tool()
def plan_legacy_diagram_refactor(
    document_id: str,
    diagram_id: str,
    layout_policy: str = "",
    layout: str = "LEFT_TO_RIGHT",
    theme: str = "",
) -> dict:
    """Build one stale-safe meaning-preserving refactor plan for an already-managed legacy diagram."""
    metadata, path = _owned_document(document_id)
    plan = plan_p332_legacy_refactor(
        path,
        diagram_id,
        layout_policy=layout_policy,
        layout=layout,
        theme=theme,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **plan,
    }


@core.mcp.tool()
def apply_legacy_diagram_refactor(
    document_id: str,
    expected_revision: int,
    refactor_plan: dict,
    lease_token: str = "",
) -> dict:
    """Apply one P3.32 refactor plan restricted to relation-preserving P3.30 layout/theme operations."""
    metadata, path = _owned_document(document_id)
    current_revision = int(metadata["revision"])
    ingress = metadata.get("source") == "existing-ingress"
    operations = refactor_plan.get("operations") if isinstance(refactor_plan, dict) else []
    fidelity = assess_edit_fidelity_envelope(operations or [])
    transaction = apply_legacy_diagram_refactor_atomic(
        path,
        refactor_plan,
        expected_revision=int(expected_revision),
        current_revision=current_revision,
        validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
    )
    validation = transaction["validation"]
    maps = _commit_p332_maps(
        document_id,
        metadata,
        path,
        validation,
        current_revision=current_revision,
        lease_token=lease_token,
    )
    return {
        "ok": True,
        "document_id": document_id,
        "revision_before": current_revision,
        "revision_after": int(metadata["revision"]),
        "sha256": validation["sha256"],
        "legacy_refactor": transaction,
        "diagram_lifecycle": maps["lifecycle"],
        "diagram_design_system": maps["design"],
        "diagram_quality": maps["quality"],
        "brownfield": maps["brownfield"],
        "fidelity": fidelity,
        "validation": validation,
        "transaction": "COMMITTED",
        "authority": "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }



@core.mcp.tool()
def get_typography_contract() -> dict:
    """Return P3.35 native typography bounds, script-font model and mixed-run operations."""
    core._caller_subject()
    return {"ok": True, **p335_typography_contract()}


@core.mcp.tool()
def get_typography_profile(document_id: str) -> dict:
    """Summarize an owned HWPX typography as reusable character-weighted style distributions."""
    metadata, path = _owned_document(document_id)
    profile = build_typography_profile(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **profile,
    }


@core.mcp.tool()
def compare_typography_profiles(left_document_id: str, right_document_id: str) -> dict:
    """Compare dominant typography choices of two owned HWPX documents without mutating either."""
    left_meta, left_path = _owned_document(left_document_id)
    right_meta, right_path = _owned_document(right_document_id)
    left = build_typography_profile(left_path)
    right = build_typography_profile(right_path)
    return {
        "ok": True,
        "left_document_id": left_document_id,
        "left_revision": int(left_meta["revision"]),
        "right_document_id": right_document_id,
        "right_revision": int(right_meta["revision"]),
        **compare_typography_profiles(left, right),
    }


@core.mcp.tool()
def get_paragraph_geometry_contract() -> dict:
    """Return P3.35 paragraph geometry, line-spacing, indentation and tab readback contract."""
    core._caller_subject()
    return {"ok": True, **p335_paragraph_geometry_contract()}


@core.mcp.tool()
def get_paragraph_geometry_profile(document_id: str) -> dict:
    """Summarize paragraph geometry as weighted reusable distributions without mutating the document."""
    metadata, path = _owned_document(document_id)
    profile = build_paragraph_geometry_profile(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **profile,
    }


@core.mcp.tool()
def compare_paragraph_geometry_profiles(left_document_id: str, right_document_id: str) -> dict:
    """Compare dominant paragraph geometry of two owned HWPX documents."""
    left_meta, left_path = _owned_document(left_document_id)
    right_meta, right_path = _owned_document(right_document_id)
    left = build_paragraph_geometry_profile(left_path)
    right = build_paragraph_geometry_profile(right_path)
    return {
        "ok": True,
        "left_document_id": left_document_id,
        "left_revision": int(left_meta["revision"]),
        "right_document_id": right_document_id,
        "right_revision": int(right_meta["revision"]),
        **compare_paragraph_geometry_profiles(left, right),
    }


@core.mcp.tool()
def get_document_style_exemplar(document_id: str) -> dict:
    """Extract a reusable P3.35 typography + paragraph authoring preset and native readback exemplar."""
    metadata, path = _owned_document(document_id)
    exemplar = build_document_style_exemplar(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **exemplar,
    }


@core.mcp.tool()
def get_role_aware_style_exemplars(document_id: str) -> dict:
    """Extract evidence-bounded body/title/heading/caption/table-context style presets."""
    metadata, path = _owned_document(document_id)
    profile = build_role_aware_style_exemplars(path)
    return {
        "ok": True,
        "document_id": document_id,
        "revision": int(metadata["revision"]),
        **profile,
    }


@core.mcp.tool()
def plan_document_style_transfer(
    source_document_id: str,
    target_document_id: str,
    targets: list[str],
    include_typography: bool = True,
    include_paragraph: bool = True,
) -> dict:
    """Compile a source exemplar into existing atomic formatting operations for a target document."""
    source_meta, source_path = _owned_document(source_document_id)
    target_meta, _target_path = _owned_document(target_document_id)
    exemplar = build_document_style_exemplar(source_path)
    operations = build_style_transfer_operations(
        exemplar,
        targets,
        include_typography=bool(include_typography),
        include_paragraph=bool(include_paragraph),
    )
    return {
        "ok": True,
        "source_document_id": source_document_id,
        "source_revision": int(source_meta["revision"]),
        "target_document_id": target_document_id,
        "target_revision": int(target_meta["revision"]),
        "exemplar_sha256": exemplar.get("exemplar_sha256"),
        "operations": operations,
        "apply_with": "apply_formatting",
        "expected_revision": int(target_meta["revision"]),
        "authority": "SAFE_INVERTIBLE_EXEMPLAR_DIMENSIONS_ONLY",
        "native_only_dimensions": "retained as readback and not emitted as mutation keys",
    }


@core.mcp.tool()
def build_style_corpus_profile(documents: list[dict]) -> dict:
    """Aggregate owned HWPX documents into a provenance-preserving P3.35-R3 corpus profile."""
    if not documents:
        raise ValueError("At least one document is required")
    items = []
    for item in documents:
        if not isinstance(item, dict) or not item.get("document_id"):
            raise ValueError("Each corpus item requires document_id")
        metadata, path = _owned_document(str(item["document_id"]))
        items.append({
            "path": str(path),
            "source_id": str(item.get("source_id") or item["document_id"]),
            "institution": str(item.get("institution") or "unknown"),
            "document_label": str(item.get("document_label") or metadata.get("filename") or item["document_id"]),
            "provenance_url": item.get("provenance_url"),
            "public_status": str(item.get("public_status") or "UNSPECIFIED"),
            "license_note": item.get("license_note"),
        })
    profile = build_corpus_style_profile(items)
    return {"ok": True, **profile}


@core.mcp.tool()
def build_reusable_style_library(
    documents: list[dict],
    min_documents: int = 2,
    min_share: float = 0.25,
) -> dict:
    """Build evidence-guided reusable role presets without selecting a normative winner."""
    if int(min_documents) < 1:
        raise ValueError("min_documents must be >= 1")
    if not (0 < float(min_share) <= 1):
        raise ValueError("min_share must be in (0, 1]")
    items = []
    for item in documents:
        if not isinstance(item, dict) or not item.get("document_id"):
            raise ValueError("Each corpus item requires document_id")
        metadata, path = _owned_document(str(item["document_id"]))
        items.append({
            "path": str(path),
            "source_id": str(item.get("source_id") or item["document_id"]),
            "institution": str(item.get("institution") or "unknown"),
            "document_label": str(item.get("document_label") or metadata.get("filename") or item["document_id"]),
            "provenance_url": item.get("provenance_url"),
            "public_status": str(item.get("public_status") or "UNSPECIFIED"),
            "license_note": item.get("license_note"),
        })
    profile = build_corpus_style_profile(items)
    library = build_style_library(profile, min_documents=int(min_documents), min_share=float(min_share))
    return {
        "ok": True,
        "corpus_profile_sha256": profile.get("profile_sha256"),
        **library,
    }


@core.mcp.tool()
def get_rare_feature_registry() -> dict:
    """Return P3.34 machine-readable rare-feature lanes, evidence gates and UX guard."""
    core._caller_subject()
    return {"ok": True, **rare_feature_registry()}


@core.mcp.tool()
def evaluate_rare_feature_lane(feature: str, evidence: dict | None = None) -> dict:
    """Evaluate one rare-feature lane without changing document or capability authority."""
    core._caller_subject()
    return {"ok": True, **evaluate_p334_rare_feature(feature, evidence)}


@core.mcp.tool()
def plan_rare_feature_promotion(feature: str, evidence: dict) -> dict:
    """Seal a bounded promotion plan only after every P3.34 evidence gate passes.

    This tool never changes editing authority by itself. The family operation must still
    be implemented and pass its own regression, OAuth/Docker and P3.33 delivery UX smoke.
    """
    core._caller_subject()
    return {"ok": True, **plan_p334_rare_feature_promotion(feature, evidence)}


@core.mcp.tool()
def get_product_ux_regression_contract() -> dict:
    """Return the recurring ChatGPT/plugin/file-delivery UX smoke required before closure."""
    core._caller_subject()
    return {"ok": True, **p334_ux_regression_contract()}


from mcp.types import CallToolResult, TextContent, ToolAnnotations
from p333_file_delivery import delivery_contract, export_revision, handoff


@core.mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def get_document_delivery_contract() -> dict:
    """Discover the primary HWPX workflow, recovery rules and independent evidence gates."""
    core._caller_subject()
    return {"ok": True, **delivery_contract(), "composition": document_plan_contract()}


@core.mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def deliver_document(document_id: str, revision: int | None = None, link_ttl_seconds: int = 900) -> CallToolResult:
    """Return a downloadable .hwpx resource and clickable link after exact-byte validation.

    Use after any existing editing tool, or to renew an expired link without repeating edits.
    Present the returned file/link to the user. Do not claim host attachment display or
    Hancom rendering was verified merely because export succeeded.
    """
    return handoff(export_revision(core, document_id, link_ttl_seconds, revision))


def _delivery_after_commit(document_id: str, revision: int, link_ttl_seconds: int, workflow: str) -> CallToolResult:
    try:
        receipt = export_revision(core, document_id, link_ttl_seconds, revision)
    except Exception as exc:
        # A failed handoff must not encourage replaying an already committed mutation.
        receipt = {"ok": False, "document_id": document_id, "revision": revision,
                   "workflow": workflow, "transaction": "COMMITTED",
                   "delivery_status": "RETRY_DELIVERY_ONLY", "error_type": type(exc).__name__,
                   "recovery": "Call deliver_document for this document_id and revision; do not repeat the mutation."}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(receipt))],
                              structuredContent=receipt, isError=True)
    receipt.update(workflow=workflow, transaction="COMMITTED")
    return handoff(receipt)


@core.mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def generate_document(plan: dict, filename: str = "document.hwpx", request_id: str = "",
                      template_document_id: str = "", link_ttl_seconds: int = 900) -> CallToolResult:
    """Create and return an actual downloadable HWPX in one call using the P3.21 plan.

    Translate the user's natural-language request into the existing document plan
    (get_document_delivery_contract). Reuse request_id after an interrupted create.
    Return the file/link, not an internal document ID, as the user's final deliverable.
    """
    core._caller_subject()
    core._download_secret()
    link_ttl_seconds = int(link_ttl_seconds)
    created = create_document_from_plan(plan, filename, template_document_id, request_id)
    return _delivery_after_commit(created["document_id"], int(created.get("revision", 1)),
                                  link_ttl_seconds, "CREATE_VALIDATE_EXPORT_HANDOFF")


@core.mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
def edit_document_and_deliver(document_id: str, expected_revision: int, operations: list[dict],
                              lease_token: str = "", link_ttl_seconds: int = 900) -> CallToolResult:
    """Apply one existing atomic text/paragraph edit and return the validated HWPX file.

    Resolve targets via get_document_map. Stale revisions and invalid operations fail
    before commit. Use deliver_document to recover delivery after a committed edit.
    Other native feature edits continue through their existing tools then deliver_document.
    """
    core._caller_subject()
    core._download_secret()
    link_ttl_seconds = int(link_ttl_seconds)
    edited = apply_edits(document_id, expected_revision, operations, lease_token)
    return _delivery_after_commit(document_id, edited["revision_after"], link_ttl_seconds,
                                  "EDIT_VALIDATE_EXPORT_HANDOFF")


from p335_mcp import register_corpus_tools
CORPUS_REGISTRY = register_corpus_tools(core, _owned_document)


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
