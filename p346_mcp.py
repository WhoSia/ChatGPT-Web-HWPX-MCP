from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from mcp.types import ToolAnnotations

from p345_runtime_bridge import verify_replay
from p346_platform_bridge import (
    codegen,
    execute_wasm,
    inspect_runtime,
    platform_contract,
    project_tools,
    runtime_diagnostics,
    validate_composition,
    validate_extension,
    validate_projected_tool_plan,
    validate_projected_tool_sequence,
    validate_sequence,
)


@dataclass(frozen=True)
class AdapterProfile:
    profile_id: str
    adapters: Mapping[str, Callable[..., dict]]
    guarded: bool


class AdapterRegistry:
    """Owner-scoped CAS registry over pre-admitted adapters; never loads arbitrary Python code."""

    MUTATING_ADAPTERS = {
        "DOCUMENT_TEXT_EDIT",
        "DOCUMENT_FORMAT_EDIT",
        "DOCUMENT_DESIGN_REPAIR",
    }

    def __init__(self, host_adapters: Mapping[str, Callable[..., dict]]):
        base = dict(host_adapters)
        if not base:
            raise ValueError("P3.46 adapter registry requires at least one host adapter")
        self._lock = threading.RLock()
        self._profiles: dict[str, AdapterProfile] = {
            "p3.45-compat": AdapterProfile("p3.45-compat", base, False),
            "p3.46-guarded": AdapterProfile(
                "p3.46-guarded",
                {name: self._guard(name, fn) for name, fn in base.items()},
                True,
            ),
        }
        self._document_active: dict[str, str] = {}
        self._document_generation: dict[str, int] = {}
        self._document_history: dict[str, list[str]] = {}

    @classmethod
    def _guard(cls, name: str, fn: Callable[..., dict]) -> Callable[..., dict]:
        mutation = name in cls.MUTATING_ADAPTERS

        def invoke(**kwargs):
            before = int(kwargs.get("current_revision") or 0)
            result = fn(**kwargs)
            if not isinstance(result, dict):
                raise RuntimeError("P3.46 host adapter must return a dict receipt")
            after = int(result.get("revision_after", before))
            expected = before + 1 if mutation else before
            if after != expected:
                raise RuntimeError(
                    f"P3.46 guarded adapter revision contract failed for {name}: "
                    f"{after} != {expected}"
                )
            out = dict(result)
            out["p346_adapter_profile"] = "p3.46-guarded"
            out["p346_adapter_name"] = name
            return out

        return invoke

    def _state(self, document_id: str) -> tuple[str, int, list[str]]:
        document_id = str(document_id or "")
        if not document_id:
            return "p3.46-guarded", 1, ["p3.46-guarded"]
        if document_id not in self._document_active:
            self._document_active[document_id] = "p3.46-guarded"
            self._document_generation[document_id] = 1
            self._document_history[document_id] = ["p3.46-guarded"]
        return (
            self._document_active[document_id],
            self._document_generation[document_id],
            self._document_history[document_id],
        )

    def resolve(
        self,
        adapter_name: str,
        *,
        document_id: str = "",
    ) -> Callable[..., dict]:
        with self._lock:
            active, _generation, _history = self._state(document_id)
            fn = self._profiles[active].adapters.get(adapter_name)
            if fn is None:
                raise KeyError(
                    f"P3.46 active adapter profile does not provide {adapter_name}"
                )
            return fn

    def snapshot(self, document_id: str = "") -> dict:
        with self._lock:
            active_id, generation, history = self._state(document_id)
            active = self._profiles[active_id]
            return {
                "phase": "P3.46",
                "document_id": str(document_id or "") or None,
                "generation": generation,
                "active_profile": active_id,
                "active_guarded": active.guarded,
                "default_profile": "p3.46-guarded",
                "adapters": sorted(active.adapters),
                "profiles": {
                    key: {
                        "guarded": value.guarded,
                        "adapters": sorted(value.adapters),
                    }
                    for key, value in sorted(self._profiles.items())
                },
                "history": list(history[-16:]),
                "scope": (
                    "OWNER_SCOPED_DOCUMENT_PRE_ADMITTED_ONLY"
                    if document_id
                    else "CATALOG_DEFAULT_ONLY"
                ),
            }

    def swap(
        self,
        target_profile: str,
        expected_generation: int,
        *,
        document_id: str,
    ) -> dict:
        document_id = str(document_id or "")
        if not document_id:
            raise ValueError("P3.46 adapter swap requires document_id")
        with self._lock:
            active, generation, history = self._state(document_id)
            if int(expected_generation) != generation:
                raise RuntimeError("P3.46 adapter generation CAS mismatch")
            if target_profile not in self._profiles:
                raise ValueError("P3.46 target adapter profile is not pre-admitted")
            previous = active
            changed = target_profile != previous
            if changed:
                self._document_active[document_id] = target_profile
                self._document_generation[document_id] = generation + 1
                history.append(target_profile)
            receipt = self.snapshot(document_id)
            receipt.update(
                {
                    "previous_profile": previous,
                    "swapped": changed,
                    "authority": "OWNER_SCOPED_PRE_ADMITTED_ADAPTER_PROFILE_CAS_SWAP",
                }
            )
            return receipt

    def rollback(self, expected_generation: int, *, document_id: str) -> dict:
        document_id = str(document_id or "")
        if not document_id:
            raise ValueError("P3.46 adapter rollback requires document_id")
        with self._lock:
            current, generation, history = self._state(document_id)
            if int(expected_generation) != generation:
                raise RuntimeError("P3.46 adapter generation CAS mismatch")
            if len(history) < 2:
                raise RuntimeError("P3.46 adapter rollback history is empty")
            previous = history[-2]
            if previous == current:
                raise RuntimeError("P3.46 rollback would be a no-op")
            self._document_active[document_id] = previous
            self._document_generation[document_id] = generation + 1
            history.append(previous)
            receipt = self.snapshot(document_id)
            receipt.update(
                {
                    "previous_profile": current,
                    "rolled_back_to": previous,
                    "authority": "OWNER_SCOPED_PRE_ADMITTED_ADAPTER_PROFILE_SAFE_ROLLBACK",
                }
            )
            return receipt


