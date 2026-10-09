from __future__ import annotations
import argparse,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from hwpx_mcp.corpus.p318_regression_corpus import materialize_p318_regression_corpus
from hwpx_mcp.corpus.p319_regression_corpus import materialize_p319_regression_corpus
from hwpx_mcp.corpus.p323_regression_corpus import materialize_p323_regression_corpus
from hwpx_mcp.corpus.p325_regression_corpus import materialize_p325_regression_corpus
from scripts.p43_oracles import probe_file

MATERIALIZERS=[
    ("DOCUMENT_SETUP",materialize_p318_regression_corpus),
    ("STRUCTURED_PUBLISHING",materialize_p319_regression_corpus),
    ("ADVANCED_TABLES",materialize_p323_regression_corpus),
    ("DRAWING_LAYER",materialize_p325_regression_corpus),
]

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for family,fn in MATERIALIZERS:
            family_root=root/family.lower()
            manifest=fn(family_root)
            for item in manifest.get("fixtures",[]):
                fid=str(item.get("fixture_id") or item.get("name"))
                target=family_root/fid/"target.hwpx"
                rows.append(probe_file(target,feature_family=family,source_id=f"{family}:{fid}",source_kind="GENERATED_REGRESSION_FIXTURE"))
    families=sorted({r["feature_family"] for r in rows})
    critical=[r for r in rows if not r["product_authority_pass"]]
    divergences=[r for r in rows if not r["oracle_consensus_pass"]]
    independent_pass=sum(1 for r in rows if r.get("independent_oracle_status")=="PASS")
    receipt={
        "schema":"chatgpt-web-hwpx-mcp/p4.3/generated-family-matrix/v1",
        "fixture_count":len(rows),"feature_families":families,"feature_family_count":len(families),
        "product_authority_pass":not critical,
        "oracle_consensus_pass":not divergences,
        "independent_oracle_coverage":round(independent_pass/len(rows),6) if rows else 0.0,
        "critical_failure_count":len(critical),"oracle_divergence_count":len(divergences),"rows":rows,
        "authority":"GENERATED_FEATURE_FAMILY_MULTI_ORACLE_STRUCTURAL_EVIDENCE",
    }
    Path(a.out).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"fixture_count":len(rows),"feature_families":families,"critical":len(critical),"divergences":len(divergences),"independent_coverage":receipt["independent_oracle_coverage"]}))
    return 0 if not critical and len(rows)>=18 and len(families)>=4 else 1
if __name__=="__main__":raise SystemExit(main())
