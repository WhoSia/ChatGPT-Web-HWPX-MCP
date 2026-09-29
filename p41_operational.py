from __future__ import annotations

import gc
import hashlib
import importlib.metadata as md
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from typing import Any, Callable, Mapping

PRODUCT = "0.27.0-p4.1"
PHASE = "P4.1"
P41_BASELINE_PYTHON_HWPX = "6.5.0"
PINNED_PYTHON_HWPX = "6.6.0"
DEFAULT_MIGRATION_CANDIDATE = "6.6.0"

_FAILURES = {
    "AUTH_REQUIRED": {
        "retryable": True,
        "user_message": "Authentication is required or expired.",
        "next_action": "Reconnect or refresh authorization, then retry the same operation.",
        "operator_action": "Verify OAuth metadata, token issuance, and protected-resource configuration.",
    },
    "CONCURRENCY_CONFLICT": {
        "retryable": True,
        "user_message": "The document changed while this operation was being prepared.",
        "next_action": "Refresh the document state and retry against the latest revision.",
        "operator_action": "Inspect revision/lease/CAS receipts; do not bypass optimistic concurrency.",
    },
    "COMPATIBILITY_UNSUPPORTED": {
        "retryable": False,
        "user_message": "The requested runtime or dependency combination is not certified for this release.",
        "next_action": "Use the pinned supported runtime or run the upgrade compatibility harness first.",
        "operator_action": "Collect migration evidence and promote only after the P4.1 upgrade gate passes.",
    },
    "DURABLE_STORE_UNAVAILABLE": {
        "retryable": True,
        "user_message": "Durable product state is temporarily unavailable.",
        "next_action": "Retry after the service recovers; do not assume the previous mutation committed.",
        "operator_action": "Check Postgres reachability, durable receipts, and recovery logs.",
    },
    "HOST_CAPABILITY_MISMATCH": {
        "retryable": False,
        "user_message": "The active host does not satisfy the certified capability contract.",
        "next_action": "Use a compatible host adapter/profile or recertify the environment.",
        "operator_action": "Compare P3.46 adapter and P3.47/P3.49 host-conformance receipts.",
    },
    "EXTERNAL_WORLD_CONTACT_REQUIRED": {
        "retryable": True,
        "user_message": "This result requires external render or native-application evidence that is not currently available.",
        "next_action": "Run the required world-contact step and resume with its receipt.",
        "operator_action": "Verify the render/Hancom/capture boundary rather than substituting structural evidence.",
    },
    "INPUT_INVALID": {
        "retryable": False,
        "user_message": "The request does not satisfy the current product contract.",
        "next_action": "Correct the indicated input or use the relevant contract-inspection tool.",
        "operator_action": "Keep validation fail-closed; improve diagnostics if the invalid field is not identifiable.",
    },
    "NOT_FOUND": {
        "retryable": False,
        "user_message": "The requested document, revision, package, or resource was not found.",
        "next_action": "Refresh identifiers and retry only with an existing resource.",
        "operator_action": "Check retention, ownership, and exact content-addressed identifiers.",
    },
    "INTERNAL_PRODUCT_FAILURE": {
        "retryable": False,
        "user_message": "The product encountered an unclassified internal failure.",
        "next_action": "Preserve the operation context and diagnostic receipt; avoid repeated destructive retries.",
        "operator_action": "Reproduce with the release head and classify the failure before changing behavior.",
    },
}

def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()

def _version(distribution: str) -> str | None:
    try:
        return md.version(distribution)
    except md.PackageNotFoundError:
        return None

def _node_version() -> str | None:
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        return None
    try:
        proc = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None

def operational_readiness_contract() -> dict:
    contract = {
        "schema": "chatgpt-web-hwpx-mcp/p4.1/operational-readiness-contract/v1",
        "phase": PHASE,
        "product": PRODUCT,
        "mode": "MAINTENANCE_FIRST_PRODUCT_BASELINE",
        "axes": [
            "REAL_WORLD_COMPATIBILITY",
            "LATENCY_AND_MEMORY",
            "FAILURE_TAXONOMY",
            "ACTIONABLE_DIAGNOSTICS",
            "UPGRADE_MIGRATION",
            "RELEASE_OPERATIONAL_READINESS",
        ],
        "p41_baseline_python_hwpx_pin": P41_BASELINE_PYTHON_HWPX,
        "production_python_hwpx_pin": PINNED_PYTHON_HWPX,
        "production_pin_authority": "P4.2",
        "default_migration_candidate": DEFAULT_MIGRATION_CANDIDATE,
        "new_architecture_by_default": False,
        "measurement_is_not_world_contact": True,
        "candidate_compatibility_does_not_change_production_pin": True,
    }
    return {**contract, "contract_sha256": _sha(contract)}

