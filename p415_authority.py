from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

PHASE = "P4.15"
PRODUCT = "0.40.0-p4.15"
PARENT_PRODUCT = "0.39.0-p4.14"
LEGACY_PARENT_HEAD = "43039e416fcd32baf2f01827b5decc77d0c81439"
PARENT_HEAD = "c90eeeba4a832ae9c61a7fe83498961b84668cca"
SCHEMA = "chatgpt-web-hwpx-mcp/p415/release-authority-graph/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

OBSERVED_KINDS = {
    "GIT_EXACT_HEAD", "GIT_ANCESTRY", "CI", "FULL_LIFECYCLE", "EXACT_HEAD_DOCKER",
    "RELEASE_ARTIFACT", "RENDER_DEPLOY", "PRODUCTION_BOUNDARY", "NATIVE_HANCOM",
    "ROLLBACK_TARGET", "PRODUCTION_ATTESTATION",
}
DERIVED_KINDS = {"RELEASE_ADMISSION", "ROLLBACK_AUTHORITY", "NATIVE_HOSTED_CONFORMANCE"}
MACHINE_REQUIRED = {
    "GIT_EXACT_HEAD", "GIT_ANCESTRY", "CI", "FULL_LIFECYCLE",
    "EXACT_HEAD_DOCKER", "RELEASE_ARTIFACT", "RENDER_DEPLOY",
    "PRODUCTION_BOUNDARY", "PRODUCTION_ATTESTATION",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def authority_contract() -> dict:
    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": SCHEMA,
        "immutable_parent": {"product": PARENT_PRODUCT, "exact_head": PARENT_HEAD},
        "history_rewrite_equivalence": {"legacy_exact_head": LEGACY_PARENT_HEAD, "rewritten_exact_head": PARENT_HEAD, "reason": "HUMAN_ATTRIBUTION_REWRITE_ONLY"},
        "evidence_planes": ["SOURCE_LINEAGE", "BUILD_TEST", "ARTIFACT", "HOSTED_RUNTIME", "NATIVE_RUNTIME", "ROLLBACK"],
        "truth_layers": {
            "OBSERVED": "Externally observed or independently reproducible evidence.",
            "DERIVED": "Claim computed only from declared graph predecessors.",
            "PENDING": "Evidence explicitly absent or unavailable; never coerced to PASS.",
        },
        "native_rule": "HOSTED_SUCCESS_NEVER_IMPLIES_NATIVE_HANCOM_PASS",
        "admission_rule": "MACHINE_RELEASE_MAY_PASS_WITH_NATIVE_PENDING_UNLESS_NATIVE_FIDELITY_IS_CLAIMED",
        "rollback_rule": "TARGET_MUST_BE_CERTIFIED_AUTHORIZED_ANCESTOR_WITH_MATCHING_ARTIFACT_IDENTITY",
        "drift_rule": "CONTINUOUS_ATTESTATION_CAN_HOLD_AUTHORITY_BUT CANNOT REWRITE SEALED RELEASE IDENTITY",
        "authority": "P415_SELF_VERIFYING_RELEASE_AUTHORITY_CONTRACT",
    }
    result["contract_sha256"] = canonical_sha256(result)
    return result


def make_node(kind: str, node_id: str, status: str, *, subject: Mapping[str, Any], evidence: Mapping[str, Any], truth: str = "OBSERVED") -> dict:
    payload = {
        "kind": str(kind),
        "node_id": str(node_id),
        "status": str(status),
        "truth": str(truth),
        "subject": dict(subject),
        "evidence": dict(evidence),
    }
    payload["node_sha256"] = canonical_sha256(payload)
    return payload


def make_edge(source: str, target: str, relation: str) -> dict:
    payload = {"source": str(source), "target": str(target), "relation": str(relation)}
    payload["edge_sha256"] = canonical_sha256(payload)
    return payload


def build_graph(*, exact_head: str, nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]] = ()) -> dict:
    graph = {
        "schema": SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "exact_head": exact_head,
        "parent": {"product": PARENT_PRODUCT, "exact_head": PARENT_HEAD},
        "nodes": [dict(x) for x in nodes],
        "edges": [dict(x) for x in edges],
    }
    graph["graph_sha256"] = canonical_sha256(graph)
    return graph


