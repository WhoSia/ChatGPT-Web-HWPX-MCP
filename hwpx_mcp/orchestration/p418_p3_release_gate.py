"""P4.18-P3 production readiness gate: deny missing/unauthenticated evidence.

This is a diagnostic verdict, never a deploy or mutation authorization.
"""
from __future__ import annotations
from collections.abc import Mapping

REQUIRED = (
    "trusted_host_authentication",
    "host_secret_custody",
    "confirmed_consent_e2e",
    "server_owned_task_binding",
    "durable_document_commit_e2e",
    "concurrent_mutation_idempotency",
    "crash_after_commit_reconciliation",
    "native_hwpx_fidelity",
    "windows_compatibility",
    "exact_head_ci",
    "exact_head_docker",
    "full_lifecycle",
    "production_boundary",
    "rollback_drill",
    "public_mcp_smoke",
    "performance_slo",
)


def assess_p3_release(evidence: Mapping) -> dict:
    if not isinstance(evidence, Mapping):
        raise ValueError("release evidence must be an object")
    if set(evidence) - {"head_sha", "gates"}:
        raise ValueError("unknown release evidence fields")
    head = evidence.get("head_sha")
    if not isinstance(head, str) or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("exact lowercase git head SHA required")
    gates = evidence.get("gates")
    if not isinstance(gates, Mapping):
        raise ValueError("gates must be an object")
    if set(gates) - set(REQUIRED):
        raise ValueError("unsupported release gate")
    failures = []
    for name in REQUIRED:
        row = gates.get(name)
        if not isinstance(row, Mapping) or set(row) != {"head_sha", "status", "evidence_ref"}:
            failures.append(name)
            continue
        ref = row["evidence_ref"]
        if row["status"] != "PASS" or row["head_sha"] != head or not isinstance(ref, str) or not ref.strip():
            failures.append(name)
    return {
        "schema": "chatgpt-web-hwpx-mcp/p4.18-p3/release-assessment/v1",
        "head_sha": head,
        "required_gate_count": len(REQUIRED),
        "failed_gates": failures,
        "eligible_for_manual_release_review": not failures,
        "authorizes_release": False,
        "authority": "ADVISORY_ONLY_NO_HOST_OR_DEPLOY_AUTHORITY",
    }
