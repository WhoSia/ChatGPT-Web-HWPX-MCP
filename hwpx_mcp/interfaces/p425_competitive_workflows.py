"""P4.25 everyday HWPX editing tools: exposed from existing P3.37 engine.

Inspired by template filling and plan/preview/apply UX offered by MIT
HWPX MCP peers. No upstream source code is copied. Reuses existing native
inline editing and the P3.0 durable revision store, not a new XML engine.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from hwpx_mcp.orchestration.p337_product_workflow import (
    fill_template_atomic,
    plan_literal_placeholder_fill,
)


def register_competitive_workflows(core):
    """Register practical tools on the same authenticated Streamable HTTP host."""

    def _owned(document_id: str):
        subject = core._caller_subject()
        metadata = core._load_metadata(document_id)
        if metadata["owner_subject"] != subject:
            raise PermissionError("DOCUMENT_NOT_OWNED")
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row["owner_subject"] != subject:
            raise FileNotFoundError("DOCUMENT_REVISION_NOT_AVAILABLE")
        return metadata, row

    @core.mcp.tool()
    def preview_template_fill(
        document_id: str,
        values: dict[str, str],
        require_each: bool = True,
        require_unique: bool = False,
    ) -> dict:
        """Preview {{placeholder}}/literal replacements before modifying an HWPX.

        Supports text in the existing inline editor's coordinate map,
        including any table-cell text represented there. Returns an edit
        count and match counts, not the entire original document.
        """
        metadata, row = _owned(document_id)
        with tempfile.TemporaryDirectory(prefix="p425-preview-") as tmp:
            template = Path(tmp) / "source.hwpx"
            template.write_bytes(row["bytes"])
            plan = plan_literal_placeholder_fill(
                template, values, require_each=require_each,
                require_unique=require_unique,
            )
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "source_sha256": row["sha256"],
            "operation_count": plan["operation_count"],
            "matches": plan["matches"],
            "plan_sha256": plan["plan_sha256"],
            "committed": False,
        }

    @core.mcp.tool()
    def fill_template_and_deliver(
        document_id: str,
        values: dict[str, str],
        expected_revision: int,
        require_each: bool = True,
        require_unique: bool = False,
    ) -> dict:
        """Fill placeholders, save one durable HWPX revision, return its download.

        No external file path required. The prior revision is retained.
        If another editor commits first, P3.0 revision CAS rejects this edit.
        An unchanged existing HWPX can be exported again without repeating
        a mutation.
        """
        metadata, row = _owned(document_id)
        if type(expected_revision) is not int or row["revision"] != expected_revision:
            raise RuntimeError("REVISION_CONFLICT_REFRESH_AND_PREVIEW")
        with tempfile.TemporaryDirectory(prefix="p425-fill-") as tmp:
            source = Path(tmp) / "template.hwpx"
            output = Path(tmp) / "filled.hwpx"
            source.write_bytes(row["bytes"])
            receipt = fill_template_atomic(
                source, output, values,
                require_each=require_each, require_unique=require_unique,
                validator=lambda path: core.validate_hwpx_package(path, ingress=False),
            )
            changed = output.read_bytes()
        digest = hashlib.sha256(changed).hexdigest()
        # Commit into the existing owner-specific durable document, never
        # produce a second anonymous file or write a user-supplied path.
        new_metadata = dict(metadata)
        new_metadata["revision"] = expected_revision + 1
        new_metadata["sha256"] = digest
        new_metadata["bytes"] = len(changed)
        new_metadata["last_template_fill_sha256"] = receipt["fill_sha256"]
        commit = core.DOCUMENT_STORE.put_revision(
            document_id=document_id,
            owner_subject=row["owner_subject"],
            revision=expected_revision + 1,
            expected_revision=expected_revision,
            data=changed,
            metadata=new_metadata,
            expires_at_epoch=row["expires_at_epoch"],
        )
        # Hydrate via the canonical document cache read path; a future
        # operation never sees stale cached bytes after an edit.
        core._load_metadata(document_id)
        from hwpx_mcp.delivery.p333_file_delivery import export_revision
        export = export_revision(core, document_id, link_ttl_seconds=900)
        return {
            "ok": True, "document_id": document_id,
            "revision": expected_revision + 1,
            "sha256": digest,
            "bytes": len(changed),
            "matches": receipt["matches"],
            "operation_count": receipt["operation_count"],
            "fill_receipt_sha256": receipt["fill_sha256"],
            "commit_receipt": commit,
            "download_url": export["download_url"],
            "filename": export["filename"],
            "mime_type": export["mime_type"],
            "delivery_status": export["delivery_status"],
            "source_template_mutated": False,
        }