def _node_issue(node: Mapping[str, Any], exact_head: str) -> list[dict]:
    issues: list[dict] = []
    kind = str(node.get("kind") or "")
    truth = str(node.get("truth") or "")
    subject = node.get("subject") if isinstance(node.get("subject"), Mapping) else {}
    evidence = node.get("evidence") if isinstance(node.get("evidence"), Mapping) else {}
    if kind not in OBSERVED_KINDS | DERIVED_KINDS:
        issues.append({"code": "UNKNOWN_EVIDENCE_KIND", "node_id": node.get("node_id")})
    if truth not in {"OBSERVED", "DERIVED", "PENDING"}:
        issues.append({"code": "INVALID_TRUTH_LAYER", "node_id": node.get("node_id")})
    if kind in OBSERVED_KINDS and truth == "DERIVED":
        issues.append({"code": "OBSERVED_KIND_CANNOT_BE_DERIVED", "node_id": node.get("node_id")})
    if kind in DERIVED_KINDS and truth == "OBSERVED":
        issues.append({"code": "DERIVED_KIND_CANNOT_BE_OBSERVED", "node_id": node.get("node_id")})
    claimed = str(subject.get("exact_head") or "")
    if claimed and claimed != exact_head:
        issues.append({"code": "NODE_EXACT_HEAD_MISMATCH", "node_id": node.get("node_id"), "claimed": claimed})
    product = str(subject.get("product") or "")
    if product and product != PRODUCT:
        issues.append({"code": "NODE_PRODUCT_MISMATCH", "node_id": node.get("node_id"), "claimed": product})
    if kind == "GIT_EXACT_HEAD" and (not _HEX40.fullmatch(exact_head) or evidence.get("observed_head") != exact_head):
        issues.append({"code": "EXACT_HEAD_NOT_OBSERVED", "node_id": node.get("node_id")})
    if kind == "GIT_ANCESTRY" and evidence.get("ancestor") != PARENT_HEAD:
        issues.append({"code": "PARENT_ANCESTRY_NOT_PROVEN", "node_id": node.get("node_id")})
    if kind in {"RELEASE_ARTIFACT", "PRODUCTION_BOUNDARY", "NATIVE_HANCOM"}:
        digest = evidence.get("sha256")
        if digest is not None and not _HEX64.fullmatch(str(digest).lower()):
            issues.append({"code": "INVALID_EVIDENCE_DIGEST", "node_id": node.get("node_id")})
    expected = dict(node)
    digest = expected.pop("node_sha256", None)
    if digest != canonical_sha256(expected):
        issues.append({"code": "NODE_DIGEST_MISMATCH", "node_id": node.get("node_id")})
    return issues


