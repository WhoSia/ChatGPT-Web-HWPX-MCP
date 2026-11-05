"""P4.24 revision-scoped encrypted native PDF artifact custody (not a download service).

Requires an existing verified document revision and P4.14 accepted evidence
from trusted server-side loaders. This storage primitive never authorizes
submission or delivery independently of the signed-handoff gate.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import psycopg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PDF_AAD_PREFIX = b"p424-native-pdf-custody-v1\0"
MAX_PDF_BYTES = 100 * 1024 * 1024


class P424PdfStore:
    """Owner-scoped AES-GCM PDF bytes in a separate revision-bound Postgres table.

    Intentionally does not edit hwpx_documents and does not expose URLs.
    The connection URL and 32+ character secret must be server-side only.
    """

    def __init__(self, database_url: str, state_secret: str) -> None:
        if not database_url:
            raise ValueError("PDF_DATABASE_URL_REQUIRED")
        if not isinstance(state_secret, str) or len(state_secret) < 32:
            raise ValueError("PDF_CUSTODY_SECRET_TOO_SHORT")
        self.database_url = database_url
        key = hashlib.sha256(b"p424-pdf-custody-key\0" + state_secret.encode("utf-8")).digest()
        self._aead = AESGCM(key)
        self._ensure_schema()

    def _connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.database_url, autocommit=autocommit)

    def _ensure_schema(self) -> None:
        # Revision deletion/expiry is the source of truth for PDF retention.
        # PDF custody must not block owner deletion or revision compaction.
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hwpx_p424_native_pdf (
                      evidence_id CHAR(64) PRIMARY KEY,
                      document_id TEXT NOT NULL,
                      revision INTEGER NOT NULL CHECK (revision > 0),
                      owner_subject TEXT NOT NULL,
                      source_sha256 CHAR(64) NOT NULL,
                      pdf_sha256 CHAR(64) NOT NULL,
                      pdf_bytes INTEGER NOT NULL CHECK (pdf_bytes BETWEEN 64 AND 104857600),
                      ciphertext BYTEA NOT NULL,
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      FOREIGN KEY (document_id, revision)
                        REFERENCES hwpx_document_revisions(document_id, revision)
                        ON DELETE CASCADE
                    )
                """)

    @staticmethod
    def _aad(evidence_id: str, document_id: str, revision: int,
             owner_subject: str, source_sha256: str, pdf_sha256: str) -> bytes:
        # Length-prefix fields to make concatenation unambiguous even when
        # document_id or owner contains separators.
        fields = (evidence_id, document_id, str(revision),
                  owner_subject, source_sha256, pdf_sha256)
        return PDF_AAD_PREFIX + b"".join(
            len(v.encode("utf-8")).to_bytes(4, "big") + v.encode("utf-8")
            for v in fields
        )

    @staticmethod
    def _check_receipt(*, admission: dict[str, Any], document: dict[str, Any],
                       evidence_id: str, owner_subject: str, pdf: bytes) -> str:
        if admission.get("status") != "ADMISSION_CHECK_PASSED" or admission.get("production_delivery_authorized") is not False:
            raise PermissionError("P424_ADMISSION_NOT_PASSED")
        if admission.get("p414_signature_accepted") is not True:
            raise PermissionError("P414_SIGNATURE_NOT_ACCEPTED")
        if any(admission.get(k) is not False for k in
               ("durable_replay_check_performed", "encrypted_custody_performed", "owner_scoped_delivery_performed")):
            raise PermissionError("P424_ADMISSION_EVIDENCE_INVALID")
        if not isinstance(evidence_id, str) or len(evidence_id) != 64 or not all(c in "0123456789abcdef" for c in evidence_id):
            raise ValueError("EVIDENCE_ID_INVALID")
        if not hmac.compare_digest(str(admission.get("signed_evidence_sha256", "")), evidence_id):
            raise PermissionError("EVIDENCE_ID_MISMATCH")
        if document.get("owner_subject") != owner_subject or not owner_subject:
            raise PermissionError("OWNER_MISMATCH")
        if document.get("document_id") != admission.get("document_id") or document.get("revision") != admission.get("revision"):
            raise PermissionError("DOCUMENT_REVISION_MISMATCH")
        if not isinstance(document.get("sha256"), str) or len(document["sha256"]) != 64:
            raise ValueError("SOURCE_SHA256_REQUIRED")
        if not isinstance(pdf, bytes) or not 64 <= len(pdf) <= MAX_PDF_BYTES:
            raise ValueError("PDF_SIZE_INVALID")
        if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-2048:]:
            raise ValueError("PDF_MAGIC_INVALID")
        sha = hashlib.sha256(pdf).hexdigest()
        if admission.get("pdf_sha256") != sha or admission.get("pdf_bytes") != len(pdf):
            raise PermissionError("PDF_DIGEST_OR_LENGTH_MISMATCH")
        return sha

    def put_verified(
        self, *, admission: dict[str, Any], document: dict[str, Any],
        evidence_id: str, authenticated_owner: str, pdf_bytes: bytes,
        evidence_store: Any,
    ) -> dict[str, Any]:
        """Seal bytes only if P4.14 durable evidence already accepted.

        A replayed idempotent PUT returns the existing identical record.
        Different bytes/source/owner/revision cannot overwrite the record.
        This is not a worker transfer or a signed download endpoint.
        """
        digest = self._check_receipt(
            admission=admission, document=document, evidence_id=evidence_id,
            owner_subject=authenticated_owner, pdf=pdf_bytes,
        )
        accepted = evidence_store.accepted_receipt_by_id(evidence_id)
        if (
            not isinstance(accepted, dict)
            or accepted.get("validation_result", {}).get("accepted") is not True
            or accepted.get("normalized_evidence", {}).get("test_only") is True
        ):
            raise PermissionError("DURABLE_SIGNED_EVIDENCE_NOT_ACCEPTED")
        normalized = accepted["normalized_evidence"]
        binding = normalized.get("document_binding") or {}
        if (
            binding.get("document_id") != document["document_id"]
            or binding.get("revision") != document["revision"]
            or binding.get("document_sha256") != document["sha256"]
            or binding.get("owner_subject") != authenticated_owner
        ):
            raise PermissionError("DURABLE_EVIDENCE_DOCUMENT_BINDING_MISMATCH")
        outputs = normalized.get("outputs") or []
        if len(outputs) != 1 or outputs[0].get("pdf_sha256") != digest or outputs[0].get("bytes") != len(pdf_bytes):
            raise PermissionError("DURABLE_EVIDENCE_PDF_MISMATCH")

        aad = self._aad(evidence_id, document["document_id"], document["revision"],
                        authenticated_owner, document["sha256"], digest)
        nonce = os.urandom(12)
        encrypted = nonce + self._aead.encrypt(nonce, pdf_bytes, aad)
        with self._connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hwpx_p424_native_pdf
                      (evidence_id,document_id,revision,owner_subject,source_sha256,
                       pdf_sha256,pdf_bytes,ciphertext)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (evidence_id) DO NOTHING
                """, (evidence_id, document["document_id"], document["revision"],
                      authenticated_owner, document["sha256"], digest,
                      len(pdf_bytes), encrypted))
                inserted = cur.rowcount == 1
                cur.execute("""
                    SELECT document_id,revision,owner_subject,source_sha256,
                           pdf_sha256,pdf_bytes FROM hwpx_p424_native_pdf
                    WHERE evidence_id=%s FOR UPDATE
                """, (evidence_id,))
                existing = cur.fetchone()
                expected = (document["document_id"], document["revision"],
                            authenticated_owner, document["sha256"],
                            digest, len(pdf_bytes))
                if not existing or tuple(existing) != expected:
                    raise PermissionError("EVIDENCE_ID_ALREADY_BOUND_TO_DIFFERENT_ARTIFACT")
        return {"status": "ENCRYPTED_CUSTODY_CREATED" if inserted else "ENCRYPTED_CUSTODY_ALREADY_EXISTS",
                "evidence_id": evidence_id, "document_id": document["document_id"],
                "revision": document["revision"], "pdf_sha256": digest, "pdf_bytes": len(pdf_bytes),
                "owner_scoped_delivery_performed": False}

    def load_owned(
        self, *, evidence_id: str, authenticated_owner: str,
        document_store: Any,
    ) -> bytes:
        """Decrypt only when the live revision exists and belongs to this owner."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT document_id,revision,owner_subject,source_sha256,
                       pdf_sha256,pdf_bytes,ciphertext
                FROM hwpx_p424_native_pdf
                WHERE evidence_id=%s AND owner_subject=%s
            """, (evidence_id, authenticated_owner))
            row = cur.fetchone()
        if row is None:
            raise FileNotFoundError("PDF_NOT_FOUND_OR_NOT_OWNED")
        doc_id, revision, owner, source_sha, pdf_sha, byte_count, encrypted = row
        revision_record = document_store.load_revision(doc_id, revision)
        if (revision_record is None or revision_record.get("owner_subject") != authenticated_owner
            or revision_record.get("sha256") != source_sha):
            raise PermissionError("SOURCE_REVISION_NOT_AVAILABLE_OR_CHANGED")
        raw = bytes(encrypted)
        if len(raw) < 29:
            raise ValueError("ENCRYPTED_PDF_TRUNCATED")
        aad = self._aad(evidence_id, doc_id, revision, owner, source_sha, pdf_sha)
        plaintext = self._aead.decrypt(raw[:12], raw[12:], aad)
        if len(plaintext) != byte_count or not hmac.compare_digest(hashlib.sha256(plaintext).hexdigest(), pdf_sha):
            raise ValueError("ENCRYPTED_PDF_INTEGRITY_MISMATCH")
        return plaintext
