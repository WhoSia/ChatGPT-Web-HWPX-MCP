"""Fail-closed, metadata-only audit of runtime release inputs (not an image scan)."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

def audit(root: Path) -> dict:
    docker = (root / "Dockerfile").read_text(encoding="utf-8")
    req = (root / "requirements.txt").read_text(encoding="utf-8")
    required = ("LICENSE", "SECURITY.md", "THIRD_PARTY_NOTICES.md")
    missing = [p for p in required if not (root / p).is_file()]
    stages = re.split(r"(?m)(?=^FROM\\s+)", docker)
    final_stage = next((stage for stage in reversed(stages) if stage.strip().startswith("FROM ")), "")
    broad_copy = [line.strip() for line in final_stage.splitlines() if re.match(r"\\s*COPY\\s+(?:benchmarks/|corpus/|fixtures/)", line)]
    unsafe_inheritance = bool(re.search(r"(?m)^FROM\\s+release-smoke-builder(?:\\s|$)", final_stage))
    # Static boundary check: no runtime inheritance from corpus-bearing stage.
    clean_final_stage = " AS production" in final_stage.splitlines()[0] if final_stage else False
    bases = re.findall(r"(?m)^FROM\s+(\S+)", docker)
    ranges = [s.strip() for s in req.splitlines() if s.strip() and not s.lstrip().startswith("#") and "==" not in s]
    return {
        "schema": "release-artifact-audit/v1",
        "documentation_missing": missing,
        "docker_base_images": bases,
        "unbounded_corpus_copy": broad_copy,
        "final_stage_isolated": clean_final_stage and not unsafe_inheritance,
        "build_stage_contains_unreviewed_corpus": any("COPY corpus/ corpus/" in stage for stage in stages[:-1]),
        "direct_unpinned_ranges": ranges,
        "image_contents_verified": False,
        "transitive_licenses_cleared": False,
        "consumer_hancom_open_verified": False,
        "stable_release_admitted": False,
        "disposition": "HOLD" if missing or broad_copy or not clean_final_stage or unsafe_inheritance else "PENDING_IMAGE_AND_CONSUMER_EVIDENCE",
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="-")
    args = parser.parse_args()
    result = audit(Path.cwd())
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.report == "-":
        print(output)
    else:
        p = Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(output, encoding="utf-8")
    if result["documentation_missing"]:
        raise SystemExit("Missing mandatory release rights/security documentation")
