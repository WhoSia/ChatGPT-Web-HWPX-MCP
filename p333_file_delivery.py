"""File delivery over the existing revision store; no document/graph engine."""
from __future__ import annotations

import hashlib
import hmac
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from mcp.types import CallToolResult, ResourceLink, TextContent
from starlette.responses import PlainTextResponse, Response

MIME = "application/hwp+zip"


def delivery_contract() -> dict:
    return {
        "phase": "P3.33",
        "primary_workflow": ["generate_document", "edit_document_and_deliver", "deliver_document"],
        "ancestry": ["P3.21 composer", "P2 atomic edits", "P3.0 revision custody", "P3.21-P3.32 native layers"],
        "handoff": "MCP resource_link plus signed revision-bound HTTP attachment",
        "link_ttl_seconds": {"minimum": 60, "maximum": 900, "default": 900},
        "recovery": "Reissue deliver_document for the retained revision; never repeat an edit to refresh a link.",
        "evidence_gates": {
            "chatgpt_attachment_rendering": "HOST_OBSERVATION_REQUIRED",
            "hancom_open_resave": "NATIVE_RENDER_EVIDENCE_REQUIRED",
            "rare_features": {
                "lane": "INDEPENDENT_OF_PRIMARY_DELIVERY",
                "status": "EVIDENCE_GATE_CLOSED",
                "features": ["pixel recognition", "occupied name-carrier override", "cross-anchor adoption", "parallel managed edges", "smart connectLine endpoints", "semantic auto-repair", "mixed-run shape text", "polygon preserving resize", "native callout", "existing group/ungroup", "tracked-change accept/reject/protection", "column insertion", "second Hancom version"],
                "promotion_requires": ["bounded native evidence", "family regression", "primary workflow regression", "OAuth and Docker smoke", "canonical lineage update"],
            },
        },
    }


def _signature(core, document_id: str, revision: int, digest: str, expiry: int) -> str:
    payload = f"p333-delivery\0{document_id}\0{revision}\0{digest}\0{expiry}".encode()
    return hmac.new(core._download_secret(), payload, hashlib.sha256).hexdigest()


def export_revision(core, document_id: str, link_ttl_seconds: int = 900, revision: int | None = None) -> dict:
    core._paths(document_id)  # validate opaque identity before storage access
    subject = core._caller_subject()
    row = (core.DOCUMENT_STORE.load_current(document_id) if revision is None
           else core.DOCUMENT_STORE.load_revision(document_id, int(revision)))
    if row is None:
        raise FileNotFoundError("Document revision is no longer retained")
    if row["owner_subject"] != subject:
        raise PermissionError("Document is not owned by the authenticated principal")
    raw = row["bytes"]
    digest = hashlib.sha256(raw).hexdigest()
    if digest != row["sha256"]:
        raise ValueError("Revision integrity mismatch")
    # Validate private exact bytes, never the shared mutable execution cache.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "export.hwpx"
        path.write_bytes(raw)
        validation = core.validate_hwpx_package(path, ingress=False)
    expiry = min(int(time.time()) + max(60, min(int(link_ttl_seconds), 900)), int(row["expires_at_epoch"]))
    if expiry <= int(time.time()):
        raise FileNotFoundError("Document expired")
    revision = int(row["revision"])
    query = urlencode({"rev": revision, "sha": digest, "exp": expiry,
                       "sig": _signature(core, document_id, revision, digest, expiry)})
    return {
        "ok": True, "document_id": document_id, "revision": revision,
        "filename": core.sanitize_filename(row["metadata"]["filename"]),
        "bytes": len(raw), "sha256": digest, "mime_type": MIME,
        "download_url": f"{core.PUBLIC_BASE_URL}/deliveries/{document_id}?{query}",
        "download_expires_at": core._utc_iso(expiry), "cache_policy": "private, no-store",
        "validation": {"valid": validation["valid"], "sha256": validation["sha256"]},
        "delivery_status": "READY_FOR_DOWNLOAD", "host_attachment_status": "NOT_OBSERVED",
    }


def handoff(receipt: dict) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(type="text", text=f"[{receipt['filename']}]({receipt['download_url']})\n"
                        f"Download the validated HWPX file. Link expires {receipt['download_expires_at']}."),
            ResourceLink(type="resource_link", uri=receipt["download_url"],
                         name=receipt["filename"], mimeType=MIME, size=receipt["bytes"],
                         description="Validated HWPX file, bound to one retained revision."),
        ],
        structuredContent=receipt,
    )


async def download_revision(core, request):
    document_id = request.path_params.get("document_id", "")
    if not core.DOC_ID_RE.fullmatch(document_id):
        return PlainTextResponse("Invalid document id", status_code=400)
    try:
        revision = int(request.query_params.get("rev", "0"))
        expiry = int(request.query_params.get("exp", "0"))
    except ValueError:
        return PlainTextResponse("Invalid revision or expiry", status_code=400)
    if expiry <= int(time.time()):
        return PlainTextResponse("Download link expired; request a fresh delivery", status_code=410)
    digest = request.query_params.get("sha", "")
    signature = request.query_params.get("sig", "")
    expected = _signature(core, document_id, revision, digest, expiry)
    if not signature or not hmac.compare_digest(signature, expected):
        return PlainTextResponse("Invalid download signature", status_code=403)
    row = core.DOCUMENT_STORE.load_revision(document_id, revision)
    if row is None:
        return PlainTextResponse("Document revision unavailable", status_code=404)
    raw = row["bytes"]
    if row["sha256"] != digest or hashlib.sha256(raw).hexdigest() != digest:
        return PlainTextResponse("Revision integrity mismatch", status_code=409)
    filename = core.sanitize_filename(row["metadata"]["filename"])
    return Response(raw, media_type=MIME, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer", "ETag": f'"{digest}"',
    })
