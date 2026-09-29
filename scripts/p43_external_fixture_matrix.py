from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from scripts.p43_oracles import probe_file

def download(url:str,target:Path,expected_size:int)->None:
    req=urllib.request.Request(url,headers={"User-Agent":"ChatGPT-Web-HWPX-MCP-P4.3/1.0"})
    last=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=35) as r:data=r.read(12_000_000)
            if len(data)>=12_000_000:raise RuntimeError("immutable fixture exceeded 12MB bound")
            if expected_size and len(data)!=expected_size:
                raise RuntimeError(f"immutable fixture size mismatch: expected {expected_size}, got {len(data)}")
            target.write_bytes(data);return
        except Exception as exc:
            last=exc
            if attempt<2:time.sleep(2**attempt)
    raise RuntimeError(f"immutable fixture download failed: {type(last).__name__}") from last

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--manifest",required=True);p.add_argument("--out",required=True);a=p.parse_args()
    manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"));rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for item in manifest:
            target=root/(item["source_id"]+".hwpx")
            try:
                download(item["download_url"],target,int(item.get("expected_size") or 0))
                row=probe_file(target,feature_family=item["feature_family"],source_id=item["source_id"],source_kind="IMMUTABLE_OPEN_SOURCE_FIXTURE")
                row.update({
                    "repository":item["repository"],"commit":item["commit"],"path":item["path"],
                    "git_blob_sha":item["git_blob_sha"],"license":item["license"],
                })
            except Exception as exc:
                row={
                    "source_id":item["source_id"],"source_kind":"IMMUTABLE_OPEN_SOURCE_FIXTURE",
                    "feature_family":item["feature_family"],"repository":item["repository"],"commit":item["commit"],
                    "path":item["path"],"git_blob_sha":item["git_blob_sha"],"license":item["license"],
                    "product_authority_pass":False,"oracle_consensus_pass":False,
                    "independent_oracle_status":"NOT_RUN","error_class":type(exc).__name__,"error":str(exc)[:300],
                }
            rows.append(row)
    critical=[r for r in rows if not r.get("product_authority_pass")]
    divergences=[r for r in rows if not r.get("oracle_consensus_pass")]
    independent_pass=sum(1 for r in rows if r.get("independent_oracle_status")=="PASS")
    families=sorted({r["feature_family"] for r in rows})
    repositories=sorted({r["repository"] for r in rows})
    receipt={
        "schema":"chatgpt-web-hwpx-mcp/p4.3/immutable-external-matrix/v1",
        "document_count":len(rows),"repository_count":len(repositories),"repositories":repositories,
        "feature_families":families,"feature_family_count":len(families),
        "product_authority_pass":not critical,"oracle_consensus_pass":not divergences,
        "independent_oracle_coverage":round(independent_pass/len(rows),6) if rows else 0.0,
        "critical_failure_count":len(critical),"oracle_divergence_count":len(divergences),"rows":rows,
        "provenance":"EXACT_REPOSITORY_COMMIT_PLUS_GIT_BLOB_SHA_AND_LICENSE",
    }
    Path(a.out).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "documents":len(rows),"repositories":repositories,"families":families,
        "critical":len(critical),"divergences":len(divergences),
        "independent_coverage":receipt["independent_oracle_coverage"],
        "rows":[{"source_id":r.get("source_id"),"product_authority_pass":r.get("product_authority_pass"),
                 "independent_oracle_status":r.get("independent_oracle_status"),
                 "hwpxkit_error":(r.get("hwpxkit") or {}).get("error_class")} for r in rows],
    }))
    return 0 if len(rows)>=6 and len(repositories)>=2 and not critical else 1

if __name__=="__main__":raise SystemExit(main())
