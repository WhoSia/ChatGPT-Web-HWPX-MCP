"""P4.24 G2 admission boundary for P4.14-signed native PDF artifacts.

Pure fail-closed validation. It does not transport, persist, decrypt, serve,
or mark documents delivered. Durable replay rejection and encrypted
owner-scoped custody remain separate mandatory production operations.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any, Mapping

from hwpx_mcp.evidence.p414_evidence_service import verify_signed_receipt


def _equal(a: Any, b: Any) -> bool:
    return isinstance(a, str) and isinstance(b, str) and hmac.compare_digest(a, b)


def assess_signed_pdf_handoff(
    *,
    receipt: Mapping[str, Any],
    key_registry: Mapping[str, Any],
    pdf_bytes: bytes,
    document_id: str,
    owner_subject: str,
    revision: int,
    source_sha256: str,
    expected_head: str,
    expected_fixture_id: str,
    now: datetime | None = None,
    max_pdf_bytes: int = 100 * 1024 * 1024,
) -> dict[str, Any]:
    """Check exact signed job + owner/revision/source and actual PDF bytes.

    Only call after authenticated request ownership has been established by
    the existing DocumentStore. Owner identity must come from auth context,
    never a user-supplied request field. No result authorizes delivery.
    """
    issues: list[str] = []
    if not isinstance(pdf_bytes, bytes) or not 64 <= len(pdf_bytes) <= max_pdf_bytes:
        issues.append("PDF_BYTES_INVALID_OR_TOO_LARGE")
    if not isinstance(document_id, str) or not document_id.strip():
        issues.append("DOCUMENT_ID_REQUIRED")
    if not isinstance(owner_subject, str) or not owner_subject.strip():
        issues.append("AUTHENTICATED_OWNER_REQUIRED")
    if type(revision) is not int or revision < 1:
        issues.append("REVISION_REQUIRED")
    if not isinstance(expected_head, str) or len(expected_head) != 40:
        issues.append("EXACT_HEAD_REQUIRED")
    if not isinstance(expected_fixture_id, str) or not expected_fixture_id.strip():
        issues.append("FIXTURE_ID_REQUIRED")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        issues.append("SOURCE_DIGEST_REQUIRED")

    validation = verify_signed_receipt(
        receipt, key_registry, now=now, expected_head=expected_head,
        allow_test_receipts=False,
    )
    if not validation.get("accepted"):
        issues.append("P414_SIGNATURE_OR_PROTOCOL_REJECTED")
    payload = receipt.get("signed_payload")
    if not isinstance(payload, Mapping):
        payload = {}

    if payload.get("capture_status") != "CAPTURED":
        issues.append("NATIVE_CAPTURE_NOT_COMPLETED")
    if payload.get("recovery_status") != "COMPLETE":
        issues.append("CAPTURE_RECOVERY_INCOMPLETE")
    if payload.get("visual_verdict") not in ("PASS", "PASS_WITH_RESIDUALS"):
        issues.append("HUMAN_VISUAL_REVIEW_REQUIRED")
    custody = payload.get("process_custody")
    if not isinstance(custody, Mapping) or custody.get("global_kill_used") is not False:
        issues.append("UNSAFE_PROCESS_CUSTODY")

    binding = payload.get("document_binding")
    if not isinstance(binding, Mapping):
        binding = {}
    if (
        binding.get("document_id") != document_id
        or type(binding.get("revision")) is not int
        or binding.get("revision") != revision
        or not _equal(binding.get("document_sha256"), source_sha256)
        or binding.get("owner_subject") != owner_subject
    ):
        issues.append("SIGNED_OWNER_REVISION_SOURCE_MISMATCH")

    sources = payload.get("source_files")
    outputs = payload.get("outputs")
    if not isinstance(sources, list):
        sources = []
    if not isinstance(outputs, list):
        outputs = []
    source_matches = [
        row for row in sources
        if isinstance(row, Mapping) and row.get("fixture_id") == expected_fixture_id
    ]
    output_matches = [
        row for row in outputs
        if isinstance(row, Mapping) and row.get("fixture_id") == expected_fixture_id
    ]
    if len(sources) != 1 or len(outputs) != 1 or len(source_matches) != 1 or len(output_matches) != 1:
        issues.append("ONE_DOCUMENT_ONE_NATIVE_PDF_REQUIRED")
    elif (
        not _equal(source_matches[0].get("sha256"), source_sha256)
        or source_matches[0].get("unchanged_after_capture") is not True
    ):
        issues.append("SOURCE_CAPTURE_DIGEST_MISMATCH")

    digest = hashlib.sha256(pdf_bytes).hexdigest() if isinstance(pdf_bytes, bytes) else None
    if isinstance(pdf_bytes, bytes) and (
        not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-2048:]
    ):
        issues.append("PDF_STRUCTURE_MARKERS_MISSING")
    if len(output_matches) == 1:
        out = output_matches[0]
        if (
            not _equal(out.get("pdf_sha256"), digest)
            or type(out.get("bytes")) is not int
            or out.get("bytes") != (len(pdf_bytes) if isinstance(pdf_bytes, bytes) else -1)
            or type(out.get("page_count")) is not int
            or out.get("page_count") < 1
            or out.get("export_succeeded") is not True
        ):
            issues.append("SIGNED_PDF_BYTES_OR_PAGE_COUNT_MISMATCH")

    return {
        "schema": "p424.signed-native-pdf-handoff.v1",
        "status": "ADMISSION_CHECK_PASSED" if not issues else "REJECTED",
        "issues": sorted(set(issues)),
        "pdf_sha256": digest,
        "pdf_bytes": len(pdf_bytes) if isinstance(pdf_bytes, bytes) else None,
        "signed_evidence_sha256": validation.get("raw_receipt_sha256"),
        "p414_signature_accepted": validation.get("accepted") is True,
        "p414_issues": validation.get("issues", []),
        "document_id": document_id,
        "revision": revision,
        "native_engine": "HANCOM_HWP_EXE_COM" if not issues else "UNVERIFIED",
        "durable_replay_check_performed": False,
        "encrypted_custody_performed": False,
        "owner_scoped_delivery_performed": False,
        "production_delivery_authorized": False,
    }
