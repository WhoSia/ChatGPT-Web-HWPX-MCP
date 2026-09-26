from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

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
    validate_sequence,
)


@dataclass(frozen=True)
class AdapterProfile:
    profile_id: str
    adapters: Mapping[str, Callable[..., dict]]
    guarded: bool


class AdapterRegistry:
    """CAS registry over pre-admitted adapters; never loads arbitrary Python code."""

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
        self._active = "p3.46-guarded"
        self._generation = 1
        self._history: list[str] = ["p3.45-compat", "p3.46-guarded"]

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

    def resolve(self, adapter_name: str) -> Callable[..., dict]:
        with self._lock:
            fn = self._profiles[self._active].adapters.get(adapter_name)
            if fn is None:
                raise KeyError(
                    f"P3.46 active adapter profile does not provide {adapter_name}"
                )
            return fn

    def snapshot(self) -> dict:
        with self._lock:
            active = self._profiles[self._active]
            return {
                "phase": "P3.46",
                "generation": self._generation,
                "active_profile": self._active,
                "active_guarded": active.guarded,
                "adapters": sorted(active.adapters),
                "profiles": {
                    key: {
                        "guarded": value.guarded,
                        "adapters": sorted(value.adapters),
                    }
                    for key, value in sorted(self._profiles.items())
                },
                "history": list(self._history[-16:]),
                "scope": "PROCESS_LOCAL_PRE_ADMITTED_ONLY",
            }

    def swap(self, target_profile: str, expected_generation: int) -> dict:
        with self._lock:
            if int(expected_generation) != self._generation:
                raise RuntimeError("P3.46 adapter generation CAS mismatch")
            if target_profile not in self._profiles:
                raise ValueError("P3.46 target adapter profile is not pre-admitted")
            previous = self._active
            changed = target_profile != previous
            if changed:
                self._active = target_profile
                self._generation += 1
                self._history.append(target_profile)
            receipt = self.snapshot()
            receipt.update(
                {
                    "previous_profile": previous,
                    "swapped": changed,
                    "authority": "PRE_ADMITTED_ADAPTER_PROFILE_CAS_SWAP",
                }
            )
            return receipt

    def rollback(self, expected_generation: int) -> dict:
        with self._lock:
            if int(expected_generation) != self._generation:
                raise RuntimeError("P3.46 adapter generation CAS mismatch")
            if len(self._history) < 2:
                raise RuntimeError("P3.46 adapter rollback history is empty")
            current = self._active
            previous = self._history[-2]
            if previous == current:
                raise RuntimeError("P3.46 rollback would be a no-op")
            self._active = previous
            self._generation += 1
            self._history.append(previous)
            receipt = self.snapshot()
            receipt.update(
                {
                    "previous_profile": current,
                    "rolled_back_to": previous,
                    "authority": "PRE_ADMITTED_ADAPTER_PROFILE_SAFE_ROLLBACK",
                }
            )
            return receipt


def register_p346_tools(
    core,
    owned_document: Callable[[str], tuple[dict, Any]],
    adapter_registry: AdapterRegistry,
):
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

    @core.mcp.tool()
    def get_developer_platform_contract() -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **platform_contract(),
            "adapter_registry": adapter_registry.snapshot(),
        }

    @core.mcp.tool()
    def project_document_tool_surface(
        extensions: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **project_tools(extensions or [])}

    @core.mcp.tool()
    def validate_document_effect_composition(plan: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **validate_composition(plan)}

    @core.mcp.tool()
    def validate_document_tool_sequence(effects: list[str]) -> dict:
        core._caller_subject()
        return {"ok": True, **validate_sequence(effects)}

    @core.mcp.tool()
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

    @core.mcp.tool()
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

    @core.mcp.tool()
    def get_host_adapter_registry() -> dict:
        core._caller_subject()
        return {"ok": True, **adapter_registry.snapshot()}

    @core.mcp.tool()
    def hot_swap_document_host_adapter_profile(
        target_profile: str,
        expected_generation: int,
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **adapter_registry.swap(target_profile, int(expected_generation)),
        }

    @core.mcp.tool()
    def rollback_document_host_adapter_profile(
        expected_generation: int,
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **adapter_registry.rollback(int(expected_generation)),
        }

    @core.mcp.tool()
    def validate_sandboxed_document_extension(manifest: dict) -> dict:
        core._caller_subject()
        return {"ok": True, "extension": validate_extension(manifest)}

    @core.mcp.tool()
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

    @core.mcp.tool()
    def generate_document_platform_contracts(
        extensions: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **codegen(extensions or [])}

    return {
        "phase": "P3.46",
        "contract": platform_contract(),
        "adapter_registry": adapter_registry.snapshot(),
    }
