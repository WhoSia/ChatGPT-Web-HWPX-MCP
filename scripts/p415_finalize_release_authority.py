from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.evidence.p415_authority import (
    PRODUCT,
    build_graph,
    canonical_sha256,
    evaluate_admission,
    make_node,
    verify_continuous_production_attestation,
    verify_graph,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hex64(value: str, field: str) -> str:
    v = str(value or "").lower()
    if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise ValueError(f"{field} must be a 64-character hexadecimal SHA-256")
    return v


def finalize(
    *,
    machine_bundle: Path,
    out: Path,
    release_artifact_id: str,
    release_artifact_sha256: str,
    render_deploy_id: str,
    boundary_receipt: Path,
    boundary_artifact_id: str,
    boundary_artifact_sha256: str,
) -> dict:
    machine = _load(machine_bundle)
    if machine.get("phase") != "P4.15" or machine.get("product") != PRODUCT:
        raise ValueError("machine bundle is not a P4.15 authority bundle")
    graph = machine.get("graph")
    if not isinstance(graph, dict) or verify_graph(graph).get("status") != "PASS":
        raise ValueError("machine evidence graph is invalid")
    exact_head = str(machine.get("exact_head") or "")
    boundary = _load(boundary_receipt)
    if boundary.get("ok") is not True or boundary.get("classification") != "PRODUCTION_BOUNDARY_PASS":
        raise ValueError("production boundary receipt is not PASS")

    observations = boundary.get("observations") if isinstance(boundary.get("observations"), list) else []
    ready = next((x for x in reversed(observations) if x.get("state") == "READY"), None)
    if not ready:
        raise ValueError("boundary receipt contains no READY production observation")
    observed_head = str(ready.get("observed_commit") or "")
    observed_product = str(ready.get("observed_version") or "")
    attestation = verify_continuous_production_attestation(
        expected_head=exact_head,
        expected_product=PRODUCT,
        observed_head=observed_head,
        observed_product=observed_product,
        boundary_pass=True,
    )
    if attestation["status"] != "PASS":
        raise ValueError(f"production attestation failed: {attestation['issues']}")

    subject = {"product": PRODUCT, "exact_head": exact_head}
    nodes = list(graph.get("nodes") or [])
    nodes.extend([
        make_node(
            "RELEASE_ARTIFACT",
            "release-artifact",
            "PASS",
            subject=subject,
            evidence={
                "artifact_id": str(release_artifact_id),
                "sha256": _hex64(release_artifact_sha256, "release_artifact_sha256"),
            },
        ),
        make_node(
            "RENDER_DEPLOY",
            "render-deploy",
            "PASS",
            subject=subject,
            evidence={"deploy_id": str(render_deploy_id), "observed_head": observed_head, "observed_product": observed_product},
        ),
        make_node(
            "PRODUCTION_BOUNDARY",
            "production-boundary",
            "PASS",
            subject=subject,
            evidence={
                "artifact_id": str(boundary_artifact_id),
                "sha256": _hex64(boundary_artifact_sha256, "boundary_artifact_sha256"),
                "classification": boundary.get("classification"),
            },
        ),
        make_node(
            "PRODUCTION_ATTESTATION",
            "continuous-production-attestation",
            "PASS",
            subject=subject,
            evidence={
                "observed_head": observed_head,
                "observed_product": observed_product,
                "attestation_sha256": attestation["attestation_sha256"],
            },
        ),
    ])
    final_graph = build_graph(exact_head=exact_head, nodes=nodes, edges=graph.get("edges") or [])
    verification = verify_graph(final_graph)
    admission = evaluate_admission(final_graph, claim_native_fidelity=False)
    if verification["status"] != "PASS" or admission["verdict"] != "PASS":
        raise RuntimeError(f"final release authority did not admit: verification={verification['status']} admission={admission['verdict']}")

    payload = {
        "schema": "chatgpt-web-hwpx-mcp/p415/final-release-authority/v1",
        "phase": "P4.15",
        "product": PRODUCT,
        "exact_head": exact_head,
        "release_artifact_id": str(release_artifact_id),
        "render_deploy_id": str(render_deploy_id),
        "boundary_artifact_id": str(boundary_artifact_id),
        "graph": final_graph,
        "verification": verification,
        "production_attestation": attestation,
        "admission": admission,
        "native_world_contact": "PENDING",
        "native_pass_claimed": False,
        "verdict": "P415_RELEASE_ADMISSION_PASS_NATIVE_WORLD_CONTACT_PENDING",
        "authority": "P415_FINAL_SELF_VERIFYING_RELEASE_AUTHORITY",
    }
    payload["bundle_sha256"] = canonical_sha256(payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "phase": payload["phase"],
        "product": payload["product"],
        "exact_head": exact_head,
        "graph": verification["status"],
        "admission": admission["verdict"],
        "native_world_contact": payload["native_world_contact"],
        "bundle_sha256": payload["bundle_sha256"],
        "out": str(out),
    }, ensure_ascii=False))
    return payload


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--machine-bundle", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--release-artifact-id", required=True)
    p.add_argument("--release-artifact-sha256", required=True)
    p.add_argument("--render-deploy-id", required=True)
    p.add_argument("--boundary-receipt", type=Path, required=True)
    p.add_argument("--boundary-artifact-id", required=True)
    p.add_argument("--boundary-artifact-sha256", required=True)
    a = p.parse_args()
    finalize(
        machine_bundle=a.machine_bundle,
        out=a.out,
        release_artifact_id=a.release_artifact_id,
        release_artifact_sha256=a.release_artifact_sha256,
        render_deploy_id=a.render_deploy_id,
        boundary_receipt=a.boundary_receipt,
        boundary_artifact_id=a.boundary_artifact_id,
        boundary_artifact_sha256=a.boundary_artifact_sha256,
    )
