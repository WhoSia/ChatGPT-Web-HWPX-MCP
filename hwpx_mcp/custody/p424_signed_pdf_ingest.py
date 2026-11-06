"""P4.24 G2 signed native PDF receipt + encrypted artifact ingest coordinator.

Two durable stores are separate transactions: admission evidence can commit
before the PDF insert. This is intentionally recoverable with identical
receipt and immutable bytes, NOT an atomic distributed transaction.
No network endpoint, job scheduler, key registration or download privilege.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping

from hwpx_mcp.custody.p424_signed_pdf_handoff import assess_signed_pdf_handoff
from hwpx_mcp.evidence.p414_evidence_service import canonical_sha256, verify_signed_receipt


def ingest_signed_native_pdf(
    *,
    receipt: Mapping[str, Any],
    pdf_bytes: bytes,
    document_id: str,
    revision: int,
    expected_fixture_id: str,
    expected_head: str,
    authenticated_owner: str,
    authorized_job: Mapping[str, Any],
    document_store: Any,
    evidence_store: Any,
    pdf_store: Any,
    now=None,
) -> dict[str, Any]:
    """Fail closed unless authenticated owner, signed evidence and bytes agree.

    authenticated_owner is derived by the caller from OAuth middleware.
    The caller must also enforce job authorization before accepting the
    receipt; this function does NOT authorize arbitrary Windows agents.
    """
    if not isinstance(document_id, str) or not document_id:
        raise ValueError("DOCUMENT_ID_REQUIRED")
    if type(revision) is not int or revision < 1:
        raise ValueError("REVISION_REQUIRED")
    if not isinstance(authenticated_owner, str) or not authenticated_owner:
        raise PermissionError("AUTHENTICATED_OWNER_REQUIRED")
    if not isinstance(pdf_bytes, bytes) or not 64 <= len(pdf_bytes) <= 100 * 1024 * 1024:
        raise ValueError("PDF_BYTES_INVALID")
    document = document_store.load_revision(document_id, revision)
    if document is None or document.get("owner_subject") != authenticated_owner:
        raise PermissionError("HWPX_DOCUMENT_NOT_OWNED_OR_RETAINED")
    source = document.get("bytes")
    if not isinstance(source, bytes):
        raise ValueError("SOURCE_BYTES_UNAVAILABLE")
    source_hash = hashlib.sha256(source).hexdigest()
    if not isinstance(document.get("sha256"), str) or not hmac.compare_digest(
        source_hash, document["sha256"]
    ):
        raise ValueError("SOURCE_REVISION_DIGEST_MISMATCH")
    if document.get("document_id") != document_id or document.get("revision") != revision:
        raise PermissionError("SOURCE_REVISION_IDENTITY_MISMATCH")

    # A signature from a trusted Windows agent does NOT itself prove that
    # the server dispatched this job. Require server-authored job authorization
    # retrieved from durable job custody, never supplied by the client.
    signed = receipt.get("signed_payload") if isinstance(receipt, Mapping) else None
    if not isinstance(signed, Mapping) or not isinstance(authorized_job, Mapping):
        raise PermissionError("AUTHORIZED_CAPTURE_JOB_REQUIRED")
    expected_binding = {
        "document_id": document_id, "revision": revision,
        "document_sha256": source_hash, "owner_subject": authenticated_owner,
    }
    if (
        not isinstance(authorized_job.get("job_id"), str)
        or not isinstance(authorized_job.get("nonce"), str)
        or len(authorized_job["nonce"]) < 22
        or authorized_job.get("owner_subject") != authenticated_owner
        or authorized_job.get("document_id") != document_id
        or type(authorized_job.get("revision")) is not int
        or authorized_job["revision"] != revision
        or authorized_job.get("source_sha256") != source_hash
        or not isinstance(authorized_job.get("source_manifest_sha256"), str)
        or signed.get("source_manifest_sha256") != authorized_job["source_manifest_sha256"]
        or authorized_job.get("exact_head") != expected_head
        or authorized_job.get("fixture_id") != expected_fixture_id
        or authorized_job.get("status") != "ISSUED"
        or signed.get("job_id") != authorized_job["job_id"]
        or signed.get("nonce") != authorized_job["nonce"]
        or signed.get("exact_head") != authorized_job["exact_head"]
        or signed.get("document_binding") != expected_binding
    ):
        raise PermissionError("SIGNED_JOB_NOT_AUTHORIZED_FOR_DOCUMENT")

    registry = evidence_store.list_keys(active_only=False)
    admission = assess_signed_pdf_handoff(
        receipt=receipt, key_registry=registry, pdf_bytes=pdf_bytes,
        document_id=document_id, owner_subject=authenticated_owner,
        revision=revision, source_sha256=source_hash,
        expected_head=expected_head, expected_fixture_id=expected_fixture_id,
        now=now,
    )
    if admission["status"] != "ADMISSION_CHECK_PASSED":
        return {
            "status": "REJECTED", "stage": "SIGNED_ADMISSION",
            "issues": admission["issues"],
            "p414_issues": admission["p414_issues"],
            "production_delivery_authorized": False,
        }

    # P4.14's database stores signed evidence and rejects altered job/nonce
    # replay. Exact receipt replay is idempotent. Commit occurs before PDF
    # storage; an interrupted run may resume with the identical receipt.
    # Persist the authoritative complete P4.14 verifier decision: never
    # synthesize or downgrade signature validation fields at the DB boundary.
    full_validation = verify_signed_receipt(
        receipt, registry, now=now, expected_head=expected_head,
        allow_test_receipts=False,
    )
    if full_validation.get("accepted") is not True:
        raise PermissionError("P414_SIGNED_EVIDENCE_REVALIDATION_FAILED")
    evidence_result = evidence_store.record_attempt(receipt, full_validation)
    if evidence_result.get("accepted") is not True:
        return {
            "status": "REJECTED", "stage": "DURABLE_REPLAY_GATE",
            "issues": evidence_result.get("issues", []),
            "production_delivery_authorized": False,
        }
    evidence_id = canonical_sha256(receipt)
    if not hmac.compare_digest(evidence_id, str(evidence_result.get("evidence_id", ""))):
        raise RuntimeError("DURABLE_EVIDENCE_ID_MISMATCH")

    # Store independently verifies the accepted persisted evidence, owner,
    # source revision and exact PDF hash. No delivery URL is created here.
    custody_result = pdf_store.put_verified(
        admission=admission, document=document,
        evidence_id=evidence_id, authenticated_owner=authenticated_owner,
        pdf_bytes=pdf_bytes, evidence_store=evidence_store,
    )
    if custody_result.get("status") not in {
        "ENCRYPTED_CUSTODY_CREATED", "ENCRYPTED_CUSTODY_ALREADY_EXISTS"
    }:
        raise RuntimeError("PDF_CUSTODY_NOT_CONFIRMED")
    return {
        "status": "ENCRYPTED_PDF_CUSTODY_CONFIRMED",
        "evidence_id": evidence_id,
        "document_id": document_id,
        "revision": revision,
        "source_sha256": source_hash,
        "pdf_sha256": admission["pdf_sha256"],
        "pdf_bytes": admission["pdf_bytes"],
        "idempotent_receipt_retry": evidence_result.get("idempotent_retry") is True,
        "custody_status": custody_result["status"],
        "production_delivery_authorized": False,
        "owner_scoped_delivery_performed": False,
        "cross_store_atomicity": "NOT_GUARANTEED_RETRY_SAFE",
    }
