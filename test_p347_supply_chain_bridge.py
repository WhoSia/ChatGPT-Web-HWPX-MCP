from __future__ import annotations

import base64
import copy
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from p346_platform_bridge import validate_extension
from p347_supply_chain_bridge import (
    certify_extension_package,
    compare_host_conformance,
    compare_reproducible_builds,
    normalize_extension_package,
    solve_package_compatibility,
    validate_rollout_transition,
    verify_certificate,
    verify_dependency_closure,
)


BUILD_A = Ed25519PrivateKey.generate()
BUILD_B = Ed25519PrivateKey.generate()
HOST_A = Ed25519PrivateKey.generate()
HOST_B = Ed25519PrivateKey.generate()


def _stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pem(key):
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


TRUST_POLICY = {
    "schema": "chatgpt-web-hwpx-mcp/p3.47/trust-policy/v1",
    "builders": [
        {"builder_id": "github-actions/pytest-primary", "key_id": "build-a", "public_key_pem": _pem(BUILD_A)},
        {"builder_id": "github-actions/pytest-rebuild", "key_id": "build-b", "public_key_pem": _pem(BUILD_B)},
    ],
    "hosts": [
        {"host_id": "python-host", "host_contract_sha256": "e" * 64, "key_id": "host-a", "public_key_pem": _pem(HOST_A)},
        {"host_id": "shadow-host", "host_contract_sha256": "f" * 64, "key_id": "host-b", "public_key_pem": _pem(HOST_B)},
    ],
}


def _sign(record, key, key_id):
    body = copy.deepcopy(record)
    body.pop("verification", None)
    record["verification"] = {
        "algorithm": "ed25519",
        "key_id": key_id,
        "signature_base64": base64.b64encode(key.sign(_stable(body).encode())).decode(),
    }


def _wasm(value: int = 42) -> bytes:
    if value < 0 or value > 63:
        raise ValueError("fixture only supports small i32 constants")
    return bytes.fromhex(
        "0061736d01000000"
        "0105016000017f"
        "03020100"
        "070c0108703334365f72756e0000"
        f"0a0601040041{value:02x}0b"
    )


def _manifest(module: bytes, version: str = "1.0.0", effect: str = "PURE") -> dict:
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.46/extension-manifest/v1",
        "extension_id": "pytest.extension",
        "version": version,
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
            "name": "pytest.extension.pure",
            "version": version,
            "effect": effect,
            "adapter": "PYTEST_WASM",
            "deterministic": True,
            "evidence": ["PYTEST"],
        }],
        "node_kinds": [],
        "tools": [{
            "name": "pytest_extension_tool",
            "capability": "pytest.extension.pure",
            "effect": effect,
            "description": "test tool",
            "input_schema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "additionalProperties": False,
            },
        }],
    }


def _package(
    module: bytes | None = None,
    version: str = "1.0.0",
    builder_id: str = "github-actions/pytest-primary",
    key=BUILD_A,
    key_id: str = "build-a",
) -> dict:
    module = module or _wasm()
    manifest = _manifest(module, version)
    manifest_sha = validate_extension(manifest)["manifest_sha256"]
    module_sha = hashlib.sha256(module).hexdigest()
    source_sha = hashlib.sha256(b"source-tree").hexdigest()
    package = {
        "schema": "chatgpt-web-hwpx-mcp/p3.47/extension-package/v1",
        "extension": manifest,
        "module_base64": base64.b64encode(module).decode("ascii"),
        "dependencies": [],
        "build_attestation": {
            "schema": "chatgpt-web-hwpx-mcp/p3.47/build-attestation/v1",
            "predicate_type": "https://slsa.dev/provenance/v1",
            "builder": {"id": builder_id},
            "build_type": "deterministic-wasm",
            "source": {
                "uri": "git+https://example.invalid/extension",
                "revision": "deadbeef",
                "sha256": source_sha,
            },
            "invocation": {"parameters": {"opt": "deterministic"}},
            "materials": [{"uri": "source-tree", "sha256": source_sha}],
            "subjects": [
                {"name": "extension-manifest.json", "sha256": manifest_sha},
                {"name": "module.wasm", "sha256": module_sha},
            ],
            "reproducible": True,
        },
    }
    _sign(package["build_attestation"], key, key_id)
    return package


def _rebuild(package):
    out = copy.deepcopy(package)
    out["build_attestation"]["builder"]["id"] = "github-actions/pytest-rebuild"
    out["build_attestation"].pop("verification", None)
    _sign(out["build_attestation"], BUILD_B, "build-b")
    return out


