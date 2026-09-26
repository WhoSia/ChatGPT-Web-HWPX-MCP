from __future__ import annotations

import base64
import hashlib

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

gates = contract["certification"]["required_gates"]
evidence = [
    {"gate": gate, "status": "PASS", "evidence_sha256": hashlib.sha256(gate.encode()).hexdigest()}
    for gate in gates
]
obs = {
    "semantic_sha256": "a" * 64,
    "mutation_footprint_sha256": "b" * 64,
    "revision_delta": 0,
    "package_part_sha256": "c" * 64,
    "render_observable_sha256": "d" * 64,
}
certified = certify_extension_package(
    package,
    evidence=evidence,
    host_observations=[
        {"host_id": "release-host-a", **obs},
        {"host_id": "release-host-b", **obs},
    ],
)
assert certified["certificate"]["status"] == "PASS"
assert certified["rust"]["authority"] == "RUST_CERTIFICATE_SEAL_PASS"
promotion = validate_rollout_transition("CANARY", "PROMOTED", certified["certificate"])
assert promotion["rust"]["authority"] == "RUST_ROLLOUT_TRANSITION_PASS"
print("P3.47 release smoke PASS")