def register_p346_tools(
    core,
    owned_document: Callable[[str], tuple[dict, Any]],
    adapter_registry: AdapterRegistry,
):
    read_only = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )
    runtime_config = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=False,
    )

    def _load_run(document_id: str, run_id: str) -> tuple[dict, dict]:
        metadata, _ = owned_document(document_id)
        runs = metadata.get("p345_transaction_runs") or {}
        if not isinstance(runs, dict) or run_id not in runs:
            raise FileNotFoundError(
                "P3.46 inspector could not find P3.45 transaction run"
            )
        state = runs[run_id]
        if not isinstance(state, dict):
            raise RuntimeError("P3.46 inspected runtime state is malformed")
        verify_replay(state)
        return metadata, state

    @core.mcp.tool(annotations=read_only)
    def get_developer_platform_contract() -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **platform_contract(),
            "adapter_registry": adapter_registry.snapshot(),
        }

    @core.mcp.tool(annotations=read_only)
    def project_document_tool_surface(
        extensions: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **project_tools(extensions or [])}

    @core.mcp.tool(annotations=read_only)
    def validate_document_effect_composition(plan: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **validate_composition(plan)}

    @core.mcp.tool(annotations=read_only)
    def validate_document_tool_sequence(effects: list[str]) -> dict:
        core._caller_subject()
        return {"ok": True, **validate_sequence(effects)}

    @core.mcp.tool(annotations=read_only)
    def validate_projected_document_tool_plan(
        plan: dict,
        extensions: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **validate_projected_tool_plan(plan, extensions or [])}

    @core.mcp.tool(annotations=read_only)
    def validate_projected_document_tool_sequence(
        tool_names: list[str],
        extensions: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **validate_projected_tool_sequence(tool_names, extensions or []),
        }

    @core.mcp.tool(annotations=read_only)
    def inspect_document_runtime(document_id: str, run_id: str) -> dict:
        metadata, state = _load_run(document_id, run_id)
        inspected = inspect_runtime(state)
        return {
            "ok": True,
            "document_id": document_id,
            "durable_revision": int(metadata["revision"]),
            **inspected,
            "authority": "READ_ONLY_REPLAY_VERIFIED_DEVELOPER_INSPECTOR",
        }

    @core.mcp.tool(annotations=read_only)
    def get_document_runtime_diagnostics(
        document_id: str,
        run_id: str,
    ) -> dict:
        metadata, state = _load_run(document_id, run_id)
        diagnostic = runtime_diagnostics(state)
        return {
            "ok": diagnostic.get("ok") is True,
            "document_id": document_id,
            "durable_revision": int(metadata["revision"]),
            **diagnostic,
            "authority": "READ_ONLY_STRUCTURED_RUNTIME_DIAGNOSTICS",
        }

    @core.mcp.tool(annotations=read_only)
    def get_host_adapter_registry(document_id: str = "") -> dict:
        if document_id:
            owned_document(document_id)
        else:
            core._caller_subject()
        return {"ok": True, **adapter_registry.snapshot(document_id)}

    @core.mcp.tool(annotations=runtime_config)
    def hot_swap_document_host_adapter_profile(
        document_id: str,
        target_profile: str,
        expected_generation: int,
    ) -> dict:
        owned_document(document_id)
        return {
            "ok": True,
            **adapter_registry.swap(
                target_profile,
                int(expected_generation),
                document_id=document_id,
            ),
        }

    @core.mcp.tool(annotations=runtime_config)
    def rollback_document_host_adapter_profile(
        document_id: str,
        expected_generation: int,
    ) -> dict:
        owned_document(document_id)
        return {
            "ok": True,
            **adapter_registry.rollback(
                int(expected_generation),
                document_id=document_id,
            ),
        }

    @core.mcp.tool(annotations=read_only)
    def validate_sandboxed_document_extension(manifest: dict) -> dict:
        core._caller_subject()
        return {"ok": True, "extension": validate_extension(manifest)}

    @core.mcp.tool(annotations=read_only)
    def execute_sandboxed_document_extension_probe(
        manifest: dict,
        module_base64: str,
    ) -> dict:
        core._caller_subject()
        receipt = execute_wasm(manifest, module_base64)
        return {
            "ok": True,
            **receipt,
            "authority": "SEPARATE_PROCESS_PURE_WASM_NO_IMPORTS_EXECUTION",
        }

    @core.mcp.tool(annotations=read_only)
    def generate_document_platform_contracts(
        extensions: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **codegen(extensions or [])}

    projected = project_tools()
    projected_names = {str(row.get("name")) for row in projected.get("tools", [])}
    bound_names = {
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
    if projected_names != bound_names:
        raise RuntimeError(
            "P3.46 projected tool surface diverged from Python MCP bindings: "
            f"projected={sorted(projected_names)} bound={sorted(bound_names)}"
        )

    return {
        "phase": "P3.46",
        "contract": platform_contract(),
        "tool_surface_sha256": projected.get("surface_sha256"),
        "adapter_registry": adapter_registry.snapshot(),
    }
