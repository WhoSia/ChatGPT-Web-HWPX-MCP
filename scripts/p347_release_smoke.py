from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p346_platform_bridge import validate_extension
from p347_supply_chain_bridge import (
    certify_extension_package,
    normalize_extension_package,
    supply_chain_contract,
    validate_rollout_transition,
)


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def public_pem(key):
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def sign_record(record, key, key_id):
    body = copy.deepcopy(record)
    body.pop("verification", None)
    record["verification"] = {
        "algorithm": "ed25519",
        "key_id": key_id,
        "signature_base64": base64.b64encode(
            key.sign(stable(body).encode("utf-8"))
        ).decode("ascii"),
    }


build_a = Ed25519PrivateKey.generate()
build_b = Ed25519PrivateKey.generate()
host_a = Ed25519PrivateKey.generate()
host_b = Ed25519PrivateKey.generate()
trust_policy = {
    "schema": "chatgpt-web-hwpx-mcp/p3.47/trust-policy/v1",
    "builders": [
        {"builder_id": "hwpx-mcp-release-smoke", "key_id": "build-a", "public_key_pem": public_pem(build_a)},
        {"builder_id": "hwpx-mcp-release-smoke-rebuild", "key_id": "build-b", "public_key_pem": public_pem(build_b)},
    ],
    "hosts": [
        {"host_id": "release-host-a", "host_contract_sha256": "e" * 64, "key_id": "host-a", "public_key_pem": public_pem(host_a)},
        {"host_id": "release-host-b", "host_contract_sha256": "f" * 64, "key_id": "host-b", "public_key_pem": public_pem(host_b)},
    ],
}

module = bytes.fromhex(
    "0061736d01000000"
    "0105016000017f"
    "03020100"
    "070c0108703334365f72756e0000"
    "0a06010400412a0b"
)
manifest = {
    "schema": "chatgpt-web-hwpx-mcp/p3.46/extension-manifest/v1",
    "extension_id": "release.smoke",
    "version": "1.0.0",
    "host_abi": "p3.46-extension-v1",
    "execution": {
        "mode": "WASM_NO_IMPORTS",
        "module_sha256": hashlib.sha256(module).hexdigest(),
        "entrypoint": "p346_run",
        "deterministic": True,
        "max_module_bytes": 65536,
        "timeout_ms": 250,
    },
    "capabilities": [{
        "name": "release.smoke.pure",
        "version": "1.0.0",
        "effect": "PURE",
        "adapter": "RELEASE_SMOKE_WASM",
        "deterministic": True,
        "evidence": ["RELEASE_SMOKE"],
    }],
    "node_kinds": [],
    "tools": [],
}
manifest_sha = validate_extension(manifest)["manifest_sha256"]
source_sha = hashlib.sha256(b"p347-release-smoke-source").hexdigest()
package = {
    "schema": "chatgpt-web-hwpx-mcp/p3.47/extension-package/v1",
    "extension": manifest,
    "module_base64": base64.b64encode(module).decode("ascii"),
    "dependencies": [],
    "build_attestation": {
        "schema": "chatgpt-web-hwpx-mcp/p3.47/build-attestation/v1",
        "predicate_type": "https://slsa.dev/provenance/v1",
        "builder": {"id": "hwpx-mcp-release-smoke"},
        "build_type": "deterministic-wasm",
        "source": {
            "uri": "git+https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP",
            "revision": "release-smoke",
            "sha256": source_sha,
        },
        "invocation": {"parameters": {"profile": "release-smoke"}},
        "materials": [{"uri": "source", "sha256": source_sha}],
        "subjects": [
            {"name": "extension-manifest.json", "sha256": manifest_sha},
            {"name": "module.wasm", "sha256": hashlib.sha256(module).hexdigest()},
        ],
        "reproducible": True,
    },
}
sign_record(package["build_attestation"], build_a, "build-a")

contract = supply_chain_contract()
assert contract["phase"] == "P3.47"
assert contract["product"] == "0.24.0-p3.47"
normalized = normalize_extension_package(package)
assert normalized["package_id"].startswith("sha256:")

rebuild_package = copy.deepcopy(package)
rebuild_package["build_attestation"]["builder"]["id"] = "hwpx-mcp-release-smoke-rebuild"
rebuild_package["build_attestation"].pop("verification", None)
sign_record(rebuild_package["build_attestation"], build_b, "build-b")

obs_common = {
    "semantic_sha256": "a" * 64,
    "mutation_footprint_sha256": "b" * 64,
    "revision_delta": 0,
    "package_part_sha256": "c" * 64,
    "render_observable_sha256": "d" * 64,
}
observations = [
    {
        "host_id": "release-host-a",
        "host_contract_sha256": "e" * 64,
        "receipt_sha256": hashlib.sha256(b"release-host-a").hexdigest(),
        **obs_common,
    },
    {
        "host_id": "release-host-b",
        "host_contract_sha256": "f" * 64,
        "receipt_sha256": hashlib.sha256(b"release-host-b").hexdigest(),
        **obs_common,
    },
]
sign_record(observations[0], host_a, "host-a")
sign_record(observations[1], host_b, "host-b")

certified = certify_extension_package(
    package,
    rebuild_package=rebuild_package,
    trust_policy=trust_policy,
    host_observations=observations,
)
assert certified["certificate"]["status"] == "PASS"
assert certified["rust"]["authority"] == "RUST_CERTIFICATE_SEAL_PASS"
assert certified["derived_evidence"]["authority"] == "P347_DERIVED_CERTIFICATION_EVIDENCE_PASS"
assert certified["derived_evidence"]["provenance_trust"]["independent_builder_roots"] is True
assert certified["derived_evidence"]["host_trust"]["trusted"] is True
assert certified["derived_evidence"]["execution"]["deterministic"] is True
assert all(certified["derived_evidence"]["execution"]["negative_controls"].values())
promotion = validate_rollout_transition("CANARY", "PROMOTED", certified["certificate"])
assert promotion["rust"]["authority"] == "RUST_ROLLOUT_TRANSITION_PASS"

forged = copy.deepcopy(rebuild_package)
forged["build_attestation"]["builder"]["id"] = "forged-builder"
try:
    certify_extension_package(
        package,
        rebuild_package=forged,
        trust_policy=trust_policy,
        host_observations=observations,
    )
except RuntimeError:
    pass
else:
    raise AssertionError("forged builder provenance was accepted")

print("P3.47 release smoke PASS")
