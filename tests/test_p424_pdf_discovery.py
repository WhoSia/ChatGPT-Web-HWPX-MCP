"""Native PDF artifact discovery without exposing evidence IDs to users.

Mocked storage: no Windows bridge, Hancom, or prior p424-validation files.
"""
from __future__ import annotations

import hashlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hwpx_mcp.delivery import p424_pdf_http as http

DOC = "doc_" + "a" * 24
OWNER = "owner-synthetic-test"
EVIDENCE = "b" * 64
SOURCE = b"PK" + b"synthetic-only" * 20
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()


class DocumentStore:
    def __init__(self, owner=OWNER):
        self.owner = owner
    def load_revision(self, document_id, revision):
        if document_id != DOC or revision != 2:
            return None
        return {"document_id": DOC, "revision": revision,
                "owner_subject": self.owner, "sha256": SOURCE_SHA,
                "bytes": SOURCE, "expires_at_epoch": 1900000000}


class PdfStore:
    def __init__(self, entries=None):
        self.entries = entries if entries is not None else [{
            "evidence_id": EVIDENCE,
            "pdf_sha256": "c" * 64, "pdf_bytes": 500,
            "created_at": "2026-11-10T00:00:00+00:00",
        }]
        self.last_query = None

    def list_owned(self, **kwargs):
        self.last_query = kwargs
        return self.entries[:kwargs["limit"]]


class NativePdfDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.docs = DocumentStore()
        self.pdfs = PdfStore()
        self.core = SimpleNamespace(
            _caller_subject=lambda: OWNER,
            _paths=lambda document_id: document_id,
            DOCUMENT_STORE=self.docs,
            PUBLIC_BASE_URL="https://example.test",
            _download_secret=lambda: b"synthetic-secret-long-enough-123456789",
        )

    def test_lists_available_pdfs_for_exact_owner_revision(self):
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "YES"}), patch.object(http, "_store", return_value=self.pdfs):
            result = http.list_authenticated_native_pdfs(
                self.core, document_id=DOC, revision=2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "PDF_READY")
        self.assertEqual(result["pdf_count"], 1)
        self.assertEqual(result["artifacts"][0]["evidence_id"], EVIDENCE)
        self.assertEqual(self.pdfs.last_query["authenticated_owner"], OWNER)
        self.assertEqual(self.pdfs.last_query["source_sha256"], SOURCE_SHA)

    def test_missing_pdf_reports_not_generated(self):
        self.pdfs.entries = []
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "YES"}), patch.object(http, "_store", return_value=self.pdfs):
            result = http.issue_authenticated_pdf_link(
                self.core, document_id=DOC, revision=2)
        self.assertEqual(result["code"], "P424_PDF_NOT_GENERATED")
        self.assertFalse(result["native_pdf_created"])

    def test_latest_pdf_id_selected_without_user_supplied_evidence(self):
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "YES"}), patch.object(http, "_store", return_value=self.pdfs), patch.object(http, "issue_pdf_delivery", return_value={"download_url": "https://example.test/p424/native-pdf/doc_test"} ) as issuer:
            result = http.issue_authenticated_pdf_link(
                self.core, document_id=DOC, revision=2)
        self.assertTrue(result["ok"])
        self.assertEqual(issuer.call_args.kwargs["evidence_id"], EVIDENCE)

    def test_wrong_owner_cannot_list_pdf_evidence(self):
        self.docs.owner = "other-owner"
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "YES"}), patch.object(http, "_store", return_value=self.pdfs):
            with self.assertRaises(FileNotFoundError):
                http.list_authenticated_native_pdfs(
                    self.core, document_id=DOC, revision=2)
        self.assertIsNone(self.pdfs.last_query)

    def test_disabled_feature_makes_no_storage_calls(self):
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "NO"}), patch.object(http, "_store") as store:
            result = http.list_authenticated_native_pdfs(
                self.core, document_id=DOC, revision=2)
        self.assertFalse(result["ok"])
        store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
