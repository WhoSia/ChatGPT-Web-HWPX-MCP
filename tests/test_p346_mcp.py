from __future__ import annotations

import pytest

import p346_mcp
from p345_runtime_bridge import host_receipt_sha256
from p346_mcp import AdapterRegistry, register_p346_tools


class _MCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, annotations=None):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


class _Core:
    def __init__(self):
        self.mcp = _MCP()


def _readonly(**kwargs):
    return {
        "revision_after": int(kwargs["current_revision"]),
        "output_sha256": "a" * 64,
    }


def _mutation(**kwargs):
    return {
        "revision_after": int(kwargs["current_revision"]) + 1,
        "output_sha256": "b" * 64,
    }


def test_hot_swap_registry_cas_guard_and_rollback():
    registry = AdapterRegistry({
        "DOCUMENT_SNAPSHOT": _readonly,
        "DOCUMENT_TEXT_EDIT": _mutation,
    })
    snap = registry.snapshot("doc-a")
    assert snap["active_profile"] == "p3.46-guarded"
    assert len(snap["active_contract_sha256"]) == 64
    assert len(snap["profiles"]["p3.46-guarded"]["contract_sha256"]) == 64
    assert registry.resolve("DOCUMENT_SNAPSHOT", document_id="doc-a")(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )["revision_after"] == 3
    mutation = registry.resolve("DOCUMENT_TEXT_EDIT", document_id="doc-a")(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert mutation["revision_after"] == 4
    assert mutation["p346_adapter_profile"] == "p3.46-guarded"

    swapped = registry.swap(
        "p3.45-compat",
        snap["generation"],
        document_id="doc-a",
    )
    assert swapped["swapped"] is True
    assert swapped["active_profile"] == "p3.45-compat"
    assert registry.snapshot("doc-b")["active_profile"] == "p3.46-guarded"
    assert registry.snapshot("doc-b")["generation"] == 1
    with pytest.raises(RuntimeError, match="generation CAS"):
        registry.swap(
            "p3.46-guarded",
            snap["generation"],
            document_id="doc-a",
        )

    rolled = registry.rollback(
        swapped["generation"],
        document_id="doc-a",
    )
    assert rolled["rolled_back_to"] == "p3.46-guarded"
    assert rolled["active_profile"] == "p3.46-guarded"


def test_guard_rejects_revision_contract_violation():
    def bad(**kwargs):
        return {"revision_after": int(kwargs["current_revision"]) + 2}

    registry = AdapterRegistry({"DOCUMENT_TEXT_EDIT": bad})
    with pytest.raises(RuntimeError, match="revision contract failed"):
        registry.resolve("DOCUMENT_TEXT_EDIT", document_id="doc-a")(
            document_id="d",
            current_revision=7,
            inputs={},
            lease_token="",
        )


def test_arbitrary_profile_registration_is_not_exposed():
    registry = AdapterRegistry({"DOCUMENT_SNAPSHOT": _readonly})
    with pytest.raises(ValueError, match="not pre-admitted"):
        registry.swap(
            "uploaded-python-code",
            registry.snapshot("doc-a")["generation"],
            document_id="doc-a",
        )


def test_run_local_binding_survives_document_swap_and_restart_hint():
    registry = AdapterRegistry({
        "DOCUMENT_SNAPSHOT": _readonly,
    })
    first = registry.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-1",
    )
    first_receipt = first(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert first_receipt["p346_adapter_profile"] == "p3.46-guarded"
    assert first_receipt["p346_adapter_generation"] == 1
    assert len(first_receipt["p346_adapter_contract_sha256"]) == 64

    snap = registry.snapshot("doc-a")
    registry.swap(
        "p3.45-compat",
        snap["generation"],
        document_id="doc-a",
    )

    same_run = registry.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-1",
    )
    same_receipt = same_run(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert same_receipt["p346_adapter_profile"] == "p3.46-guarded"
    assert same_receipt["p346_adapter_generation"] == 1
    assert (
        same_receipt["p346_adapter_contract_sha256"]
        == first_receipt["p346_adapter_contract_sha256"]
    )

    next_run = registry.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-2",
    )
    next_receipt = next_run(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert next_receipt["p346_adapter_profile"] == "p3.45-compat"
    assert next_receipt["p346_adapter_generation"] == 2

    restarted = AdapterRegistry({"DOCUMENT_SNAPSHOT": _readonly})
    recovered = restarted.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-2",
        pinned_profile="p3.45-compat",
        pinned_generation=2,
        pinned_contract_sha256=next_receipt[
            "p346_adapter_contract_sha256"
        ],
    )
    recovered_receipt = recovered(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert recovered_receipt["p346_adapter_profile"] == "p3.45-compat"
    assert recovered_receipt["p346_adapter_generation"] == 2
    assert (
        recovered_receipt["p346_adapter_contract_sha256"]
        == next_receipt["p346_adapter_contract_sha256"]
    )

    with pytest.raises(RuntimeError, match="profile contract drift"):
        restarted.resolve(
            "DOCUMENT_SNAPSHOT",
            document_id="doc-a",
            run_id="run-contract-drift",
            pinned_profile="p3.45-compat",
            pinned_generation=2,
            pinned_contract_sha256="0" * 64,
        )

def test_inspector_surfaces_orphan_host_receipt_sidecar(monkeypatch):
    names = {
        "get_developer_platform_contract",
        "project_document_tool_surface",
        "validate_document_effect_composition",
        "validate_document_tool_sequence",
        "validate_projected_document_tool_plan",
        "validate_projected_document_tool_sequence",
        "inspect_document_runtime",
        "get_document_runtime_diagnostics",
        "get_host_adapter_registry",
        "hot_swap_document_host_adapter_profile",
        "rollback_document_host_adapter_profile",
        "validate_sandboxed_document_extension",
        "execute_sandboxed_document_extension_probe",
        "generate_document_platform_contracts",
    }
    monkeypatch.setattr(
        p346_mcp,
        "project_tools",
        lambda extensions=None: {
            "tools": [{"name": name} for name in sorted(names)],
            "surface_sha256": "s" * 64,
        },
    )
    monkeypatch.setattr(p346_mcp, "platform_contract", lambda: {"phase": "P3.46"})
    monkeypatch.setattr(p346_mcp, "verify_replay", lambda state: {"ok": True})
    monkeypatch.setattr(
        p346_mcp,
        "inspect_runtime",
        lambda state: {
            "schema": "chatgpt-web-hwpx-mcp/p3.46/runtime-inspector/v1",
            "phase": "P3.46",
            "run": {"run_id": state["run_id"]},
        },
    )

    state = {
        "run_id": "run-orphan",
        "compiled": {"topological_order": ["snapshot"]},
        "outputs": {
            "snapshot": {
                "output_sha256": "a" * 64,
                "receipt_sha256": "b" * 64,
            }
        },
    }
    orphan = {
        "node_id": "orphan",
        "adapter": "DOCUMENT_SNAPSHOT",
        "adapter_profile": "p3.46-guarded",
        "adapter_generation": 1,
        "adapter_contract_sha256": "c" * 64,
        "revision_before": 1,
        "revision_after": 1,
        "output_sha256": "a" * 64,
        "receipt_sha256": "b" * 64,
    }
    orphan["provenance_sha256"] = host_receipt_sha256(orphan)
    metadata = {
        "revision": 1,
        "p345_transaction_runs": {"run-orphan": state},
        "p346_runtime_host_receipts": {
            "run-orphan": {"orphan": orphan}
        },
    }

    core = _Core()
    register_p346_tools(
        core,
        lambda document_id: (metadata, None),
        AdapterRegistry({"DOCUMENT_SNAPSHOT": _readonly}),
    )
    inspected = core.mcp.tools["inspect_document_runtime"](
        "doc",
        "run-orphan",
    )
    assert inspected["ok"] is False
    assert any(
        row.get("code") == "HOST_RECEIPT_UNKNOWN_NODE"
        for row in inspected["host_execution_receipt_diagnostics"]
    )