def runtime_compatibility_matrix(candidate_version: str = DEFAULT_MIGRATION_CANDIDATE) -> dict:
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(candidate_version)):
        raise ValueError("candidate_version must be a numeric dotted version")
    python_hwpx = _version("python-hwpx")
    mcp_version = _version("mcp")
    lxml_version = _version("lxml")
    node_version = _node_version()
    python_supported = sys.version_info[:2] == (3, 12)
    hwpx_supported = python_hwpx == PINNED_PYTHON_HWPX
    mcp_supported = mcp_version == "2.2.0"
    lxml_major = int(lxml_version.split(".", 1)[0]) if lxml_version and lxml_version[0].isdigit() else -1
    lxml_supported = 5 <= lxml_major < 7
    rows = [
        {"component": "python", "observed": platform.python_version(), "expected": "3.12.x", "status": "SUPPORTED" if python_supported else "UNVALIDATED"},
        {"component": "python-hwpx", "observed": python_hwpx, "expected": PINNED_PYTHON_HWPX, "status": "SUPPORTED_PINNED" if hwpx_supported else "UNVALIDATED_RUNTIME"},
        {"component": "mcp", "observed": mcp_version, "expected": "2.2.0", "status": "SUPPORTED" if mcp_supported else "UNVALIDATED"},
        {"component": "lxml", "observed": lxml_version, "expected": ">=5,<7", "status": "SUPPORTED" if lxml_supported else "UNVALIDATED"},
        {"component": "node", "observed": node_version, "expected": "runtime available", "status": "SUPPORTED" if node_version else "MISSING"},
        {"component": "python-hwpx migration candidate", "observed": candidate_version, "expected": PINNED_PYTHON_HWPX, "status": "PROMOTED_BY_P4.2" if str(candidate_version) == PINNED_PYTHON_HWPX else "REQUIRES_MIGRATION_GATE"},
    ]
    ready = python_supported and hwpx_supported and mcp_supported and lxml_supported and bool(node_version)
    payload = {
        "phase": PHASE,
        "product": PRODUCT,
        "runtime_status": "SUPPORTED_BASELINE" if ready else "DEGRADED_OR_UNVALIDATED",
        "rows": rows,
        "production_pin_unchanged": True,
    }
    return {**payload, "matrix_sha256": _sha(payload)}

def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]

def profile_callable(name: str, fn: Callable[[], Any], sample_count: int = 3, hard_ceiling_ms: float | None = None) -> dict:
    count = int(sample_count)
    if count < 1 or count > 10:
        raise ValueError("sample_count must be between 1 and 10")
    timings: list[float] = []
    gc.collect()
    tracemalloc.start()
    try:
        for _ in range(count):
            started = time.perf_counter()
            fn()
            timings.append((time.perf_counter() - started) * 1000.0)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    p50 = statistics.median(timings)
    p95 = _percentile(timings, 0.95)
    status = "PASS" if hard_ceiling_ms is None or p95 <= hard_ceiling_ms else "REGRESSION"
    return {
        "operation": name,
        "samples": count,
        "latency_ms": {
            "min": round(min(timings), 3),
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "max": round(max(timings), 3),
        },
        "python_peak_bytes": int(peak),
        "hard_ceiling_ms": hard_ceiling_ms,
        "status": status,
    }

def profile_operations(specs: Mapping[str, tuple[Callable[[], Any], float | None]], sample_count: int = 3) -> dict:
    operations = [
        profile_callable(name, fn, sample_count=sample_count, hard_ceiling_ms=ceiling)
        for name, (fn, ceiling) in specs.items()
    ]
    payload = {
        "phase": PHASE,
        "product": PRODUCT,
        "sample_count": int(sample_count),
        "operations": operations,
        "status": "PASS" if all(row["status"] == "PASS" for row in operations) else "REGRESSION",
        "interpretation": "CI/runtime baseline only; not native-render or human-visual authority",
    }
    return {**payload, "receipt_sha256": _sha(payload)}

def diagnose_failure(message: str = "", code: str = "") -> dict:
    text = (str(code) + " " + str(message))[:1024].lower()
    category = "INTERNAL_PRODUCT_FAILURE"
    if any(k in text for k in ("401", "oauth", "authentication", "invalid_token", "authorization")):
        category = "AUTH_REQUIRED"
    elif any(k in text for k in ("cas mismatch", "stale revision", "stale generation", "lease", "concurrency")):
        category = "CONCURRENCY_CONFLICT"
    elif any(k in text for k in ("unsupported version", "compatibility", "dependency version", "requires python-hwpx")):
        category = "COMPATIBILITY_UNSUPPORTED"
    elif any(k in text for k in ("postgres", "database", "durable_store", "durable store", "connection refused")):
        category = "DURABLE_STORE_UNAVAILABLE"
    elif any(k in text for k in ("adapter profile", "host conformance", "capability mismatch", "host capability")):
        category = "HOST_CAPABILITY_MISMATCH"
    elif any(k in text for k in ("world contact", "hancom", "native render", "external evidence", "render required")):
        category = "EXTERNAL_WORLD_CONTACT_REQUIRED"
    elif any(k in text for k in ("not found", "filenotfound", "missing resource", "missing package")):
        category = "NOT_FOUND"
    elif any(k in text for k in ("invalid", "schema", "valueerror", "malformed", "must be")):
        category = "INPUT_INVALID"
    row = _FAILURES[category]
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "category": category,
        **row,
        "safe_context": {"code": str(code)[:128] or None},
        "raw_exception_echoed": False,
    }

def evaluate_upgrade_candidate(candidate_version: str, evidence: Mapping[str, Any]) -> dict:
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(candidate_version)):
        raise ValueError("candidate_version must be a numeric dotted version")
    required = ["candidate_probe", "legacy_compatibility", "product_workflow", "full_lifecycle", "docker_smoke"]
    normalized = {key: bool(evidence.get(key)) for key in required}
    missing = [key for key, passed in normalized.items() if not passed]
    verdict = "READY_FOR_CONTROLLED_CANARY" if not missing else "HOLD"
    payload = {
        "phase": PHASE,
        "product": PRODUCT,
        "current_pin": PINNED_PYTHON_HWPX,
        "candidate_version": str(candidate_version),
        "evidence": normalized,
        "missing_or_failed_evidence": missing,
        "verdict": verdict,
        "production_pin_unchanged": True,
        "authority": "P41_MIGRATION_EVIDENCE_ADJUDICATION_NOT_AUTOMATIC_PROMOTION",
    }
    return {**payload, "evidence_sha256": _sha(payload)}
