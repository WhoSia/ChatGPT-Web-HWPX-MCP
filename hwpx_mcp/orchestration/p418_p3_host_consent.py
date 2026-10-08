"""P4.18-P3 trusted-host confirmation verification boundary.

The signer MUST live in an independent interactive host, never in an MCP tool,
agent prompt, or model-visible input. This module only verifies an assertion.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping

class ConfirmationError(ValueError):
    pass

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def verify_host_confirmation(*, secret: bytes, envelope: Mapping,
                             owner: str, workflow_id: str,
                             draft_sha256: str, preview_sha256: str,
                             effect_scope: str, now: int | None = None) -> bool:
    """Verify host-origin consent scoped to exact draft, preview and action.

    A valid signature alone is not a one-use grant. The PostgreSQL STAGED ->
    APPROVED compare-and-set enforces consumption; host must authenticate the
    human independently before it signs.
    """
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ConfirmationError("independent host verification secret required")
    if not isinstance(envelope, Mapping) or set(envelope) != {"payload", "signature"}:
        return False
    payload = envelope.get("payload")
    signature = envelope.get("signature")
    if not isinstance(payload, Mapping) or not isinstance(signature, str):
        return False
    required = {"version", "subject", "workflow_id", "draft_sha256",
                "preview_sha256", "effect_scope", "issued_at", "expires_at", "decision"}
    if set(payload) != required:
        return False
    if payload["version"] != "p418-p3-host-consent-v1" or payload["decision"] != "APPROVE":
        return False
    if any(payload[k] != v for k, v in {
        "subject": owner, "workflow_id": workflow_id,
        "draft_sha256": draft_sha256, "preview_sha256": preview_sha256,
        "effect_scope": effect_scope}.items()):
        return False
    issued, expiry = payload["issued_at"], payload["expires_at"]
    if isinstance(issued, bool) or isinstance(expiry, bool) or not isinstance(issued, int) or not isinstance(expiry, int):
        return False
    clock = int(time.time()) if now is None else now
    if not issued <= clock <= expiry or expiry - issued > 300 or issued < clock - 300:
        return False
    expected = hmac.new(secret, b"p418-p3-consent-v1\0" + _canonical(payload), hashlib.sha256).digest()
    try:
        observed = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    except (ValueError, base64.binascii.Error):
        return False
    return hmac.compare_digest(expected, observed)
