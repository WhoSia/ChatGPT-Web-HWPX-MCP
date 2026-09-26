from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.46/developer-platform-contract/v1"


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _node_bin() -> str:
    explicit = str(os.environ.get("P346_NODE_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("node") or shutil.which("nodejs")
    if not found:
        raise RuntimeError("P3.46 TypeScript platform kernel requires Node.js")
    return found


def _runtime_script() -> Path:
    explicit = str(os.environ.get("P346_TS_RUNTIME") or "").strip()
    candidates = [
        Path(explicit) if explicit else None,
        ROOT / "runtime" / "scripts" / "p346_platform_cli.js",
        ROOT / ".tmp" / "p346-ts" / "scripts" / "p346_platform_cli.js",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("P3.46 compiled TypeScript platform kernel is unavailable")


def _runtime(
    command: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timeout: float = 5.0,
) -> dict:
    proc = subprocess.run(
        [_node_bin(), "--max-old-space-size=64", str(_runtime_script()), command],
        input="" if payload is None else _stable(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env={
            "PATH": os.environ.get("PATH", ""),
            "NODE_NO_WARNINGS": "1",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "P3.46 TypeScript platform kernel failed: "
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("P3.46 TypeScript platform kernel emitted invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("P3.46 TypeScript result must be an object")
    return result


def _guard_bin() -> str:
    explicit = str(os.environ.get("P346_GUARD_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("p346-guard")
    if found:
        return found
    candidate = ROOT / "rust" / "p346_guard" / "target" / "release" / "p346-guard"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("P3.46 Rust effect guard is unavailable")


def _guard(command: str, payload: Mapping[str, Any]) -> dict:
    proc = subprocess.run(
        [_guard_bin(), command],
        input=_stable(payload),
        text=True,
        capture_output=True,
        timeout=3,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "P3.46 Rust effect guard failed: "
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("P3.46 Rust effect guard emitted invalid JSON") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("P3.46 Rust effect guard returned a non-PASS result")
    return result


def platform_contract() -> dict:
    result = _runtime("contract")
    if result.get("schema") != CONTRACT_SCHEMA or result.get("phase") != "P3.46":
        raise RuntimeError("P3.46 platform contract mismatch")
    return result


def project_tools(extensions: Sequence[Mapping[str, Any]] | None = None) -> dict:
    return _runtime("project-tools", {"extensions": list(extensions or [])})


def validate_extension(manifest: Mapping[str, Any]) -> dict:
    return _runtime("validate-extension", manifest)


def validate_composition(plan: Mapping[str, Any]) -> dict:
    ts = _runtime("validate-composition", plan)
    rust = _guard("check-plan", plan)
    if ts.get("topological_order") != rust.get("topological_order"):
        raise RuntimeError("P3.46 TypeScript/Rust effect-plan order divergence")
    return {
        "typescript": ts,
        "rust": rust,
        "authority": "CROSS_RUNTIME_EFFECT_PLAN_PASS",
    }


def validate_sequence(effects: Sequence[str]) -> dict:
    payload = {"effects": list(effects)}
    ts = _runtime("validate-sequence", payload)
    rust = _guard("check-sequence", payload)
    return {
        "typescript": ts,
        "rust": rust,
        "authority": "CROSS_RUNTIME_TOOL_SEQUENCE_PASS",
    }


def inspect_runtime(state: Mapping[str, Any]) -> dict:
    return _runtime("inspect", {"state": state})


def runtime_diagnostics(state: Mapping[str, Any]) -> dict:
    return _runtime("diagnostics", {"state": state})


def codegen(extensions: Sequence[Mapping[str, Any]] | None = None) -> dict:
    return _runtime("codegen", {"extensions": list(extensions or [])})


def execute_wasm(manifest: Mapping[str, Any], module_base64: str) -> dict:
    execution = manifest.get("execution") if isinstance(manifest, Mapping) else None
    requested_ms = 1500
    if isinstance(execution, Mapping):
        try:
            requested_ms = int(execution.get("timeout_ms") or 1500)
        except (TypeError, ValueError):
            requested_ms = 1500
    requested_ms = max(25, min(1500, requested_ms))
    # The TypeScript kernel validates the manifest. The parent process owns the
    # kill boundary so a synchronous/infinite WASM body cannot defeat JS timers.
    parent_timeout = min(2.0, requested_ms / 1000.0 + 0.5)
    return _runtime(
        "run-wasm",
        {"manifest": manifest, "module_base64": str(module_base64)},
        timeout=parent_timeout,
    )
