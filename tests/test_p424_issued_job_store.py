"""P4.24 server-issued native job authorization boundary tests.

These tests don't touch a real DB. The opt-in disposable-DB suite is
separate. They ensure source/owner/expiry validation happens before INSERT.
"""
from __future__ import annotations

import hashlib
from datetime import datetime,timedelta,timezone
import unittest

from hwpx_mcp.custody.p424_job_store import P424IssuedJobStore
from hwpx_mcp.evidence.p414_evidence_service import canonical_sha256

SOURCE=b"PK"+b"synthetic-document"*30
SHA=hashlib.sha256(SOURCE).hexdigest()
OWNER="owner-test"
DOC="doc_"+"a"*24


class Documents:
    def __init__(self):
        self.owner=OWNER
        self.data=SOURCE
    def load_revision(self,doc,rev):
        if doc!=DOC or rev!=2:
            return None
        return {"document_id":DOC,"revision":2,"owner_subject":self.owner,
                "sha256":SHA,"bytes":self.data,"expires_at_epoch":1893456000}


class Cursor:
    def __init__(self):
        self.queries=[]
    def execute(self,sql,args=None):
        self.queries.append((sql,args))
        return self
    def fetchone(self):
        return {"job_id":"job-test-001"}


class Connection:
    def __init__(self,cursor):
        self.cur=cursor
    def __enter__(self): return self
    def __exit__(self,*exc): return False
    def execute(self,sql,args=None):
        return self.cur.execute(sql,args)


def job(now):
    manifest = {"files": [{"fixture_id": "p424-private-fixture",
                           "path": "source.hwpx", "sha256": SHA,
                           "bytes": len(SOURCE), "lowering_family": "SYNTHETIC"}]}
    return {"source_manifest": manifest,
            "agent_id": "test-agent",
            "job_id":"job-test-001",
            "nonce":"random-server-issued-nonce-123456",
            "document_id":DOC,"revision":2,"source_sha256":SHA,
            "source_manifest_sha256":canonical_sha256(manifest),
            "exact_head":"d"*40,"fixture_id":"p424-private-fixture",
            "expires_at":now+timedelta(minutes=15)}


class P424IssuedJobTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,6,tzinfo=timezone.utc)
        self.document=Documents()
        self.cursor=Cursor()
        self.store=P424IssuedJobStore.__new__(P424IssuedJobStore)
        self.store._connect=lambda **kwargs: Connection(self.cursor)

    def test_issue_job_persists_only_verified_source_and_owner(self):
        result=self.store.issue_job(job=job(self.now),document_store=self.document,
                                    authenticated_owner=OWNER,now=self.now)
        self.assertEqual(result["status"],"ISSUED")
        self.assertFalse(result["production_delivery_authorized"])
        self.assertEqual(len(self.cursor.queries),1)
        self.assertIn("INSERT INTO hwpx_p424_issued_native_job",self.cursor.queries[0][0])

    def test_cross_owner_never_writes_a_job(self):
        with self.assertRaisesRegex(PermissionError,"NOT_OWNED"):
            self.store.issue_job(job=job(self.now),document_store=self.document,
                                 authenticated_owner="other-user",now=self.now)
        self.assertEqual(len(self.cursor.queries),0)

    def test_modified_source_never_writes_a_job(self):
        self.document.data+=b"altered"
        with self.assertRaisesRegex(ValueError,"SOURCE_DIGEST_MISMATCH"):
            self.store.issue_job(job=job(self.now),document_store=self.document,
                                 authenticated_owner=OWNER,now=self.now)
        self.assertEqual(len(self.cursor.queries),0)

    def test_replay_nonce_or_invalid_digest_is_rejected_before_insert(self):
        for changes in [
            {"nonce":"short"}, {"agent_id":""}, {"source_sha256":"0"*64},
            {"revision":0},{"exact_head":"z"*40},
        ]:
            with self.assertRaises(ValueError):
                self.store.issue_job(job={**job(self.now),**changes},
                                     document_store=self.document,
                                     authenticated_owner=OWNER,now=self.now)
        self.assertEqual(len(self.cursor.queries),0)

    def test_manifest_mismatch_or_extra_fixture_rejected_before_insert(self):
        baseline = job(self.now)
        manifest = {"files": [*baseline["source_manifest"]["files"],
                              {**baseline["source_manifest"]["files"][0],
                               "fixture_id": "another-fixture", "path": "second.hwpx"}]}
        for changes in [{"source_manifest_sha256": "0"*64},
                        {"source_manifest": manifest,
                         "source_manifest_sha256": canonical_sha256(manifest)}]:
            with self.assertRaisesRegex(ValueError, "MANIFEST_BINDING_MISMATCH"):
                self.store.issue_job(job={**baseline, **changes},
                                     document_store=self.document,
                                     authenticated_owner=OWNER, now=self.now)
        self.assertEqual(len(self.cursor.queries), 0)

    def test_expired_or_long_running_job_cannot_be_issued(self):
        for expiry in (self.now-timedelta(seconds=1),
                       self.now+timedelta(hours=13),
                       datetime(2030,1,1,tzinfo=timezone.utc)):
            with self.assertRaisesRegex(ValueError,"EXPIRY"):
                self.store.issue_job(job={**job(self.now),"expires_at":expiry},
                                     document_store=self.document,
                                     authenticated_owner=OWNER,now=self.now)
        self.assertEqual(len(self.cursor.queries),0)

    def test_missing_job_returns_none_without_database_access(self):
        self.assertIsNone(self.store.load_issued_job("invalid/slash"))
        self.assertEqual(len(self.cursor.queries),0)

    def test_job_revocation_is_scoped_to_owner(self):
        self.store.revoke_job("job-test-001",authenticated_owner=OWNER)
        self.assertIn("owner_subject=%s",self.cursor.queries[0][0])


if __name__=="__main__":
    unittest.main()
