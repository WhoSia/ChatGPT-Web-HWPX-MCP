"""Check that a healthy runtime reports the intended deployment commit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.request import urlopen


def assess_live_build(expected_sha: str, health: dict) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("expected a full lowercase Git commit SHA")
    observed = health.get("release_commit")
    if health.get("status") != "ok":
        verdict = "UNHEALTHY"
    elif not isinstance(observed, str) or not re.fullmatch(r"[0-9a-f]{40}", observed):
        verdict = "BUILD_ID_UNAVAILABLE"
    elif observed != expected_sha:
        verdict = "BUILD_MISMATCH"
    else:
        verdict = "BUILD_MATCH"
    return {
        "expected_sha": expected_sha,
        "observed_sha": observed if verdict in {"BUILD_MATCH", "BUILD_MISMATCH"} else None,
        "verdict": verdict,
    }


def assess_render_deployment(expected_sha: str, health: dict, deployment: dict) -> dict:
    result = assess_live_build(expected_sha, health)
    deploy_id = deployment.get("id")
    commit = deployment.get("commit")
    deploy_sha = commit.get("id") if isinstance(commit, dict) else None
    if not isinstance(deploy_id, str) or not deploy_id.startswith("dep-"):
        raise ValueError("expected a Render deployment ID")
    if not isinstance(deploy_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", deploy_sha):
        raise ValueError("expected a full Render deployment commit SHA")
    if deployment.get("status") != "live":
        verdict = "DEPLOY_NOT_LIVE"
    elif deploy_sha != expected_sha:
        verdict = "DEPLOY_BUILD_MISMATCH"
    else:
        verdict = result["verdict"]
    return {
        **result,
        "runtime_verdict": result["verdict"],
        "deployment_id": deploy_id,
        "deployment_sha": deploy_sha,
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("health_url")
    parser.add_argument("expected_sha")
    parser.add_argument("--render-deployment", type=Path,
                        help="JSON deployment record from Render")
    args = parser.parse_args()
    try:
        with urlopen(args.health_url, timeout=20) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("health response must be a JSON object")
        if args.render_deployment is None:
            result = assess_live_build(args.expected_sha, payload)
        else:
            deployment = json.loads(args.render_deployment.read_text(encoding="utf-8-sig"))
            if not isinstance(deployment, dict):
                raise ValueError("deployment record must be a JSON object")
            result = assess_render_deployment(args.expected_sha, payload, deployment)
    except (OSError, ValueError) as exc:
        result = {"verdict": "CHECK_FAILED", "error_type": type(exc).__name__}
    print(json.dumps(result))
    return 0 if result["verdict"] == "BUILD_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
