from __future__ import annotations

from p415_authority import (
    PARENT_HEAD,
    PRODUCT,
    build_graph,
    evaluate_admission,
    evaluate_rollback,
    make_node,
    reconcile_native_hosted,
    verify_continuous_production_attestation,
    verify_graph,
)


def _subject(head: str) -> dict:
    return {"product": PRODUCT, "exact_head": head}


def main() -> None:
    head = "a" * 40
    nodes = [
        make_node("GIT_EXACT_HEAD", "head", "PASS", subject=_subject(head), evidence={"observed_head": head}),
        make_node("GIT_ANCESTRY", "ancestry", "PASS", subject=_subject(head), evidence={"ancestor": PARENT_HEAD, "descendant": head}),
        make_node("CI", "ci", "PASS", subject=_subject(head), evidence={"run_id": "ci"}),
        make_node("FULL_LIFECYCLE", "lifecycle", "PASS", subject=_subject(head), evidence={"run_id": "lifecycle"}),
        make_node("EXACT_HEAD_DOCKER", "docker", "PASS", subject=_subject(head), evidence={"image": "hwpx-mcp-p415:" + head}),
        make_node("RELEASE_ARTIFACT", "artifact", "PASS", subject=_subject(head), evidence={"sha256": "b" * 64}),
        make_node("RENDER_DEPLOY", "render", "PASS", subject=_subject(head), evidence={"deploy_id": "dep-test"}),
        make_node("PRODUCTION_BOUNDARY", "boundary", "PASS", subject=_subject(head), evidence={"sha256": "c" * 64}),
        make_node("PRODUCTION_ATTESTATION", "attestation", "PASS", subject=_subject(head), evidence={"observed_head": head, "observed_product": PRODUCT}),
    ]
    graph = build_graph(exact_head=head, nodes=nodes)
    assert verify_graph(graph)["status"] == "PASS"
    admission = evaluate_admission(graph)
    assert admission["verdict"] == "PASS"
    assert admission["native_status"] == "PENDING"
    assert any(x["code"] == "NATIVE_WORLD_CONTACT_PENDING" for x in admission["issues"])
    native_required = evaluate_admission(graph, claim_native_fidelity=True)
    assert native_required["verdict"] == "HOLD"
    assert reconcile_native_hosted(hosted={"status": "PASS"}, native=None)["status"] == "NATIVE_PENDING"

    drift = verify_continuous_production_attestation(
        expected_head=head,
        expected_product=PRODUCT,
        observed_head="d" * 40,
        observed_product=PRODUCT,
        boundary_pass=True,
    )
    assert drift["status"] == "HOLD"

    target = {"exact_head": PARENT_HEAD, "artifact_sha256": "e" * 64, "certification_status": "CERTIFIED"}
    assert evaluate_rollback(current_head=head, target_release=target, ancestry_proven=True, artifact_sha256_observed="e" * 64)["status"] == "PASS"
    assert evaluate_rollback(current_head=head, target_release=target, ancestry_proven=False, artifact_sha256_observed="e" * 64)["status"] == "DENIED"
    print("P4.15 self-verifying release authority smoke PASS; native world-contact remains unclaimed")


if __name__ == "__main__":
    main()
