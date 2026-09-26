from __future__ import annotations

import base64
import copy
import hashlib

import pytest

from p346_platform_bridge import (
    codegen,
    execute_wasm,
    inspect_runtime,
    platform_contract,
    project_tools,
    runtime_diagnostics,
    validate_composition,
    validate_extension,
    validate_sequence,
)


def _plan():
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
        "nodes": [
            {"id": "inspect", "deps": [], "effect": "READ_ONLY", "action": "REUSE", "reusable": True},
            {"id": "edit", "deps": ["inspect"], "effect": "DOCUMENT_MUTATION", "action": "EXECUTE"},
            {"id": "render", "deps": ["edit"], "effect": "EXTERNAL_WORLD_CONTACT", "action": "WAIT_EXTERNAL"},
            {"id": "deliver", "deps": ["render"], "effect": "DELIVERY", "action": "EXECUTE"},
        ],
    }


def _manifest(module: bytes) -> dict:
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.46/extension-manifest/v1",
        "extension_id": "pytest.wasm",
        "version": "1.0.0",
        "host_abi": "p3.46-extension-v1",
        "execution": {
            "mode": "WASM_NO_IMPORTS",
            "module_sha256": hashlib.sha256(module).hexdigest(),
            "entrypoint": "p346_run",
            "deterministic": True,
            "max_module_bytes": 1024,
            "timeout_ms": 250,
        },
        "capabilities": [{
            "name": "pytest.pure",
            "version": "1.0.0",
            "effect": "PURE",
            "adapter": "PYTEST_WASM",
            "deterministic": True,
            "evidence": ["PYTEST"],
        }],
        "node_kinds": [],
        "tools": [],
    }


def test_contract_codegen_and_cross_runtime_effect_guard():
    contract = platform_contract()
    assert contract["phase"] == "P3.46"
    assert set(contract["effect_types"]) == {
        "READ_ONLY",
        "PURE",
        "DOCUMENT_MUTATION",
        "RUNTIME_CONFIGURATION",
        "EXTERNAL_WORLD_CONTACT",
        "DELIVERY",
    }
    surface = project_tools()
    assert surface["phase"] == "P3.46"
    inspector = next(row for row in surface["tools"] if row["name"] == "inspect_document_runtime")
    assert inspector["effect"] == "READ_ONLY"
    swap = next(row for row in surface["tools"] if row["name"] == "hot_swap_document_host_adapter_profile")
    assert swap["effect"] == "RUNTIME_CONFIGURATION"
    validated = validate_composition(_plan())
    assert validated["typescript"]["topological_order"] == ["inspect", "edit", "render", "deliver"]
    assert validated["rust"]["authority"] == "RUST_EFFECT_PLAN_INVARIANT_PASS"
    assert validate_sequence(["READ_ONLY", "DOCUMENT_MUTATION", "DELIVERY"])["rust"]["ok"] is True
    generated = codegen()
    assert generated["generated_sha256"]
    assert generated["tool_surface"]["surface_sha256"] == surface["surface_sha256"]


def test_effect_negative_controls_fail_closed():
    delivery_parent = _plan()
    delivery_parent["nodes"].append(
        {"id": "late", "deps": ["deliver"], "effect": "PURE", "action": "EXECUTE"}
    )
    with pytest.raises(RuntimeError):
        validate_composition(delivery_parent)

    reusable_mutation = {
        "schema": "chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
        "nodes": [{
            "id": "bad",
            "effect": "DOCUMENT_MUTATION",
            "action": "REUSE",
            "reusable": True,
        }],
    }
    with pytest.raises(RuntimeError):
        validate_composition(reusable_mutation)
    with pytest.raises(RuntimeError):
        validate_sequence(["DELIVERY", "READ_ONLY"])


def test_pure_wasm_executes_and_imported_wasm_is_denied():
    valid = bytes.fromhex(
        "0061736d01000000"
        "0105016000017f"
        "03020100"
        "070c0108703334365f72756e0000"
        "0a06010400412a0b"
    )
    manifest = _manifest(valid)
    checked = validate_extension(manifest)
    assert checked["execution"]["mode"] == "WASM_NO_IMPORTS"
    receipt = execute_wasm(manifest, base64.b64encode(valid).decode("ascii"))
    assert receipt["result"] == 42
    assert receipt["sandbox"]["no_imports"] is True
    assert receipt["sandbox"]["host_functions"] == 0

    imported = bytes.fromhex(
        "0061736d01000000"
        "0105016000017f"
        "020701017801660000"
        "070c0108703334365f72756e0000"
    )
    with pytest.raises(RuntimeError, match="denies all WASM imports"):
        execute_wasm(_manifest(imported), base64.b64encode(imported).decode("ascii"))


def test_executable_extension_cannot_claim_mutation_effect():
    valid = bytes.fromhex(
        "0061736d01000000"
        "0105016000017f"
        "03020100"
        "070c0108703334365f72756e0000"
        "0a0601040041010b"
    )
    manifest = _manifest(valid)
    manifest["capabilities"][0]["effect"] = "DOCUMENT_MUTATION"
    with pytest.raises(RuntimeError, match="PURE-only"):
        validate_extension(manifest)


def test_inspector_and_diagnostics_are_read_only():
    state = {
        "schema": "chatgpt-web-hwpx-mcp/p3.45/runtime-run/v1",
        "run_id": "inspect-fixture",
        "status": "RUNNING",
        "base_revision": 4,
        "current_revision": 4,
        "run_sha256": "a" * 64,
        "head_event_hash": "",
        "compiled": {
            "ir": {
                "nodes": [{
                    "id": "snapshot",
                    "kind": "document.snapshot",
                    "deps": [],
                }]
            },
            "topological_order": ["snapshot"],
            "side_effects": {"snapshot": "PURE"},
            "actions": {"snapshot": "REUSE"},
            "affected_nodes": [],
            "reused_nodes": ["snapshot"],
            "node_spec_sha256": {"snapshot": "b" * 64},
            "provider_binding_sha256": {"snapshot": "c" * 64},
            "provider_bindings": {
                "snapshot": {
                    "adapter": "DOCUMENT_SNAPSHOT",
                    "primary": {
                        "provider_id": "hwpx-mcp-core",
                        "provider_version": "p3.45",
                    },
                }
            },
        },
        "node_states": {"snapshot": "REUSED"},
        "outputs": {
            "snapshot": {
                "output_sha256": "d" * 64,
                "receipt_sha256": "e" * 64,
            }
        },
        "events": [],
    }
    before = copy.deepcopy(state)
    view = inspect_runtime(state)
    diagnostics = runtime_diagnostics(state)
    assert state == before
    assert view["dag"]["nodes"][0]["provider_id"] == "hwpx-mcp-core"
    assert view["cache"]["reused_nodes"] == ["snapshot"]
    assert diagnostics["ok"] is True
    assert diagnostics["summary"]["errors"] == 0
