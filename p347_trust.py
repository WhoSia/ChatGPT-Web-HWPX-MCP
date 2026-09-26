from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_POLICY_SCHEMA = "chatgpt-web-hwpx-mcp/p3.47/trust-policy/v1"
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _public_key_record(row: Mapping[str, Any]) -> tuple[str, str]:
    pem = str((row or {}).get("public_key_pem") or "")
    der_b64 = str((row or {}).get("public_key_der_base64") or "")
    try:
        if pem:
            key = serialization.load_pem_public_key(pem.encode("utf-8"))
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("not Ed25519")
            der = key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        elif der_b64:
            der = base64.b64decode(der_b64, validate=True)
            key = serialization.load_der_public_key(der)
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("not Ed25519")
        else:
            raise ValueError("missing public key")
    except Exception as exc:
        raise ValueError("P3.47 trust root public key is invalid") from exc
    fingerprint = hashlib.sha256(der).hexdigest()
    declared = str((row or {}).get("public_key_sha256") or "")
    if declared and declared != fingerprint:
        raise ValueError("P3.47 trust root fingerprint mismatch")
    return base64.b64encode(der).decode("ascii"), fingerprint


def _load_der_public_key(der_base64: str) -> Ed25519PublicKey:
    try:
        der = base64.b64decode(str(der_base64), validate=True)
        key = serialization.load_der_public_key(der)
    except Exception as exc:
        raise RuntimeError("P3.47 normalized trust root key is invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("P3.47 normalized trust root is not Ed25519")
    return key


def normalize_trust_policy(raw: Mapping[str, Any]) -> dict:
    policy = dict(raw or {})
    if policy.get("schema") != _POLICY_SCHEMA:
        raise ValueError("invalid P3.47 trust policy schema")

    builders = []
    for row in list(policy.get("builders") or []):
        builder_id = str((row or {}).get("builder_id") or "")
        key_id = str((row or {}).get("key_id") or "")
        if not builder_id or not _KEY_ID.fullmatch(key_id):
            raise ValueError("invalid P3.47 builder trust root")
        der_b64, fingerprint = _public_key_record(row or {})
        builders.append(
            {
                "builder_id": builder_id,
                "key_id": key_id,
                "public_key_der_base64": der_b64,
                "public_key_sha256": fingerprint,
            }
        )

    hosts = []
    for row in list(policy.get("hosts") or []):
        host_id = str((row or {}).get("host_id") or "")
        contract = str((row or {}).get("host_contract_sha256") or "")
        key_id = str((row or {}).get("key_id") or "")
        if not host_id or not _KEY_ID.fullmatch(key_id) or not _HEX64.fullmatch(contract):
            raise ValueError("invalid P3.47 host trust root")
        der_b64, fingerprint = _public_key_record(row or {})
        hosts.append(
            {
                "host_id": host_id,
                "host_contract_sha256": contract,
                "key_id": key_id,
                "public_key_der_base64": der_b64,
                "public_key_sha256": fingerprint,
            }
        )

    if len(builders) < 2 or len(builders) > 64:
        raise ValueError("P3.47 trust policy requires 2..64 builder roots")
    if len(hosts) < 2 or len(hosts) > 64:
        raise ValueError("P3.47 trust policy requires 2..64 host roots")
    if len({x["key_id"] for x in builders + hosts}) != len(builders) + len(hosts):
        raise ValueError("P3.47 trust policy key_id values must be globally unique")
    if len({x["public_key_sha256"] for x in builders}) != len(builders):
        raise ValueError("P3.47 builder roots must use distinct public keys")
    if len({x["public_key_sha256"] for x in hosts}) != len(hosts):
        raise ValueError("P3.47 host roots must use distinct public keys")
    if len({(x["builder_id"], x["key_id"]) for x in builders}) != len(builders):
        raise ValueError("duplicate P3.47 builder trust root")
    if len({(x["host_id"], x["host_contract_sha256"], x["key_id"]) for x in hosts}) != len(hosts):
        raise ValueError("duplicate P3.47 host trust root")

    body = {
        "schema": _POLICY_SCHEMA,
        "builders": sorted(builders, key=lambda x: (x["builder_id"], x["key_id"])),
        "hosts": sorted(hosts, key=lambda x: (x["host_id"], x["host_contract_sha256"], x["key_id"])),
    }
    return {**body, "trust_policy_sha256": _sha(body)}


def _verification(raw: Mapping[str, Any]) -> tuple[str, bytes]:
    verification = dict(raw.get("verification") or {})
    if verification.get("algorithm") != "ed25519":
        raise RuntimeError("P3.47 signed evidence requires ed25519")
    key_id = str(verification.get("key_id") or "")
    if not _KEY_ID.fullmatch(key_id):
        raise RuntimeError("P3.47 signed evidence key_id is invalid")
    try:
        signature = base64.b64decode(str(verification.get("signature_base64") or ""), validate=True)
    except Exception as exc:
        raise RuntimeError("P3.47 signed evidence signature is invalid base64") from exc
    if len(signature) != 64:
        raise RuntimeError("P3.47 Ed25519 signature must be 64 bytes")
    return key_id, signature


def _signed_body(raw: Mapping[str, Any]) -> dict:
    body = copy.deepcopy(dict(raw))
    body.pop("verification", None)
    return body


def verify_build_attestation(attestation: Mapping[str, Any], trust_policy: Mapping[str, Any]) -> dict:
    policy = normalize_trust_policy(trust_policy)
    raw = dict(attestation or {})
    builder_id = str((raw.get("builder") or {}).get("id") or "")
    key_id, signature = _verification(raw)
    roots = [
        x for x in policy["builders"]
        if x["builder_id"] == builder_id and x["key_id"] == key_id
    ]
    if len(roots) != 1:
        raise RuntimeError("P3.47 build attestation signer is not trusted")
    root = roots[0]
    body = _signed_body(raw)
    try:
        _load_der_public_key(root["public_key_der_base64"]).verify(
            signature,
            _stable(body).encode("utf-8"),
        )
    except Exception as exc:
        raise RuntimeError("P3.47 build attestation signature verification failed") from exc
    return {
        "trusted": True,
        "builder_id": builder_id,
        "key_id": key_id,
        "public_key_sha256": root["public_key_sha256"],
        "signed_payload_sha256": _sha(body),
        "trust_policy_sha256": policy["trust_policy_sha256"],
        "authority": "TRUSTED_BUILD_ATTESTATION_SIGNATURE_PASS",
    }


def verify_build_provenance_pair(
    package: Mapping[str, Any],
    rebuild_package: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
) -> dict:
    policy = normalize_trust_policy(trust_policy)
    primary = verify_build_attestation(dict(package.get("build_attestation") or {}), policy)
    rebuild = verify_build_attestation(dict(rebuild_package.get("build_attestation") or {}), policy)
    independent = (
        primary["builder_id"] != rebuild["builder_id"]
        and primary["key_id"] != rebuild["key_id"]
        and primary["public_key_sha256"] != rebuild["public_key_sha256"]
    )
    if not independent:
        raise RuntimeError("P3.47 reproducible build requires independent trusted builder roots")
    return {
        "trusted": True,
        "independent_builder_roots": True,
        "primary": primary,
        "rebuild": rebuild,
        "trust_policy_sha256": policy["trust_policy_sha256"],
        "authority": "TRUSTED_INDEPENDENT_BUILD_PROVENANCE_PASS",
    }


def verify_host_observations(
    observations: Sequence[Mapping[str, Any]],
    trust_policy: Mapping[str, Any],
) -> dict:
    policy = normalize_trust_policy(trust_policy)
    if len(observations) < 2:
        raise RuntimeError("P3.47 trusted host evidence requires at least two hosts")
    receipts = []
    for observation in observations:
        raw = dict(observation or {})
        host_id = str(raw.get("host_id") or "")
        contract = str(raw.get("host_contract_sha256") or "")
        key_id, signature = _verification(raw)
        roots = [
            x for x in policy["hosts"]
            if x["host_id"] == host_id
            and x["host_contract_sha256"] == contract
            and x["key_id"] == key_id
        ]
        if len(roots) != 1:
            raise RuntimeError("P3.47 host observation signer/contract is not trusted")
        root = roots[0]
        body = _signed_body(raw)
        try:
            _load_der_public_key(root["public_key_der_base64"]).verify(
                signature,
                _stable(body).encode("utf-8"),
            )
        except Exception as exc:
            raise RuntimeError("P3.47 host observation signature verification failed") from exc
        receipts.append(
            {
                "host_id": host_id,
                "host_contract_sha256": contract,
                "key_id": key_id,
                "public_key_sha256": root["public_key_sha256"],
                "signed_payload_sha256": _sha(body),
            }
        )
    if len({x["host_id"] for x in receipts}) != len(receipts):
        raise RuntimeError("P3.47 trusted host evidence requires distinct host identities")
    if len({x["public_key_sha256"] for x in receipts}) != len(receipts):
        raise RuntimeError("P3.47 trusted host evidence requires distinct host roots")
    return {
        "trusted": True,
        "host_count": len(receipts),
        "receipts": sorted(receipts, key=lambda x: x["host_id"]),
        "trust_policy_sha256": policy["trust_policy_sha256"],
        "authority": "TRUSTED_DIFFERENTIAL_HOST_EVIDENCE_PASS",
    }
