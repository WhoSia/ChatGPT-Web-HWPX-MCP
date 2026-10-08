import base64
import hashlib
import hmac
import json

from hwpx_mcp.orchestration.p418_p3_host_consent import verify_host_confirmation

SECRET = b"host-only-shared-secret-keep-out-of-agent-" + b"z" * 32

def signed(**changes):
    p = {"version": "p418-p3-host-consent-v1", "subject": "owner",
         "workflow_id": "wid", "draft_sha256": "a"*64,
         "preview_sha256": "b"*64, "effect_scope": "EDIT_INTENT",
         "issued_at": 1000, "expires_at": 1030, "decision": "APPROVE"}
    p.update(changes)
    raw = json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    sig = hmac.new(SECRET, b"p418-p3-consent-v1\0" + raw, hashlib.sha256).digest()
    return {"payload": p, "signature": base64.urlsafe_b64encode(sig).decode().rstrip("=")}

def verify(env, **changes):
    options = {"secret": SECRET, "envelope": env, "owner": "owner",
               "workflow_id": "wid", "draft_sha256": "a"*64,
               "preview_sha256": "b"*64, "effect_scope": "EDIT_INTENT", "now": 1005}
    options.update(changes)
    return verify_host_confirmation(**options)

def test_exact_consent():
    assert verify(signed())

def test_tampered_or_cross_scoped_consent_fails():
    clean = signed()
    for field, value in [("decision", "DENY"), ("subject", "other"),
                         ("effect_scope", "CREATE"), ("preview_sha256", "c"*64),
                         ("workflow_id", "other")]:
        changed = {"payload": dict(clean["payload"], **{field: value}), "signature": clean["signature"]}
        assert not verify(changed)
    assert not verify(clean, owner="other")
    assert not verify(clean, draft_sha256="d"*64)

def test_expiry_future_signature_and_invalid_encoding_fail():
    assert not verify(signed(), now=1040)
    assert not verify(signed(issued_at=9000, expires_at=9040))
    assert not verify(signed(issued_at=1000, expires_at=1600))
    assert not verify({"payload": signed()["payload"], "signature": "!"})
    assert not verify(signed(), secret=b"short")
