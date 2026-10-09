from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.evidence.p413_evidence_service import (
    evidence_health_summary,
    load_promoted_baseline,
    public_authoring_trust_status,
    release_manifest,
)

def run(out: Path, exact_head: str) -> dict:
    if len(exact_head)!=40:
        raise ValueError("exact_head must be 40 characters")
    out.mkdir(parents=True,exist_ok=True)
    baseline=load_promoted_baseline()
    manifest=release_manifest()
    health=evidence_health_summary()
    trust=public_authoring_trust_status()
    bundle={
        "phase":"P4.13",
        "product":"0.38.0-p4.13",
        "exact_head":exact_head,
        "inherited_native_baseline":{
            "phase":baseline["phase"],
            "product":baseline["product"],
            "exact_head":baseline["exact_head"],
            "archive_sha256":baseline["archive_sha256"],
            "case_count":len(baseline["cases"]),
        },
        "release_manifest":manifest,
        "evidence_health":health,
        "public_authoring_trust":trust,
        "authority":"P4.13_RELEASE_LINKED_HANCOM_EVIDENCE_BUNDLE",
    }
    for name,payload in [
        ("p413-release-manifest.json",manifest),
        ("p413-evidence-health.json",health),
        ("p413-public-authoring-trust.json",trust),
        ("p413-release-evidence-bundle.json",bundle),
    ]:
        (out/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(bundle,ensure_ascii=False))
    return bundle

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("/tmp/p413-release-evidence"))
    p.add_argument("--exact-head",required=True)
    a=p.parse_args()
    run(a.out,a.exact_head)
