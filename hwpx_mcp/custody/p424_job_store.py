"""Durable server-issued authorization for one P4.24 native PDF capture job.

The Windows agent signature attests what ran; this independent Postgres
record attests what the authenticated server authorized *before* it ran.
No public job-issuance endpoint is installed by this module.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class P424IssuedJobStore:
    """A Postgres authority index distinct from signed worker receipts."""

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("JOB_DATABASE_URL_REQUIRED")
        self.database_url = database_url
        self._ensure_schema()

    def _connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.database_url, autocommit=autocommit,
                               row_factory=dict_row)

    def _ensure_schema(self):
        with self._connect(autocommit=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hwpx_p424_issued_native_job (
                  job_id TEXT PRIMARY KEY,
                  nonce TEXT NOT NULL UNIQUE,
                  owner_subject TEXT NOT NULL,
                  document_id TEXT NOT NULL,
                  revision INTEGER NOT NULL CHECK (revision > 0),
                  source_sha256 CHAR(64) NOT NULL,
                  source_manifest_sha256 CHAR(64) NOT NULL,
                  exact_head CHAR(40) NOT NULL,
                  fixture_id TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'ISSUED'
                    CHECK (status IN ('ISSUED','REVOKED')),
                  expires_at TIMESTAMPTZ NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  FOREIGN KEY (document_id, revision)
                    REFERENCES hwpx_document_revisions(document_id, revision)
                    ON DELETE CASCADE
                )
            """)
            # An old RESTRICT foreign key must not quietly inhibit deletion.
            rows = conn.execute("""
                SELECT confdeltype FROM pg_constraint
                WHERE conrelid='hwpx_p424_issued_native_job'::regclass
                  AND confrelid='hwpx_document_revisions'::regclass
                  AND contype='f'
            """).fetchall()
            if len(rows) != 1 or rows[0]["confdeltype"] != "c":
                raise RuntimeError("P424_JOB_REVISION_FK_MUST_CASCADE")

    def issue_job(
        self, *, job: Mapping[str, Any], document_store: Any,
        authenticated_owner: str, now: datetime | None = None,
    ) -> dict[str, Any]:
        """Persist single-use authority for an already prepared capture job.

        The caller must authenticate owner and generate nonce/job_id server
        side; never expose this method directly to an untrusted client.
        """
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            raise ValueError("AWARE_CLOCK_REQUIRED")
        fields = ("job_id","nonce","document_id","revision","source_sha256",
                  "source_manifest_sha256","exact_head","fixture_id","expires_at")
        if not isinstance(job, Mapping) or any(job.get(k) in (None, "") for k in fields):
            raise ValueError("ISSUED_JOB_MISSING_FIELDS")
        job_id, nonce = job["job_id"], job["nonce"]
        if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
            raise ValueError("INVALID_JOB_ID")
        if not isinstance(nonce, str) or not 22 <= len(nonce) <= 256 or not nonce.isascii() or not nonce.isprintable():
            raise ValueError("INVALID_JOB_NONCE")
        if any(not isinstance(job[k], str) or not rx.fullmatch(job[k]) for k,rx in
               (("source_sha256",_HEX64),("source_manifest_sha256",_HEX64),("exact_head",_HEX40))):
            raise ValueError("INVALID_JOB_DIGEST")
        if type(job["revision"]) is not int or job["revision"] < 1:
            raise ValueError("INVALID_JOB_REVISION")
        if not isinstance(job["fixture_id"], str) or not job["fixture_id"].strip():
            raise ValueError("INVALID_JOB_FIXTURE")
        if not isinstance(job["document_id"], str) or not re.fullmatch(r"doc_[A-Za-z0-9_-]{20,64}",job["document_id"]):
            raise ValueError("INVALID_DOCUMENT_ID")
        if not isinstance(authenticated_owner, str) or not authenticated_owner:
            raise PermissionError("AUTHENTICATED_OWNER_REQUIRED")
        expires = job["expires_at"]
        if not isinstance(expires, datetime) or expires.tzinfo is None:
            raise ValueError("AWARE_JOB_EXPIRY_REQUIRED")
        if not clock < expires <= clock + timedelta(hours=12):
            raise ValueError("INVALID_JOB_EXPIRY")
        source = document_store.load_revision(job["document_id"],job["revision"])
        if not isinstance(source, Mapping) or source.get("owner_subject") != authenticated_owner:
            raise PermissionError("HWPX_SOURCE_NOT_OWNED")
        payload = source.get("bytes")
        if not isinstance(payload, bytes) or hashlib.sha256(payload).hexdigest() != source.get("sha256"):
            raise ValueError("HWPX_SOURCE_DIGEST_MISMATCH")
        if not hmac.compare_digest(source["sha256"],job["source_sha256"]):
            raise ValueError("JOB_SOURCE_MISMATCH")
        if int(source["expires_at_epoch"]) <= int(expires.timestamp()):
            raise ValueError("JOB_OUTLIVES_SOURCE")
        with self._connect(autocommit=False) as conn:
            row = conn.execute("""
                INSERT INTO hwpx_p424_issued_native_job
                  (job_id,nonce,owner_subject,document_id,revision,
                   source_sha256,source_manifest_sha256,exact_head,fixture_id,expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING job_id
            """, (job_id,nonce,authenticated_owner,job["document_id"],
                  job["revision"],job["source_sha256"],
                  job["source_manifest_sha256"],job["exact_head"],
                  job["fixture_id"],expires)).fetchone()
            if not row:
                raise RuntimeError("JOB_ISSUANCE_NOT_COMMITTED")
        return {"status":"ISSUED","job_id":job_id,"expires_at":expires.isoformat(),
                "native_pdf_created":False,"production_delivery_authorized":False}

    def load_issued_job(self, job_id: str) -> dict[str, Any] | None:
        if not isinstance(job_id,str) or not _JOB_ID.fullmatch(job_id):
            return None
        with self._connect() as conn:
            row = conn.execute("""
                SELECT job_id,nonce,owner_subject,document_id,revision,
                       source_sha256,source_manifest_sha256,exact_head,fixture_id,status
                FROM hwpx_p424_issued_native_job
                WHERE job_id=%s AND status='ISSUED' AND expires_at>NOW()
            """,(job_id,)).fetchone()
        return dict(row) if row else None

    def revoke_job(self, job_id: str, *, authenticated_owner: str) -> bool:
        if not isinstance(job_id,str) or not _JOB_ID.fullmatch(job_id):
            raise ValueError("INVALID_JOB_ID")
        with self._connect(autocommit=False) as conn:
            row = conn.execute("""
                UPDATE hwpx_p424_issued_native_job SET status='REVOKED'
                WHERE job_id=%s AND owner_subject=%s AND status='ISSUED'
                RETURNING job_id
            """, (job_id,authenticated_owner)).fetchone()
        return row is not None
