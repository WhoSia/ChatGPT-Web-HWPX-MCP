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
                "CREATE INDEX IF NOT EXISTS hwpx_documents_expiry_idx ON hwpx_documents (expires_at)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS hwpx_document_revisions_created_idx "
                "ON hwpx_document_revisions (document_id, created_at)"
            )

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
    ) -> dict:
        revision = int(revision)
        if revision < 1:
            raise ValueError("revision must be >= 1")
        raw = bytes(data)
        sha256 = hashlib.sha256(raw).hexdigest()
        declared = str(metadata.get("sha256") or sha256)
        if declared != sha256:
            raise ValueError("metadata/document SHA-256 mismatch")
        sealed_bytes = self._seal(raw, DOC_AAD)
        sealed_meta = self._seal_metadata(metadata)

        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO hwpx_documents
                        (document_id, owner_subject, current_revision, current_sha256, expires_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (document_id) DO UPDATE SET
                        owner_subject = EXCLUDED.owner_subject,
                        current_revision = GREATEST(hwpx_documents.current_revision, EXCLUDED.current_revision),
                        current_sha256 = CASE
                            WHEN EXCLUDED.current_revision >= hwpx_documents.current_revision
                            THEN EXCLUDED.current_sha256 ELSE hwpx_documents.current_sha256 END,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    """,
                    (
                        document_id,
                        owner_subject,
                        revision,
                        sha256,
                        self._expiry(expires_at_epoch),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO hwpx_document_revisions
                        (document_id, revision, sha256, byte_count, encrypted_bytes, encrypted_metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (document_id, revision) DO UPDATE SET
                        sha256 = EXCLUDED.sha256,
                        byte_count = EXCLUDED.byte_count,
                        encrypted_bytes = EXCLUDED.encrypted_bytes,
                        encrypted_metadata = EXCLUDED.encrypted_metadata
                    """,
                    (document_id, revision, sha256, len(raw), sealed_bytes, sealed_meta),
                )
            conn.commit()
        return {
            "document_id": document_id,
            "revision": revision,
            "sha256": sha256,
            "bytes": len(raw),
            "storage": self.mode,
        }

    def _load_revision_row(self, document_id: str, revision: int | None = None):
        with self._connect() as conn, conn.cursor() as cur:
            if revision is None:
                cur.execute(
                    """
                    SELECT r.revision, r.sha256, r.byte_count, r.encrypted_bytes, r.encrypted_metadata,
                           d.owner_subject, EXTRACT(EPOCH FROM d.expires_at)
                    FROM hwpx_documents d
                    JOIN hwpx_document_revisions r
                      ON r.document_id = d.document_id AND r.revision = d.current_revision
                    WHERE d.document_id = %s AND d.expires_at > NOW()
                    """,
                    (document_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT r.revision, r.sha256, r.byte_count, r.encrypted_bytes, r.encrypted_metadata,
                           d.owner_subject, EXTRACT(EPOCH FROM d.expires_at)
                    FROM hwpx_documents d
                    JOIN hwpx_document_revisions r ON r.document_id = d.document_id
                    WHERE d.document_id = %s AND r.revision = %s AND d.expires_at > NOW()
                    """,
                    (document_id, int(revision)),
                )
            return cur.fetchone()

    def load_current(self, document_id: str) -> dict | None:
        row = self._load_revision_row(document_id)
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

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM hwpx_documents WHERE document_id = %s", (document_id,))
            return cur.rowcount > 0

    def cleanup_expired(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM hwpx_documents WHERE expires_at <= NOW()")
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