def verify_graph(graph: Mapping[str, Any]) -> dict:
    issues: list[dict] = []
    if graph.get("schema") != SCHEMA or graph.get("phase") != PHASE or graph.get("product") != PRODUCT:
        issues.append({"code": "GRAPH_IDENTITY_MISMATCH"})
    exact_head = str(graph.get("exact_head") or "")
    if not _HEX40.fullmatch(exact_head):
        issues.append({"code": "INVALID_GRAPH_EXACT_HEAD"})
    if graph.get("parent") != {"product": PARENT_PRODUCT, "exact_head": PARENT_HEAD}:
        issues.append({"code": "IMMUTABLE_PARENT_MISMATCH"})
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    by_id: dict[str, Mapping[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, Mapping):
            issues.append({"code": "NODE_NOT_OBJECT"})
            continue
        node_id = str(node.get("node_id") or "")
        if not node_id or node_id in by_id:
            issues.append({"code": "DUPLICATE_OR_EMPTY_NODE_ID", "node_id": node_id})
        by_id[node_id] = node
        issues.extend(_node_issue(node, exact_head))
    for edge in edges:
        if not isinstance(edge, Mapping):
            issues.append({"code": "EDGE_NOT_OBJECT"})
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source not in by_id or target not in by_id:
            issues.append({"code": "DANGLING_EDGE", "source": source, "target": target})
        expected = dict(edge)
        digest = expected.pop("edge_sha256", None)
        if digest != canonical_sha256(expected):
            issues.append({"code": "EDGE_DIGEST_MISMATCH", "source": source, "target": target})
    expected_graph = dict(graph)
    digest = expected_graph.pop("graph_sha256", None)
    if digest != canonical_sha256(expected_graph):
        issues.append({"code": "GRAPH_DIGEST_MISMATCH"})
    result = {
        "phase": PHASE,
        "status": "PASS" if not issues else "FAIL",
        "verified": not issues,
        "issues": issues,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "exact_head": exact_head,
        "authority": "P415_CROSS_LAYER_EVIDENCE_GRAPH_VERIFIER",
    }
    result["verification_sha256"] = canonical_sha256(result)
    return result


def _kind_nodes(graph: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for node in graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []:
        if isinstance(node, Mapping):
            out.setdefault(str(node.get("kind") or ""), []).append(node)
    return out


def evaluate_admission(graph: Mapping[str, Any], *, claim_native_fidelity: bool = False) -> dict:
    verified = verify_graph(graph)
    if not verified["verified"]:
        verdict = "FAIL"
        issues = [{"code": "EVIDENCE_GRAPH_INVALID"}] + verified["issues"]
    else:
        kinds = _kind_nodes(graph)
        required = set(MACHINE_REQUIRED)
        if claim_native_fidelity:
            required.add("NATIVE_HANCOM")
        missing = sorted(kind for kind in required if not kinds.get(kind))
        failing = sorted(kind for kind in required if kinds.get(kind) and not any(str(n.get("status")) == "PASS" for n in kinds[kind]))
        if failing:
            verdict, issues = "FAIL", [{"code": "REQUIRED_EVIDENCE_FAILED", "kinds": failing}]
        elif missing:
            verdict, issues = "HOLD", [{"code": "REQUIRED_EVIDENCE_MISSING", "kinds": missing}]
        else:
            verdict, issues = "PASS", []
        if not claim_native_fidelity and not kinds.get("NATIVE_HANCOM"):
            issues.append({"code": "NATIVE_WORLD_CONTACT_PENDING", "blocking": False})
    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "exact_head": graph.get("exact_head"),
        "verdict": verdict,
        "admitted": verdict == "PASS",
        "claim_native_fidelity": bool(claim_native_fidelity),
        "native_status": "REQUIRED" if claim_native_fidelity else ("PRESENT" if _kind_nodes(graph).get("NATIVE_HANCOM") else "PENDING"),
        "issues": issues,
        "authority": "P415_AUTONOMOUS_RELEASE_ADMISSION_CONTROL",
    }
    result["decision_sha256"] = canonical_sha256(result)
    return result


def reconcile_native_hosted(*, hosted: Mapping[str, Any], native: Mapping[str, Any] | None) -> dict:
    hosted_pass = hosted.get("status") == "PASS"
    if not native:
        status = "NATIVE_PENDING"
    elif native.get("status") == "PASS":
        status = "CONFORMANT" if hosted_pass else "HOSTED_FAILURE_NATIVE_PASS"
    elif native.get("status") == "FAIL":
        status = "NATIVE_DIVERGENCE" if hosted_pass else "BOTH_FAIL"
    else:
        status = "NATIVE_PENDING"
    result = {
        "phase": PHASE,
        "status": status,
        "hosted_status": hosted.get("status"),
        "native_status": native.get("status") if native else "PENDING",
        "native_inferred_from_hosted": False,
        "authority": "P415_NATIVE_HOSTED_CONFORMANCE_RECONCILIATION",
    }
    result["reconciliation_sha256"] = canonical_sha256(result)
    return result


def verify_continuous_production_attestation(*, expected_head: str, expected_product: str, observed_head: str, observed_product: str, boundary_pass: bool) -> dict:
    issues = []
    if observed_head != expected_head:
        issues.append({"code": "PRODUCTION_HEAD_DRIFT", "expected": expected_head, "observed": observed_head})
    if observed_product != expected_product:
        issues.append({"code": "PRODUCTION_PRODUCT_DRIFT", "expected": expected_product, "observed": observed_product})
    if boundary_pass is not True:
        issues.append({"code": "PRODUCTION_BOUNDARY_NOT_PASS"})
    result = {
        "phase": PHASE,
        "status": "PASS" if not issues else "HOLD",
        "authority_intact": not issues,
        "issues": issues,
        "expected_head": expected_head,
        "observed_head": observed_head,
        "expected_product": expected_product,
        "observed_product": observed_product,
        "authority": "P415_CONTINUOUS_PRODUCTION_ATTESTATION",
    }
    result["attestation_sha256"] = canonical_sha256(result)
    return result


def evaluate_rollback(*, current_head: str, target_release: Mapping[str, Any], ancestry_proven: bool, artifact_sha256_observed: str) -> dict:
    issues = []
    target_head = str(target_release.get("exact_head") or "")
    target_digest = str(target_release.get("artifact_sha256") or "").lower()
    if not _HEX40.fullmatch(target_head):
        issues.append({"code": "INVALID_ROLLBACK_TARGET_HEAD"})
    if target_release.get("certification_status") != "CERTIFIED":
        issues.append({"code": "ROLLBACK_TARGET_NOT_CERTIFIED"})
    if ancestry_proven is not True:
        issues.append({"code": "ROLLBACK_TARGET_NOT_PROVEN_ANCESTOR"})
    if not _HEX64.fullmatch(target_digest) or target_digest != str(artifact_sha256_observed).lower():
        issues.append({"code": "ROLLBACK_ARTIFACT_IDENTITY_MISMATCH"})
    if target_head == current_head:
        issues.append({"code": "ROLLBACK_TARGET_EQUALS_CURRENT"})
    result = {
        "phase": PHASE,
        "status": "PASS" if not issues else "DENIED",
        "authorized": not issues,
        "current_head": current_head,
        "target_head": target_head,
        "issues": issues,
        "authority": "P415_PROVENANCE_AWARE_ROLLBACK_CERTIFIER",
    }
    result["rollback_sha256"] = canonical_sha256(result)
    return result
