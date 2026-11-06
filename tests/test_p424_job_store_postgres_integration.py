"""Opt-in P4.24 issued job Postgres integration, disposable database only.

Requires P424_TEST_DATABASE_DISPOSABLE=YES plus P424_TEST_DATABASE_URL.
Uses an isolated randomly named schema, never application production DB.
"""
from __future__ import annotations

import hashlib
import os
import uuid
import unittest
from datetime import datetime,timedelta,timezone

import psycopg
from psycopg.conninfo import make_conninfo

from hwpx_mcp.custody.p424_job_store import P424IssuedJobStore
from hwpx_mcp.evidence.p414_evidence_service import canonical_sha256


DOC="doc_"+"t"*24
OWNER="synthetic-owner-only"
SOURCE=b"PK"+b"synthetic-source-blob"*30
SOURCE_SHA=hashlib.sha256(SOURCE).hexdigest()


class Documents:
    def load_revision(self, doc, rev):
        if doc!=DOC or rev!=1:
            return None
        return {"document_id": DOC, "revision":1,
                "owner_subject":OWNER, "sha256":SOURCE_SHA,
                "bytes":SOURCE, "expires_at_epoch":1893456000}


@unittest.skipUnless(
    os.environ.get("P424_TEST_DATABASE_DISPOSABLE")=="YES"
    and bool(os.environ.get("P424_TEST_DATABASE_URL")),
    "Requires explicitly designated disposable Postgres database",
)
class IssuedJobPostgresIntegrationTests(unittest.TestCase):
    def test_issue_lookup_revocation_duplicate_and_source_cascade(self):
        url=os.environ["P424_TEST_DATABASE_URL"]
        schema="p424_jobs_"+uuid.uuid4().hex
        scoped=make_conninfo(url,options=f"-csearch_path={schema}")
        with psycopg.connect(url,autocommit=True) as admin:
            admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            with psycopg.connect(scoped,autocommit=True) as conn:
                conn.execute("""
                    CREATE TABLE hwpx_documents (
                      document_id TEXT PRIMARY KEY, owner_subject TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE hwpx_document_revisions (
                      document_id TEXT NOT NULL REFERENCES hwpx_documents(document_id)
                        ON DELETE CASCADE,
                      revision INTEGER NOT NULL,
                      PRIMARY KEY (document_id, revision)
                    )
                """)
                conn.execute("INSERT INTO hwpx_documents VALUES(%s,%s)",(DOC,OWNER))
                conn.execute("INSERT INTO hwpx_document_revisions VALUES(%s,1)",(DOC,))
            store=P424IssuedJobStore(scoped)
            issued=datetime.now(timezone.utc)
            manifest={"files":[{"fixture_id":"p424-test","path":"test.hwpx",
                                "sha256":SOURCE_SHA,"bytes":len(SOURCE),
                                "lowering_family":"SYNTHETIC"}]}
            job={
                "agent_id":"test-agent",
                "job_id":"p424-db-integration-001",
                "nonce":"dedicated-disposable-nonce-12345678",
                "document_id":DOC,"revision":1,"source_sha256":SOURCE_SHA,
                "source_manifest":manifest,
                "source_manifest_sha256":canonical_sha256(manifest),
                "exact_head":"a"*40,"fixture_id":"p424-test",
                "expires_at":issued+timedelta(minutes=10),
            }
            result=store.issue_job(job=job,document_store=Documents(),
                                   authenticated_owner=OWNER,now=issued)
            self.assertEqual(result["status"],"ISSUED")
            loaded=store.load_issued_job(job["job_id"])
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["nonce"],job["nonce"])
            self.assertEqual(loaded["agent_id"],job["agent_id"])
            self.assertEqual(loaded["source_manifest_sha256"],
                             job["source_manifest_sha256"])
            with self.assertRaises(psycopg.errors.UniqueViolation):
                store.issue_job(job=job,document_store=Documents(),
                                authenticated_owner=OWNER,now=issued)
            self.assertFalse(store.revoke_job(job["job_id"],
                                              authenticated_owner="other-user"))
            self.assertTrue(store.revoke_job(job["job_id"],
                                             authenticated_owner=OWNER))
            self.assertIsNone(store.load_issued_job(job["job_id"]))
            with psycopg.connect(scoped,autocommit=True) as conn:
                conn.execute("DELETE FROM hwpx_documents WHERE document_id=%s",(DOC,))
                n=conn.execute("SELECT COUNT(*) FROM hwpx_p424_issued_native_job").fetchone()[0]
                self.assertEqual(n,0)
        finally:
            with psycopg.connect(url,autocommit=True) as admin:
                admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


if __name__=="__main__":
    unittest.main()
