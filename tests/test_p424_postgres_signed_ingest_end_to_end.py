"""P4.24 opt-in REAL Postgres integration across all three custody stores.

Requires a dedicated locally hosted, disposable DB named
p424_disposable_*. NEVER point at production. Synthetic document bytes,
synthetic Ed25519 key, and signed capture receipt are used exclusively.

Runs with unittest discover -s tests -p 'test_p424_*.py' -v.
"""
from __future__ import annotations

import hashlib
import os
import uuid
import unittest
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.conninfo import make_conninfo

from hwpx_mcp.custody.p424_job_store import P424IssuedJobStore
from hwpx_mcp.custody.p424_signed_pdf_ingest import ingest_signed_native_pdf
from hwpx_mcp.evidence.p414_evidence_store import P414EvidenceStore
from hwpx_mcp.storage.p424_pdf_store import P424PdfStore
from hwpx_mcp.testing.p424_disposable_database import disposable_test_database_url

# Shared synthetic fixture is already independently validated by its unit
# suite. No real documents or private production credentials are loaded.
from test_p424_signed_pdf_ingest import (
    DOC, FIXTURE, HEAD, OWNER, PDF, SOURCE, SOURCE_SHA, signed_fixture,
)


class SyntheticDocumentStore:
    def __init__(self, expiry):
        self.expiry = expiry

    def load_revision(self, document_id, revision):
        if document_id != DOC or revision != 2:
            return None
        return {
            "document_id": DOC, "revision": 2, "owner_subject": OWNER,
            "sha256": SOURCE_SHA, "bytes": SOURCE,
            "expires_at_epoch": self.expiry.timestamp(),
        }


