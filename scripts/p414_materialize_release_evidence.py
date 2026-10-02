from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p414_evidence_service import (
    PRODUCT,
    canonical_sha256,
    evaluate_release_capture_obligation,
    hancom_build_matrix,
    release_change_vectors,
)


def materialize(out: Path, exact_head: str) -> dict:
    if len(exact_head) != 40 or any(c not in "0123456789abcdef" for c in exact_head.lower()):
        raise ValueError("exact_head must be a 40-character hexadecimal commit")
    out.mkdir(parents=True, exist_ok=True)
    seed = json.loads((Path(__file__).resolve().parents[1] / "benchmarks" / "p414_release_identity_seed.json").read_text(encoding="utf-8"))
    previous, candidate = release_change_vectors(exact_head=exact_head)
    obligation = evaluate_release_capture_obligation(previous=previous, candidate=candidate)
    matrix = hancom_build_matrix([])
    bundle = {
        "schema": "chatgpt-web-hwpx-mcp/p414/release-evidence-bundle/v1",
        "phase": "P4.14",
        "product": PRODUCT,
        "exact_head": exact_head,
        "immutable_parent": seed["parent"],
        "inherited_native_baseline": seed["inherited_native_baseline"],
        "candidate_release_identity": candidate,
        "capture_obligation": obligation,
        "build_matrix": matrix,
        "raw_signed_receipts": [],
        "normalized_native_evidence": [],
        "native_status": "NATIVE_VERIFICATION_PENDING",
        "native_pass_claimed": False,
        "authority": "P414_RELEASE_LINKED_EVIDENCE_BUNDLE",
    }
    bundle["bundle_sha256"] = canonical_sha256(bundle)
    parent_path = out / "p414-immutable-parent.json"
    obligation_path = out / "p414-capture-obligation.json"
    matrix_path = out / "p414-hancom-build-matrix.json"
    bundle_path = out / "p414-release-evidence-bundle.json"
    for path, payload in ((parent_path, seed), (obligation_path, obligation), (matrix_path, matrix), (bundle_path, bundle)):
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": "P4.14", "product": PRODUCT, "exact_head": exact_head, "obligation": obligation["status"], "native_status": bundle["native_status"], "bundle_sha256": bundle["bundle_sha256"], "files": [str(parent_path), str(obligation_path), str(matrix_path), str(bundle_path)]}, ensure_ascii=False))
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exact-head", required=True)
    args = parser.parse_args()
    materialize(args.out, args.exact_head)
