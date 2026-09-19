from __future__ import annotations

import hashlib
import os
import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

from document_store import DurableDocumentStore
import server


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

    def test_revision_cas_race_idempotent_replay_and_lease_enforcement(self) -> None:
        first = b"PK-base"
        self.store.put_revision(
            document_id=self.document_id,
            owner_subject=self.owner,
            revision=1,
            expected_revision=0,
            metadata=self._metadata(1, first),
            data=first,
            expires_at_epoch=4_102_444_800,
        )

        left = DurableDocumentStore(self.database_url, self.state_secret)
        right = DurableDocumentStore(self.database_url, self.state_secret)
        barrier = threading.Barrier(2)
        candidates = [b"PK-worker-left", b"PK-worker-right"]

        def contender(store, payload):
            barrier.wait(timeout=10)
            try:
                return (
                    "ok",
                    store.put_revision(
                        document_id=self.document_id,
                        owner_subject=self.owner,
                        revision=2,
                        expected_revision=1,
                        metadata=self._metadata(2, payload),
                        data=payload,
                        expires_at_epoch=4_102_444_800,
                    ),
                    payload,
                )
            except RuntimeError as exc:
                return ("conflict", str(exc), payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda args: contender(*args), [(left, candidates[0]), (right, candidates[1])]))

        winners = [item for item in results if item[0] == "ok"]
        losers = [item for item in results if item[0] == "conflict"]
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(len(losers), 1, results)
        self.assertIn("Revision CAS conflict", losers[0][1])

        winner_receipt = winners[0][1]
        winner_payload = winners[0][2]
        current = self.store.load_current(self.document_id)
        self.assertEqual(current["revision"], 2)
        self.assertEqual(current["bytes"], winner_payload)

        replay = self.store.put_revision(
            document_id=self.document_id,
            owner_subject=self.owner,
            revision=2,
            expected_revision=1,
            metadata=self._metadata(2, winner_payload),
            data=winner_payload,
            expires_at_epoch=4_102_444_800,
        )
        self.assertEqual(replay["commit_status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(replay["receipt_id"], winner_receipt["receipt_id"])

        receipt = self.store.get_commit_receipt(self.document_id, 2)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["receipt_id"], winner_receipt["receipt_id"])

        lease_token = secrets.token_urlsafe(32)
        lease = self.store.acquire_lease(
            self.document_id,
            holder_id="worker-a",
            expected_revision=2,
            lease_token=lease_token,
            ttl_seconds=30,
        )
        self.assertEqual(lease["expected_revision"], 2)
        with self.assertRaisesRegex(RuntimeError, "lease required"):
            self.store.put_revision(
                document_id=self.document_id,
                owner_subject=self.owner,
                revision=3,
                expected_revision=2,
                metadata=self._metadata(3, b"PK-rev3"),
                data=b"PK-rev3",
                expires_at_epoch=4_102_444_800,
            )

        committed = self.store.put_revision(
            document_id=self.document_id,
            owner_subject=self.owner,
            revision=3,
            expected_revision=2,
            metadata=self._metadata(3, b"PK-rev3"),
            data=b"PK-rev3",
            expires_at_epoch=4_102_444_800,
            lease_token=lease_token,
        )
        self.assertEqual(committed["commit_status"], "COMMITTED")
        self.assertFalse(
            self.store.validate_lease(
                self.document_id,
                lease_token=lease_token,
                expected_revision=2,
            )
        )

    def test_core_conflict_rehydrates_durable_winner_after_lost_race(self) -> None:
        document_id = "doc_" + secrets.token_urlsafe(18)
        original_dir = server.OBJECT_DIR
        try:
            with __import__("tempfile").TemporaryDirectory() as tmp:
                server.OBJECT_DIR = __import__("pathlib").Path(tmp)
                server.OBJECT_DIR.mkdir(parents=True, exist_ok=True)
                path, metadata_path = server._paths(document_id)

                base_validation = server.materialize_hwpx(path, "base", "P3.1")
                metadata = {
                    "document_id": document_id,
                    "filename": "race.hwpx",
                    "title": "P3.1",
                    "owner_subject": self.owner,
                    "created_at": server._utc_iso(),
                    "created_at_epoch": 1_700_000_000,
                    "expires_at": server._utc_iso(4_102_444_800),
                    "expires_at_epoch": 4_102_444_800,
                    "sha256": base_validation["sha256"],
                    "bytes": base_validation["bytes"],
                    "storage": server.DOCUMENT_STORE.mode,
                    "format": "hwpx",
                    "source": "generated",
                    "revision": 1,
                }
                server._write_metadata(document_id, metadata)

                winner_path = __import__("pathlib").Path(tmp) / "winner.hwpx"
                winner_validation = server.materialize_hwpx(winner_path, "winner", "P3.1")
                winner_meta = dict(metadata)
                winner_meta.update(
                    revision=2,
                    sha256=winner_validation["sha256"],
                    bytes=winner_validation["bytes"],
                )
                server.DOCUMENT_STORE.put_revision(
                    document_id=document_id,
                    owner_subject=self.owner,
                    revision=2,
                    expected_revision=1,
                    metadata=winner_meta,
                    data=winner_path.read_bytes(),
                    expires_at_epoch=4_102_444_800,
                )

                loser_validation = server.materialize_hwpx(path, "loser", "P3.1")
                loser_meta = dict(metadata)
                loser_meta.update(
                    revision=2,
                    sha256=loser_validation["sha256"],
                    bytes=loser_validation["bytes"],
                )
                with self.assertRaisesRegex(RuntimeError, "Revision CAS conflict"):
                    server._write_metadata(document_id, loser_meta)

                durable = server.DOCUMENT_STORE.load_current(document_id)
                self.assertEqual(durable["revision"], 2)
                self.assertEqual(path.read_bytes(), durable["bytes"])
                local_meta = __import__("json").loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(local_meta["revision"], 2)
                self.assertEqual(local_meta["sha256"], durable["sha256"])
        finally:
            server.DOCUMENT_STORE.delete_document(document_id)
            server.OBJECT_DIR = original_dir

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