def _obs(host: str) -> dict:
    contract, key, key_id = (
        ("e" * 64, HOST_A, "host-a")
        if host == "python-host"
        else ("f" * 64, HOST_B, "host-b")
    )
    row = {
        "host_id": host,
        "host_contract_sha256": contract,
        "receipt_sha256": hashlib.sha256(host.encode()).hexdigest(),
        "semantic_sha256": "a" * 64,
        "mutation_footprint_sha256": "b" * 64,
        "revision_delta": 0,
        "package_part_sha256": "c" * 64,
        "render_observable_sha256": "d" * 64,
    }
    _sign(row, key, key_id)
    return row


def test_content_addressed_package_dependency_closure_and_reproducibility():
    package = _package()
    normalized = normalize_extension_package(package)
    assert normalized["package_id"].startswith("sha256:")
    closure = verify_dependency_closure(package)
    assert closure["package_count"] == 1
    rebuilt = _rebuild(package)
    reproducible = compare_reproducible_builds(package, rebuilt)
    assert reproducible["reproducible"] is True
    changed = _package(_wasm(7))
    assert compare_reproducible_builds(package, changed)["reproducible"] is False


def test_compatibility_solver_detects_implementation_change_and_schema_break():
    current = _package()
    implementation = _package(_wasm(7))
    migrated = solve_package_compatibility(current, implementation)
    assert migrated["typescript"]["verdict"] == "MIGRATION_REQUIRED"
    assert migrated["rust"]["replay_admissible"] is True

    broken = copy.deepcopy(current)
    broken["extension"]["tools"][0]["input_schema"]["required"] = ["new_required"]
    broken["extension"]["tools"][0]["input_schema"]["properties"]["new_required"] = {"type": "string"}
    checked = validate_extension(broken["extension"])
    broken["build_attestation"]["subjects"][0]["sha256"] = checked["manifest_sha256"]
    broken["build_attestation"].pop("verification", None)
    _sign(broken["build_attestation"], BUILD_A, "build-a")
    replay_break = solve_package_compatibility(current, broken)
    assert replay_break["typescript"]["verdict"] == "REPLAY_BREAKING"
    assert replay_break["rust"]["replay_admissible"] is False


def test_signed_provenance_and_host_evidence_are_required_for_certification():
    package = _package()
    result = certify_extension_package(
        package,
        rebuild_package=_rebuild(package),
        trust_policy=TRUST_POLICY,
        host_observations=[_obs("python-host"), _obs("shadow-host")],
    )
    certificate = result["certificate"]
    assert certificate["status"] == "PASS"
    assert result["derived_evidence"]["provenance_trust"]["independent_builder_roots"] is True
    assert result["derived_evidence"]["host_trust"]["trusted"] is True
    assert result["rust"]["authority"] == "RUST_CERTIFICATE_SEAL_PASS"
    assert verify_certificate(certificate)["rust"]["ok"] is True
    assert validate_rollout_transition("CANARY", "PROMOTED", certificate)["rust"]["authority"] == "RUST_ROLLOUT_TRANSITION_PASS"

    forged_builder = _rebuild(package)
    forged_builder["build_attestation"]["builder"]["id"] = "forged-builder"
    with pytest.raises(RuntimeError, match="not trusted|signature"):
        certify_extension_package(
            package,
            rebuild_package=forged_builder,
            trust_policy=TRUST_POLICY,
            host_observations=[_obs("python-host"), _obs("shadow-host")],
        )

    forged_host = _obs("shadow-host")
    forged_host["semantic_sha256"] = "9" * 64
    with pytest.raises(RuntimeError, match="signature"):
        certify_extension_package(
            package,
            rebuild_package=_rebuild(package),
            trust_policy=TRUST_POLICY,
            host_observations=[_obs("python-host"), forged_host],
        )


def test_certification_fails_closed_without_independent_trusted_builder_root():
    package = _package()
    same_builder = copy.deepcopy(package)
    with pytest.raises(RuntimeError, match="independent trusted builder roots"):
        certify_extension_package(
            package,
            rebuild_package=same_builder,
            trust_policy=TRUST_POLICY,
            host_observations=[_obs("python-host"), _obs("shadow-host")],
        )


def test_raw_host_conformance_remains_descriptive_but_signed_path_is_authoritative():
    a = _obs("python-host")
    b = _obs("shadow-host")
    assert compare_host_conformance([a, b])["verdict"] == "PASS"
    tampered = copy.deepcopy(b)
    tampered["semantic_sha256"] = "f" * 64
    assert compare_host_conformance([a, tampered])["verdict"] == "DIVERGENT"
