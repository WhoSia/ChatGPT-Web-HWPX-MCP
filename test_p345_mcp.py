from __future__ import annotations

from pathlib import Path

import pytest

from p345_mcp import register_p345_tools


class _MCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


class _Store:
    def __init__(self, core):
        self.core = core
        self.leases = {}

    def acquire_lease(self, document_id, holder_id, expected_revision, lease_token, ttl_seconds):
        assert int(expected_revision) == int(self.core.meta["revision"])
        self.leases[document_id] = lease_token
        return {"ok": True}

    def release_lease(self, document_id, lease_token):
        self.leases.pop(document_id, None)
        return {"ok": True}

    def load_revision(self, document_id, revision):
        return {
            "owner_subject": "user",
            "revision": int(revision),
            "sha256": ("%064x" % int(revision))[-64:],
        }


class _Core:
    def __init__(self):
        self.mcp = _MCP()
        self.meta = {"revision": 1, "owner_subject": "user"}
        self.DOCUMENT_STORE = _Store(self)

    def _caller_subject(self):
        return "user"

    def _load_metadata(self, document_id):
        return dict(self.meta)

    def _write_metadata(self, document_id, metadata):
        self.meta = dict(metadata)

    def _require_owner(self, metadata):
        assert metadata["owner_subject"] == "user"

    def _utc_iso(self):
        return "2026-09-26T00:00:00Z"


def _ir(base_revision=1, ir_id="runtime"):
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1",
        "ir_id": ir_id,
        "document_id": "doc",
        "base_revision": base_revision,
        "nodes": [
            {"id": "snapshot", "kind": "document.snapshot", "inputs": {"view": "document"}, "reusable": True},
            {"id": "edit", "kind": "document.text.edit", "deps": ["snapshot"], "inputs": {"operations": [{"op": "fixture"}]}},
            {"id": "render", "kind": "document.render.evidence", "deps": ["edit"], "inputs": {"renderer": "HANCOM"}},
        ],
        "outputs": ["render"],
    }


def test_transaction_runtime_executes_waits_replays_and_aborts():
    core = _Core()

    def owned(document_id):
        return dict(core.meta), Path("/tmp/unused.hwpx")

    def snapshot(**kwargs):
        return {
            "revision_after": kwargs["current_revision"],
            "output_sha256": "a" * 64,
            "receipt_sha256": "1" * 64,
        }

    def text(**kwargs):
        core.meta["revision"] = int(kwargs["current_revision"]) + 1
        return {
            "revision_after": core.meta["revision"],
            "output_sha256": "b" * 64,
            "receipt_sha256": "2" * 64,
        }

    register_p345_tools(
        core,
        owned,
        {"DOCUMENT_SNAPSHOT": snapshot, "DOCUMENT_TEXT_EDIT": text},
    )
    tools = core.mcp.tools

    first = tools["compile_document_transaction"]("doc", _ir())
    again = tools["compile_document_transaction"]("doc", _ir())
    assert again["run_id"] == first["run_id"]
    assert again["idempotent_existing_run"] is True

    advanced = tools["advance_document_transaction"]("doc", first["run_id"])
    assert advanced["status"] == "WAIT_EXTERNAL"
    assert advanced["revision"] == 2

    with pytest.raises(ValueError, match="external evidence revision is stale"):
        tools["resolve_document_transaction_external"](
            "doc",
            first["run_id"],
            "render",
            {"revision": 1, "world_contact_valid": True},
        )

    resolved = tools["resolve_document_transaction_external"](
        "doc",
        first["run_id"],
        "render",
        {
            "schema": "fixture/native-render/v1",
            "document_id": "doc",
            "revision": 2,
            "world_contact_valid": True,
            "renderer": "HANCOM",
        },
    )
    assert resolved["status"] == "RUNNING"

    done = tools["advance_document_transaction"]("doc", first["run_id"])
    assert done["status"] == "COMPLETED"
    replay = tools["replay_document_transaction"]("doc", first["run_id"])
    assert replay["replay"]["completed"] is True
    assert replay["durable_revision"]["available"] is True
    obs = tools["get_document_transaction_observability"]("doc", first["run_id"])
    assert obs["event_counts"]["RUN_COMPLETED"] == 1

    second = tools["compile_document_transaction"](
        "doc", _ir(2, "runtime-next"), prior_run_id=first["run_id"]
    )
    assert second["actions"]["snapshot"] == "EXECUTE"
    aborted = tools["abort_document_transaction"]("doc", second["run_id"], "test.cancelled")
    assert aborted["status"] == "ABORTED"
    with pytest.raises(RuntimeError, match="terminal/non-runnable"):
        tools["advance_document_transaction"]("doc", second["run_id"])


def test_manifest_only_extension_provider_uses_admitted_adapter():
    core = _Core()

    def owned(document_id):
        return dict(core.meta), Path("/tmp/unused.hwpx")

    register_p345_tools(
        core,
        owned,
        {
            "DOCUMENT_SNAPSHOT": lambda **kwargs: {
                "revision_after": 1,
                "output_sha256": "a" * 64,
                "receipt_sha256": "1" * 64,
            }
        },
    )
    tools = core.mcp.tools
    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p3.45/extension-manifest/v1",
        "extension_id": "fixture-ext",
        "version": "1.0.0",
        "host_abi": "p3.45-extension-v1",
        "deterministic": True,
        "node_kinds": [
            {
                "kind": "document.snapshot.alias",
                "capability": "document.inspect",
                "adapter": "DOCUMENT_SNAPSHOT",
                "side_effect": "PURE",
                "reusable": True,
                "capability_version": "1.0.0",
                "evidence": ["STRUCTURAL_NATIVE_FACT"],
            }
        ],
    }
    checked = tools["validate_document_runtime_extension"](manifest)
    assert checked["extension"]["manifest_sha256"]

    ir = {
        "schema": "chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1",
        "ir_id": "extension-runtime",
        "document_id": "doc",
        "base_revision": 1,
        "nodes": [
            {
                "id": "ext",
                "kind": "document.snapshot.alias",
                "inputs": {"view": "document"},
                "reusable": True,
            }
        ],
    }
    compiled = tools["compile_document_transaction"]("doc", ir, extensions=[manifest])
    assert (
        compiled["provider_bindings"]["ext"]["primary"]["provider_id"]
        == "extension:fixture-ext"
    )


