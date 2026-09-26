from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from mcp.types import ToolAnnotations

from p345_runtime_bridge import host_receipt_sha256, verify_replay
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
    contract_sha256: str


class AdapterRegistry:
    """Owner-scoped CAS registry over pre-admitted adapters; never loads arbitrary Python code."""

    MUTATING_ADAPTERS = {
        "DOCUMENT_TEXT_EDIT",
        "DOCUMENT_FORMAT_EDIT",
        "DOCUMENT_DESIGN_REPAIR",
    }
    PROFILE_CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.46/host-adapter-profile-contract/v1"
    HOST_ADAPTER_ABI = "p3.46-host-adapter-v1"

    @classmethod
    def _profile_contract_sha256(
        cls,
        profile_id: str,
        adapters: Mapping[str, Callable[..., dict]],
        guarded: bool,
    ) -> str:
        body = {
            "schema": cls.PROFILE_CONTRACT_SCHEMA,
            "host_abi": cls.HOST_ADAPTER_ABI,
            "profile_id": str(profile_id),
            "guarded": bool(guarded),
            "adapters": [
                {
                    "name": name,
                    "revision_semantics": (
                        "REVISION_PLUS_ONE"
                        if name in cls.MUTATING_ADAPTERS
                        else "REVISION_STABLE"
                    ),
                }
                for name in sorted(adapters)
            ],
        }
        encoded = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def __init__(self, host_adapters: Mapping[str, Callable[..., dict]]):
        base = dict(host_adapters)
        if not base:
            raise ValueError("P3.46 adapter registry requires at least one host adapter")
        self._lock = threading.RLock()
        guarded_adapters = {
            name: self._guard(name, fn)
            for name, fn in base.items()
        }
        self._profiles: dict[str, AdapterProfile] = {
            "p3.45-compat": AdapterProfile(
                "p3.45-compat", base, False,
                self._profile_contract_sha256("p3.45-compat", base, False),
            ),
            "p3.46-guarded": AdapterProfile(
                "p3.46-guarded", guarded_adapters, True,
                self._profile_contract_sha256(
                    "p3.46-guarded", guarded_adapters, True
                ),
            ),
        }
        self._document_active: dict[str, str] = {}
        self._document_generation: dict[str, int] = {}
        self._document_history: dict[str, list[str]] = {}
        self._run_bindings: dict[tuple[str, str], tuple[str, int, str]] = {}
        self._run_binding_order: dict[str, list[str]] = {}

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

    def _remember_run_binding(
        self,
        key: tuple[str, str],
        selected: tuple[str, int, str],
    ) -> None:
        document_id, run_id = key
        self._run_bindings[key] = selected
        order = self._run_binding_order.setdefault(document_id, [])
        if run_id not in order:
            order.append(run_id)
        while len(order) > 16:
            retired = order.pop(0)
            self._run_bindings.pop((document_id, retired), None)

    def resolve(
        self,
        adapter_name: str,
        *,
        document_id: str = "",
        run_id: str = "",
        pinned_profile: str = "",
        pinned_generation: int | None = None,
        pinned_contract_sha256: str = "",
    ) -> Callable[..., dict]:
        document_id = str(document_id or "")
        run_id = str(run_id or "")
        with self._lock:
            active, generation, _history = self._state(document_id)
            key = (document_id, run_id) if document_id and run_id else None
            requested_profile = str(pinned_profile or "")
            requested_generation = (
                int(pinned_generation)
                if pinned_generation is not None
                else None
            )
            if requested_profile:
                if requested_profile not in self._profiles:
                    raise ValueError(
                        "P3.46 persisted run binding references unknown adapter profile"
                    )
                if requested_generation is None or requested_generation < 1:
                    raise ValueError(
                        "P3.46 persisted run binding requires positive generation"
                    )
                requested_contract = str(pinned_contract_sha256 or "")
                if len(requested_contract) != 64 or any(
                    ch not in "0123456789abcdef" for ch in requested_contract
                ):
                    raise ValueError(
                        "P3.46 persisted run binding requires profile contract sha256"
                    )
                current_contract = self._profiles[requested_profile].contract_sha256
                if requested_contract != current_contract:
                    raise RuntimeError(
                        "P3.46 persisted adapter profile contract drift"
                    )
                selected = (
                    requested_profile, requested_generation, requested_contract
                )
                if key is not None and key in self._run_bindings:
                    if self._run_bindings[key] != selected:
                        raise RuntimeError(
                            "P3.46 run-local adapter binding divergence"
                        )
                elif key is not None:
                    self._remember_run_binding(key, selected)
            elif key is not None and key in self._run_bindings:
                selected = self._run_bindings[key]
            else:
                selected = (
                    active, generation, self._profiles[active].contract_sha256
                )
                if key is not None:
                    self._remember_run_binding(key, selected)

            (
                selected_profile,
                selected_generation,
                selected_contract_sha256,
            ) = selected
            if (
                self._profiles[selected_profile].contract_sha256
                != selected_contract_sha256
            ):
                raise RuntimeError(
                    "P3.46 run-local adapter profile contract drift"
                )
            fn = self._profiles[selected_profile].adapters.get(adapter_name)
            if fn is None:
                raise KeyError(
                    f"P3.46 selected adapter profile does not provide {adapter_name}"
                )

        def invoke(**kwargs):
            result = fn(**kwargs)
            if not isinstance(result, dict):
                raise RuntimeError("P3.46 host adapter must return a dict receipt")
            out = dict(result)
            out["p346_adapter_profile"] = selected_profile
            out["p346_adapter_generation"] = selected_generation
            out["p346_adapter_contract_sha256"] = selected_contract_sha256
            out["p346_adapter_name"] = adapter_name
            return out

        return invoke

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
                "active_contract_sha256": active.contract_sha256,
                "host_adapter_abi": self.HOST_ADAPTER_ABI,
                "default_profile": "p3.46-guarded",
                "adapters": sorted(active.adapters),
                "profiles": {
                    key: {
                        "guarded": value.guarded,
                        "contract_sha256": value.contract_sha256,
                        "adapters": sorted(value.adapters),
                    }
                    for key, value in sorted(self._profiles.items())
                },
                "history": list(history[-16:]),
                "pinned_run_count": sum(
                    1
                    for (doc, _run) in self._run_bindings
                    if doc == str(document_id or "")
                ) if document_id else 0,
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

    def _host_execution_receipts(
        metadata: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> tuple[list[dict], list[dict]]:
        run_id = str(state.get("run_id") or "")
        raw_all = metadata.get("p346_runtime_host_receipts") or {}
        raw_run = raw_all.get(run_id) if isinstance(raw_all, dict) else {}
        if not isinstance(raw_run, dict):
            return [], [{
                "severity": "ERROR",
                "code": "HOST_RECEIPT_SIDECAR_MALFORMED",
            }]

        order = list((state.get("compiled") or {}).get("topological_order") or [])
        outputs = state.get("outputs") or {}
        rows: list[dict] = []
        issues: list[dict] = []
        bindings: set[tuple[str, int, str]] = set()
        known_node_ids = {str(node_id) for node_id in order}
        for raw_node_id in sorted(str(key) for key in raw_run):
            if raw_node_id not in known_node_ids:
                issues.append({
                    "severity": "ERROR",
                    "code": "HOST_RECEIPT_UNKNOWN_NODE",
                    "node_id": raw_node_id,
                })

        for node_id in order:
            raw = raw_run.get(node_id)
            if raw is None:
                continue
            if not isinstance(raw, dict):
                issues.append({
                    "severity": "ERROR",
                    "code": "HOST_RECEIPT_ROW_MALFORMED",
                    "node_id": node_id,
                })
                continue

            row = dict(raw)
            observed_seal = str(row.pop("provenance_sha256", "") or "")
            expected_seal = host_receipt_sha256(row)
            if observed_seal != expected_seal:
                issues.append({
                    "severity": "ERROR",
                    "code": "HOST_RECEIPT_PROVENANCE_SEAL_MISMATCH",
                    "node_id": node_id,
                })

            if str(row.get("node_id") or "") != node_id:
                issues.append({
                    "severity": "ERROR",
                    "code": "HOST_RECEIPT_NODE_ID_MISMATCH",
                    "node_id": node_id,
                })

            profile = str(row.get("adapter_profile") or "")
            try:
                generation = int(row.get("adapter_generation"))
            except (TypeError, ValueError):
                generation = 0
            contract_sha256 = str(row.get("adapter_contract_sha256") or "")
            contract_valid = (
                len(contract_sha256) == 64
                and all(ch in "0123456789abcdef" for ch in contract_sha256)
            )
            if not profile or generation < 1 or not contract_valid:
                issues.append({
                    "severity": "ERROR",
                    "code": "HOST_RECEIPT_BINDING_INVALID",
                    "node_id": node_id,
                })
            else:
                bindings.add((profile, generation, contract_sha256))

            state_output = (
                outputs.get(node_id) if isinstance(outputs, dict) else None
            )
            if not isinstance(state_output, dict):
                issues.append({
                    "severity": "ERROR",
                    "code": "HOST_RECEIPT_RUNTIME_OUTPUT_MISSING",
                    "node_id": node_id,
                })
            else:
                state_output_sha = str(state_output.get("output_sha256") or "")
                state_receipt_sha = str(state_output.get("receipt_sha256") or "")
                invalid_state_hash = any(
                    len(digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in digest)
                    for digest in (state_output_sha, state_receipt_sha)
                )
                if invalid_state_hash:
                    issues.append({
                        "severity": "ERROR",
                        "code": "HOST_RECEIPT_SEALED_RUNTIME_HASH_INVALID",
                        "node_id": node_id,
                    })
                if (
                    str(row.get("output_sha256") or "") != state_output_sha
                    or str(row.get("receipt_sha256") or "") != state_receipt_sha
                ):
                    issues.append({
                        "severity": "ERROR",
                        "code": "HOST_RECEIPT_RUNTIME_HASH_DIVERGENCE",
                        "node_id": node_id,
                    })

            rows.append({
                **row,
                "provenance_sha256": observed_seal,
            })

        if len(bindings) > 1:
            issues.append({
                "severity": "ERROR",
                "code": "ADAPTER_CONFIGURATION_DRIFT_WITHIN_RUN",
                "bindings": [
                    {
                        "adapter_profile": profile,
                        "adapter_generation": generation,
                        "adapter_contract_sha256": contract_sha256,
                    }
                    for profile, generation, contract_sha256 in sorted(bindings)
                ],
            })
        return rows, issues

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
        receipts, sidecar_issues = _host_execution_receipts(metadata, state)
        return {
            "ok": not any(
                row.get("severity") == "ERROR" for row in sidecar_issues
            ),
            "document_id": document_id,
            "durable_revision": int(metadata["revision"]),
            **inspected,
            "host_execution_receipts": receipts,
            "host_execution_receipts_sha256": host_receipt_sha256(receipts),
            "host_execution_receipt_diagnostics": sidecar_issues,
            "host_execution_receipt_authority":
                "P3.46_OWNER_SCOPED_REPLAY_PRESERVING_SIDECAR",
            "authority": "READ_ONLY_REPLAY_VERIFIED_DEVELOPER_INSPECTOR",
        }

    @core.mcp.tool(annotations=read_only)
    def get_document_runtime_diagnostics(
        document_id: str,
        run_id: str,
    ) -> dict:
        metadata, state = _load_run(document_id, run_id)
        diagnostic = runtime_diagnostics(state)
        receipts, sidecar_issues = _host_execution_receipts(metadata, state)
        rows = list(diagnostic.get("diagnostics") or []) + sidecar_issues
        errors = sum(1 for row in rows if row.get("severity") == "ERROR")
        warnings = sum(1 for row in rows if row.get("severity") == "WARNING")
        diagnostic = {
            **diagnostic,
            "ok": errors == 0,
            "diagnostics": rows,
            "summary": {"errors": errors, "warnings": warnings},
            "diagnostics_sha256": host_receipt_sha256(rows),
            "host_execution_receipts": receipts,
        }
        return {
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
