"""Opt-in real PostgreSQL round-trip for encrypted P4.24 PDF custody.

Run ONLY with a dedicated disposable Postgres test database:
P424_TEST_DATABASE_DISPOSABLE=YES P424_TEST_DATABASE_URL=postgresql://... \
  python -m unittest tests.test_p424_pdf_store_postgres_integration -v

A unique temporary schema is created and dropped in finally. The test NEVER
uses the app's production database environment variables.
"""
from __future__ import annotations

import hashlib
import os
import uuid
import unittest

import psycopg
from psycopg.conninfo import make_conninfo

from hwpx_mcp.storage.p424_pdf_store import P424PdfStore


PDF = b"%PDF-1.7\n" + b"only-synthetic-data-" * 10 + b"\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
SOURCE_SHA = "a" * 64
EVIDENCE = "b" * 64
OWNER = "test-p424-owner"
DOC_ID = "doc-p424-integration"


class _AcceptedEvidence:
    def accepted_receipt_by_id(self, evidence_id):
        if evidence_id != EVIDENCE:
            return None
        return {
            "validation_result": {"accepted": True},
            "normalized_evidence": {
                "test_only": False,
                "document_binding": {
                    "document_id": DOC_ID, "revision": 1,
                    "document_sha256": SOURCE_SHA, "owner_subject": OWNER,
                },
                "outputs": [{"pdf_sha256": PDF_SHA, "bytes": len(PDF)}],
            },
        }


class _SourceDocument:
    def __init__(self):
        self.present = True

    def load_revision(self, document_id, revision):
        if self.present and document_id == DOC_ID and revision == 1:
            return {"document_id": DOC_ID, "revision": 1,
                    "owner_subject": OWNER, "sha256": SOURCE_SHA}
        return None


def _admission():
    return {
        "status": "ADMISSION_CHECK_PASSED",
        "production_delivery_authorized": False,
        "p414_signature_accepted": True,
        "signed_evidence_sha256": EVIDENCE,
        "document_id": DOC_ID, "revision": 1,
        "pdf_sha256": PDF_SHA, "pdf_bytes": len(PDF),
        "durable_replay_check_performed": False,
        "encrypted_custody_performed": False,
        "owner_scoped_delivery_performed": False,
    }


@unittest.skipUnless(
    os.environ.get("P424_TEST_DATABASE_DISPOSABLE") == "YES"
    and bool(os.environ.get("P424_TEST_DATABASE_URL")),
    "Requires explicitly designated disposable Postgres test database",
)
class P424PostgresRoundTripTests(unittest.TestCase):
    def test_encrypt_insert_idempotent_retrieve_owner_isolation_and_cascade(self):
        url = os.environ["P424_TEST_DATABASE_URL"]
        schema = "p424_test_" + uuid.uuid4().hex
        # Construct a DB-specific schema search path: no shared app tables.
        schema_url = make_conninfo(url, options=f"-csearch_path={schema}")
        doc = {"document_id": DOC_ID, "revision": 1,
               "owner_subject": OWNER, "sha256": SOURCE_SHA}
        source = _SourceDocument()
        # Schema name generated from uuid, never user input.
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            with psycopg.connect(schema_url, autocommit=True) as connection:
                connection.execute("""
                    CREATE TABLE hwpx_documents (
                        document_id TEXT PRIMARY KEY,
                        owner_subject TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL
                    )
                """)
                connection.execute("""
                    CREATE TABLE hwpx_document_revisions (
                        document_id TEXT NOT NULL REFERENCES hwpx_documents(document_id)
                          ON DELETE CASCADE,
                        revision INTEGER NOT NULL,
                        sha256 CHAR(64) NOT NULL,
                        PRIMARY KEY (document_id, revision)
                    )
                """)
                connection.execute(
                    "INSERT INTO hwpx_documents(document_id,owner_subject,expires_at) "
                    "VALUES (%s,%s,NOW()+INTERVAL '1 day')", (DOC_ID, OWNER),
                )
                connection.execute(
                    "INSERT INTO hwpx_document_revisions(document_id,revision,sha256) "
                    "VALUES (%s,1,%s)", (DOC_ID, SOURCE_SHA),
                )
            store = P424PdfStore(schema_url, "synthetic-only-p424-secret-0123456789abcdef")
            evidence = _AcceptedEvidence()
            kwargs = {
                "admission": _admission(), "document": doc,
                "evidence_id": EVIDENCE, "authenticated_owner": OWNER,
                "pdf_bytes": PDF, "evidence_store": evidence,
            }
            inserted = store.put_verified(**kwargs)
            self.assertEqual(inserted["status"], "ENCRYPTED_CUSTODY_CREATED")
            again = store.put_verified(**kwargs)
            self.assertEqual(again["status"], "ENCRYPTED_CUSTODY_ALREADY_EXISTS")
            self.assertEqual(store.load_owned(
                evidence_id=EVIDENCE, authenticated_owner=OWNER,
                document_store=source, expected_document_id=DOC_ID,
                expected_revision=1, expected_source_sha256=SOURCE_SHA), PDF)
            with self.assertRaises(FileNotFoundError):
                store.load_owned(evidence_id=EVIDENCE,
                                 authenticated_owner="wrong-owner",
                                 document_store=source,
                                 expected_document_id=DOC_ID,
                                 expected_revision=1,
                                 expected_source_sha256=SOURCE_SHA)
            with self.assertRaisesRegex(PermissionError, "BINDING_MISMATCH"):
                store.load_owned(evidence_id=EVIDENCE, authenticated_owner=OWNER,
                                 document_store=source,
                                 expected_document_id="another-document",
                                 expected_revision=1,
                                 expected_source_sha256=SOURCE_SHA)
            with self.assertRaises(PermissionError):
                store.put_verified(**{**kwargs, "authenticated_owner": "wrong-owner"})
            with psycopg.connect(schema_url, autocommit=True) as conn:
                row = conn.execute(
                    "SELECT ciphertext FROM hwpx_p424_native_pdf WHERE evidence_id=%s",
                    (EVIDENCE,),
                ).fetchone()
                self.assertNotIn(PDF, bytes(row[0]))
                self.assertNotEqual(bytes(row[0]), PDF)
                # Owner deletion must cascade the encrypted artifact,
                # not fail because PDF custody retained its FK.
                conn.execute("DELETE FROM hwpx_documents WHERE document_id=%s", (DOC_ID,))
                count = conn.execute("SELECT COUNT(*) FROM hwpx_p424_native_pdf").fetchone()[0]
                self.assertEqual(count, 0)
        finally:
            with psycopg.connect(url, autocommit=True) as admin:
                admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


if __name__ == "__main__":
    unittest.main()
