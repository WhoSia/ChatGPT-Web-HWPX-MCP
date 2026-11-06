"""Authenticated, revision-bound native PDF delivery contract (P4.24 G2).

This is a pure service primitive, NOT an installed MCP route. Unlike the
legacy HWPX bearer download URL, redemption here requires a fresh OAuth
subject supplied by the host authentication middleware. The token alone
must never grant access.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Any
from urllib.parse import urlencode

MAX_TTL_SECONDS = 900
MIN_TTL_SECONDS = 60


def _tag(
    secret: bytes, *, owner: str, document_id: str, revision: int,
    source_sha: str, evidence_id: str, pdf_sha: str, expires_at: int,
) -> str:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("PDF_DELIVERY_SECRET_REQUIRED")
    fields = ["p424-native-pdf-delivery-v1", owner, document_id,
              revision, source_sha, evidence_id, pdf_sha, expires_at]
    msg = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def issue_pdf_delivery(
    *, pdf_store: Any, document_store: Any, authenticated_owner: str,
    document_id: str, revision: int, evidence_id: str, secret: bytes,
    public_base_url: str, now: int | None = None,
    link_ttl_seconds: int = 300,
) -> dict:
    """Issue link only after verifying retained source and encrypted PDF.

    Security requirement: authenticated_owner must come from OAuth, not an
    MCP field. The server also rechecks owner and source upon redemption.
    """
    if not authenticated_owner:
        raise ValueError("PDF_DELIVERY_IDENTITY_REQUIRED")
    if not isinstance(document_id, str) or not re.fullmatch(r"doc_[A-Za-z0-9_-]{20,64}", document_id):
        raise ValueError("PDF_DELIVERY_DOCUMENT_ID_INVALID")
    if not isinstance(evidence_id, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_id):
        raise ValueError("PDF_DELIVERY_EVIDENCE_ID_INVALID")
    if type(revision) is not int or revision < 1:
        raise ValueError("PDF_DELIVERY_REVISION_REQUIRED")
    if type(link_ttl_seconds) is not int:
        raise ValueError("PDF_DELIVERY_TTL_INVALID")
    if not public_base_url.startswith("https://"):
        raise ValueError("PDF_DELIVERY_REQUIRES_HTTPS")
    current = int(time.time()) if now is None else int(now)
    source = document_store.load_revision(document_id, revision)
    if source is None or source.get("owner_subject") != authenticated_owner:
        raise PermissionError("PDF_SOURCE_NOT_OWNED_OR_EXPIRED")
    original = source.get("bytes")
    if not isinstance(original, bytes) or hashlib.sha256(original).hexdigest() != source.get("sha256"):
        raise ValueError("PDF_SOURCE_REVISION_INVALID")
    pdf = pdf_store.load_owned(
        evidence_id=evidence_id, authenticated_owner=authenticated_owner,
        document_store=document_store, expected_document_id=document_id,
        expected_revision=revision, expected_source_sha256=source["sha256"],
    )
    pdf_sha = hashlib.sha256(pdf).hexdigest()
    expiry = min(current + max(MIN_TTL_SECONDS, min(link_ttl_seconds, MAX_TTL_SECONDS)),
                 int(source["expires_at_epoch"]))
    if expiry <= current:
        raise FileNotFoundError("PDF_SOURCE_REVISION_EXPIRED")
    signature = _tag(secret, owner=authenticated_owner, document_id=document_id,
                     revision=revision, source_sha=source["sha256"],
                     evidence_id=evidence_id, pdf_sha=pdf_sha, expires_at=expiry)
    params = urlencode({"rev": revision, "ev": evidence_id,
                        "sha": pdf_sha, "exp": expiry, "sig": signature})
    return {
        "status": "READY_FOR_AUTHENTICATED_DOWNLOAD",
        "document_id": document_id, "revision": revision,
        "evidence_id": evidence_id, "pdf_sha256": pdf_sha,
        "pdf_bytes": len(pdf), "mime_type": "application/pdf",
        "download_url": public_base_url.strip().rstrip("/") + "/p424/native-pdf/" + document_id + "?" + params,
        "expires_at_epoch": expiry,
        "redemption_requires_oauth_subject": True,
        "owner_scoped_delivery_performed": False,
        "host_attachment_status": "NOT_OBSERVED",
    }


def redeem_pdf_delivery(
    *, pdf_store: Any, document_store: Any, authenticated_owner: str,
    document_id: str, revision: int, evidence_id: str, pdf_sha256: str,
    expires_at: int, signature: str, secret: bytes, now: int | None = None,
) -> bytes:
    """Return verified PDF bytes; host must enforce OAuth and no-store headers."""
    current = int(time.time()) if now is None else int(now)
    if (not isinstance(document_id, str) or not re.fullmatch(r"doc_[A-Za-z0-9_-]{20,64}", document_id)
        or not isinstance(evidence_id, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_id)
        or not isinstance(pdf_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", pdf_sha256)):
        raise PermissionError("PDF_DELIVERY_INVALID_IDENTITY")
    if type(revision) is not int or revision < 1 or type(expires_at) is not int:
        raise PermissionError("PDF_DELIVERY_INVALID_PARAMETERS")
    if not authenticated_owner or not signature or expires_at <= current:
        raise PermissionError("PDF_DELIVERY_EXPIRED_OR_UNAUTHENTICATED")
    if expires_at - current > MAX_TTL_SECONDS:
        raise PermissionError("PDF_DELIVERY_TTL_EXCEEDED")
    source = document_store.load_revision(document_id, revision)
    if source is None or source.get("owner_subject") != authenticated_owner:
        raise PermissionError("PDF_SOURCE_NOT_OWNED_OR_EXPIRED")
    if int(source["expires_at_epoch"]) < expires_at:
        raise PermissionError("PDF_DELIVERY_EXCEEDS_DOCUMENT_RETENTION")
    calculated = _tag(
        secret, owner=authenticated_owner, document_id=document_id,
        revision=revision, source_sha=source["sha256"],
        evidence_id=evidence_id, pdf_sha=pdf_sha256, expires_at=expires_at,
    )
    if not hmac.compare_digest(calculated, signature):
        raise PermissionError("PDF_DELIVERY_BAD_SIGNATURE")
    pdf = pdf_store.load_owned(
        evidence_id=evidence_id, authenticated_owner=authenticated_owner,
        document_store=document_store, expected_document_id=document_id,
        expected_revision=revision, expected_source_sha256=source["sha256"],
    )
    if not hmac.compare_digest(hashlib.sha256(pdf).hexdigest(), pdf_sha256):
        raise ValueError("PDF_DELIVERY_BYTES_CHANGED")
    return pdf
