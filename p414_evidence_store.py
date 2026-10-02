from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from p414_evidence_service import canonical_sha256, normalize_capture_evidence


class P414EvidenceStore:
    """Postgres append-only custody for signed capture attempts and key events."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("P4.14 evidence store requires the durable Postgres URL")
        self.database_url = database_url
        self._ensure_schema()

    @property
    def mode(self) -> str:
        return "postgres-append-only-signed-native-evidence"

    def _connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.database_url, autocommit=autocommit, row_factory=dict_row)

    def _ensure_schema(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "p414_evidence_store.sql")
        with open(schema_path, encoding="utf-8") as handle:
            ddl = handle.read()
        with self._connect(autocommit=False) as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (0x50343134,))
            # The schema contains multiple statements and a PL/pgSQL body; use
            # psycopg's simple-query path rather than preparing it as one statement.
            conn.execute(ddl, prepare=False)

    def list_keys(self, *, active_only: bool = False) -> dict[str, dict]:
        where = " WHERE status='ACTIVE'" if active_only else ""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT agent_id,key_id,public_key_ed25519_b64,status,created_at,revoked_at,rotation_of "
                f"FROM hwpx_p414_agent_key{where} ORDER BY created_at,key_id"
            ).fetchall()
        return {row["key_id"]: {**row, "created_at": row["created_at"].isoformat(), "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None} for row in rows}

    def register_key(self, *, agent_id: str, key_id: str, public_key_ed25519_b64: str, rotation_of: str | None = None) -> dict:
        event_payload = {"agent_id": agent_id, "key_id": key_id, "public_key_ed25519_b64": public_key_ed25519_b64, "rotation_of": rotation_of}
        digest = canonical_sha256(event_payload)
        kind = "ROTATED" if rotation_of else "REGISTERED"
        with self._connect(autocommit=False) as conn:
            exists = conn.execute("SELECT 1 FROM hwpx_p414_agent_key WHERE key_id=%s", (key_id,)).fetchone()
            if exists:
                raise ValueError("key_id already exists; key records are not overwritten")
            if rotation_of:
                prior = conn.execute("SELECT agent_id,status FROM hwpx_p414_agent_key WHERE key_id=%s FOR UPDATE", (rotation_of,)).fetchone()
                if not prior or prior["agent_id"] != agent_id or prior["status"] != "ACTIVE":
                    raise ValueError("rotation_of must identify an active key belonging to the same agent")
            conn.execute(
                "INSERT INTO hwpx_p414_agent_key(agent_id,key_id,public_key_ed25519_b64,status,rotation_of) VALUES(%s,%s,%s,'ACTIVE',%s)",
                (agent_id, key_id, public_key_ed25519_b64, rotation_of),
            )
            event_id = f"key:{digest}"
            conn.execute(
                "INSERT INTO hwpx_p414_agent_key_event(event_id,key_id,agent_id,event_kind,payload_sha256,payload) VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
                (event_id, key_id, agent_id, kind, digest, json.dumps(event_payload)),
            )
        return {"key_id": key_id, "agent_id": agent_id, "status": "ACTIVE", "event_id": event_id, "payload_sha256": digest}

    def revoke_key(self, *, key_id: str, reason: str) -> dict:
        with self._connect(autocommit=False) as conn:
            row = conn.execute("SELECT agent_id,status FROM hwpx_p414_agent_key WHERE key_id=%s FOR UPDATE", (key_id,)).fetchone()
            if not row:
                raise KeyError("unknown key_id")
            if row["status"] == "REVOKED":
                return {"key_id": key_id, "status": "REVOKED", "idempotent": True}
            payload = {"key_id": key_id, "agent_id": row["agent_id"], "reason": reason}
            digest = canonical_sha256(payload)
            event_id = f"key:{digest}"
            conn.execute("UPDATE hwpx_p414_agent_key SET status='REVOKED',revoked_at=NOW() WHERE key_id=%s", (key_id,))
            conn.execute(
                "INSERT INTO hwpx_p414_agent_key_event(event_id,key_id,agent_id,event_kind,payload_sha256,payload) VALUES(%s,%s,%s,'REVOKED',%s,%s::jsonb)",
                (event_id, key_id, row["agent_id"], digest, json.dumps(payload)),
            )
        return {"key_id": key_id, "status": "REVOKED", "event_id": event_id, "payload_sha256": digest}

    def record_attempt(self, receipt: Mapping[str, Any], validation: Mapping[str, Any]) -> dict:
        evidence_id = canonical_sha256(receipt)
        payload = receipt.get("signed_payload") if isinstance(receipt.get("signed_payload"), Mapping) else {}
        agent_id = str(receipt.get("agent_id") or "")
        key_id = str(receipt.get("key_id") or "")
        job_id = str(payload.get("job_id") or "unknown")
        nonce = str(payload.get("nonce") or "unknown")
        normalized = normalize_capture_evidence(receipt, validation)
        with self._connect(autocommit=False) as conn:
            # Serialize decisions for this agent/job and agent/nonce to make replay rejection race-safe.
            lock_material = hashlib.sha256(f"{agent_id}\0{job_id}\0{nonce}".encode()).digest()[:8]
            lock_id = int.from_bytes(lock_material, "big", signed=True)
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
            exact = conn.execute(
                "SELECT evidence_id,validation_result::text FROM hwpx_p414_receipt_attempt "
                "WHERE agent_id=%s AND job_id=%s AND evidence_id=%s AND accepted=TRUE ORDER BY received_at LIMIT 1",
                (agent_id, job_id, evidence_id),
            ).fetchone()
            if exact and validation.get("accepted") is True:
                result = json.loads(exact["validation_result"])
                return {**result, "idempotent_retry": True, "evidence_id": evidence_id}
            replay = conn.execute(
                "SELECT evidence_id,job_id FROM hwpx_p414_receipt_attempt WHERE agent_id=%s AND accepted=TRUE AND (job_id=%s OR nonce=%s) LIMIT 1",
                (agent_id, job_id, nonce),
            ).fetchone()
            accepted_validation = dict(validation)
            if replay:
                accepted_validation["status"] = "REJECTED"
                accepted_validation["accepted"] = False
                accepted_validation.setdefault("issues", []).append({"code": "REPLAYED_JOB_OR_NONCE", "prior_evidence_id": replay["evidence_id"]})
                accepted_validation["validation_sha256"] = canonical_sha256(accepted_validation)
                normalized = normalize_capture_evidence(receipt, accepted_validation)
            attempt_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO hwpx_p414_receipt_attempt(attempt_id,evidence_id,agent_id,key_id,job_id,nonce,exact_head,product,raw_receipt,signed_payload,canonical_sha256,validation_result,normalized_evidence,accepted) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s)",
                (attempt_id, evidence_id, agent_id, key_id, job_id, nonce, payload.get("exact_head"), payload.get("product"), json.dumps(receipt, ensure_ascii=False), json.dumps(payload, ensure_ascii=False), str(validation.get("canonical_sha256") or ""), json.dumps(accepted_validation, ensure_ascii=False), json.dumps(normalized, ensure_ascii=False), bool(accepted_validation.get("accepted"))),
            )
        return {**accepted_validation, "evidence_id": evidence_id, "attempt_id": attempt_id, "idempotent_retry": False}

    def accepted_receipts(self, *, exact_head: str = "", limit: int = 1000) -> list[dict]:
        clause = " AND exact_head=%s" if exact_head else ""
        params = (exact_head, max(1, min(int(limit), 5000))) if exact_head else (max(1, min(int(limit), 5000)),)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT normalized_evidence::text FROM hwpx_p414_receipt_attempt WHERE accepted=TRUE" + clause + " ORDER BY received_at DESC LIMIT %s",
                params,
            ).fetchall()
        return [item for row in rows if (item := json.loads(row["normalized_evidence"])).get("test_only") is not True]

    def accepted_receipt_by_id(self, evidence_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT raw_receipt::text,validation_result::text,normalized_evidence::text FROM hwpx_p414_receipt_attempt WHERE evidence_id=%s AND accepted=TRUE ORDER BY received_at LIMIT 1",
                (evidence_id,),
            ).fetchone()
        if not row:
            return None
        normalized = json.loads(row["normalized_evidence"])
        if normalized.get("test_only") is True:
            return None
        return {"raw_receipt": json.loads(row["raw_receipt"]), "validation_result": json.loads(row["validation_result"]), "normalized_evidence": normalized}

    def accepted_raw_receipts(self, *, exact_head: str, limit: int = 1000) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT raw_receipt::text,normalized_evidence::text FROM hwpx_p414_receipt_attempt "
                "WHERE accepted=TRUE AND exact_head=%s ORDER BY received_at DESC LIMIT %s",
                (exact_head, max(1, min(int(limit), 5000))),
            ).fetchall()
        return [json.loads(row["raw_receipt"]) for row in rows if json.loads(row["normalized_evidence"]).get("test_only") is not True]

    def receipt_for_document(self, *, document_id: str, revision: int, document_sha256: str) -> dict | None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT normalized_evidence::text FROM hwpx_p414_receipt_attempt WHERE accepted=TRUE ORDER BY received_at DESC LIMIT 1000"
            ).fetchall()
        for row in rows:
            evidence = json.loads(row["normalized_evidence"])
            if evidence.get("test_only") is not True and evidence.get("document_binding") == {"document_id": document_id, "revision": int(revision), "document_sha256": document_sha256}:
                return evidence
        return None

    def counts(self) -> dict:
        with self._connect() as conn:
            keys = conn.execute("SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE status='REVOKED') AS revoked FROM hwpx_p414_agent_key").fetchone()
            receipts = conn.execute("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE accepted) AS accepted, COUNT(*) FILTER (WHERE validation_result::text LIKE '%REPLAYED_JOB_OR_NONCE%') AS replayed FROM hwpx_p414_receipt_attempt").fetchone()
        return {"key_count": int(keys["n"]), "revoked_key_count": int(keys["revoked"]), "receipt_attempt_count": int(receipts["total"]), "accepted_receipt_count": int(receipts["accepted"]), "replay_rejection_count": int(receipts["replayed"])}


def default_database_url() -> str:
    return (os.environ.get("P414_EVIDENCE_DATABASE_URL", "").strip() or os.environ.get("P30_DOCUMENT_DATABASE_URL", "").strip() or os.environ.get("P12_AUTH_DATABASE_URL", "").strip())
