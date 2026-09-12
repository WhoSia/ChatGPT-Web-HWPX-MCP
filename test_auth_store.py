from __future__ import annotations

import os
import secrets
import unittest

import psycopg
from mcp.server.auth.provider import RefreshToken

from auth_store import DurableOAuthStore


class DurableOAuthStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = os.environ["P12_AUTH_DATABASE_URL"]
        self.state_secret = os.environ["P12_STATE_SECRET"]
        self.client_id = "ci_" + secrets.token_urlsafe(12)
        self.subject = "hwpx-owner"
        self.token_value = "rt_ci_" + secrets.token_urlsafe(24)
        self.token = RefreshToken(
            token=self.token_value,
            client_id=self.client_id,
            scopes=["hwpx", "offline_access"],
            expires_at=4_102_444_800,
            resource="http://127.0.0.1:8000/mcp",
            subject=self.subject,
        )

    def test_restart_safe_encrypted_refresh_and_durable_revocation(self) -> None:
        first_process = DurableOAuthStore(self.database_url, self.state_secret)
        first_process.put(
            "refresh",
            self.token.token,
            self.token,
            client_id=self.client_id,
            subject=self.subject,
            expires_at=self.token.expires_at,
        )

        # A brand-new store object models a fresh server process after restart.
        second_process = DurableOAuthStore(self.database_url, self.state_secret)
        restored = second_process.get("refresh", self.token.token)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.token, self.token.token)
        self.assertEqual(restored.client_id, self.client_id)

        # The database payload must not contain a usable refresh token in plaintext.
        key_hash = second_process._fingerprint("refresh", self.token.token)
        with psycopg.connect(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM hwpx_oauth_state WHERE kind='refresh' AND key_hash=%s",
                (key_hash,),
            )
            encrypted_payload = bytes(cur.fetchone()[0])
        self.assertNotIn(self.token.token.encode("utf-8"), encrypted_payload)

        affected = second_process.revoke_family(self.client_id, self.subject)
        self.assertGreaterEqual(affected, 1)

        third_process = DurableOAuthStore(self.database_url, self.state_secret)
        self.assertIsNone(third_process.get("refresh", self.token.token))


if __name__ == "__main__":
    unittest.main()
