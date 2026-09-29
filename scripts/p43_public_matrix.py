from __future__ import annotations
import argparse,json,sys,tempfile,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.p43_oracles import probe_file

def download(url:str,target:Path)->None:
    req=urllib.request.Request(url,headers={"User-Agent":"ChatGPT-Web-HWPX-MCP-P4.3/1.0"})
    last=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=35) as r:data=r.read(12_000_000)
            if len(data)>=12_000_000:raise RuntimeError("document exceeds 12MB bounded canary")
            target.write_bytes(data);return
        except Exception as exc:
            last=exc
            if attempt<2:time.sleep(2**attempt)
    raise RuntimeError(f"download failed: {type(last).__name__}") from last

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--manifest",required=True);p.add_argument("--out",required=True);a=p.parse_args()
    manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"));rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for item in manifest:
            target=root/(item["source_id"]+".hwpx")
            try:
                download(item["download_url"],target)
                row=probe_file(target,feature_family="PUBLIC_OFFICIAL_DOCUMENT",source_id=item["source_id"],source_kind="PUBLIC_EPHEMERAL")
                row.update({"institution":item.get("institution"),"source_page":item.get("source_page"),"license":item.get("license")})
            except Exception as exc:
                row={"source_id":item["source_id"],"source_kind":"PUBLIC_EPHEMERAL","feature_family":"PUBLIC_OFFICIAL_DOCUMENT","institution":item.get("institution"),"source_page":item.get("source_page"),"oracle_consensus_pass":False,"error_class":type(exc).__name__}
            rows.append(row)
    critical=[r for r in rows if not r.get("product_authority_pass")]
    divergences=[r for r in rows if not r.get("oracle_consensus_pass")]
    independent_pass=sum(1 for r in rows if r.get("independent_oracle_status")=="PASS")
    receipt={
        "schema":"chatgpt-web-hwpx-mcp/p4.3/public-matrix/v1",
        "document_count":len(rows),"institution_count":len({r.get("institution") for r in rows if r.get("institution")}),
        "feature_family_count":1,"product_authority_pass":not critical,"oracle_consensus_pass":not divergences,
        "independent_oracle_coverage":round(independent_pass/len(rows),6) if rows else 0.0,
        "critical_failure_count":len(critical),"oracle_divergence_count":len(divergences),"rows":rows,
        "coverage_note":"Official public seed, not population-representative HWPX sampling.",
    }
    Path(a.out).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"documents":len(rows),"institutions":receipt["institution_count"],"critical":len(critical),"divergences":len(divergences),"independent_coverage":receipt["independent_oracle_coverage"],"rows":[{"source_id":r.get("source_id"),"product_authority_pass":r.get("product_authority_pass"),"independent_oracle_status":r.get("independent_oracle_status"),"hwpxkit_error":(r.get("hwpxkit") or {}).get("error_class")} for r in rows]}))
    return 0 if len(rows)>=3 and not critical else 1
if __name__=="__main__":raise SystemExit(main())
