"""Check that a healthy runtime reports the intended deployment commit."""
from __future__ import annotations

import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("health_url")
    parser.add_argument("expected_sha")
    args = parser.parse_args()
    try:
        with urlopen(args.health_url, timeout=20) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("health response must be a JSON object")
        result = assess_live_build(args.expected_sha, payload)
    except (OSError, ValueError) as exc:
        result = {"verdict": "CHECK_FAILED", "error_type": type(exc).__name__}
    print(json.dumps(result))
    return 0 if result["verdict"] == "BUILD_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
