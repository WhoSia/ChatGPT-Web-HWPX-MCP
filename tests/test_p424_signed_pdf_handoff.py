"""P4.24 signed-PDF handoff admission: synthetic signatures, never private PDFs."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hwpx_mcp.custody.p424_signed_pdf_handoff import assess_signed_pdf_handoff
from hwpx_mcp.evidence.p414_evidence_service import (
    AGENT_VERSION, PRODUCT, PROTOCOL_VERSION, SCHEMA, canonical_json, canonical_sha256
)


PDF = b"%PDF-1.7\\n" + b"synthetic-only" * 15 + b"\\n%%EOF\\n"
DOC = "doc-synthetic-p424"
HEAD = "1" * 40
SOURCE_SHA = "a" * 64
FIXTURE = "synthetic-document"


def fixture(*, visual="PASS", owner="subject-test-1"):
    clock = datetime.now(timezone.utc)
    source = {"fixture_id": FIXTURE, "path": "fixture.hwpx", "sha256": SOURCE_SHA,
              "bytes": 2048, "lowering_family": "SYNTHETIC"}
    manifest = {"files": [source]}
    payload = {
        "schema": SCHEMA, "protocol_version": PROTOCOL_VERSION, "product": PRODUCT,
        "job_id": "p424-test-job-001", "exact_head": HEAD,
        "source_manifest_sha256": canonical_sha256(manifest), "source_manifest": manifest,
        "hancom_version": "13.0.0.3622", "hancom_build": "13.0.0.3622",
        "hancom_executable_sha256": "b" * 64,
        "windows_version": "Windows test", "windows_build": "testbuild",
        "capture_agent_version": AGENT_VERSION,
        "issued_at": clock.isoformat(),
        "expires_at": (clock + timedelta(hours=1)).isoformat(),
        "nonce": "p424-synthetic-nonce-long-enough-xyz123",
        "source_files": [{"fixture_id": FIXTURE, "path": "fixture.hwpx",
                          "sha256": SOURCE_SHA, "unchanged_after_capture": True}],
        "outputs": [{"fixture_id": FIXTURE, "pdf_sha256": hashlib.sha256(PDF).hexdigest(),
                     "bytes": len(PDF), "page_count": 1, "export_succeeded": True}],
        "capture_manifest_sha256": "e" * 64,
        "process_custody": {"global_kill_used": False},
        "capture_status": "CAPTURED", "recovery_status": "COMPLETE",
        "visual_verdict": visual,
        "visual_observations": {"human_adjudications": [
            {"fixture_id": FIXTURE, "reviewer": "human-operator", "reviewed_at": clock.isoformat(),
             "status": visual}]},
        "document_binding": {"document_id": DOC, "revision": 2,
                             "document_sha256": SOURCE_SHA, "owner_subject": owner},
    }
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    keys = {"synthetic-key": {"agent_id": "synthetic-agent", "status": "ACTIVE",
                             "public_key_ed25519_b64": base64.b64encode(public).decode("ascii")}}
    def sign(data):
        return {
            "schema": SCHEMA, "agent_id": "synthetic-agent", "key_id": "synthetic-key",
            "signed_payload": data,
            "canonical_sha256": canonical_sha256(data),
            "signature_ed25519_b64": base64.b64encode(key.sign(canonical_json(data))).decode("ascii")
        }
    return payload, keys, sign


class SignedNativePdfAdmissionTests(unittest.TestCase):
    def check(self, *, payload=None, keys=None, sign=None, pdf=PDF, owner="subject-test-1", head=HEAD):
        if payload is None:
            payload, keys, sign = fixture()
        return assess_signed_pdf_handoff(
            receipt=sign(payload), key_registry=keys, pdf_bytes=pdf,
            document_id=DOC, owner_subject=owner, revision=2,
            source_sha256=SOURCE_SHA, expected_head=head, expected_fixture_id=FIXTURE,
        )

    def test_valid_signed_single_document_pdf_is_only_admitted_not_delivered(self):
        result = self.check()
        self.assertEqual(result["status"], "ADMISSION_CHECK_PASSED")
        self.assertTrue(result["p414_signature_accepted"])
        self.assertFalse(result["production_delivery_authorized"])
        self.assertFalse(result["encrypted_custody_performed"])
        self.assertFalse(result["durable_replay_check_performed"])
        self.assertFalse(result["owner_scoped_delivery_performed"])

    def test_wrong_owner_refused_even_with_valid_signature(self):
        result = self.check(owner="different-user")
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("SIGNED_OWNER_REVISION_SOURCE_MISMATCH", result["issues"])

    def test_modified_pdf_refused_even_with_valid_signature(self):
        result = self.check(pdf=PDF + b"tampered")
        self.assertIn("SIGNED_PDF_BYTES_OR_PAGE_COUNT_MISMATCH", result["issues"])

    def test_visual_pending_blocks_pdf_admission(self):
        p, k, sign = fixture(visual="PENDING")
        result = self.check(payload=p, keys=k, sign=sign)
        self.assertIn("HUMAN_VISUAL_REVIEW_REQUIRED", result["issues"])

    def test_valid_signature_missing_signed_owner_is_refused(self):
        p, k, sign = fixture()
        p["document_binding"].pop("owner_subject")
        result = self.check(payload=p, keys=k, sign=sign)
        self.assertIn("SIGNED_OWNER_REVISION_SOURCE_MISMATCH", result["issues"])

    def test_wrong_exact_head_blocks_admission(self):
        result = self.check(head="2" * 40)
        self.assertIn("P414_SIGNATURE_OR_PROTOCOL_REJECTED", result["issues"])

    def test_false_visual_pass_cannot_be_self_asserted(self):
        p, k, sign = fixture()
        p["visual_observations"]["human_adjudications"] = []
        result = self.check(payload=p, keys=k, sign=sign)
        self.assertIn("P414_SIGNATURE_OR_PROTOCOL_REJECTED", result["issues"])

    def test_multiple_outputs_rejected_as_ambiguous(self):
        p, k, sign = fixture()
        p["outputs"].append(dict(p["outputs"][0], fixture_id="extra"))
        result = self.check(payload=p, keys=k, sign=sign)
        self.assertIn("ONE_DOCUMENT_ONE_NATIVE_PDF_REQUIRED", result["issues"])

    def test_bad_pdf_header_is_rejected(self):
        result = self.check(pdf=b"X" + PDF[1:])
        self.assertIn("PDF_STRUCTURE_MARKERS_MISSING", result["issues"])

    def test_expired_signing_key_rejected(self):
        p, k, sign = fixture()
        k["synthetic-key"]["status"] = "REVOKED"
        result = self.check(payload=p, keys=k, sign=sign)
        self.assertIn("P414_SIGNATURE_OR_PROTOCOL_REJECTED", result["issues"])


if __name__ == "__main__":
    unittest.main()
