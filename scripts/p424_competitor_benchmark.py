"""P4.24 matched-pair HWPX product benchmark; no invented performance scores.

The input is an operator-created JSONL file of completed, independently
recorded runs. The tool cannot execute or certify competing MCP servers.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from statistics import median
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
STATUSES = {"PASS", "FAIL", "UNSUPPORTED", "UNVERIFIED"}


def validate_run(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("benchmark entry must be an object")
    required = ("product", "task", "fixture_sha256", "environment", "status")
    for key in required:
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"missing or invalid field: {key}")
    if not SHA256.fullmatch(raw["fixture_sha256"]):
        raise ValueError("fixture_sha256 must be lowercase hexadecimal SHA-256")
    trial_id = raw.get("trial_id", "1")
    if not isinstance(trial_id, str) or not trial_id.strip() or len(trial_id) > 64:
        raise ValueError("trial_id must be a nonempty string up to 64 chars")
    if raw["status"] not in STATUSES:
        raise ValueError("invalid status; do not replace unavailable with PASS")
    if raw["status"] == "PASS":
        if raw.get("consumer_verified") is not True:
            raise ValueError("PASS requires independent consumer verification")
        if raw.get("native_visual_accepted") is not True:
            raise ValueError("PASS requires native visual acceptance")
        ms = raw.get("elapsed_ms")
        if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not 0 < ms < 1e9:
            raise ValueError("PASS requires positive finite elapsed_ms")
        if not isinstance(raw.get("artifact_sha256"), str) or not SHA256.fullmatch(raw["artifact_sha256"]):
            raise ValueError("PASS requires independently checked artifact_sha256")
    elif raw.get("consumer_verified") is True or raw.get("native_visual_accepted") is True:
        raise ValueError("non-PASS entries cannot claim completed consumer/native gate")
    return dict(raw)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                entry = validate_run(json.loads(line))
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid benchmark line {line_no}: {exc}") from exc
            entries.append(entry)
    return entries


def compare_matched(
    runs: list[dict[str, Any]], baseline: str, candidate: str
) -> dict[str, Any]:
    """Compare only uniquely recorded same-task/fixture/environment PASS pairs."""
    if not baseline or not candidate or baseline == candidate:
        raise ValueError("baseline and candidate must be different, nonempty names")
    indexed: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        entry = validate_run(run)
        if entry["product"] in (baseline, candidate):
            key = (entry["product"], entry["task"], entry["fixture_sha256"], entry["environment"], entry.get("trial_id", "1"))
            indexed[key].append(entry)
    duplicates = [k for k, v in indexed.items() if len(v) > 1]
    if duplicates:
        raise ValueError(f"duplicate trial keys: {len(duplicates)}; distinguish repetitions with trial_id")
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for (product, task, fixture, environment, trial_id), values in indexed.items():
        grouped[(task, fixture, environment, trial_id)][product] = values[0]
    valid_pairs = []
    excluded: dict[str, int] = defaultdict(int)
    for key, by_product in sorted(grouped.items()):
        if baseline not in by_product or candidate not in by_product:
            excluded["missing_comparator"] += 1
            continue
        a, b = by_product[baseline], by_product[candidate]
        if a["status"] != "PASS" or b["status"] != "PASS":
            excluded["not_both_verified_pass"] += 1
            continue
        valid_pairs.append({
            "task": key[0], "fixture_sha256": key[1], "environment": key[2],
            "trial_id": key[3],
            "baseline_ms": a["elapsed_ms"], "candidate_ms": b["elapsed_ms"],
            "difference_ms": b["elapsed_ms"] - a["elapsed_ms"],
        })
    return {
        "schema": "p424/competitor-pair-comparison/v1",
        "baseline": baseline, "candidate": candidate,
        "verified_matched_pairs": len(valid_pairs),
        "excluded": dict(sorted(excluded.items())),
        "median_candidate_minus_baseline_ms": (
            median(p["difference_ms"] for p in valid_pairs) if valid_pairs else None
        ),
        "ranking_authorized": False,
        "pairs": valid_pairs,
        "notice": "Descriptive matched pairs only; not statistical or native release certification.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    try:
        report = compare_matched(read_jsonl(args.jsonl), args.baseline, args.candidate)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
