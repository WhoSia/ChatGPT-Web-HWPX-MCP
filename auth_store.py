from __future__ import annotations

import hashlib
import os
import pickle
from datetime import datetime, timezone
from typing import Any

import psycopg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"chatgpt-web-hwpx-mcp:p1.2:oauth-state"


class DurableOAuthStore:
    """Encrypted Postgres-backed state for OAuth clients, codes, and tokens.

    Lookup keys are SHA-256 fingerprints. Serialized MCP SDK objects are encrypted
    and authenticated with AES-GCM before leaving the process, so the database
    never stores usable bearer/refresh/code values in plaintext.
    """

    def __init__(self, database_url: str, state_secret: str) -> None:
        if not database_url:
            raise RuntimeError("P12_AUTH_DATABASE_URL is required")
        if len(state_secret) < 32:
            raise RuntimeError("P12_STATE_SECRET must contain at least 32 characters")
        self.database_url = database_url
        self._cipher = AESGCM(hashlib.sha256(state_secret.encode("utf-8")).digest())
        self._ensure_schema()

    @property
    def mode(self) -> str:
        return "postgres-encrypted"

    @staticmethod
    def _fingerprint(kind: str, key: str) -> str:
        return hashlib.sha256(f"{kind}\0{key}".encode("utf-8")).hexdigest()

    def _seal(self, obj: Any) -> bytes:
        nonce = os.urandom(12)
        raw = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        return nonce + self._cipher.encrypt(nonce, raw, AAD)

    def _open(self, payload: bytes) -> Any:
        raw = bytes(payload)
        nonce, ciphertext = raw[:12], raw[12:]
        return pickle.loads(self._cipher.decrypt(nonce, ciphertext, AAD))

    def _connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.database_url, autocommit=autocommit)

    def _ensure_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hwpx_oauth_state (
                    kind TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    client_id TEXT,
                    subject TEXT,
                    expires_at TIMESTAMPTZ,
                    revoked_at TIMESTAMPTZ,
                    payload BYTEA NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (kind, key_hash)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS hwpx_oauth_state_family_idx "
                "ON hwpx_oauth_state (client_id, subject, kind)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS hwpx_oauth_state_expiry_idx "
                "ON hwpx_oauth_state (expires_at)"
            )

    @staticmethod
    def _expiry(value: float | int | None):
        if value is None:
            return None
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    def _upsert_cursor(
        self,
        cur,
        *,
        kind: str,
        key: str,
        obj: Any,
        client_id: str | None = None,
        subject: str | None = None,
        expires_at: float | int | None = None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO hwpx_oauth_state
                (kind, key_hash, client_id, subject, expires_at, revoked_at, payload, updated_at)
            VALUES (%s, %s, %s, %s, %s, NULL, %s, NOW())
            ON CONFLICT (kind, key_hash) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                subject = EXCLUDED.subject,
                expires_at = EXCLUDED.expires_at,
                revoked_at = NULL,
                payload = EXCLUDED.payload,
                updated_at = NOW()
            """,
            (
                kind,
                self._fingerprint(kind, key),
                client_id,
                subject,
                self._expiry(expires_at),
                self._seal(obj),
            ),
        )

    def put(
        self,
        kind: str,
        key: str,
        obj: Any,
        *,
        client_id: str | None = None,
        subject: str | None = None,
        expires_at: float | int | None = None,
    ) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            self._upsert_cursor(
                cur,
                kind=kind,
                key=key,
                obj=obj,
                client_id=client_id,
                subject=subject,
                expires_at=expires_at,
            )

    def get(self, kind: str, key: str) -> Any | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM hwpx_oauth_state
                WHERE kind = %s AND key_hash = %s
                  AND revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                """,
                (kind, self._fingerprint(kind, key)),
            )
            row = cur.fetchone()
        return None if row is None else self._open(row[0])

    def delete(self, kind: str, key: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM hwpx_oauth_state WHERE kind = %s AND key_hash = %s",
                (kind, self._fingerprint(kind, key)),
            )

    def consume_and_issue(
        self,
        *,
        consumed_kind: str,
        consumed_key: str,
        issued: list[dict[str, Any]],
    ) -> bool:
        """Atomically consume a one-time code/refresh token and issue successors."""
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM hwpx_oauth_state
                    WHERE kind = %s AND key_hash = %s
                      AND revoked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    FOR UPDATE
                    """,
                    (consumed_kind, self._fingerprint(consumed_kind, consumed_key)),
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    return False
                cur.execute(
                    """
                    UPDATE hwpx_oauth_state
                    SET revoked_at = NOW(), updated_at = NOW()
                    WHERE kind = %s AND key_hash = %s
                    """,
                    (consumed_kind, self._fingerprint(consumed_kind, consumed_key)),
                )
                for item in issued:
                    self._upsert_cursor(cur, **item)
            conn.commit()
        return True

    def revoke_family(self, client_id: str, subject: str | None) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            if subject is None:
                cur.execute(
                    """
                    UPDATE hwpx_oauth_state
                    SET revoked_at = NOW(), updated_at = NOW()
                    WHERE client_id = %s
                      AND kind IN ('access', 'refresh')
                      AND revoked_at IS NULL
                    """,
                    (client_id,),
                )
            else:
                cur.execute(
                    """
                    UPDATE hwpx_oauth_state
                    SET revoked_at = NOW(), updated_at = NOW()
                    WHERE client_id = %s
                      AND subject = %s
                      AND kind IN ('access', 'refresh')
                      AND revoked_at IS NULL
                    """,
                    (client_id, subject),
                )
            return cur.rowcount

    def cleanup(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM hwpx_oauth_state
                WHERE kind <> 'client'
                  AND expires_at IS NOT NULL
                  AND expires_at <= NOW()
                """
            )
            return cur.rowcount

    def counts(self) -> dict[str, int]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT kind, COUNT(*)
                FROM hwpx_oauth_state
                WHERE revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                GROUP BY kind
                """
            )
            return {kind: int(count) for kind, count in cur.fetchall()}
