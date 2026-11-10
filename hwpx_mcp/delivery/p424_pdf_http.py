"""Feature-gated P4.24 native PDF HTTP handoff via existing OAuth provider.

The GET endpoint never treats the signed URL as a bearer authorization.
It requires a fresh OAuth Authorization header on EVERY request. This
integration is opt-in, and does not schedule remote Windows conversions.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from starlette.responses import PlainTextResponse, Response

from hwpx_mcp.delivery.p424_pdf_delivery import issue_pdf_delivery, redeem_pdf_delivery
from hwpx_mcp.storage.p424_pdf_store import P424PdfStore

_ID = re.compile(r"^doc_[A-Za-z0-9_-]{20,64}$")
_EVIDENCE = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def enabled() -> bool:
    return os.environ.get("P424_NATIVE_PDF_DELIVERY_ENABLED") == "YES"


def _secret(core: Any) -> bytes:
    raw = core._download_secret()
    if not isinstance(raw, bytes) or len(raw) < 32:
        raise RuntimeError("P424_DOWNLOAD_SECRET_TOO_SHORT")
    return raw


@lru_cache(maxsize=1)
def _cached_store(database_url: str, state_secret: str) -> P424PdfStore:
    # Schema DDL executes only on first use, never on each PDF download.
    # Runtime configuration or key rotation requires an application restart.
    return P424PdfStore(database_url, state_secret)


def _store(core: Any):
    if not enabled():
        raise RuntimeError("P424_NATIVE_PDF_DELIVERY_DISABLED")
    if not core.PUBLIC_BASE_URL.startswith("https://"):
        raise RuntimeError("P424_HTTPS_REQUIRED")
    database_url = os.environ.get("P424_PDF_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("P424_PDF_DATABASE_URL_REQUIRED")
    return _cached_store(database_url, core.STATE_SECRET)


def list_authenticated_native_pdfs(core: Any, *,
                                    document_id: str, revision: int,
                                    limit: int = 20) -> dict:
    """Discover retained PDFs without asking the user for a 64-digit ID.

    No PDF is fabricated or scheduled if the revision lacks a native PDF.
    """
    if not enabled():
        return {"ok": False, "code": "P424_NATIVE_PDF_DELIVERY_DISABLED"}
    subject = core._caller_subject()
    core._paths(document_id)
    if type(revision) is not int or revision < 1:
        raise ValueError("REVISION_INVALID")
    document = core.DOCUMENT_STORE.load_revision(document_id, revision)
    if document is None or document.get("owner_subject") != subject:
        raise FileNotFoundError("PDF_SOURCE_REVISION_UNAVAILABLE")
    pdfs = _store(core).list_owned(
        document_id=document_id, revision=revision,
        authenticated_owner=subject,
        source_sha256=document["sha256"], limit=limit,
    )
    return {
        "ok": True, "document_id": document_id, "revision": revision,
        "status": "PDF_READY" if pdfs else "PDF_NOT_GENERATED",
        "pdf_count": len(pdfs), "artifacts": pdfs,
        "native_pdf_created_by_this_call": False,
    }


def issue_authenticated_pdf_link(core: Any, *,
                                 document_id: str, revision: int,
                                 evidence_id: str | None = None,
                                 link_ttl_seconds: int = 300) -> dict:
    """Invoke from an authenticated MCP tool, never a public anonymous route."""
    if not enabled():
        return {"ok": False, "code": "P424_NATIVE_PDF_DELIVERY_DISABLED"}
    subject = core._caller_subject()
    core._paths(document_id)  # existing opaque document ID validation
    pdf_store = _store(core)
    if evidence_id is None:
        discovery = list_authenticated_native_pdfs(
            core, document_id=document_id, revision=revision, limit=1,
        )
        if not discovery["artifacts"]:
            return {
                "ok": False, "code": "P424_PDF_NOT_GENERATED",
                "document_id": document_id, "revision": revision,
                "native_pdf_created": False,
            }
        evidence_id = discovery["artifacts"][0]["evidence_id"]
    result = issue_pdf_delivery(
        pdf_store=pdf_store, document_store=core.DOCUMENT_STORE,
        authenticated_owner=subject, document_id=document_id,
        revision=revision, evidence_id=evidence_id,
        secret=_secret(core), public_base_url=core.PUBLIC_BASE_URL,
        link_ttl_seconds=link_ttl_seconds,
    )
    return {
        "ok": True, **result,
        "download_authentication": "OAUTH_BEARER_HEADER_REQUIRED",
        "browser_link_without_oauth_header_supported": False,
    }


async def _request_subject(core: Any, request: Any) -> str | None:
    # A ChatGPT MCP auth context is not guaranteed in custom Starlette
    # routes, so validate the header through the same OAuth provider.
    header = request.headers.get("authorization", "")
    if not isinstance(header, str) or not re.fullmatch(r"Bearer [^\s]+", header, re.IGNORECASE):
        return None
    access = header.split(" ", 1)[1]
    token = await core.OAUTH_PROVIDER.load_access_token(access)
    if token is None:
        return None
    if (
        token.subject != core.SUBJECT
        or core.HWPX_SCOPE not in token.scopes
        or str(token.resource).rstrip("/") != core.MCP_RESOURCE_URL.rstrip("/")
    ):
        return None
    return token.subject


async def download_authenticated_pdf(core: Any, request: Any) -> Response:
    """Actual HTTP GET handler; no Authorization header means no PDF."""
    headers = {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    if not enabled():
        return PlainTextResponse("Native PDF delivery is disabled", status_code=503, headers=headers)
    try:
        subject = await _request_subject(core, request)
    except Exception:
        return PlainTextResponse("Authentication unavailable", status_code=503, headers=headers)
    if not subject:
        return PlainTextResponse("OAuth authorization required", status_code=401, headers=headers)
    doc_id = request.path_params.get("document_id", "")
    qs = request.query_params
    try:
        if not _ID.fullmatch(doc_id):
            raise ValueError("invalid document")
        revision, expiry = int(qs.get("rev", "")), int(qs.get("exp", ""))
        evidence_id, digest, signature = qs.get("ev", ""), qs.get("sha", ""), qs.get("sig", "")
        if not _EVIDENCE.fullmatch(evidence_id) or not _SHA.fullmatch(digest):
            raise ValueError("invalid signed identity")
        if not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise ValueError("invalid signed token")
        store = _store(core)
        pdf = redeem_pdf_delivery(
            pdf_store=store, document_store=core.DOCUMENT_STORE,
            authenticated_owner=subject, document_id=doc_id,
            revision=revision, evidence_id=evidence_id,
            pdf_sha256=digest, expires_at=expiry, signature=signature,
            secret=_secret(core),
        )
    except (ValueError, PermissionError, FileNotFoundError):
        # Prevent document existence, owner or signature validity probing.
        return PlainTextResponse("PDF link invalid or unavailable", status_code=404, headers=headers)
    except Exception:
        # Never reveal DB, path, key or document information to the client.
        return PlainTextResponse("PDF delivery unavailable", status_code=503, headers=headers)

    return Response(
        pdf, media_type="application/pdf",
        headers={
            **headers,
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote('native-hancom.pdf')}",
            "ETag": f'"{digest}"',
        },
    )
