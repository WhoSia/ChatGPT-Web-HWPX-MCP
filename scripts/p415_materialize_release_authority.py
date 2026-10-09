from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.evidence.p415_authority import (
    PARENT_HEAD,
    PRODUCT,
    build_graph,
    canonical_sha256,
    evaluate_admission,
    make_node,
    verify_graph,
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _subject(head: str) -> dict:
    return {"product": PRODUCT, "exact_head": head}


def materialize(out: Path, exact_head: str, *, ci: bool, lifecycle: bool, docker: bool) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    observed_head = _git("rev-parse", "HEAD")
    if observed_head != exact_head:
        raise RuntimeError(f"HEAD mismatch: expected {exact_head}, observed {observed_head}")
    ancestry_ok = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PARENT_HEAD, exact_head],
        check=False,
    ).returncode == 0
    subject = _subject(exact_head)
    nodes = [
        make_node("GIT_EXACT_HEAD", "git-head", "PASS", subject=subject, evidence={"observed_head": observed_head}),
        make_node("GIT_ANCESTRY", "git-parent", "PASS" if ancestry_ok else "FAIL", subject=subject, evidence={"ancestor": PARENT_HEAD, "descendant": exact_head}),
    ]
    if ci:
        nodes.append(make_node("CI", "focused-ci", "PASS", subject=subject, evidence={"source": "P4.15 workflow dependency"}))
    if lifecycle:
        nodes.append(make_node("FULL_LIFECYCLE", "full-lifecycle", "PASS", subject=subject, evidence={"source": "P4.15 workflow dependency"}))
    if docker:
        nodes.append(make_node("EXACT_HEAD_DOCKER", "exact-head-docker", "PASS", subject=subject, evidence={"image": "hwpx-mcp-p415:" + exact_head}))
    graph = build_graph(exact_head=exact_head, nodes=nodes)
    verified = verify_graph(graph)
    admission = evaluate_admission(graph)
    payload = {
        "phase": "P4.15",
        "product": PRODUCT,
        "exact_head": exact_head,
        "graph": graph,
        "verification": verified,
        "admission": admission,
        "native_world_contact": "PENDING",
        "native_pass_claimed": False,
        "authority": "P415_RELEASE_AUTHORITY_MATERIALIZATION",
    }
    payload["bundle_sha256"] = canonical_sha256(payload)
    path = out / "p415-release-authority.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "phase": "P4.15",
        "product": PRODUCT,
        "exact_head": exact_head,
        "graph_status": verified["status"],
        "admission": admission["verdict"],
        "native_world_contact": "PENDING",
        "bundle_sha256": payload["bundle_sha256"],
        "path": str(path),
    }, ensure_ascii=False))
    if verified["status"] != "PASS" or not ancestry_ok:
        raise SystemExit(1)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exact-head", required=True)
    parser.add_argument("--ci-pass", action="store_true")
    parser.add_argument("--lifecycle-pass", action="store_true")
    parser.add_argument("--docker-pass", action="store_true")
    args = parser.parse_args()
    materialize(args.out, args.exact_head, ci=args.ci_pass, lifecycle=args.lifecycle_pass, docker=args.docker_pass)
