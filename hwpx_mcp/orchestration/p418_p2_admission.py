"""P4.18-P2 durable execution admission ledger.

This module deliberately does not expose a user approval tool. A trusted host
must verify an actual user-confirmation event before calling approve(). Merely
supplying a Boolean or a preview hash is not confirmation.

Conservative crash safety: a claimed mutation whose outcome is not durably
recorded enters UNCERTAIN and MUST NOT be replayed automatically. Recovery
requires a separately verified underlying document commit receipt.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class AdmissionError(ValueError):
    pass


class DurableApprovalLedger:
    """Transaction-scoped ledger; caller identity must come from server auth."""

    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("durable approval ledger requires PostgreSQL")
        self.database_url = database_url
        self._ensure_schema()

    def _connect(self):
        return psycopg.connect(self.database_url, autocommit=False)

    def _ensure_schema(self):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hwpx_p418_workflow_admission (
                    workflow_id TEXT PRIMARY KEY,
                    owner_subject TEXT NOT NULL,
                    draft_sha256 TEXT NOT NULL,
                    preview_sha256 TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    effect_scope TEXT NOT NULL,
                    approval_key_hash TEXT,
                    expires_at TIMESTAMPTZ NOT NULL,
                    state TEXT NOT NULL CHECK (state IN
                      ('STAGED','APPROVED','CLAIMED','COMMITTED','UNCERTAIN','ABORTED')),
                    execution_key TEXT UNIQUE,
                    result_json JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

    @staticmethod
    def _require_digest(name: str, value: str):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise AdmissionError(f"{name} must be a lower-case SHA-256 hex digest")

    def stage(self, *, owner: str, draft_sha256: str, preview_sha256: str,
              bound_inputs: Mapping[str, Any], effect_scope: str, ttl_seconds: int = 600) -> dict:
        if not isinstance(owner, str) or not owner.strip():
            raise AdmissionError("authenticated owner required")
        self._require_digest("draft_sha256", draft_sha256)
        self._require_digest("preview_sha256", preview_sha256)
        if effect_scope not in {"CREATE", "EDIT_INTENT", "TEMPLATE_FILL"}:
            raise AdmissionError("unsupported mutation effect scope")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 1800:
            raise AdmissionError("approval lifetime must be 60..1800 seconds")
        if not isinstance(bound_inputs, Mapping):
            raise AdmissionError("server-verified bindings required")
        binding_sha256 = canonical_sha(bound_inputs)
        workflow_id = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO hwpx_p418_workflow_admission
                  (workflow_id,owner_subject,draft_sha256,preview_sha256,binding_sha256,
                   effect_scope,expires_at,state)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'STAGED')
            """, (workflow_id, owner, draft_sha256, preview_sha256, binding_sha256,
                  effect_scope, expires_at))
        return {"workflow_id": workflow_id, "state": "STAGED", "expires_at": expires_at.isoformat(),
                "approval_granted": False}

    def approve(self, *, owner: str, workflow_id: str,
                trusted_confirmation: Any, verify_confirmation: Callable[..., bool]) -> dict:
        """Requires host-owned verification, not MCP agent-supplied approval."""
        if not callable(verify_confirmation) or not verify_confirmation(owner, workflow_id, trusted_confirmation):
            raise AdmissionError("trusted host user confirmation required")
        key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE hwpx_p418_workflow_admission
                   SET state='APPROVED',approval_key_hash=%s,updated_at=NOW()
                 WHERE workflow_id=%s AND owner_subject=%s AND state='STAGED'
                   AND expires_at>NOW()
                RETURNING draft_sha256,preview_sha256,effect_scope
            """, (key_hash, workflow_id, owner))
            row = cur.fetchone()
            if row is None:
                raise AdmissionError("missing, stale or already-approved workflow")
        return {"workflow_id": workflow_id, "approval_key": key, "state": "APPROVED",
                "effect_scope": row[2], "draft_sha256": row[0], "preview_sha256": row[1]}

    def claim(self, *, owner: str, workflow_id: str, approval_key: str,
              draft_sha256: str, preview_sha256: str, bound_inputs: Mapping[str, Any],
              effect_scope: str, execution_key: str) -> dict:
        if not isinstance(execution_key, str) or not 16 <= len(execution_key) <= 160:
            raise AdmissionError("stable execution key required")
        binding_hash = canonical_sha(bound_inputs)
        provided_hash = hashlib.sha256(approval_key.encode("utf-8")).hexdigest()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT owner_subject,draft_sha256,preview_sha256,binding_sha256,
                       effect_scope,approval_key_hash,state,expires_at,execution_key,result_json
                  FROM hwpx_p418_workflow_admission
                 WHERE workflow_id=%s FOR UPDATE
            """, (workflow_id,))
            r = cur.fetchone()
            if r is None or r[0] != owner:
                raise AdmissionError("workflow not found for caller")
            if not (r[1] == draft_sha256 and r[2] == preview_sha256 and
                    r[3] == binding_hash and r[4] == effect_scope and
                    isinstance(r[5], str) and hmac.compare_digest(r[5], provided_hash)):
                raise AdmissionError("approval no longer matches draft, preview, bindings or scope")
            if r[6] == "COMMITTED" and r[8] == execution_key:
                return {"state": "COMMITTED", "replay": True, "result": r[9]}
            if r[6] in {"CLAIMED", "UNCERTAIN"}:
                return {"state": "UNCERTAIN", "replay": False,
                        "reason": "MUTATION_OUTCOME_REQUIRES_DURABLE_RECONCILIATION"}
            if r[6] != "APPROVED" or r[7] <= datetime.now(timezone.utc):
                raise AdmissionError("approval expired or no longer admissible")
            cur.execute("""
                UPDATE hwpx_p418_workflow_admission
                   SET state='CLAIMED',execution_key=%s,updated_at=NOW()
                 WHERE workflow_id=%s
            """, (execution_key, workflow_id))
        return {"state": "CLAIMED", "replay": False,
                "warning": "If the process crashes before a durable commit receipt, quarantine; never auto-replay."}

    def committed(self, *, owner: str, workflow_id: str, execution_key: str,
                  result: Mapping[str, Any], verify_commit: Callable[..., bool]) -> dict:
        if not callable(verify_commit) or not verify_commit(owner, result):
            raise AdmissionError("verified durable underlying commit receipt required")
        if not isinstance(result, Mapping):
            raise AdmissionError("result object required")
        payload = dict(result)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE hwpx_p418_workflow_admission
                   SET state='COMMITTED',result_json=%s::jsonb,updated_at=NOW()
                 WHERE workflow_id=%s AND owner_subject=%s AND
                       execution_key=%s AND state='CLAIMED'
                RETURNING workflow_id
            """, (json.dumps(payload, ensure_ascii=False), workflow_id, owner, execution_key))
            if cur.fetchone() is None:
                raise AdmissionError("claim not found or already reconciled")
        return {"state": "COMMITTED", "result": payload}

    def reconcile_uncertain(self, *, owner: str, workflow_id: str,
                            execution_key: str, result: Mapping[str, Any],
                            verify_commit: Callable[..., bool]) -> dict:
        """Record *verified* external commit; never re-executes the mutation.

        Requires a trusted verifier that checks durable revision, SHA and
        owner custody against the underlying document commit ledger.
        """
        if not isinstance(result, Mapping):
            raise AdmissionError("durable commit receipt object required")
        if not callable(verify_commit) or not verify_commit(owner, result):
            raise AdmissionError("independent durable commit verification required")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE hwpx_p418_workflow_admission
                   SET state='COMMITTED',result_json=%s::jsonb,updated_at=NOW()
                 WHERE workflow_id=%s AND owner_subject=%s AND
                       execution_key=%s AND state='UNCERTAIN'
                RETURNING workflow_id
            """, (json.dumps(dict(result), ensure_ascii=False),
                  workflow_id, owner, execution_key))
            if cur.fetchone() is None:
                raise AdmissionError("matching uncertain claim not found")
        return {"state": "COMMITTED", "result": dict(result),
                "mutation_replayed": False, "route": "VERIFIED_EXISTING_COMMIT_ONLY"}

    def recover(self, *, owner: str, workflow_id: str) -> dict:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT state,result_json FROM hwpx_p418_workflow_admission
                 WHERE workflow_id=%s AND owner_subject=%s FOR UPDATE
            """, (workflow_id, owner))
            row = cur.fetchone()
            if row is None:
                raise AdmissionError("workflow not found")
            state, result = row
            if state == "CLAIMED":
                cur.execute("""UPDATE hwpx_p418_workflow_admission SET state='UNCERTAIN',
                    updated_at=NOW() WHERE workflow_id=%s""", (workflow_id,))
                state = "UNCERTAIN"
        return {"state": state, "result": result if state == "COMMITTED" else None,
                "replay_allowed": False,
                "recovery_route": "EXACT_REVISION_DELIVERY_ONLY" if state == "COMMITTED"
                                  else "MANUAL_DURABLE_COMMIT_RECONCILIATION" if state == "UNCERTAIN"
                                  else "NO_MUTATION_REPLAY"}
