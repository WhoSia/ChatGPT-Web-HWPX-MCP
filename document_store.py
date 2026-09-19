from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DOC_AAD = b"chatgpt-web-hwpx-mcp:p3.0:document-revision"
META_AAD = b"chatgpt-web-hwpx-mcp:p3.0:document-metadata"


class DurableDocumentStore:
    """Encrypted, versioned Postgres custody for HWPX document bytes.

    OAuth state and document custody intentionally use different tables, AAD
    domains, and derived encryption keys. A revision row is the durable byte
    snapshot; hwpx_documents is only the current-pointer/retention index.
    """

    def __init__(self, database_url: str, state_secret: str) -> None:
        if not database_url:
            raise RuntimeError("P30_DOCUMENT_DATABASE_URL/P12_AUTH_DATABASE_URL is required")
        if len(state_secret) < 32:
            raise RuntimeError("P12_STATE_SECRET must contain at least 32 characters")
        self.database_url = database_url
        key = hashlib.sha256(
            b"p3.0-document-custody\0" + state_secret.encode("utf-8")
        ).digest()
        self._cipher = AESGCM(key)
        self._ensure_schema()
        self._backfill_audit_hashes()

    @property
    def mode(self) -> str:
        return "postgres-encrypted-versioned"

    def _connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.database_url, autocommit=autocommit)

    def _seal(self, raw: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._cipher.encrypt(nonce, raw, aad)

    def _open(self, payload: bytes, aad: bytes) -> bytes:
        raw = bytes(payload)
        if len(raw) < 13:
            raise ValueError("Durable document payload is truncated")
        return self._cipher.decrypt(raw[:12], raw[12:], aad)

    def _seal_metadata(self, metadata: dict) -> bytes:
        raw = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return self._seal(raw, META_AAD)

    def _open_metadata(self, payload: bytes) -> dict:
        return json.loads(self._open(payload, META_AAD).decode("utf-8"))

    def _ensure_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hwpx_documents (
                    document_id TEXT PRIMARY KEY,
                    owner_subject TEXT NOT NULL,
                    current_revision INTEGER NOT NULL,
                    current_sha256 TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hwpx_document_revisions (
                    document_id TEXT NOT NULL REFERENCES hwpx_documents(document_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    byte_count INTEGER NOT NULL,
                    encrypted_bytes BYTEA NOT NULL,
                    encrypted_metadata BYTEA NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (document_id, revision)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hwpx_document_commits (
                    document_id TEXT NOT NULL REFERENCES hwpx_documents(document_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (document_id, revision),
                    UNIQUE (receipt_id)
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE hwpx_document_commits
                    ADD COLUMN IF NOT EXISTS previous_audit_hash TEXT,
                    ADD COLUMN IF NOT EXISTS audit_hash TEXT
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hwpx_document_revision_pins (
                    document_id TEXT NOT NULL REFERENCES hwpx_documents(document_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    pin_reason TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (document_id, revision),
                    FOREIGN KEY (document_id, revision)
                        REFERENCES hwpx_document_revisions(document_id, revision)
                        ON DELETE RESTRICT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hwpx_document_leases (
                    document_id TEXT PRIMARY KEY REFERENCES hwpx_documents(document_id) ON DELETE CASCADE,
                    lease_token_hash TEXT NOT NULL,
                    holder_id TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS hwpx_documents_expiry_idx ON hwpx_documents (expires_at)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS hwpx_document_revisions_created_idx "
                "ON hwpx_document_revisions (document_id, created_at)"
            )

    @staticmethod
    def _audit_hash(
        *,
        document_id: str,
        revision: int,
        expected_revision: int,
        sha256: str,
        receipt_id: str,
        previous_audit_hash: str,
    ) -> str:
        payload = "\0".join(
            [
                "p3.2-audit",
                document_id,
                str(int(revision)),
                str(int(expected_revision)),
                sha256,
                receipt_id,
                previous_audit_hash,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _backfill_audit_hashes(self) -> None:
        """Backfill the deterministic audit chain for pre-P3.2 commit rows."""
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT document_id
                    FROM hwpx_document_commits
                    ORDER BY document_id
                    """
                )
                document_ids = [row[0] for row in cur.fetchall()]
                for document_id in document_ids:
                    cur.execute(
                        """
                        SELECT revision, expected_revision, sha256, receipt_id,
                               previous_audit_hash, audit_hash
                        FROM hwpx_document_commits
                        WHERE document_id = %s
                        ORDER BY revision ASC
                        FOR UPDATE
                        """,
                        (document_id,),
                    )
                    previous = "GENESIS"
                    for revision, expected_revision, sha256, receipt_id, stored_previous, stored_audit in cur.fetchall():
                        audit = self._audit_hash(
                            document_id=document_id,
                            revision=int(revision),
                            expected_revision=int(expected_revision),
                            sha256=str(sha256),
                            receipt_id=str(receipt_id),
                            previous_audit_hash=previous,
                        )
                        # Migration only: populate audit fields for pre-P3.2 rows.
                        # Once a row has an audit hash, never "heal" it here; a mismatch
                        # must remain observable to verify_audit_chain after restart.
                        if stored_audit is None:
                            cur.execute(
                                """
                                UPDATE hwpx_document_commits
                                SET previous_audit_hash=%s, audit_hash=%s
                                WHERE document_id=%s AND revision=%s
                                  AND audit_hash IS NULL
                                """,
                                (previous, audit, document_id, int(revision)),
                            )
                        previous = audit
            conn.commit()

    @staticmethod
    def _expiry(value: float | int):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    def put_revision(
        self,
        *,
        document_id: str,
        owner_subject: str,
        revision: int,
        metadata: dict,
        data: bytes,
        expires_at_epoch: float | int,
        expected_revision: int | None = None,
        lease_token: str | None = None,
    ) -> dict:
        """CAS-commit one revision or return an idempotent replay receipt.

        New documents commit revision 1 with expected_revision=0. Existing
        documents may advance only current_revision -> current_revision+1.
        Replaying the already-current revision is accepted only when SHA-256
        matches exactly; conflicting bytes at the same revision are rejected.
        """
        revision = int(revision)
        if revision < 1:
            raise ValueError("revision must be >= 1")
        if expected_revision is None:
            expected_revision = max(0, revision - 1)
        expected_revision = int(expected_revision)
        raw = bytes(data)
        sha256 = hashlib.sha256(raw).hexdigest()
        declared = str(metadata.get("sha256") or sha256)
        if declared != sha256:
            raise ValueError("metadata/document SHA-256 mismatch")
        sealed_bytes = self._seal(raw, DOC_AAD)
        sealed_meta = self._seal_metadata(metadata)
        receipt_id = hashlib.sha256(
            f"{document_id}\0{revision}\0{sha256}".encode("utf-8")
        ).hexdigest()

        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_revision, current_sha256, owner_subject
                    FROM hwpx_documents
                    WHERE document_id = %s
                    FOR UPDATE
                    """,
                    (document_id,),
                )
                current = cur.fetchone()

                active_lease = None
                if current is not None and revision != int(current[0]):
                    cur.execute(
                        """
                        SELECT lease_token_hash, expected_revision, expires_at
                        FROM hwpx_document_leases
                        WHERE document_id = %s AND expires_at > NOW()
                        """,
                        (document_id,),
                    )
                    active_lease = cur.fetchone()
                    if active_lease is not None:
                        if not lease_token:
                            conn.rollback()
                            raise RuntimeError("Document lease required for commit")
                        if self._lease_hash(lease_token) != str(active_lease[0]):
                            conn.rollback()
                            raise RuntimeError("Document lease token mismatch")
                        if int(active_lease[1]) != expected_revision:
                            conn.rollback()
                            raise RuntimeError(
                                f"Document lease revision mismatch: lease={active_lease[1]}, expected={expected_revision}"
                            )

                if current is None:
                    if revision != 1 or expected_revision != 0:
                        conn.rollback()
                        raise RuntimeError(
                            f"Revision CAS conflict: durable document absent; "
                            f"expected initial 0->1, got {expected_revision}->{revision}"
                        )
                    cur.execute(
                        """
                        INSERT INTO hwpx_documents
                            (document_id, owner_subject, current_revision, current_sha256, expires_at, created_at, updated_at)
                        VALUES (%s, %s, 1, %s, %s, NOW(), NOW())
                        """,
                        (
                            document_id,
                            owner_subject,
                            sha256,
                            self._expiry(expires_at_epoch),
                        ),
                    )
                    replay = False
                else:
                    current_revision, current_sha, current_owner = int(current[0]), str(current[1]), str(current[2])
                    if current_owner != owner_subject:
                        conn.rollback()
                        raise PermissionError("Durable document owner mismatch")

                    if revision == current_revision:
                        if sha256 != current_sha:
                            conn.rollback()
                            raise RuntimeError(
                                f"Revision CAS conflict: revision {revision} already exists with different SHA-256"
                            )
                        # Same revision + same bytes is an idempotent replay. Metadata
                        # may be refreshed, but bytes/current pointer remain unchanged.
                        replay = True
                    else:
                        if current_revision != expected_revision or revision != expected_revision + 1:
                            conn.rollback()
                            raise RuntimeError(
                                f"Revision CAS conflict: durable current={current_revision}, "
                                f"expected={expected_revision}, attempted={revision}"
                            )
                        replay = False
                        cur.execute(
                            """
                            UPDATE hwpx_documents
                            SET current_revision = %s,
                                current_sha256 = %s,
                                expires_at = %s,
                                updated_at = NOW()
                            WHERE document_id = %s AND current_revision = %s
                            """,
                            (
                                revision,
                                sha256,
                                self._expiry(expires_at_epoch),
                                document_id,
                                expected_revision,
                            ),
                        )
                        if cur.rowcount != 1:
                            conn.rollback()
                            raise RuntimeError("Revision CAS conflict during current-pointer update")

                if replay:
                    cur.execute(
                        """
                        UPDATE hwpx_document_revisions
                        SET encrypted_metadata = %s
                        WHERE document_id = %s AND revision = %s AND sha256 = %s
                        """,
                        (sealed_meta, document_id, revision, sha256),
                    )
                    if cur.rowcount != 1:
                        conn.rollback()
                        raise RuntimeError("Idempotent replay revision row is missing")
                else:
                    cur.execute(
                        """
                        INSERT INTO hwpx_document_revisions
                            (document_id, revision, sha256, byte_count, encrypted_bytes, encrypted_metadata, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (document_id, revision, sha256, len(raw), sealed_bytes, sealed_meta),
                    )
                    cur.execute(
                        """
                        SELECT audit_hash
                        FROM hwpx_document_commits
                        WHERE document_id = %s AND revision = %s
                        """,
                        (document_id, expected_revision),
                    )
                    previous_row = cur.fetchone()
                    previous_audit_hash = (
                        str(previous_row[0])
                        if previous_row is not None and previous_row[0]
                        else "GENESIS"
                    )
                    audit_hash = self._audit_hash(
                        document_id=document_id,
                        revision=revision,
                        expected_revision=expected_revision,
                        sha256=sha256,
                        receipt_id=receipt_id,
                        previous_audit_hash=previous_audit_hash,
                    )
                    cur.execute(
                        """
                        INSERT INTO hwpx_document_commits
                            (document_id, revision, expected_revision, sha256, receipt_id,
                             previous_audit_hash, audit_hash, committed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            document_id,
                            revision,
                            expected_revision,
                            sha256,
                            receipt_id,
                            previous_audit_hash,
                            audit_hash,
                        ),
                    )

                cur.execute(
                    """
                    UPDATE hwpx_documents
                    SET expires_at = %s, updated_at = NOW()
                    WHERE document_id = %s
                    """,
                    (self._expiry(expires_at_epoch), document_id),
                )
                if lease_token:
                    cur.execute(
                        """
                        DELETE FROM hwpx_document_leases
                        WHERE document_id = %s AND lease_token_hash = %s
                        """,
                        (document_id, self._lease_hash(lease_token)),
                    )
            conn.commit()

        return {
            "document_id": document_id,
            "revision": revision,
            "expected_revision": expected_revision,
            "sha256": sha256,
            "bytes": len(raw),
            "storage": self.mode,
            "receipt_id": receipt_id,
            "commit_status": "IDEMPOTENT_REPLAY" if replay else "COMMITTED",
        }

    def update_retention(
        self,
        document_id: str,
        *,
        expected_revision: int,
        expires_at_epoch: float | int,
    ) -> dict:
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_revision
                    FROM hwpx_documents
                    WHERE document_id = %s
                    FOR UPDATE
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise FileNotFoundError("Unknown document_id")
                current_revision = int(row[0])
                if current_revision != int(expected_revision):
                    conn.rollback()
                    raise RuntimeError(
                        f"Revision CAS conflict: durable current={current_revision}, expected={expected_revision}"
                    )
                cur.execute(
                    """
                    UPDATE hwpx_documents
                    SET expires_at = %s, updated_at = NOW()
                    WHERE document_id = %s
                    """,
                    (self._expiry(expires_at_epoch), document_id),
                )
            conn.commit()
        return {
            "document_id": document_id,
            "revision": current_revision,
            "expires_at_epoch": float(expires_at_epoch),
        }

    def get_commit_receipt(self, document_id: str, revision: int) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT expected_revision, sha256, receipt_id, committed_at
                FROM hwpx_document_commits
                WHERE document_id = %s AND revision = %s
                """,
                (document_id, int(revision)),
            )
            row = cur.fetchone()
        if row is None:
            return None
        expected_revision, sha256, receipt_id, committed_at = row
        return {
            "document_id": document_id,
            "revision": int(revision),
            "expected_revision": int(expected_revision),
            "sha256": sha256,
            "receipt_id": receipt_id,
            "committed_at": committed_at.astimezone(timezone.utc).isoformat(),
        }

    @staticmethod
    def _lease_hash(token: str) -> str:
        return hashlib.sha256(("lease\0" + token).encode("utf-8")).hexdigest()

    def acquire_lease(
        self,
        document_id: str,
        *,
        holder_id: str,
        expected_revision: int,
        lease_token: str,
        ttl_seconds: int = 30,
    ) -> dict:
        ttl_seconds = max(5, min(int(ttl_seconds), 300))
        token_hash = self._lease_hash(lease_token)
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_revision
                    FROM hwpx_documents
                    WHERE document_id = %s
                    FOR UPDATE
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise FileNotFoundError("Unknown document_id")
                current_revision = int(row[0])
                if current_revision != int(expected_revision):
                    conn.rollback()
                    raise RuntimeError(
                        f"Revision CAS conflict: durable current={current_revision}, expected={expected_revision}"
                    )
                cur.execute(
                    """
                    DELETE FROM hwpx_document_leases
                    WHERE document_id = %s AND expires_at <= NOW()
                    """,
                    (document_id,),
                )
                cur.execute(
                    """
                    SELECT holder_id, expected_revision, expires_at
                    FROM hwpx_document_leases
                    WHERE document_id = %s
                    """,
                    (document_id,),
                )
                existing = cur.fetchone()
                if existing is not None:
                    conn.rollback()
                    raise RuntimeError(
                        f"Document lease conflict: held by {existing[0]} for revision {existing[1]}"
                    )
                cur.execute(
                    """
                    INSERT INTO hwpx_document_leases
                        (document_id, lease_token_hash, holder_id, expected_revision, expires_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'), NOW())
                    """,
                    (document_id, token_hash, holder_id[:200], int(expected_revision), ttl_seconds),
                )
                cur.execute(
                    "SELECT expires_at FROM hwpx_document_leases WHERE document_id = %s",
                    (document_id,),
                )
                expires_at = cur.fetchone()[0]
            conn.commit()
        return {
            "document_id": document_id,
            "holder_id": holder_id[:200],
            "expected_revision": int(expected_revision),
            "ttl_seconds": ttl_seconds,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        }

    def validate_lease(
        self,
        document_id: str,
        *,
        lease_token: str,
        expected_revision: int,
    ) -> bool:
        token_hash = self._lease_hash(lease_token)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM hwpx_document_leases
                WHERE document_id = %s
                  AND lease_token_hash = %s
                  AND expected_revision = %s
                  AND expires_at > NOW()
                """,
                (document_id, token_hash, int(expected_revision)),
            )
            return cur.fetchone() is not None

    def release_lease(self, document_id: str, *, lease_token: str) -> bool:
        token_hash = self._lease_hash(lease_token)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM hwpx_document_leases
                WHERE document_id = %s AND lease_token_hash = %s
                """,
                (document_id, token_hash),
            )
            return cur.rowcount > 0

    def cleanup_expired_leases(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM hwpx_document_leases WHERE expires_at <= NOW()")
            return cur.rowcount

    def _load_revision_row(
        self,
        document_id: str,
        revision: int | None = None,
        *,
        allow_expired: bool = False,
    ):
        expiry_clause = "" if allow_expired else " AND d.expires_at > NOW()"
        with self._connect() as conn, conn.cursor() as cur:
            if revision is None:
                cur.execute(
                    f"""
                    SELECT r.revision, r.sha256, r.byte_count, r.encrypted_bytes, r.encrypted_metadata,
                           d.owner_subject, EXTRACT(EPOCH FROM d.expires_at)
                    FROM hwpx_documents d
                    JOIN hwpx_document_revisions r
                      ON r.document_id = d.document_id AND r.revision = d.current_revision
                    WHERE d.document_id = %s{expiry_clause}
                    """,
                    (document_id,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT r.revision, r.sha256, r.byte_count, r.encrypted_bytes, r.encrypted_metadata,
                           d.owner_subject, EXTRACT(EPOCH FROM d.expires_at)
                    FROM hwpx_documents d
                    JOIN hwpx_document_revisions r ON r.document_id = d.document_id
                    WHERE d.document_id = %s AND r.revision = %s{expiry_clause}
                    """,
                    (document_id, int(revision)),
                )
            return cur.fetchone()

    def load_current(self, document_id: str, *, allow_expired: bool = False) -> dict | None:
        row = self._load_revision_row(document_id, allow_expired=allow_expired)
        if row is None:
            return None
        revision, sha256, byte_count, encrypted_bytes, encrypted_metadata, owner_subject, expires_epoch = row
        data = self._open(encrypted_bytes, DOC_AAD)
        metadata = self._open_metadata(encrypted_metadata)
        if hashlib.sha256(data).hexdigest() != sha256 or len(data) != int(byte_count):
            raise ValueError("Durable document revision integrity mismatch")
        return {
            "document_id": document_id,
            "revision": int(revision),
            "sha256": sha256,
            "bytes": data,
            "metadata": metadata,
            "owner_subject": owner_subject,
            "expires_at_epoch": float(expires_epoch),
        }

    def load_revision(self, document_id: str, revision: int) -> dict | None:
        row = self._load_revision_row(document_id, int(revision))
        if row is None:
            return None
        rev, sha256, byte_count, encrypted_bytes, encrypted_metadata, owner_subject, expires_epoch = row
        data = self._open(encrypted_bytes, DOC_AAD)
        metadata = self._open_metadata(encrypted_metadata)
        if hashlib.sha256(data).hexdigest() != sha256 or len(data) != int(byte_count):
            raise ValueError("Durable document revision integrity mismatch")
        return {
            "document_id": document_id,
            "revision": int(rev),
            "sha256": sha256,
            "bytes": data,
            "metadata": metadata,
            "owner_subject": owner_subject,
            "expires_at_epoch": float(expires_epoch),
        }

    def list_revisions(self, document_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.revision, r.sha256, r.byte_count, r.created_at,
                       (r.revision = d.current_revision) AS is_current
                FROM hwpx_document_revisions r
                JOIN hwpx_documents d ON d.document_id = r.document_id
                WHERE r.document_id = %s AND d.expires_at > NOW()
                ORDER BY r.revision ASC
                """,
                (document_id,),
            )
            rows = cur.fetchall()
        return [
            {
                "revision": int(revision),
                "sha256": sha256,
                "bytes": int(byte_count),
                "created_at": created_at.astimezone(timezone.utc).isoformat(),
                "is_current": bool(is_current),
            }
            for revision, sha256, byte_count, created_at, is_current in rows
        ]

    def pin_revision(self, document_id: str, revision: int, *, reason: str = "restore-anchor") -> dict:
        revision = int(revision)
        reason = (reason or "restore-anchor")[:240]
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.current_revision
                    FROM hwpx_documents d
                    JOIN hwpx_document_revisions r
                      ON r.document_id=d.document_id AND r.revision=%s
                    WHERE d.document_id=%s AND d.expires_at > NOW()
                    FOR UPDATE
                    """,
                    (revision, document_id),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise FileNotFoundError("Durable revision not found")
                cur.execute(
                    """
                    INSERT INTO hwpx_document_revision_pins
                        (document_id, revision, pin_reason, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (document_id, revision)
                    DO UPDATE SET pin_reason=EXCLUDED.pin_reason
                    """,
                    (document_id, revision, reason),
                )
            conn.commit()
        return {
            "document_id": document_id,
            "revision": revision,
            "pin_reason": reason,
            "pinned": True,
        }

    def unpin_revision(self, document_id: str, revision: int) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM hwpx_document_revision_pins
                WHERE document_id=%s AND revision=%s
                """,
                (document_id, int(revision)),
            )
            return cur.rowcount > 0

    def list_revision_pins(self, document_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT revision, pin_reason, created_at
                FROM hwpx_document_revision_pins
                WHERE document_id=%s
                ORDER BY revision ASC
                """,
                (document_id,),
            )
            rows = cur.fetchall()
        return [
            {
                "revision": int(revision),
                "pin_reason": reason,
                "created_at": created_at.astimezone(timezone.utc).isoformat(),
            }
            for revision, reason, created_at in rows
        ]

    def compact_revisions(
        self,
        document_id: str,
        *,
        expected_revision: int,
        keep_last: int = 3,
        dry_run: bool = True,
    ) -> dict:
        """Prune unpinned historical byte snapshots while retaining the commit audit chain."""
        keep_last = max(1, min(int(keep_last), 100))
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_revision
                    FROM hwpx_documents
                    WHERE document_id=%s AND expires_at > NOW()
                    FOR UPDATE
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise FileNotFoundError("Unknown document_id")
                current_revision = int(row[0])
                if current_revision != int(expected_revision):
                    conn.rollback()
                    raise RuntimeError(
                        f"Revision CAS conflict: durable current={current_revision}, expected={expected_revision}"
                    )
                cur.execute(
                    """
                    SELECT holder_id, expected_revision
                    FROM hwpx_document_leases
                    WHERE document_id=%s AND expires_at > NOW()
                    """,
                    (document_id,),
                )
                lease = cur.fetchone()
                if lease is not None:
                    conn.rollback()
                    raise RuntimeError(
                        f"Active document lease blocks compaction: holder={lease[0]}, revision={lease[1]}"
                    )
                cur.execute(
                    """
                    SELECT revision FROM hwpx_document_revision_pins
                    WHERE document_id=%s
                    """,
                    (document_id,),
                )
                pinned = {int(r[0]) for r in cur.fetchall()}
                floor = max(1, current_revision - keep_last + 1)
                protected = pinned | set(range(floor, current_revision + 1)) | {current_revision}
                cur.execute(
                    """
                    SELECT revision
                    FROM hwpx_document_revisions
                    WHERE document_id=%s
                    ORDER BY revision ASC
                    """,
                    (document_id,),
                )
                existing = [int(r[0]) for r in cur.fetchall()]
                candidates = [r for r in existing if r not in protected]
                if not dry_run and candidates:
                    cur.execute(
                        """
                        DELETE FROM hwpx_document_revisions
                        WHERE document_id=%s AND revision = ANY(%s)
                        """,
                        (document_id, candidates),
                    )
                    if cur.rowcount != len(candidates):
                        conn.rollback()
                        raise RuntimeError("Compaction row-count mismatch")
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
        return {
            "document_id": document_id,
            "revision": current_revision,
            "keep_last": keep_last,
            "pinned_revisions": sorted(pinned),
            "protected_revisions": sorted(protected),
            "prunable_revisions": candidates,
            "deleted_revisions": [] if dry_run else candidates,
            "dry_run": bool(dry_run),
            "commit_ledger_preserved": True,
        }

    def verify_audit_chain(self, document_id: str) -> dict:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT current_revision, current_sha256
                FROM hwpx_documents
                WHERE document_id=%s
                """,
                (document_id,),
            )
            document = cur.fetchone()
            if document is None:
                raise FileNotFoundError("Unknown document_id")
            current_revision, current_sha = int(document[0]), str(document[1])
            cur.execute(
                """
                SELECT revision, expected_revision, sha256, receipt_id,
                       previous_audit_hash, audit_hash
                FROM hwpx_document_commits
                WHERE document_id=%s
                ORDER BY revision ASC
                """,
                (document_id,),
            )
            commits = cur.fetchall()
            cur.execute(
                """
                SELECT revision
                FROM hwpx_document_revisions
                WHERE document_id=%s
                ORDER BY revision ASC
                """,
                (document_id,),
            )
            retained = [int(r[0]) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT revision
                FROM hwpx_document_revision_pins
                WHERE document_id=%s
                ORDER BY revision ASC
                """,
                (document_id,),
            )
            pinned = [int(r[0]) for r in cur.fetchall()]

        previous = "GENESIS"
        failures: list[dict[str, Any]] = []
        last_revision = 0
        last_sha = None
        for revision, expected_revision, sha256, receipt_id, stored_previous, stored_audit in commits:
            revision = int(revision)
            expected_revision = int(expected_revision)
            calculated = self._audit_hash(
                document_id=document_id,
                revision=revision,
                expected_revision=expected_revision,
                sha256=str(sha256),
                receipt_id=str(receipt_id),
                previous_audit_hash=previous,
            )
            if expected_revision != revision - 1:
                failures.append({"revision": revision, "reason": "non-monotonic expected_revision"})
            if stored_previous != previous:
                failures.append({"revision": revision, "reason": "previous audit hash mismatch"})
            if stored_audit != calculated:
                failures.append({"revision": revision, "reason": "audit hash mismatch"})
            previous = calculated
            last_revision = revision
            last_sha = str(sha256)

        if last_revision != current_revision or last_sha != current_sha:
            failures.append({"revision": current_revision, "reason": "current pointer/commit mismatch"})
        if current_revision not in retained:
            failures.append({"revision": current_revision, "reason": "current revision bytes missing"})
        missing_pins = [r for r in pinned if r not in retained]
        for revision in missing_pins:
            failures.append({"revision": revision, "reason": "pinned restore anchor missing"})

        return {
            "document_id": document_id,
            "current_revision": current_revision,
            "commit_count": len(commits),
            "retained_revisions": retained,
            "compacted_revisions": [
                r for r in range(1, current_revision + 1) if r not in retained
            ],
            "pinned_revisions": pinned,
            "audit_head": previous if commits else "GENESIS",
            "audit_chain_valid": not failures,
            "restore_reachability_valid": not missing_pins and current_revision in retained,
            "failures": failures,
        }

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM hwpx_documents WHERE document_id = %s", (document_id,))
            return cur.rowcount > 0

    def cleanup_expired(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM hwpx_documents d
                WHERE d.expires_at <= NOW()
                  AND NOT EXISTS (
                      SELECT 1 FROM hwpx_document_leases l
                      WHERE l.document_id=d.document_id AND l.expires_at > NOW()
                  )
                """
            )
            return cur.rowcount

    def counts(self) -> dict[str, int]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE expires_at > NOW()),
                    COALESCE(SUM(current_revision) FILTER (WHERE expires_at > NOW()), 0)
                FROM hwpx_documents
                """
            )
            documents, revision_floor = cur.fetchone()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM hwpx_document_revisions r
                JOIN hwpx_documents d ON d.document_id = r.document_id
                WHERE d.expires_at > NOW()
                """
            )
            revisions = cur.fetchone()[0]
        return {
            "documents": int(documents),
            "revisions": int(revisions),
            "revision_floor_sum": int(revision_floor),
        }
