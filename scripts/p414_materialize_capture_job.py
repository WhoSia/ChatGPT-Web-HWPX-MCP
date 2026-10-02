from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p414_evidence_service import PRODUCT, canonical_sha256, validate_capture_job


def materialize(*, source_root: Path, output_target: Path, exact_head: str, out: Path, ttl_hours: int = 4) -> dict:
    if len(exact_head) != 40 or any(c not in "0123456789abcdef" for c in exact_head.lower()):
        raise ValueError("exact_head must be a 40-character hexadecimal commit")
    source_root = source_root.resolve(strict=True)
    output_target = output_target.resolve(strict=False)
    if output_target == source_root or source_root in output_target.parents:
        raise ValueError("output_target must be outside the immutable source root")
    baseline = json.loads((Path(__file__).resolve().parents[1] / "benchmarks" / "p412_native_requalification.json").read_text(encoding="utf-8"))
    files = []
    for case in sorted(baseline["cases"], key=lambda x: x["case_id"]):
        fixture_id = case["case_id"]
        # P4.12's immutable native pack keeps the p48- fixture prefix. Never
        # rename, regenerate, or substitute bytes to make a manifest fit.
        basename = fixture_id + ".hwpx"
        path = source_root / basename
        if not path.is_file():
            raise FileNotFoundError(f"exact source fixture missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest.lower() != case["source_sha256"].lower():
            raise ValueError(f"source fixture hash differs from immutable P4.12 identity: {fixture_id}")
        files.append({"fixture_id": fixture_id, "path": basename, "sha256": digest, "bytes": path.stat().st_size, "lowering_family": "P4.8_SEMANTIC_COMPONENTS"})
    manifest = {"files": files}
    now = datetime.now(timezone.utc)
    job = {
        "schema": "chatgpt-web-hwpx-mcp/p414/capture-job/v1",
        "job_id": "p414-" + uuid.uuid4().hex,
        "exact_head": exact_head.lower(),
        "product": PRODUCT,
        "source_root": str(source_root),
        "source_manifest": manifest,
        "source_manifest_sha256": canonical_sha256(manifest),
        "hancom_build_expected": baseline["hancom"]["expected_version"],
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=max(1, min(int(ttl_hours), 12)))).isoformat(),
        "nonce": secrets.token_urlsafe(32),
        "output_target": str(output_target),
        "capture_kind": "P412_FIVE_ARCHETYPE_PROTOCOL_REQUALIFICATION",
        "document_binding": None,
    }
    validation = validate_capture_job(job, now=now)
    if validation["status"] != "PASS":
        raise ValueError(f"materialized job failed validation: {validation}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(job, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"job_id": job["job_id"], "exact_head": exact_head, "source_manifest_sha256": job["source_manifest_sha256"], "fixture_count": len(files), "expires_at": job["expires_at"], "job_envelope_path": str(out)}, ensure_ascii=False))
    return job


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-target", type=Path, required=True)
    parser.add_argument("--exact-head", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ttl-hours", type=int, default=4)
    args = parser.parse_args()
    materialize(source_root=args.source_root, output_target=args.output_target, exact_head=args.exact_head, out=args.out, ttl_hours=args.ttl_hours)
