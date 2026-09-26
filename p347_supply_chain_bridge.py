from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from p346_platform_bridge import execute_wasm, validate_extension
from p347_trust import normalize_trust_policy, verify_build_provenance_pair, verify_host_observations

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


def _evidence_sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def derive_certification_evidence(
    package: Mapping[str, Any],
    *,
    rebuild_package: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]] = (),
    host_observations: Sequence[Mapping[str, Any]] = (),
) -> dict:
    normalized = normalize_extension_package(package)
    closure = verify_dependency_closure(package, catalog)
    reproducibility = compare_reproducible_builds(package, rebuild_package)
    conformance = compare_host_conformance(host_observations)
    normalized_policy = normalize_trust_policy(trust_policy)
    provenance_trust = verify_build_provenance_pair(package, rebuild_package, normalized_policy)
    host_trust = verify_host_observations(host_observations, normalized_policy)

    manifest = copy.deepcopy(dict(package.get("extension") or {}))
    module_base64 = str(package.get("module_base64") or "")
    checked_manifest = validate_extension(manifest)
    first = execute_wasm(manifest, module_base64)
    second = execute_wasm(manifest, module_base64)
    deterministic = _stable(first) == _stable(second)
    sandbox = first.get("sandbox") if isinstance(first, dict) else {}
    sandbox_pass = (
        deterministic
        and sandbox.get("no_imports") is True
        and sandbox.get("linear_memory") is False
        and sandbox.get("tables") is False
        and sandbox.get("filesystem") is False
        and sandbox.get("network") is False
        and int(sandbox.get("host_functions") or 0) == 0
    )

    negative_results: dict[str, bool] = {}
    try:
        raw = bytearray(base64.b64decode(module_base64, validate=True))
        if not raw:
            raise RuntimeError("empty module")
        raw[-1] ^= 1
        execute_wasm(manifest, base64.b64encode(bytes(raw)).decode("ascii"))
        negative_results["module_tamper_rejected"] = False
    except Exception:
        negative_results["module_tamper_rejected"] = True

    try:
        escalation = copy.deepcopy(manifest)
        for capability in escalation.get("capabilities") or []:
            capability["effect"] = "DOCUMENT_MUTATION"
        for tool in escalation.get("tools") or []:
            tool["effect"] = "DOCUMENT_MUTATION"
        validate_extension(escalation)
        negative_results["effect_escalation_rejected"] = False
    except Exception:
        negative_results["effect_escalation_rejected"] = True

    memory = bytes.fromhex(
        "0061736d01000000"
        "0105016000017f"
        "03020100"
        "0503010001"
        "070c0108703334365f72756e0000"
        "0a06010400412a0b"
    )
    try:
        memory_manifest = copy.deepcopy(manifest)
        memory_manifest["execution"]["module_sha256"] = hashlib.sha256(memory).hexdigest()
        execute_wasm(memory_manifest, base64.b64encode(memory).decode("ascii"))
        negative_results["memory_section_rejected"] = False
    except Exception:
        negative_results["memory_section_rejected"] = True

    negative_pass = all(negative_results.values())
    gates = [
        ("MANIFEST_VALID", True, checked_manifest),
        ("MODULE_HASH_BOUND", normalized.get("module_sha256") == manifest.get("execution", {}).get("module_sha256"), normalized),
        (
            "PROVENANCE_SUBJECT_BOUND",
            bool(provenance_trust.get("trusted")),
            {"build_attestation": normalized.get("build_attestation"), "trust": provenance_trust},
        ),
        ("DEPENDENCY_CLOSURE_VALID", True, closure),
        (
            "REPRODUCIBLE_BUILD_PASS",
            bool(reproducibility.get("reproducible"))
            and bool(provenance_trust.get("independent_builder_roots")),
            {"reproducibility": reproducibility, "trust": provenance_trust},
        ),
        ("DETERMINISM_REPLAY_PASS", deterministic, {"first": first, "second": second}),
        ("SANDBOX_PASS", sandbox_pass, first),
        (
            "HOST_CONFORMANCE_PASS",
            conformance.get("verdict") == "PASS" and bool(host_trust.get("trusted")),
            {"conformance": conformance, "trust": host_trust},
        ),
        ("NEGATIVE_CONTROLS_PASS", negative_pass, negative_results),
    ]
    evidence = [
        {
            "gate": gate,
            "status": "PASS" if passed else "FAIL",
            "evidence_sha256": _evidence_sha(receipt),
        }
        for gate, passed, receipt in gates
    ]
    return {
        "evidence": evidence,
        "normalized_package": normalized,
        "dependency_closure": closure,
        "reproducibility": reproducibility,
        "host_conformance": conformance,
        "trust_policy": normalized_policy,
        "provenance_trust": provenance_trust,
        "host_trust": host_trust,
        "execution": {
            "first_receipt_sha256": _evidence_sha(first),
            "second_receipt_sha256": _evidence_sha(second),
            "deterministic": deterministic,
            "sandbox_pass": sandbox_pass,
            "negative_controls": negative_results,
        },
        "authority": "P347_DERIVED_CERTIFICATION_EVIDENCE_PASS"
        if all(row["status"] == "PASS" for row in evidence)
        else "P347_DERIVED_CERTIFICATION_EVIDENCE_FAIL",
    }


def certify_extension_package(
    package: Mapping[str, Any],
    *,
    rebuild_package: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]] = (),
    host_observations: Sequence[Mapping[str, Any]] = (),
) -> dict:
    derived = derive_certification_evidence(
        package,
        rebuild_package=rebuild_package,
        trust_policy=trust_policy,
        catalog=catalog,
        host_observations=host_observations,
    )
    certificate = _runtime(
        "certify",
        {
            "package": dict(package),
            "catalog": [dict(x) for x in catalog],
            "evidence": derived["evidence"],
            "host_observations": [dict(x) for x in host_observations],
        },
    )
    if certificate.get("status") == "PASS":
        rust = _guard("check-certificate", certificate)
    else:
        rust = {"ok": False, "authority": "RUST_CERTIFICATE_NOT_ADMITTED"}
    return {"certificate": certificate, "rust": rust, "derived_evidence": derived}


def verify_certificate(certificate: Mapping[str, Any]) -> dict:
    ts = _runtime("verify-certificate", {"certificate": dict(certificate)})
    rust = _guard("check-certificate", dict(certificate))
    return {"typescript": ts, "rust": rust}


def validate_rollout_transition(from_state: str, to_state: str, certificate: Mapping[str, Any]) -> dict:
    payload = {"from": from_state, "to": to_state, "certificate": dict(certificate)}
    ts = _runtime("transition", payload)
    rust = _guard("check-transition", payload)
    return {"typescript": ts, "rust": rust}


def validate_certified_rollback(
    current_certificate: Mapping[str, Any],
    target_certificate: Mapping[str, Any],
) -> dict:
    payload = {
        "current_certificate": dict(current_certificate),
        "target_certificate": dict(target_certificate),
    }
    ts = _runtime("rollback", payload)
    rust = _guard("check-rollback", payload)
    if ts.get("current_package_id") != rust.get("current_package_id"):
        raise RuntimeError("P3.47 rollback current-package cross-runtime divergence")
    if ts.get("target_package_id") != rust.get("target_package_id"):
        raise RuntimeError("P3.47 rollback target-package cross-runtime divergence")
    return {
        "typescript": ts,
        "rust": rust,
        "authority": "CROSS_RUNTIME_CERTIFIED_ROLLBACK_PASS",
    }
