#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from p2_document import build_document_map
from p322_review_workflow import build_review_workflow_map


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        default="artifacts/p334r2-tracked-resolution-pack/protection-enable/target.hwpx",
    )
    ap.add_argument(
        "--out",
        default="artifacts/p334r2-protected-resolution-pack",
    )
    args = ap.parse_args()
    source = Path(args.source)
    out = Path(args.out)
    if not source.exists():
        raise FileNotFoundError(
            f"Native protected artifact not found: {source}. "
            "Run the stage-one P3.34-R2 capture first and keep its artifacts directory."
        )
    out.mkdir(parents=True, exist_ok=True)

    from capture_runtime import attach_capture_runtime
    attach_capture_runtime(out)

    mapped = build_review_workflow_map(source)
    if mapped["counts"]["tracked_changes"] != 1:
        raise RuntimeError("Protected source must contain exactly one unresolved tracked change")

    cases = [
        {
            "id": "protected-cancel-accept",
            "action": "ATTEMPT_ACCEPT_ALL_CANCEL_PASSWORD",
            "expected": "PROTECTED_CHANGE_REMAINS",
        },
        {
            "id": "protected-correct-accept",
            "action": "ACCEPT_ALL_WITH_PASSWORD",
            "expected": "INSERT_ACCEPTED",
        },
        {
            "id": "protected-correct-reject",
            "action": "REJECT_ALL_WITH_PASSWORD",
            "expected": "INSERT_REJECTED",
        },
    ]

    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r2/protected-resolution/v1",
        "phase": "P3.34-R2",
        "password": "P334R2!",
        "native_source": str(source),
        "native_source_sha256": sha(source),
        "cases": [],
    }
    for spec in cases:
        d = out / spec["id"]
        d.mkdir(parents=True, exist_ok=True)
        target = d / "target.hwpx"
        shutil.copy2(source, target)
        item = {**spec, "target": str(target), "source_sha256": sha(source)}
        (d / "case.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest["cases"].append(item)

    (out / "capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("P3.34-R2 materialized 3 protected-resolution native fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
