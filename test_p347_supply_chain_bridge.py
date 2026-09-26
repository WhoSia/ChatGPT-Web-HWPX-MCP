from __future__ import annotations

import base64
import copy
import hashlib

import pytest

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
        "capabilities": [
            {
                "name": "pytest.extension.pure",
                "version": version,
                "effect": effect,
                "adapter": "PYTEST_WASM",
                "deterministic": True,
                "evidence": ["PYTEST"],
            }
        ],
        "node_kinds": [],
        "tools": [
            {
                "name": "pytest_extension_tool",
                "capability": "pytest.extension.pure",
                "effect": effect,
                "description": "test tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": False,
                },
            }
        ],
    }


def _package(
    module: bytes | None = None,
    version: str = "1.0.0",
    builder_id: str = "github-actions/pytest-primary",
) -> dict:
    module = module or _wasm()
    manifest = _manifest(module, version)
    manifest_sha = validate_extension(manifest)["manifest_sha256"]
    module_sha = hashlib.sha256(module).hexdigest()
    source_sha = hashlib.sha256(b"source-tree").hexdigest()
    return {
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


def _obs(host: str, seed: str = "a", contract_seed: str = "e") -> dict:
    digest = seed * 64
    return {
        "host_id": host,
        "host_contract_sha256": contract_seed * 64,
        "receipt_sha256": hashlib.sha256(host.encode()).hexdigest(),
        "semantic_sha256": digest,
        "mutation_footprint_sha256": "b" * 64,
        "revision_delta": 0,
        "package_part_sha256": "c" * 64,
        "render_observable_sha256": "d" * 64,
    }



def test_content_addressed_package_dependency_closure_and_reproducibility():
    package = _package()
    normalized = normalize_extension_package(package)
    assert normalized["package_id"].startswith("sha256:")
    assert len(normalized["artifact_sha256"]) == 64
    closure = verify_dependency_closure(package)
    assert closure["package_count"] == 1
    assert closure["root_package_id"] == normalized["package_id"]

    second = copy.deepcopy(package)
    second["build_attestation"]["builder"]["id"] = "github-actions/pytest-rebuild"
    reproducible = compare_reproducible_builds(package, second)
    assert reproducible["reproducible"] is True
    assert reproducible["same_artifact"] is True

    changed = _package(_wasm(7))
    different = compare_reproducible_builds(package, changed)
    assert different["reproducible"] is False
    assert different["same_artifact"] is False


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
    replay_break = solve_package_compatibility(current, broken)
    assert replay_break["typescript"]["verdict"] == "REPLAY_BREAKING"
    assert replay_break["rust"]["replay_admissible"] is False


def test_host_conformance_certificate_seal_and_rollout_cross_runtime():
    conformance = compare_host_conformance([
        _obs("python-host", contract_seed="e"),
        _obs("shadow-host", contract_seed="f"),
    ])
    assert conformance["verdict"] == "PASS"
    divergent = _obs("bad-host", "f")
    mismatch = compare_host_conformance([
        _obs("python-host", contract_seed="e"),
        {**divergent, "host_contract_sha256": "9" * 64},
    ])
    assert mismatch["verdict"] == "DIVERGENT"

    package = _package()
    rebuild = copy.deepcopy(package)
    rebuild["build_attestation"]["builder"]["id"] = "github-actions/pytest-rebuild"
    result = certify_extension_package(
        package,
        rebuild_package=rebuild,
        host_observations=[
            _obs("python-host", contract_seed="e"),
            _obs("shadow-host", contract_seed="f"),
        ],
    )
    certificate = result["certificate"]
    assert certificate["status"] == "PASS"
    assert result["rust"]["authority"] == "RUST_CERTIFICATE_SEAL_PASS"
    verified = verify_certificate(certificate)
    assert verified["typescript"]["ok"] is True
    assert verified["rust"]["ok"] is True

    transition = validate_rollout_transition("CANARY", "PROMOTED", certificate)
    assert transition["typescript"]["authority"] == "ROLLOUT_TRANSITION_GOVERNANCE_PASS"
    assert transition["rust"]["authority"] == "RUST_ROLLOUT_TRANSITION_PASS"

    tampered = copy.deepcopy(certificate)
    tampered["artifact_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="seal"):
        verify_certificate(tampered)


def test_certification_fails_closed_without_independent_rebuild():
    package = _package()
    same_builder = copy.deepcopy(package)
    result = certify_extension_package(
        package,
        rebuild_package=same_builder,
        host_observations=[
            _obs("python-host", contract_seed="e"),
            _obs("shadow-host", contract_seed="f"),
        ],
    )
    assert result["derived_evidence"]["reproducibility"]["independent_builder"] is False
    assert result["certificate"]["status"] == "FAIL"
    assert result["rust"]["ok"] is False
