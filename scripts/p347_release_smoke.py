from __future__ import annotations

import base64
import copy
import hashlib
import sys
from pathlib import Path

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
contract = supply_chain_contract()
assert contract["phase"] == "P3.47"
assert contract["product"] == "0.24.0-p3.47"
normalized = normalize_extension_package(package)
assert normalized["package_id"].startswith("sha256:")

obs = {
    "semantic_sha256": "a" * 64,
    "mutation_footprint_sha256": "b" * 64,
    "revision_delta": 0,
    "package_part_sha256": "c" * 64,
    "render_observable_sha256": "d" * 64,
}
rebuild_package = copy.deepcopy(package)
rebuild_package["build_attestation"]["builder"]["id"] = "hwpx-mcp-release-smoke-rebuild"
certified = certify_extension_package(
    package,
    rebuild_package=rebuild_package,
    host_observations=[
        {
            "host_id": "release-host-a",
            "host_contract_sha256": "e" * 64,
            "receipt_sha256": hashlib.sha256(b"release-host-a").hexdigest(),
            **obs,
        },
        {
            "host_id": "release-host-b",
            "host_contract_sha256": "f" * 64,
            "receipt_sha256": hashlib.sha256(b"release-host-b").hexdigest(),
            **obs,
        },
    ],
)
assert certified["certificate"]["status"] == "PASS"
assert certified["rust"]["authority"] == "RUST_CERTIFICATE_SEAL_PASS"
assert certified["derived_evidence"]["authority"] == "P347_DERIVED_CERTIFICATION_EVIDENCE_PASS"
assert certified["derived_evidence"]["reproducibility"]["independent_builder"] is True
assert certified["derived_evidence"]["execution"]["deterministic"] is True
assert all(certified["derived_evidence"]["execution"]["negative_controls"].values())
promotion = validate_rollout_transition("CANARY", "PROMOTED", certified["certificate"])
assert promotion["rust"]["authority"] == "RUST_ROLLOUT_TRANSITION_PASS"
print("P3.47 release smoke PASS")
