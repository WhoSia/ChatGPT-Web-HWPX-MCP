from __future__ import annotations

import secrets
from typing import Any, Callable, Mapping

from p345_runtime_bridge import (
    compile_ir,
    create_run,
    host_receipt_sha256,
    observability,
    prior_snapshot_from_state,
    runtime_contract,
    time_travel,
    transition,
    validate_extension,
    verify_replay,
)

MAX_RUNS_PER_DOCUMENT = 4
MAX_OBSERVATION_ENVELOPES = 256


def register_p345_tools(
    core,
    owned_document: Callable[[str], tuple[dict, Any]],
    host_adapters: Mapping[str, Callable[..., dict]],
):
    adapters = dict(host_adapters)
    admitted_adapters = set(adapters) | {"EXTERNAL_RENDER"}

    def _load(document_id: str, run_id: str) -> tuple[dict, dict]:
        metadata = core._load_metadata(document_id)
        core._require_owner(metadata)
        runs = metadata.get("p345_transaction_runs") or {}
        if not isinstance(runs, dict) or run_id not in runs:
            raise FileNotFoundError("P3.45 transaction run not found")
        state = runs[run_id]
        if not isinstance(state, dict):
            raise RuntimeError("P3.45 stored run is malformed")
        verify_replay(state)
        return metadata, state

    def _persist(document_id: str, state: dict) -> None:
        verify_replay(state)
        metadata = core._load_metadata(document_id)
        core._require_owner(metadata)
        if int(metadata["revision"]) != int(state["current_revision"]):
            raise RuntimeError(
                "P3.45 runtime/document revision divergence; refusing to persist"
            )
        runs = dict(metadata.get("p345_transaction_runs") or {})
        order = list(metadata.get("p345_transaction_run_order") or [])
        run_id = str(state["run_id"])
        if run_id not in order:
            order.append(run_id)
        runs[run_id] = state
        while len(order) > MAX_RUNS_PER_DOCUMENT:
            retired = order.pop(0)
            runs.pop(retired, None)
        envelopes = dict(metadata.get("p345_runtime_observation_envelopes") or {})
        rows = list(envelopes.get(run_id) or [])
        event_seq = len(state.get("events") or [])
        if not rows or int(rows[-1].get("event_seq", -1)) != event_seq:
            rows.append(
                {
                    "event_seq": event_seq,
                    "observed_at": core._utc_iso(),
                    "status": str(state.get("status") or ""),
                    "revision": int(state.get("current_revision") or 0),
                }
            )
        envelopes[run_id] = rows[-MAX_OBSERVATION_ENVELOPES:]
        envelopes = {key: envelopes[key] for key in order if key in envelopes}
        metadata["p345_transaction_runs"] = runs
        metadata["p345_transaction_run_order"] = order
        metadata["p345_runtime_observation_envelopes"] = envelopes
        metadata["p345_last_run_id"] = run_id
        core._write_metadata(document_id, metadata)

    def _validated_extension(manifest: Mapping[str, Any]) -> dict:
        checked = validate_extension(manifest)
        for row in checked.get("node_kinds") or []:
            adapter = str((row or {}).get("adapter") or "")
            if adapter not in admitted_adapters:
                raise ValueError(
                    f"P3.45 extension adapter is not admitted by this host: {adapter}"
                )
        return checked

    def _prior(document_id: str, prior_run_id: str) -> dict:
        if not prior_run_id:
            return {}
        _metadata, prior_state = _load(document_id, prior_run_id)
        return prior_snapshot_from_state(prior_state)

    def _node(state: Mapping[str, Any], node_id: str) -> dict:
        nodes = ((state.get("compiled") or {}).get("ir") or {}).get("nodes") or []
        for row in nodes:
            if isinstance(row, dict) and row.get("id") == node_id:
                return row
        raise RuntimeError("P3.45 compiled node is unavailable")

    def _result_summary(result: Mapping[str, Any], *, revision_before: int) -> dict:
        revision_after = int(result.get("revision_after", revision_before))
        output_sha = str(result.get("output_sha256") or result.get("sha256") or "")
        if len(output_sha) != 64:
            output_sha = host_receipt_sha256(
                {"revision_after": revision_after, "result": dict(result)}
            )
        receipt_sha = str(result.get("receipt_sha256") or "")
        if len(receipt_sha) != 64:
            receipt_sha = host_receipt_sha256(dict(result))
        return {
            "revision_after": revision_after,
            "output_sha256": output_sha,
            "receipt_sha256": receipt_sha,
        }

    @core.mcp.tool()
    def get_document_transaction_runtime_contract() -> dict:
        """Return the P3.45 IR/runtime/replay/capability/extension/observability constitution."""
        core._caller_subject()
        contract = runtime_contract()
        return {
            "ok": True,
            **contract,
            "host_adapter_allowlist": sorted(admitted_adapters),
            "persistence": "OWNER_SCOPED_DURABLE_DOCUMENT_METADATA",
            "mutation_serialization": "P3.2_DOCUMENT_LEASE_PLUS_REVISION_CAS",
        }

    @core.mcp.tool()
    def get_document_runtime_capabilities() -> dict:
        """Return the TypeScript-owned built-in provider catalog used by P3.45 negotiation."""
        core._caller_subject()
        contract = runtime_contract()
        return {
            "ok": True,
            "phase": "P3.45",
            "provider": contract["builtin_provider"],
            "supported_builtin_node_kinds": contract["supported_builtin_node_kinds"],
            "host_adapter_allowlist": sorted(admitted_adapters),
        }

    @core.mcp.tool()
    def validate_document_runtime_extension(manifest: dict) -> dict:
        """Validate one manifest-only P3.45 extension against the host adapter ABI; no code is loaded."""
        core._caller_subject()
        return {"ok": True, "extension": _validated_extension(manifest)}

    @core.mcp.tool()
    def compile_document_transaction(
        document_id: str,
        ir: dict,
        extensions: list[dict] | None = None,
        prior_run_id: str = "",
        changed_node_ids: list[str] | None = None,
    ) -> dict:
        """Compile one declarative authoring IR into a deterministic incremental runtime plan and persist a new run."""
        metadata, _path = owned_document(document_id)
        current_revision = int(metadata["revision"])
        if str(ir.get("document_id") or "") != document_id:
            raise ValueError("P3.45 IR document_id must match the owned document")
        if int(ir.get("base_revision") or 0) != current_revision:
            raise ValueError(
                f"P3.45 IR base revision is stale: {ir.get('base_revision')} != {current_revision}"
            )
        checked_extensions = [_validated_extension(row) for row in (extensions or [])]
        request = {
            "ir": ir,
            "extensions": checked_extensions,
            "prior_snapshot": _prior(document_id, str(prior_run_id or "")),
            "changed_node_ids": list(changed_node_ids or []),
        }
        compiled = compile_ir(request)
        state = create_run(compiled)
        verify_replay(state)
        existing_runs = metadata.get("p345_transaction_runs") or {}
        existing = existing_runs.get(state["run_id"]) if isinstance(existing_runs, dict) else None
        if isinstance(existing, dict):
            verify_replay(existing)
            if (
                str((existing.get("compiled") or {}).get("plan_sha256") or "")
                != str(compiled.get("plan_sha256") or "")
            ):
                raise RuntimeError("P3.45 deterministic run-id collision")
            return {
                "ok": True,
                "document_id": document_id,
                "revision": current_revision,
                "run_id": existing["run_id"],
                "run_sha256": existing["run_sha256"],
                "ir_sha256": compiled["ir_sha256"],
                "plan_sha256": compiled["plan_sha256"],
                "topological_order": compiled["topological_order"],
                "actions": compiled["actions"],
                "affected_nodes": compiled["affected_nodes"],
                "reused_nodes": compiled["reused_nodes"],
                "provider_bindings": compiled["provider_bindings"],
                "status": existing["status"],
                "idempotent_existing_run": True,
                "authority": "TYPESCRIPT_COMPILED_RUST_VERIFIED_TRANSACTION_PLAN",
            }
        _persist(document_id, state)
        return {
            "ok": True,
            "document_id": document_id,
            "revision": current_revision,
            "run_id": state["run_id"],
            "run_sha256": state["run_sha256"],
            "ir_sha256": compiled["ir_sha256"],
            "plan_sha256": compiled["plan_sha256"],
            "topological_order": compiled["topological_order"],
            "actions": compiled["actions"],
            "affected_nodes": compiled["affected_nodes"],
            "reused_nodes": compiled["reused_nodes"],
            "provider_bindings": compiled["provider_bindings"],
            "status": state["status"],
            "authority": "TYPESCRIPT_COMPILED_RUST_VERIFIED_TRANSACTION_PLAN",
        }

    @core.mcp.tool()
    def get_document_transaction_run(document_id: str, run_id: str) -> dict:
        """Return one persisted P3.45 runtime state after Rust replay verification."""
        metadata, state = _load(document_id, run_id)
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            "run": state,
            "replay": verify_replay(state),
        }

    @core.mcp.tool()
    def advance_document_transaction(
        document_id: str,
        run_id: str,
        max_nodes: int = 8,
    ) -> dict:
        """Advance a P3.45 run until completion, an external-evidence pause, or a fail-closed hold."""
        max_nodes = int(max_nodes)
        if max_nodes < 1 or max_nodes > 16:
            raise ValueError("max_nodes must be between 1 and 16")
        metadata, state = _load(document_id, run_id)
        if int(metadata["revision"]) != int(state["current_revision"]):
            raise RuntimeError("P3.45 runtime is stale relative to the document revision")
        if state.get("status") == "COMPLETED":
            return {
                "ok": True,
                "document_id": document_id,
                "run_id": run_id,
                "revision": int(state["current_revision"]),
                "status": "COMPLETED",
                "executed": [],
                "run_sha256": state["run_sha256"],
                "head_event_hash": state["head_event_hash"],
                "idempotent_terminal_read": True,
            }
        if state.get("status") in {"ABORTED", "HOLD"}:
            raise RuntimeError(f"P3.45 runtime is terminal/non-runnable: {state.get('status')}")
        if any(value == "RUNNING" for value in (state.get("node_states") or {}).values()):
            raise RuntimeError(
                "P3.45 found an in-flight node after interruption; automatic commit inference is forbidden"
            )

        executed: list[dict] = []
        order = list((state.get("compiled") or {}).get("topological_order") or [])
        for _ in range(max_nodes):
            states = dict(state.get("node_states") or {})
            pending = [node_id for node_id in order if states.get(node_id) == "PENDING"]
            if not pending:
                if state.get("status") != "COMPLETED":
                    state = transition(state, {"type": "COMPLETE_RUN"})
                    verify_replay(state)
                    _persist(document_id, state)
                return {
                    "ok": True,
                    "document_id": document_id,
                    "run_id": run_id,
                    "revision": int(state["current_revision"]),
                    "status": state["status"],
                    "executed": executed,
                    "run_sha256": state["run_sha256"],
                    "head_event_hash": state["head_event_hash"],
                }

            node_id = pending[0]
            action = str((state["compiled"]["actions"] or {}).get(node_id) or "")
            if action == "WAIT_EXTERNAL":
                state = transition(state, {"type": "WAIT_NODE", "node_id": node_id})
                verify_replay(state)
                _persist(document_id, state)
                return {
                    "ok": True,
                    "document_id": document_id,
                    "run_id": run_id,
                    "revision": int(state["current_revision"]),
                    "status": "WAIT_EXTERNAL",
                    "waiting_node_id": node_id,
                    "run_sha256": state["run_sha256"],
                    "head_event_hash": state["head_event_hash"],
                    "next": "Provide measured external evidence with resolve_document_transaction_external.",
                }
            if action != "EXECUTE":
                raise RuntimeError(f"P3.45 unexpected pending action: {action}")

            binding = state["compiled"]["provider_bindings"][node_id]
            adapter_name = str(binding.get("adapter") or "")
            adapter = adapters.get(adapter_name)
            if adapter is None:
                raise RuntimeError(f"P3.45 host adapter unavailable: {adapter_name}")
            node = _node(state, node_id)
            revision_before = int(state["current_revision"])
            state = transition(state, {"type": "START_NODE", "node_id": node_id})
            verify_replay(state)
            _persist(document_id, state)

            lease_token = ""
            side_effect = str(state["compiled"]["side_effects"].get(node_id) or "")
            try:
                if side_effect == "DOCUMENT_MUTATION":
                    lease_token = secrets.token_urlsafe(32)
                    core.DOCUMENT_STORE.acquire_lease(
                        document_id,
                        holder_id=f"p345:{run_id}:{node_id}"[:160],
                        expected_revision=revision_before,
                        lease_token=lease_token,
                        ttl_seconds=60,
                    )
                result = adapter(
                    document_id=document_id,
                    current_revision=revision_before,
                    inputs=dict(node.get("inputs") or {}),
                    lease_token=lease_token,
                )
                summary = _result_summary(result, revision_before=revision_before)
                state = transition(
                    state,
                    {"type": "COMMIT_NODE", "node_id": node_id, **summary},
                )
                verify_replay(state)
                _persist(document_id, state)
                executed.append(
                    {"node_id": node_id, "adapter": adapter_name, **summary}
                )
            except Exception as exc:
                if lease_token:
                    try:
                        core.DOCUMENT_STORE.release_lease(
                            document_id, lease_token=lease_token
                        )
                    except Exception:
                        pass
                latest = core._load_metadata(document_id)
                if int(latest["revision"]) != revision_before:
                    raise RuntimeError(
                        "P3.45 adapter changed the durable revision but the runtime did not receive a commit receipt; "
                        "automatic recovery is forbidden"
                    ) from exc
                state = transition(
                    state,
                    {
                        "type": "FAIL_NODE",
                        "node_id": node_id,
                        "error_type": type(exc).__name__,
                    },
                )
                verify_replay(state)
                _persist(document_id, state)
                raise

        return {
            "ok": True,
            "document_id": document_id,
            "run_id": run_id,
            "revision": int(state["current_revision"]),
            "status": state["status"],
            "executed": executed,
            "run_sha256": state["run_sha256"],
            "head_event_hash": state["head_event_hash"],
            "next": "Call advance_document_transaction again to continue the bounded run.",
        }

    @core.mcp.tool()
    def resolve_document_transaction_external(
        document_id: str,
        run_id: str,
        node_id: str,
        evidence_receipt: dict,
    ) -> dict:
        """Resolve one WAIT_EXTERNAL node with measured evidence; replay never fabricates world contact."""
        _metadata, state = _load(document_id, run_id)
        if (state.get("node_states") or {}).get(node_id) != "WAITING_EXTERNAL":
            raise ValueError("P3.45 node is not waiting for external evidence")
        if not isinstance(evidence_receipt, dict) or not evidence_receipt:
            raise ValueError("P3.45 external evidence receipt must be a non-empty object")
        if evidence_receipt.get("world_contact_valid") is not True:
            raise ValueError("P3.45 external evidence must explicitly assert world_contact_valid=true")
        if int(evidence_receipt.get("revision") or 0) != int(state["current_revision"]):
            raise ValueError("P3.45 external evidence revision is stale")
        receipt_document_id = str(evidence_receipt.get("document_id") or "")
        if receipt_document_id and receipt_document_id != document_id:
            raise ValueError("P3.45 external evidence document_id mismatch")
        receipt_sha = host_receipt_sha256(evidence_receipt)
        state = transition(
            state,
            {
                "type": "RESOLVE_NODE",
                "node_id": node_id,
                "output_sha256": receipt_sha,
                "receipt_sha256": receipt_sha,
            },
        )
        verify_replay(state)
        _persist(document_id, state)
        return {
            "ok": True,
            "document_id": document_id,
            "run_id": run_id,
            "node_id": node_id,
            "revision": int(state["current_revision"]),
            "status": state["status"],
            "evidence_receipt_sha256": receipt_sha,
            "run_sha256": state["run_sha256"],
            "head_event_hash": state["head_event_hash"],
        }

    @core.mcp.tool()
    def abort_document_transaction(
        document_id: str,
        run_id: str,
        reason_code: str = "operator.cancelled",
    ) -> dict:
        """Explicitly abort a P3.45 run when durable revision custody still matches the runtime."""
        metadata, state = _load(document_id, run_id)
        if int(metadata["revision"]) != int(state["current_revision"]):
            raise RuntimeError(
                "P3.45 cannot abort while durable revision diverges; explicit reconciliation is required"
            )
        if state.get("status") == "COMPLETED":
            raise ValueError("P3.45 completed run cannot be aborted")
        if state.get("status") == "ABORTED":
            return {
                "ok": True,
                "document_id": document_id,
                "run_id": run_id,
                "revision": int(state["current_revision"]),
                "status": "ABORTED",
                "run_sha256": state["run_sha256"],
                "head_event_hash": state["head_event_hash"],
                "idempotent_terminal_read": True,
            }
        state = transition(
            state,
            {"type": "ABORT_RUN", "reason_code": str(reason_code or "operator.cancelled")},
        )
        verify_replay(state)
        _persist(document_id, state)
        return {
            "ok": True,
            "document_id": document_id,
            "run_id": run_id,
            "revision": int(state["current_revision"]),
            "status": state["status"],
            "run_sha256": state["run_sha256"],
            "head_event_hash": state["head_event_hash"],
            "authority": "EXPLICIT_ABORT_WITHOUT_COMMIT_INFERENCE",
        }

    @core.mcp.tool()
    def replay_document_transaction(
        document_id: str,
        run_id: str,
        event_seq: int = 0,
    ) -> dict:
        """Verify the full Rust event chain and inspect a read-only historical runtime checkpoint."""
        metadata, state = _load(document_id, run_id)
        replay = verify_replay(state)
        seq = int(event_seq) if int(event_seq) > 0 else len(state.get("events") or [])
        snapshot = time_travel(state, seq)
        revision = int(snapshot["revision"])
        durable = core.DOCUMENT_STORE.load_revision(document_id, revision)
        available = bool(
            durable is not None
            and durable.get("owner_subject") == metadata.get("owner_subject")
        )
        return {
            "ok": True,
            "document_id": document_id,
            "run_id": run_id,
            "replay": replay,
            "time_travel": snapshot,
            "durable_revision": {
                "revision": revision,
                "available": available,
                "sha256": durable.get("sha256") if available else None,
            },
            "authority": "READ_ONLY_DETERMINISTIC_TIME_TRAVEL_NOT_DOCUMENT_RESTORE",
        }

    @core.mcp.tool()
    def get_document_transaction_observability(document_id: str, run_id: str) -> dict:
        """Return low-cardinality runtime event metrics with observation time outside deterministic hashes."""
        metadata, state = _load(document_id, run_id)
        summary = observability(state)
        envelopes = (
            (metadata.get("p345_runtime_observation_envelopes") or {}).get(run_id)
            or []
        )
        return {
            "ok": True,
            "document_id": document_id,
            **summary,
            "observation_envelopes": envelopes,
            "authority": "OPERATIONAL_OBSERVABILITY_SEPARATE_FROM_REPLAY_HASH_AUTHORITY",
        }

    return {
        "phase": "P3.45",
        "contract": runtime_contract(),
        "host_adapter_allowlist": sorted(admitted_adapters),
    }