@unittest.skipUnless(
    os.environ.get("P424_TEST_DATABASE_DISPOSABLE") == "YES"
    and bool(os.environ.get("P424_TEST_DATABASE_URL")),
    "Requires explicitly designated disposable Postgres database",
)
class P424RealPostgresSignedIngestTests(unittest.TestCase):
    def test_issued_job_signed_receipt_evidence_pdf_and_deletion_cascade(self):
        url = disposable_test_database_url()
        schema = "p424_e2e_" + uuid.uuid4().hex
        scoped = make_conninfo(url, options=f"-csearch_path={schema}")
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            with psycopg.connect(scoped, autocommit=True) as conn:
                conn.execute("""
                    CREATE TABLE hwpx_documents (
                        document_id TEXT PRIMARY KEY, owner_subject TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE hwpx_document_revisions (
                        document_id TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        PRIMARY KEY(document_id, revision),
                        FOREIGN KEY(document_id) REFERENCES hwpx_documents(document_id)
                        ON DELETE CASCADE
                    )
                """)
                conn.execute("INSERT INTO hwpx_documents VALUES(%s,%s)", (DOC, OWNER))
                conn.execute("INSERT INTO hwpx_document_revisions VALUES(%s,2)", (DOC,))

            clock = datetime.now(timezone.utc)
            document_store = SyntheticDocumentStore(clock + timedelta(hours=2))
            job_store = P424IssuedJobStore(scoped)
            evidence_store = P414EvidenceStore(scoped)
            pdf_store = P424PdfStore(scoped, "p424-synthetic-only-secret-0123456789abcdef")
            receipt, key_registry = signed_fixture()
            key = key_registry["test-key"]
            evidence_store.register_key(
                agent_id=key["agent_id"], key_id="test-key",
                public_key_ed25519_b64=key["public_key_ed25519_b64"],
            )
            signed = receipt["signed_payload"]
            job = {
                "job_id": signed["job_id"], "agent_id": receipt["agent_id"],
                "nonce": signed["nonce"], "document_id": DOC, "revision": 2,
                "source_sha256": SOURCE_SHA,
                "source_manifest": signed["source_manifest"],
                "source_manifest_sha256": signed["source_manifest_sha256"],
                "exact_head": HEAD, "fixture_id": FIXTURE,
                "expires_at": clock + timedelta(minutes=20),
            }
            job_store.issue_job(job=job, document_store=document_store,
                                authenticated_owner=OWNER, now=clock)
            params = {
                "receipt": receipt, "pdf_bytes": PDF, "document_id": DOC,
                "revision": 2, "expected_fixture_id": FIXTURE,
                "expected_head": HEAD, "authenticated_owner": OWNER,
                "job_store": job_store, "document_store": document_store,
                "evidence_store": evidence_store, "pdf_store": pdf_store,
            }
            # Mismatched PDF must not even enter signed-evidence custody.
            bad = ingest_signed_native_pdf(**{**params, "pdf_bytes": PDF + b"tampered"})
            self.assertEqual(bad["status"], "REJECTED")
            with psycopg.connect(scoped) as conn:
                n = conn.execute("SELECT COUNT(*) FROM hwpx_p414_receipt_attempt").fetchone()[0]
                self.assertEqual(n, 0)

            class FailingPdfStore:
                def put_verified(self, **_kwargs):
                    raise RuntimeError("SIMULATED_PDF_DB_COMMIT_FAILURE")

            # Durable evidence commits first. A failed PDF write must NOT
            # create an encrypted PDF row; the exact receipt must be
            # recoverable by a later retry.
            with self.assertRaisesRegex(RuntimeError, "SIMULATED_PDF_DB_COMMIT_FAILURE"):
                ingest_signed_native_pdf(**{**params, "pdf_store": FailingPdfStore()})
            with psycopg.connect(scoped) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM hwpx_p414_receipt_attempt WHERE accepted=TRUE"
                ).fetchone()[0], 1)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM hwpx_p424_native_pdf"
                ).fetchone()[0], 0)

            first = ingest_signed_native_pdf(**params)
            self.assertTrue(first["idempotent_receipt_retry"])
            self.assertEqual(first["status"], "ENCRYPTED_PDF_CUSTODY_CONFIRMED")
            second = ingest_signed_native_pdf(**params)
            self.assertTrue(second["idempotent_receipt_retry"])
            self.assertEqual(second["custody_status"], "ENCRYPTED_CUSTODY_ALREADY_EXISTS")
            self.assertEqual(first["evidence_id"], second["evidence_id"])

            got = pdf_store.load_owned(
                evidence_id=first["evidence_id"], authenticated_owner=OWNER,
                document_store=document_store, expected_document_id=DOC,
                expected_revision=2, expected_source_sha256=SOURCE_SHA,
            )
            self.assertEqual(got, PDF)
            with self.assertRaises(FileNotFoundError):
                pdf_store.load_owned(
                    evidence_id=first["evidence_id"],
                    authenticated_owner="another-owner",
                    document_store=document_store,
                    expected_document_id=DOC, expected_revision=2,
                    expected_source_sha256=SOURCE_SHA,
                )
            with psycopg.connect(scoped, autocommit=True) as conn:
                ciphertext = bytes(conn.execute(
                    "SELECT ciphertext FROM hwpx_p424_native_pdf WHERE evidence_id=%s",
                    (first["evidence_id"],),
                ).fetchone()[0])
                self.assertNotEqual(ciphertext, PDF)
                self.assertNotIn(PDF, ciphertext)
                # A signed audit record remains append-only even after owner
                # source deletion; PDF bytes and issued job must cascade.
                conn.execute("DELETE FROM hwpx_documents WHERE document_id=%s", (DOC,))
                for table in ("hwpx_p424_native_pdf", "hwpx_p424_issued_native_job"):
                    self.assertEqual(conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0], 0)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM hwpx_p414_receipt_attempt WHERE accepted=TRUE"
                ).fetchone()[0], 1)
        finally:
            with psycopg.connect(url, autocommit=True) as admin:
                admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


if __name__ == "__main__":
    unittest.main()