def test_p346_host_receipt_sidecar_preserves_p345_replay_state():
    core = _Core()

    def owned(document_id):
        return dict(core.meta), Path("/tmp/unused.hwpx")

    def snapshot(**kwargs):
        return {
            "revision_after": kwargs["current_revision"],
            "output_sha256": "a" * 64,
            "receipt_sha256": "1" * 64,
        }

    def text(**kwargs):
        core.meta["revision"] = int(kwargs["current_revision"]) + 1
        return {
            "revision_after": core.meta["revision"],
            "output_sha256": "b" * 64,
            "receipt_sha256": "2" * 64,
        }

    adapters = {
        "DOCUMENT_SNAPSHOT": snapshot,
        "DOCUMENT_TEXT_EDIT": text,
    }

    def resolver(
        adapter_name,
        *,
        document_id="",
        run_id="",
        pinned_profile="",
        pinned_generation=None,
        pinned_contract_sha256="",
    ):
        assert document_id == "doc"
        assert run_id
        profile = pinned_profile or "p3.46-guarded"
        generation = int(pinned_generation or 1)
        contract_sha256 = pinned_contract_sha256 or ("c" * 64)
        fn = adapters[adapter_name]

        def invoke(**kwargs):
            result = dict(fn(**kwargs))
            result.update({
                "p346_adapter_profile": profile,
                "p346_adapter_generation": generation,
                "p346_adapter_contract_sha256": contract_sha256,
                "p346_adapter_name": adapter_name,
            })
            return result

        return invoke

    register_p345_tools(
        core,
        owned,
        adapters,
        adapter_resolver=resolver,
    )
    tools = core.mcp.tools
    compiled = tools["compile_document_transaction"]("doc", _ir())
    advanced = tools["advance_document_transaction"]("doc", compiled["run_id"])
    assert advanced["status"] == "WAIT_EXTERNAL"

    stored = core.meta["p345_transaction_runs"][compiled["run_id"]]
    replayed = tools["get_document_transaction_run"](
        "doc",
        compiled["run_id"],
    )
    assert replayed["replay"]["ok"] is True
    assert replayed["run"]["run_sha256"] == stored["run_sha256"]

    sidecar = core.meta["p346_runtime_host_receipts"][compiled["run_id"]]
    assert set(sidecar) == {"snapshot", "edit"}
    assert sidecar["snapshot"]["adapter_profile"] == "p3.46-guarded"
    assert sidecar["snapshot"]["adapter_generation"] == 1
    assert sidecar["snapshot"]["adapter_contract_sha256"] == "c" * 64
    assert sidecar["edit"]["receipt_sha256"] == "2" * 64
    assert len(sidecar["snapshot"]["provenance_sha256"]) == 64


def test_tampered_p346_sidecar_fails_before_next_host_execution():
    core = _Core()
    calls = {"snapshot": 0, "text": 0}

    def owned(document_id):
        return dict(core.meta), Path("/tmp/unused.hwpx")

    def snapshot(**kwargs):
        calls["snapshot"] += 1
        return {
            "revision_after": kwargs["current_revision"],
            "output_sha256": "a" * 64,
            "receipt_sha256": "1" * 64,
        }

    def text(**kwargs):
        calls["text"] += 1
        core.meta["revision"] = int(kwargs["current_revision"]) + 1
        return {
            "revision_after": core.meta["revision"],
            "output_sha256": "b" * 64,
            "receipt_sha256": "2" * 64,
        }

    adapters = {
        "DOCUMENT_SNAPSHOT": snapshot,
        "DOCUMENT_TEXT_EDIT": text,
    }

    def resolver(
        adapter_name,
        *,
        document_id="",
        run_id="",
        pinned_profile="",
        pinned_generation=None,
        pinned_contract_sha256="",
    ):
        fn = adapters[adapter_name]
        profile = pinned_profile or "p3.46-guarded"
        generation = int(pinned_generation or 1)
        contract_sha256 = pinned_contract_sha256 or ("c" * 64)

        def invoke(**kwargs):
            result = dict(fn(**kwargs))
            result.update({
                "p346_adapter_profile": profile,
                "p346_adapter_generation": generation,
                "p346_adapter_contract_sha256": contract_sha256,
                "p346_adapter_name": adapter_name,
            })
            return result

        return invoke

    register_p345_tools(
        core,
        owned,
        adapters,
        adapter_resolver=resolver,
    )
    tools = core.mcp.tools
    compiled = tools["compile_document_transaction"]("doc", _ir())

    first = tools["advance_document_transaction"](
        "doc",
        compiled["run_id"],
        max_nodes=1,
    )
    assert first["status"] == "RUNNING"
    assert calls == {"snapshot": 1, "text": 0}

    row = core.meta["p346_runtime_host_receipts"][compiled["run_id"]]["snapshot"]
    row["adapter_profile"] = "p3.45-compat"

    with pytest.raises(RuntimeError, match="provenance seal mismatch"):
        tools["advance_document_transaction"]("doc", compiled["run_id"])
    assert calls == {"snapshot": 1, "text": 0}
