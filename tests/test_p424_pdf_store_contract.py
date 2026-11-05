"""Fail-closed and cryptographic properties of P4.24 PDF custody.

Unit-level tests only: no Postgres integration or remote PDF delivery claimed.
"""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from hwpx_mcp.storage.p424_pdf_store import P424PdfStore


PDF = b"%PDF-1.7\n" + b"synthetic-plaintext" * 8 + b"\n%%EOF\n"
SHA = hashlib.sha256(PDF).hexdigest()
SOURCE_SHA = "a" * 64
EVIDENCE = "b" * 64


def material():
    doc = {"document_id": "doc-local-synthetic", "revision": 2,
           "owner_subject": "subject-test-1", "sha256": SOURCE_SHA}
    admission = {
        "status": "ADMISSION_CHECK_PASSED", "production_delivery_authorized": False,
        "p414_signature_accepted": True,
        "signed_evidence_sha256": EVIDENCE,
        "document_id": doc["document_id"], "revision": 2,
        "pdf_sha256": SHA, "pdf_bytes": len(PDF),
        "durable_replay_check_performed": False,
        "encrypted_custody_performed": False,
        "owner_scoped_delivery_performed": False,
    }
    return doc, admission


class PdfCustodyContractTests(unittest.TestCase):
    def test_checks_fail_closed_on_unapproved_and_wrong_owner(self):
        doc, adm = material()
        check = P424PdfStore._check_receipt
        with self.assertRaisesRegex(PermissionError, "ADMISSION_NOT_PASSED"):
            check(admission={**adm, "status": "REJECTED"}, document=doc,
                  evidence_id=EVIDENCE, owner_subject="subject-test-1", pdf=PDF)
        with self.assertRaisesRegex(PermissionError, "OWNER_MISMATCH"):
            check(admission=adm, document=doc, evidence_id=EVIDENCE,
                  owner_subject="another-subject", pdf=PDF)

    def test_bad_pdf_bytes_and_wrong_evidence_fail_closed(self):
        doc, adm = material()
        check = P424PdfStore._check_receipt
        with self.assertRaisesRegex(PermissionError, "PDF_DIGEST_OR_LENGTH_MISMATCH"):
            check(admission=adm, document=doc, evidence_id=EVIDENCE,
                  owner_subject="subject-test-1", pdf=PDF + b"mutation")
        with self.assertRaisesRegex(PermissionError, "EVIDENCE_ID_MISMATCH"):
            check(admission=adm, document=doc, evidence_id="c" * 64,
                  owner_subject="subject-test-1", pdf=PDF)

    def test_valid_synthetic_pdf_is_only_eligible_for_custody(self):
        doc, adm = material()
        got = P424PdfStore._check_receipt(
            admission=adm, document=doc, evidence_id=EVIDENCE,
            owner_subject="subject-test-1", pdf=PDF)
        self.assertEqual(got, SHA)

    def test_aad_binds_document_owner_revision_and_pdf_digest(self):
        base = (EVIDENCE, "doc-1", 3, "owner-1", SOURCE_SHA, SHA)
        a = P424PdfStore._aad(*base)
        self.assertNotEqual(a, P424PdfStore._aad(EVIDENCE, "doc-1", 4, "owner-1", SOURCE_SHA, SHA))
        self.assertNotEqual(a, P424PdfStore._aad(EVIDENCE, "doc-1", 3, "owner-2", SOURCE_SHA, SHA))
        self.assertNotEqual(a, P424PdfStore._aad(EVIDENCE, "doc-2", 3, "owner-1", SOURCE_SHA, SHA))
        self.assertNotEqual(a, P424PdfStore._aad(EVIDENCE, "doc-1", 3, "owner-1", SOURCE_SHA, "d" * 64))

    def test_aes_gcm_fails_if_owner_associated_data_changes(self):
        key = hashlib.sha256(b"p424-pdf-custody-key\0" + b"synthetic" * 8).digest()
        aead = AESGCM(key)
        nonce = b"\x11" * 12
        aad = P424PdfStore._aad(EVIDENCE, "doc-1", 1, "owner-a", SOURCE_SHA, SHA)
        encrypted = aead.encrypt(nonce, PDF, aad)
        self.assertEqual(aead.decrypt(nonce, encrypted, aad), PDF)
        with self.assertRaises(Exception):
            aead.decrypt(nonce, encrypted, P424PdfStore._aad(
                EVIDENCE, "doc-1", 1, "owner-b", SOURCE_SHA, SHA
            ))


if __name__ == "__main__":
    unittest.main()
