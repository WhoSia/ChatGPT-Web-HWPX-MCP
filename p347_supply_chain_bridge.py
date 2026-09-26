from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _node_bin() -> str:
    explicit = str(os.environ.get("P347_NODE_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("node") or shutil.which("nodejs")
    if not found:
        raise RuntimeError("P3.47 TypeScript supply-chain kernel requires Node.js")
    return found


def _runtime_script() -> Path:
    explicit = str(os.environ.get("P347_TS_RUNTIME") or "").strip()
    candidates = [
        Path(explicit) if explicit else None,
        ROOT / "runtime" / "scripts" / "p347_supply_chain_cli.js",
        ROOT / ".tmp" / "p347-ts" / "scripts" / "p347_supply_chain_cli.js",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("P3.47 compiled TypeScript supply-chain kernel is unavailable")


def _runtime(command: str, payload: Mapping[str, Any] | None = None, *, timeout: float = 6.0) -> dict:
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
            "P3.47 TypeScript supply-chain kernel failed: "
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("P3.47 TypeScript supply-chain kernel emitted invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("P3.47 TypeScript result must be an object")
    return result


def _guard_bin() -> str:
    explicit = str(os.environ.get("P347_CERTIFIER_BIN") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("p347-certifier")
    if found:
        return found
    candidate = ROOT / "rust" / "p347_certifier" / "target" / "release" / "p347-certifier"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("P3.47 Rust certification guard is unavailable")


def _guard(command: str, payload: Mapping[str, Any]) -> dict:
    proc = subprocess.run(
        [_guard_bin(), command],
        input=_stable(payload),
        text=True,
        capture_output=True,
        timeout=4.0,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "P3.47 Rust certification guard failed: "
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )
    result = json.loads(proc.stdout)
    if not isinstance(result, dict):
        raise RuntimeError("P3.47 Rust guard result must be an object")
    return result


def supply_chain_contract() -> dict:
    return _runtime("contract")


def normalize_extension_package(package: Mapping[str, Any]) -> dict:
    return _runtime("package", {"package": dict(package)})


def verify_dependency_closure(package: Mapping[str, Any], catalog: Sequence[Mapping[str, Any]] = ()) -> dict:
    return _runtime("dependencies", {"package": dict(package), "catalog": [dict(x) for x in catalog]})


def compare_reproducible_builds(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict:
    return _runtime("reproducibility", {"left": dict(left), "right": dict(right)})


def solve_package_compatibility(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict:
    ts = _runtime("compatibility", {"current": dict(current), "candidate": dict(candidate)})
    rust = _guard("check-compatibility", ts)
    return {"typescript": ts, "rust": rust}


def compare_host_conformance(observations: Sequence[Mapping[str, Any]]) -> dict:
    return _runtime("conformance", {"observations": [dict(x) for x in observations]})


def certify_extension_package(
    package: Mapping[str, Any],
    *,
    catalog: Sequence[Mapping[str, Any]] = (),
    evidence: Sequence[Mapping[str, Any]] = (),
    host_observations: Sequence[Mapping[str, Any]] = (),
) -> dict:
    certificate = _runtime(
        "certify",
        {
            "package": dict(package),
            "catalog": [dict(x) for x in catalog],
            "evidence": [dict(x) for x in evidence],
            "host_observations": [dict(x) for x in host_observations],
        },
    )
    if certificate.get("status") == "PASS":
        rust = _guard("check-certificate", certificate)
    else:
        rust = {"ok": False, "authority": "RUST_CERTIFICATE_NOT_ADMITTED"}
    return {"certificate": certificate, "rust": rust}


def verify_certificate(certificate: Mapping[str, Any]) -> dict:
    ts = _runtime("verify-certificate", {"certificate": dict(certificate)})
    rust = _guard("check-certificate", dict(certificate))
    return {"typescript": ts, "rust": rust}


def validate_rollout_transition(from_state: str, to_state: str, certificate: Mapping[str, Any]) -> dict:
    payload = {"from": from_state, "to": to_state, "certificate": dict(certificate)}
    ts = _runtime("transition", payload)
    rust = _guard("check-transition", payload)
    return {"typescript": ts, "rust": rust}
