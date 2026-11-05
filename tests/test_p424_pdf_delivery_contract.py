"""P4.24 native PDF OAuth-bound link contract (pure mock storage)."""
from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlsplit
import unittest

from hwpx_mcp.delivery.p424_pdf_delivery import issue_pdf_delivery, redeem_pdf_delivery

PDF = b"%PDF-1.7\n" + b"synthetic-document" * 10 + b"\n%%EOF\n"
SOURCE = b"PK" + b"synthetic-HWPX" * 15
OWNER = "owner-test-001"
DOC = "doc_" + "a" * 24
EVIDENCE = "b" * 64
SECRET = b"synthetic-key-not-production-1234567890"
NOW = 1_800_000_000


class Documents:
    def __init__(self):
        self.owner = OWNER
        self.expiry = NOW + 900

    def load_revision(self, doc, revision):
        if doc != DOC or revision != 2:
            return None
        return {"owner_subject": self.owner, "document_id": DOC,
                "revision": 2, "sha256": hashlib.sha256(SOURCE).hexdigest(),
                "bytes": SOURCE, "expires_at_epoch": self.expiry}


class PDFs:
    def load_owned(self, *, evidence_id, authenticated_owner, document_store):
        if evidence_id != EVIDENCE or authenticated_owner != OWNER:
            raise FileNotFoundError("not-owned")
        return PDF


class PdfDeliveryContractTests(unittest.TestCase):
    def setUp(self):
        self.docs = Documents()
        self.pdfs = PDFs()
        self.args = {"pdf_store": self.pdfs, "document_store": self.docs,
                     "authenticated_owner": OWNER, "document_id": DOC,
                     "revision": 2, "evidence_id": EVIDENCE,
                     "secret": SECRET}

    def issue(self, **kwargs):
        return issue_pdf_delivery(**{**self.args, "public_base_url": "https://example.test",
                                      "now": NOW, **kwargs})

    def redeem(self, issued, **changes):
        q = parse_qs(urlsplit(issued["download_url"]).query)
        req = {"pdf_store": self.pdfs, "document_store": self.docs,
               "authenticated_owner": OWNER, "document_id": DOC,
               "revision": int(q["rev"][0]), "evidence_id": q["ev"][0],
               "pdf_sha256": q["sha"][0], "expires_at": int(q["exp"][0]),
               "signature": q["sig"][0], "secret": SECRET, "now": NOW + 1}
        req.update(changes)
        return redeem_pdf_delivery(**req)

    def test_issued_token_requires_oauth_and_exact_revision_on_redeem(self):
        issued = self.issue(link_ttl_seconds=240)
        self.assertTrue(issued["redemption_requires_oauth_subject"])
        self.assertFalse(issued["owner_scoped_delivery_performed"])
        self.assertEqual(self.redeem(issued), PDF)

    def test_wrong_owner_or_revision_is_rejected(self):
        issued = self.issue()
        with self.assertRaises(PermissionError):
            self.redeem(issued, authenticated_owner="attacker")
        with self.assertRaises(PermissionError):
            self.redeem(issued, revision=3)

    def test_token_expiry_rejected(self):
        issued = self.issue(link_ttl_seconds=60)
        with self.assertRaisesRegex(PermissionError, "EXPIRED"):
            self.redeem(issued, now=NOW + 61)

    def test_tampered_pdf_hash_or_signature_is_rejected(self):
        issued = self.issue()
        with self.assertRaisesRegex(PermissionError, "BAD_SIGNATURE"):
            self.redeem(issued, pdf_sha256="0" * 64)
        with self.assertRaisesRegex(PermissionError, "BAD_SIGNATURE"):
            self.redeem(issued, signature="0" * 64)

    def test_document_retention_caps_expiration(self):
        self.docs.expiry = NOW + 40
        issued = self.issue(link_ttl_seconds=900)
        self.assertEqual(issued["expires_at_epoch"], NOW + 40)
        self.assertEqual(self.redeem(issued), PDF)
        self.docs.expiry = NOW + 20
        with self.assertRaisesRegex(PermissionError, "RETENTION"):
            self.redeem(issued)

    def test_invalid_insecure_base_url_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.issue(public_base_url="http://example.test")

    def test_deleted_source_revokes_link(self):
        issued = self.issue()
        self.docs.owner = "another-owner"
        with self.assertRaisesRegex(PermissionError, "NOT_OWNED"):
            self.redeem(issued)

    def test_malformed_document_or_evidence_id_cannot_be_issued(self):
        with self.assertRaisesRegex(ValueError, "DOCUMENT_ID_INVALID"):
            self.issue(document_id="../cross-tenant")
        with self.assertRaisesRegex(ValueError, "EVIDENCE_ID_INVALID"):
            self.issue(evidence_id="not-a-sha256")

    def test_malformed_document_or_evidence_id_cannot_be_redeemed(self):
        issued = self.issue()
        with self.assertRaisesRegex(PermissionError, "INVALID_IDENTITY"):
            self.redeem(issued, evidence_id="../forged")
        with self.assertRaisesRegex(PermissionError, "INVALID_IDENTITY"):
            self.redeem(issued, document_id="invalid-doc")


if __name__ == "__main__":
    unittest.main()
