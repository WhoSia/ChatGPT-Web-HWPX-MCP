from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import hashlib
import json
from hwpx_mcp.custody.p411_capture_protocol import validate_capture_request

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--exact-head",required=True)
    p.add_argument("--source-dir",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--source-manifest",required=True,type=Path)
    p.add_argument("--capture-kind",default="archetype")
    p.add_argument("--hancom-version",default="13.0.0.3622")
    p.add_argument("--out",type=Path,default=Path("/tmp/p411-capture-request.json"))
    a=p.parse_args()
    digest=hashlib.sha256(a.source_manifest.read_bytes()).hexdigest()
    request={
        "job_id":hashlib.sha256((a.exact_head+"\0"+digest+"\0"+a.capture_kind).encode()).hexdigest()[:24],
        "exact_head":a.exact_head,
        "source_manifest_sha256":digest,
        "source_dir":a.source_dir,
        "output_dir":a.output_dir,
        "hancom_version_expected":a.hancom_version,
        "capture_kind":a.capture_kind,
    }
    validation=validate_capture_request(request)
    if validation["status"]!="PASS":
        raise SystemExit(json.dumps(validation))
    a.out.write_text(json.dumps(request,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"job_id":request["job_id"],"request_validation_sha256":validation["request_validation_sha256"]}))

if __name__=="__main__":
    main()
