"""P4.24 two-stage signed PDF ingest, synthetic Ed25519 evidence only."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hwpx_mcp.custody.p424_signed_pdf_ingest import ingest_signed_native_pdf
from hwpx_mcp.evidence.p414_evidence_service import (
    AGENT_VERSION, PRODUCT, PROTOCOL_VERSION, SCHEMA, canonical_json, canonical_sha256,
)

SOURCE = b"PK" + b"synthetic-HWPX" * 30
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()
PDF = b"%PDF-1.7\n" + b"synthetic-native-pdf" * 15 + b"\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
DOC = "doc_" + "d" * 24
OWNER = "oauth-subject-1"
HEAD = "1" * 40
FIXTURE = "p424-synthetic"


def signed_fixture():
    now = datetime.now(timezone.utc)
    manifest = {"files": [{"fixture_id": FIXTURE, "path": "fixture.hwpx",
                           "sha256": SOURCE_SHA, "bytes": len(SOURCE),
                           "lowering_family": "SYNTHETIC"}]}
    payload = {
        "schema": SCHEMA, "protocol_version": PROTOCOL_VERSION,
        "product": PRODUCT, "job_id": "p424-ingest-test-001",
        "exact_head": HEAD, "source_manifest": manifest,
        "source_manifest_sha256": canonical_sha256(manifest),
        "hancom_version": "13.0.0.3622", "hancom_build": "13.0.0.3622",
        "hancom_executable_sha256": "b" * 64,
        "windows_version": "Windows Synthetic", "windows_build": "synthetic",
        "capture_agent_version": AGENT_VERSION, "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "nonce": "synthetic-ingest-nonce-123456789012345",
        "source_files": [{"fixture_id": FIXTURE, "path": "fixture.hwpx",
                          "sha256": SOURCE_SHA, "unchanged_after_capture": True}],
        "outputs": [{"fixture_id": FIXTURE, "pdf_sha256": PDF_SHA,
                     "bytes": len(PDF), "page_count": 1, "export_succeeded": True}],
        "capture_manifest_sha256": "c" * 64,
        "process_custody": {"global_kill_used": False},
        "capture_status": "CAPTURED", "recovery_status": "COMPLETE",
        "visual_verdict": "PASS",
        "visual_observations": {"human_adjudications": [
            {"fixture_id": FIXTURE, "reviewer": "local-operator",
             "reviewed_at": now.isoformat(), "status": "PASS"}]},
        "document_binding": {
            "document_id": DOC, "revision": 2,
            "owner_subject": OWNER, "document_sha256": SOURCE_SHA,
        },
    }
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    keys = {"test-key": {
        "agent_id": "test-agent", "status": "ACTIVE",
        "public_key_ed25519_b64": base64.b64encode(public).decode("ascii"),
    }}
    receipt = {
        "schema": SCHEMA, "agent_id": "test-agent", "key_id": "test-key",
        "signed_payload": payload, "canonical_sha256": canonical_sha256(payload),
        "signature_ed25519_b64": base64.b64encode(
            private.sign(canonical_json(payload))
        ).decode("ascii"),
    }
    return receipt, keys


class Documents:
    def __init__(self):
        self.source = SOURCE
        self.owner = OWNER

    def load_revision(self, doc, rev):
        if doc != DOC or rev != 2:
            return None
        return {"document_id": doc, "revision": rev, "bytes": self.source,
                "sha256": SOURCE_SHA, "owner_subject": self.owner}


class Evidence:
    def __init__(self, keys):
        self.keys = keys
        self.records = {}
        self.calls = 0
        self.reject = False

    def list_keys(self, *, active_only):
        assert active_only is False
        return self.keys

    def record_attempt(self, receipt, validation):
        self.calls += 1
        assert validation["accepted"] is True
        assert validation["authority"] == "P414_SIGNED_NATIVE_RECEIPT_VERIFIER"
        assert validation["raw_receipt_sha256"] == canonical_sha256(receipt)
        if self.reject:
            return {"accepted": False, "issues": [{"code": "REPLAYED_JOB_OR_NONCE"}]}
        evidence_id = canonical_sha256(receipt)
        duplicate = evidence_id in self.records
        self.records[evidence_id] = {
            "validation_result": validation,
            "normalized_evidence": {
                "test_only": False,
                "document_binding": receipt["signed_payload"]["document_binding"],
                "outputs": receipt["signed_payload"]["outputs"],
            },
        }
        return {"accepted": True, "evidence_id": evidence_id,
                "idempotent_retry": duplicate}

    def accepted_receipt_by_id(self, evidence_id):
        return self.records.get(evidence_id)


class PdfCustody:
    def __init__(self):
        self.results = {}
        self.fail_next = False

    def put_verified(self, *, admission, document, evidence_id,
                     authenticated_owner, pdf_bytes, evidence_store):
        assert admission["status"] == "ADMISSION_CHECK_PASSED"
        assert evidence_store.accepted_receipt_by_id(evidence_id)
        assert document["owner_subject"] == authenticated_owner
        assert hashlib.sha256(pdf_bytes).hexdigest() == PDF_SHA
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("TRANSIENT_DB_INSERT_FAILED")
        duplicate = evidence_id in self.results
        self.results[evidence_id] = pdf_bytes
        return {"status": "ENCRYPTED_CUSTODY_ALREADY_EXISTS" if duplicate
                else "ENCRYPTED_CUSTODY_CREATED"}


class SignedPdfIngestTests(unittest.TestCase):
    def setUp(self):
        self.receipt, keys = signed_fixture()
        self.docs, self.ev, self.pdfs = Documents(), Evidence(keys), PdfCustody()
        self.authorized_job = {
            "job_id": self.receipt["signed_payload"]["job_id"],
            "nonce": self.receipt["signed_payload"]["nonce"],
            "status": "ISSUED", "owner_subject": OWNER,
            "document_id": DOC, "revision": 2,
            "source_sha256": SOURCE_SHA, "exact_head": HEAD,
            "fixture_id": FIXTURE,
        }
        self.args = {
            "authorized_job": self.authorized_job,
            "receipt": self.receipt, "pdf_bytes": PDF, "document_id": DOC,
            "revision": 2, "expected_fixture_id": FIXTURE, "expected_head": HEAD,
            "authenticated_owner": OWNER, "document_store": self.docs,
            "evidence_store": self.ev, "pdf_store": self.pdfs,
        }

    def ingest(self, **change):
        return ingest_signed_native_pdf(**{**self.args, **change})

    def test_valid_signed_pdf_passes_two_stores_but_not_delivered(self):
        result = self.ingest()
        self.assertEqual(result["status"], "ENCRYPTED_PDF_CUSTODY_CONFIRMED")
        self.assertEqual(result["cross_store_atomicity"], "NOT_GUARANTEED_RETRY_SAFE")
        self.assertFalse(result["production_delivery_authorized"])
        self.assertEqual(self.pdfs.results[result["evidence_id"]], PDF)

    def test_same_receipt_retry_is_idempotent(self):
        first = self.ingest()
        second = self.ingest()
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertTrue(second["idempotent_receipt_retry"])
        self.assertEqual(second["custody_status"], "ENCRYPTED_CUSTODY_ALREADY_EXISTS")

    def test_transient_custody_error_can_resume_same_receipt(self):
        self.pdfs.fail_next = True
        with self.assertRaisesRegex(RuntimeError, "TRANSIENT_DB_INSERT_FAILED"):
            self.ingest()
        self.assertEqual(len(self.ev.records), 1)
        self.assertEqual(len(self.pdfs.results), 0)
        result = self.ingest()
        self.assertEqual(result["status"], "ENCRYPTED_PDF_CUSTODY_CONFIRMED")
        self.assertEqual(len(self.pdfs.results), 1)

    def test_missing_durable_job_authorization_blocks_signed_receipt(self):
        with self.assertRaisesRegex(PermissionError, "AUTHORIZED_CAPTURE_JOB_REQUIRED"):
            self.ingest(authorized_job=None)
        self.assertEqual(self.ev.calls, 0)

    def test_unissued_or_different_nonce_job_blocks_signed_receipt(self):
        for changes in [{"status": "DRAFT"}, {"nonce": "different-job-nonce-with-22-chars"},
                        {"owner_subject": "some-other-owner"},
                        {"source_sha256": "0" * 64},
                        {"exact_head": "2" * 40}]:
            with self.assertRaisesRegex(PermissionError, "SIGNED_JOB_NOT_AUTHORIZED"):
                self.ingest(authorized_job={**self.authorized_job, **changes})
        self.assertEqual(self.ev.calls, 0)

    def test_wrong_owner_denied_without_writing_evidence(self):
        with self.assertRaises(PermissionError):
            self.ingest(authenticated_owner="another-user")
        self.assertEqual(self.ev.calls, 0)

    def test_modified_source_denied_before_evidence(self):
        self.docs.source += b"tampered"
        with self.assertRaisesRegex(ValueError, "SOURCE_REVISION_DIGEST_MISMATCH"):
            self.ingest()
        self.assertEqual(self.ev.calls, 0)

    def test_pdf_tamper_denied_without_evidence(self):
        result = self.ingest(pdf_bytes=PDF + b"changed")
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(self.ev.calls, 0)

    def test_altered_signed_receipt_denied_without_evidence(self):
        r = {**self.receipt, "signed_payload": {
            **self.receipt["signed_payload"], "hancom_build": "tampered",
        }}
        result = self.ingest(receipt=r)
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(self.ev.calls, 0)

    def test_replayed_job_nonce_denied_before_pdf_store(self):
        self.ev.reject = True
        result = self.ingest()
        self.assertEqual(result["stage"], "DURABLE_REPLAY_GATE")
        self.assertEqual(self.pdfs.results, {})


if __name__ == "__main__":
    unittest.main()
