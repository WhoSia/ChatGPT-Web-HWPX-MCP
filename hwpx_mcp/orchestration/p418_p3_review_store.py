"""Encrypted P4.18-P3 human-review custody for server-origin approval.

A STAGED record contains fingerprints only. The user must see the exact
original draft, preview and source bindings when providing consent. This
separate store encrypts the full original normalized payload with AES-GCM,
binds it to the admission ledger's immutable hashes and owner, and never
returns a client-provided replacement as evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

import psycopg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError, canonical_sha
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow

_DOMAIN = b"chatgpt-web-hwpx-mcp/p4.18-p3/review-store/aesgcm/v1\0"
_MAX_PAYLOAD = 262144


class DurableNativeReviewStore:
    def __init__(self, database_url: str, state_secret: str):
        if not database_url:
            raise RuntimeError("PostgreSQL required for durable human review")
        if not isinstance(state_secret, str) or len(state_secret) < 32:
            raise RuntimeError("a distinct, strong server state secret is required")
        self.database_url = database_url
        self._aead = AESGCM(hashlib.sha256(_DOMAIN + state_secret.encode("utf-8")).digest())
        self._ensure_schema()

    def _connect(self):
        return psycopg.connect(self.database_url, autocommit=False)

    def _ensure_schema(self):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hwpx_p418_native_review (
                    workflow_id TEXT PRIMARY KEY
                        REFERENCES hwpx_p418_workflow_admission(workflow_id)
                        ON DELETE CASCADE,
                    owner_subject TEXT NOT NULL,
                    encrypted_review BYTEA NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

    @staticmethod
    def _aad(owner: str, workflow_id: str) -> bytes:
        return _DOMAIN + owner.encode("utf-8") + b"\0" + workflow_id.encode("utf-8")

    @staticmethod
    def _identities(draft: Mapping, preview: Mapping, bindings: Mapping) -> dict:
        if not isinstance(draft, Mapping) or not isinstance(preview, Mapping) or not isinstance(bindings, Mapping):
            raise AdmissionError("full review requires canonical draft, preview and bindings")
        if preview_workflow(draft) != dict(preview):
            raise AdmissionError("review preview does not match canonical draft")
        steps = draft.get("steps")
        mutations = [step for step in steps if isinstance(step, Mapping) and step.get("effect") == "MUTATION"] if isinstance(steps, list) else []
        if len(mutations) != 1 or mutations[0].get("task", {}).get("kind") != "EDIT_INTENT":
            raise AdmissionError("host native review supports exactly one edit")
        return {
            "draft_sha256": draft["draft_sha256"],
            "preview_sha256": preview["preview_sha256"],
            "binding_sha256": canonical_sha(bindings),
            "effect_scope": "EDIT_INTENT",
        }

    def persist_staged(self, *, owner: str, workflow_id: str,
                       draft: Mapping, preview: Mapping, bound_inputs: Mapping) -> None:
        if not isinstance(owner, str) or not owner or not isinstance(workflow_id, str) or not workflow_id:
            raise AdmissionError("authenticated staged review owner and workflow required")
        identity = self._identities(draft, preview, bound_inputs)
        payload = {"draft": draft, "preview": preview, "bound_inputs": bound_inputs}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > _MAX_PAYLOAD:
            raise AdmissionError("native edit review exceeds durable custody limit")
        nonce = os.urandom(12)
        sealed = nonce + self._aead.encrypt(nonce, raw, self._aad(owner, workflow_id))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT draft_sha256,preview_sha256,binding_sha256,effect_scope
                  FROM hwpx_p418_workflow_admission
                 WHERE owner_subject=%s AND workflow_id=%s
                   AND state='STAGED' AND expires_at>NOW() FOR UPDATE
            """, (owner, workflow_id))
            row = cur.fetchone()
            if row is None or dict(zip(identity, row)) != identity:
                raise AdmissionError("durable staged admission differs from encrypted payload")
            cur.execute("""
                INSERT INTO hwpx_p418_native_review
                    (workflow_id,owner_subject,encrypted_review)
                VALUES (%s,%s,%s)
            """, (workflow_id, owner, sealed))

    def load_staged(self, *, owner: str, workflow_id: str) -> dict[str, Any]:
        if not isinstance(owner, str) or not owner or not isinstance(workflow_id, str) or not workflow_id:
            raise AdmissionError("authenticated staged review owner required")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT r.encrypted_review,
                       a.draft_sha256,a.preview_sha256,
                       a.binding_sha256,a.effect_scope
                  FROM hwpx_p418_native_review r
                  JOIN hwpx_p418_workflow_admission a ON a.workflow_id=r.workflow_id
                 WHERE r.workflow_id=%s AND r.owner_subject=%s
                   AND a.owner_subject=%s AND a.state='STAGED'
                   AND a.expires_at>NOW()
            """, (workflow_id, owner, owner))
            row = cur.fetchone()
        if row is None:
            raise AdmissionError("encrypted staged review missing or no longer available")
        from cryptography.exceptions import InvalidTag
        try:
            sealed = bytes(row[0])
            raw = self._aead.decrypt(sealed[:12], sealed[12:], self._aad(owner, workflow_id))
            if len(raw) > _MAX_PAYLOAD:
                raise AdmissionError("stored review exceeds custody limit")
            record = json.loads(raw.decode("utf-8"))
            identity = self._identities(record["draft"], record["preview"], record["bound_inputs"])
        except (InvalidTag, ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise AdmissionError("encrypted staged review failed integrity validation") from exc
        if dict(zip(identity, row[1:])) != identity:
            raise AdmissionError("encrypted review no longer matches durable admission")
        return record


@lru_cache(maxsize=2)
def get_native_review_store(database_url: str, state_secret: str) -> DurableNativeReviewStore:
    return DurableNativeReviewStore(database_url, state_secret)
