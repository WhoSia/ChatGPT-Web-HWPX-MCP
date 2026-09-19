from __future__ import annotations

import hashlib
import os
import secrets
import unittest

import psycopg

from document_store import DurableDocumentStore


class DurableDocumentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = os.environ["P12_AUTH_DATABASE_URL"]
        self.state_secret = os.environ["P12_STATE_SECRET"]
        self.document_id = "doc_" + secrets.token_urlsafe(18)
        self.owner = "hwpx-owner"
        self.store = DurableDocumentStore(self.database_url, self.state_secret)

    def tearDown(self) -> None:
        self.store.delete_document(self.document_id)

    def _metadata(self, revision: int, data: bytes) -> dict:
        return {
            "document_id": self.document_id,
            "owner_subject": self.owner,
            "revision": revision,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "filename": "durable.hwpx",
            "expires_at_epoch": 4_102_444_800,
        }

    def test_encrypted_restart_safe_version_history(self) -> None:
        first = b"PK-first-revision"
        second = b"PK-second-revision"

        self.store.put_revision(
            document_id=self.document_id,
            owner_subject=self.owner,
            revision=1,
            metadata=self._metadata(1, first),
            data=first,
            expires_at_epoch=4_102_444_800,
        )
        self.store.put_revision(
            document_id=self.document_id,
            owner_subject=self.owner,
            revision=2,
            metadata=self._metadata(2, second),
            data=second,
            expires_at_epoch=4_102_444_800,
        )

        # A fresh store object models a new Render process.
        restarted = DurableDocumentStore(self.database_url, self.state_secret)
        current = restarted.load_current(self.document_id)
        self.assertIsNotNone(current)
        self.assertEqual(current["revision"], 2)
        self.assertEqual(current["bytes"], second)

        historical = restarted.load_revision(self.document_id, 1)
        self.assertIsNotNone(historical)
        self.assertEqual(historical["bytes"], first)

        versions = restarted.list_revisions(self.document_id)
        self.assertEqual([v["revision"] for v in versions], [1, 2])
        self.assertFalse(versions[0]["is_current"])
        self.assertTrue(versions[1]["is_current"])

        # Neither document body nor filename metadata may be visible plaintext
        # in the encrypted revision columns.
        with psycopg.connect(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT encrypted_bytes, encrypted_metadata
                FROM hwpx_document_revisions
                WHERE document_id=%s AND revision=2
                """,
                (self.document_id,),
            )
            encrypted_bytes, encrypted_metadata = cur.fetchone()
        self.assertNotIn(second, bytes(encrypted_bytes))
        self.assertNotIn(b"durable.hwpx", bytes(encrypted_metadata))


if __name__ == "__main__":
    unittest.main()
