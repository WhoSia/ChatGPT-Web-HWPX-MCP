from copy import deepcopy

from hwpx_mcp.evidence.p415_authority import (
    PARENT_HEAD,
    PRODUCT,
    build_graph,
    evaluate_admission,
    evaluate_rollback,
    make_node,
    verify_continuous_production_attestation,
    verify_graph,
)


def subject(head):
    return {"product": PRODUCT, "exact_head": head}


def machine_graph(head="1" * 40):
    nodes = [
        make_node("GIT_EXACT_HEAD", "head", "PASS", subject=subject(head), evidence={"observed_head": head}),
        make_node("GIT_ANCESTRY", "ancestry", "PASS", subject=subject(head), evidence={"ancestor": PARENT_HEAD, "descendant": head}),
        make_node("CI", "ci", "PASS", subject=subject(head), evidence={"run_id": "1"}),
        make_node("FULL_LIFECYCLE", "life", "PASS", subject=subject(head), evidence={"run_id": "2"}),
        make_node("EXACT_HEAD_DOCKER", "docker", "PASS", subject=subject(head), evidence={"image": "x"}),
        make_node("RELEASE_ARTIFACT", "artifact", "PASS", subject=subject(head), evidence={"sha256": "2" * 64}),
        make_node("RENDER_DEPLOY", "render", "PASS", subject=subject(head), evidence={"deploy_id": "dep"}),
        make_node("PRODUCTION_BOUNDARY", "boundary", "PASS", subject=subject(head), evidence={"sha256": "3" * 64}),
        make_node("PRODUCTION_ATTESTATION", "attestation", "PASS", subject=subject(head), evidence={"observed_head": head}),
    ]
    return build_graph(exact_head=head, nodes=nodes)


def test_machine_release_passes_without_claiming_native():
    graph = machine_graph()
    assert verify_graph(graph)["verified"] is True
    verdict = evaluate_admission(graph)
    assert verdict["verdict"] == "PASS"
    assert verdict["native_status"] == "PENDING"


def test_native_claim_is_hard_gate():
    verdict = evaluate_admission(machine_graph(), claim_native_fidelity=True)
    assert verdict["verdict"] == "HOLD"
    assert verdict["admitted"] is False


def test_stale_or_forged_graph_fails():
    graph = machine_graph()
    graph["nodes"][0]["evidence"]["observed_head"] = "f" * 40
    assert verify_graph(graph)["status"] == "FAIL"


def test_wrong_parent_ancestry_fails():
    graph = machine_graph()
    graph["nodes"][1] = make_node("GIT_ANCESTRY", "ancestry", "PASS", subject=subject(graph["exact_head"]), evidence={"ancestor": "9" * 40})
    graph["graph_sha256"] = __import__("p415_authority").canonical_sha256({k: v for k, v in graph.items() if k != "graph_sha256"})
    result = verify_graph(graph)
    assert any(x["code"] == "PARENT_ANCESTRY_NOT_PROVEN" for x in result["issues"])


def test_deployment_drift_holds_authority():
    head = "1" * 40
    result = verify_continuous_production_attestation(
        expected_head=head,
        expected_product=PRODUCT,
        observed_head="4" * 40,
        observed_product=PRODUCT,
        boundary_pass=True,
    )
    assert result["status"] == "HOLD"
    assert result["authority_intact"] is False


def test_uncertified_or_digest_mismatched_rollback_denied():
    head = "1" * 40
    target = {"exact_head": PARENT_HEAD, "artifact_sha256": "5" * 64, "certification_status": "UNVERIFIED"}
    assert evaluate_rollback(current_head=head, target_release=target, ancestry_proven=True, artifact_sha256_observed="5" * 64)["authorized"] is False
    target["certification_status"] = "CERTIFIED"
    assert evaluate_rollback(current_head=head, target_release=target, ancestry_proven=True, artifact_sha256_observed="6" * 64)["authorized"] is False


def test_dangling_or_tampered_edge_fails():
    from hwpx_mcp.evidence.p415_authority import canonical_sha256, make_edge
    graph = machine_graph()
    graph["edges"] = [make_edge("head", "missing-node", "DEPENDS_ON")]
    graph["graph_sha256"] = canonical_sha256({k: v for k, v in graph.items() if k != "graph_sha256"})
    result = verify_graph(graph)
    assert any(x["code"] == "DANGLING_EDGE" for x in result["issues"])

    graph = machine_graph()
    graph["edges"] = [make_edge("head", "ci", "DEPENDS_ON")]
    graph["edges"][0]["relation"] = "FORGED"
    graph["graph_sha256"] = canonical_sha256({k: v for k, v in graph.items() if k != "graph_sha256"})
    result = verify_graph(graph)
    assert any(x["code"] == "EDGE_DIGEST_MISMATCH" for x in result["issues"])
