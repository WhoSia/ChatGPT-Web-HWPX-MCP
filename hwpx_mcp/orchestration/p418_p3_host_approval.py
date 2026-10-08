"""Independent, passphrase-confirmed P4.18-P3 user approval host.

Only the FIRST-PARTY trusted web host may instantiate this controller.
No LLM/MCP tool issues a confirmation or receives an approval_key.
The operator must provision two independent high-entropy secrets separately
from OAuth and PostgreSQL state secrets before enabling the route.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable, Mapping
from typing import Any

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError, DurableApprovalLedger
from hwpx_mcp.orchestration.p418_p3_host_consent import _canonical
from hwpx_mcp.orchestration.p418_p3_review_packet import prepare_native_edit_review_packet
from hwpx_mcp.orchestration.p418_p3_review_store import DurableNativeReviewStore


class TrustedNativeEditApprovalHost:
    """User-initiated reauth -> exact staged review -> explicit mutation."""

    def __init__(self, *, ledger: DurableApprovalLedger,
                 reviews: DurableNativeReviewStore, owner: str,
                 review_passphrase: str, signing_secret: bytes,
                 native_executor: Callable[..., Mapping[str, Any]]):
        if not isinstance(owner, str) or not owner:
            raise RuntimeError("trusted host authenticated owner required")
        if not isinstance(review_passphrase, str) or len(review_passphrase) < 24:
            raise RuntimeError("dedicated human-confirmation passphrase required")
        if not isinstance(signing_secret, bytes) or len(signing_secret) < 32:
            raise RuntimeError("dedicated host-only signing secret required")
        if not callable(native_executor):
            raise RuntimeError("host-owned native edit execution adapter required")
        self.ledger = ledger
        self.reviews = reviews
        self.owner = owner
        self._passphrase = review_passphrase
        self._signing_secret = signing_secret
        self._native_executor = native_executor

    def _authenticate(self, workflow_id: str, supplied: str) -> None:
        if not self.reviews.verify_host_passphrase(
            owner=self.owner, workflow_id=workflow_id,
            supplied=supplied, expected=self._passphrase):
            raise AdmissionError("human confirmation authentication rejected")

    def _read_exact_review(self, workflow_id: str):
        saved = self.reviews.load_staged(owner=self.owner, workflow_id=workflow_id)
        packet = prepare_native_edit_review_packet(
            owner=self.owner, workflow_id=workflow_id, ledger=self.ledger,
            draft=saved["draft"], preview=saved["preview"],
            staged_bindings=saved["bound_inputs"])
        return saved, packet

    def inspect(self, *, workflow_id: str, passphrase: str) -> dict:
        self._authenticate(workflow_id, passphrase)
        _, packet = self._read_exact_review(workflow_id)
        return packet

    def deny(self, *, workflow_id: str, passphrase: str) -> dict:
        self._authenticate(workflow_id, passphrase)
        return self.ledger.abort_unclaimed(owner=self.owner, workflow_id=workflow_id)

    def approve_and_execute(self, *, workflow_id: str, passphrase: str,
                            displayed_review_sha256: str) -> dict:
        self._authenticate(workflow_id, passphrase)
        saved, packet = self._read_exact_review(workflow_id)
        if not isinstance(displayed_review_sha256, str) or not hmac.compare_digest(
                displayed_review_sha256, packet["review_packet_sha256"]):
            raise AdmissionError("displayed human review changed before confirmation")
        # The signing secret and approval_key stay server-only. This request
        # is initiated by a separate human HTML form with explicit approval.
        issued = int(time.time())
        payload = {
            "version": "p418-p3-host-consent-v1",
            "subject": self.owner,
            "workflow_id": workflow_id,
            "draft_sha256": saved["draft"]["draft_sha256"],
            "preview_sha256": saved["preview"]["preview_sha256"],
            "effect_scope": "EDIT_INTENT",
            "issued_at": issued,
            "expires_at": issued + 120,
            "decision": "APPROVE",
        }
        mac = hmac.new(
            self._signing_secret,
            b"p418-p3-consent-v1\0" + _canonical(payload),
            hashlib.sha256,
        ).digest()
        envelope = {
            "payload": payload,
            "signature": base64.urlsafe_b64encode(mac).decode("ascii").rstrip("="),
        }
        grant = self.ledger.approve_host_assertion(
            owner=self.owner, workflow_id=workflow_id,
            envelope=envelope, host_secret=self._signing_secret)
        result = self._native_executor(
            owner=self.owner, workflow_id=workflow_id,
            approval_key=grant["approval_key"],
            draft=saved["draft"], preview=saved["preview"],
            bound_inputs=saved["bound_inputs"],
            execution_key="p418-host-" + workflow_id,
        )
        # Never return secret tokens, env settings or authenticated approval
        # key to the browser; only the durable result needed for receipt.
        if not isinstance(result, Mapping):
            raise AdmissionError("trusted native execution result missing")
        return {
            "workflow_id": workflow_id,
            "state": result.get("state"),
            "mutation_executed": result.get("mutation_executed") is True,
            "delivery_only": result.get("delivery_only") is True,
            "requires_reconciliation": result.get("requires_reconciliation") is True,
            "document_id": packet["source"]["document_id"],
            "committed_revision": (
                result.get("result", {}).get("revision")
                if isinstance(result.get("result"), Mapping) else None),
            "authority": "TRUSTED_HOST_USER_APPROVED_NATIVE_EDIT",
        }
