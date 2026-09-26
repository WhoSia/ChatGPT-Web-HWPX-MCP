from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.45/runtime-contract/v1"


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def host_receipt_sha256(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _node_bin() -> str:
    explicit = str(os.environ.get("P345_NODE_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("node") or shutil.which("nodejs")
    if not found:
        raise RuntimeError("P3.45 TypeScript runtime requires Node.js")
    return found


def _runtime_script() -> Path:
    explicit = str(os.environ.get("P345_TS_RUNTIME") or "").strip()
    candidates = [
        Path(explicit) if explicit else None,
        ROOT / "runtime" / "p345_runtime_cli.js",
        ROOT / ".tmp" / "p345-ts" / "scripts" / "p345_runtime_cli.js",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("P3.45 compiled TypeScript runtime is unavailable")


def _runtime(command: str, payload: Mapping[str, Any] | None = None) -> dict:
    proc = subprocess.run(
        [_node_bin(), str(_runtime_script()), command],
        input="" if payload is None else _stable(payload),
        text=True,
        capture_output=True,
        timeout=12,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "P3.45 TypeScript runtime failed: "
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("P3.45 TypeScript runtime emitted invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("P3.45 TypeScript runtime result must be an object")
    return result


def _replay_bin() -> str:
    explicit = str(os.environ.get("P345_REPLAY_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("p345-replay")
    if found:
        return found
    candidate = ROOT / "rust" / "p345_replay" / "target" / "release" / "p345-replay"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("P3.45 Rust replay verifier is unavailable")


def runtime_contract() -> dict:
    result = _runtime("contract")
    if result.get("schema") != CONTRACT_SCHEMA or result.get("phase") != "P3.45":
        raise RuntimeError("P3.45 runtime contract mismatch")
    return result


def compile_ir(payload: Mapping[str, Any]) -> dict:
    return _runtime("compile", payload)


def create_run(compiled: Mapping[str, Any]) -> dict:
    return _runtime("create-run", compiled)


def transition(state: Mapping[str, Any], command: Mapping[str, Any]) -> dict:
    return _runtime("transition", {"state": state, "command": command})


def time_travel(state: Mapping[str, Any], seq: int) -> dict:
    return _runtime("time-travel", {"state": state, "seq": int(seq)})


def observability(state: Mapping[str, Any]) -> dict:
    return _runtime("observability", {"state": state})


def validate_extension(manifest: Mapping[str, Any]) -> dict:
    return _runtime("validate-extension", manifest)


def verify_replay(state: Mapping[str, Any]) -> dict:
    proc = subprocess.run(
        [_replay_bin(), "verify"],
        input=_stable(state),
        text=True,
        capture_output=True,
        timeout=8,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "P3.45 Rust replay verification failed: "
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("P3.45 Rust verifier emitted invalid JSON") from exc
    if (
        not isinstance(result, dict)
        or result.get("ok") is not True
        or result.get("head_event_hash") != state.get("head_event_hash")
    ):
        raise RuntimeError("P3.45 Rust replay verification did not bind the current state")
    return result


def prior_snapshot_from_state(state: Mapping[str, Any]) -> dict:
    compiled = dict(state.get("compiled") or {})
    node_specs = dict(compiled.get("node_spec_sha256") or {})
    binding_hashes = dict(compiled.get("provider_binding_sha256") or {})
    node_states = dict(state.get("node_states") or {})
    outputs = dict(state.get("outputs") or {})
    prior: dict[str, dict] = {}
    for node_id, terminal in node_states.items():
        if terminal not in {"COMMITTED", "REUSED"}:
            continue
        output = dict(outputs.get(node_id) or {})
        output_sha = str(output.get("output_sha256") or "")
        if len(output_sha) != 64:
            continue
        if node_id not in node_specs or node_id not in binding_hashes:
            continue
        prior[str(node_id)] = {
            "node_spec_sha256": str(node_specs[node_id]),
            "provider_binding_sha256": str(binding_hashes[node_id]),
            "output_sha256": output_sha,
            "terminal_state": str(terminal),
        }
    return prior
