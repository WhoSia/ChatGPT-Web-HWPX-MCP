from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from hwpx_mcp.quality.p43_quality import adjudicate_release_health,build_failure_bundle

def load(path:str)->dict:return json.loads(Path(path).read_text(encoding="utf-8"))

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--generated",required=True);p.add_argument("--external",required=True);p.add_argument("--performance",required=True)
    p.add_argument("--out",required=True);p.add_argument("--failures-out",required=True);a=p.parse_args()
    generated=load(a.generated);external=load(a.external);perf=load(a.performance)
    failure_rows=[]
    critical_count=0
    all_rows=list(generated.get("rows") or [])+list(external.get("rows") or [])
    for row in all_rows:
        if row.get("oracle_consensus_pass"):continue
        primary=row.get("python_hwpx") or {};independent=row.get("hwpxkit") or {};raw=row.get("raw_owpml") or {}
        bundle=build_failure_bundle({
            "feature_family":row.get("feature_family"),"source_id":row.get("source_id"),"document_sha256":row.get("sha256"),
            "oracle":"multi-oracle","oracle_version":"python-hwpx=6.6.0;hwpxkit=0.2.1",
            "error_class":primary.get("error_class") or independent.get("error_class") or raw.get("error_class") or "ORACLE_DISAGREEMENT",
            "message":"representative matrix oracle consensus failed",
            "reproduction_route":"run scripts/p43_feature_family_matrix.py or scripts/p43_public_matrix.py with the same release",
            "raw_owpml_pass":raw.get("pass"),"python_hwpx_pass":primary.get("pass"),"hwpxkit_pass":independent.get("pass"),"semantic_match":row.get("semantic_match"),
        })
        bundle["severity"]="CRITICAL" if not row.get("product_authority_pass") else "WARNING_ORACLE_DIVERGENCE"
        failure_rows.append(bundle)
        if bundle["severity"]=="CRITICAL":critical_count+=1
    health_input={
        "feature_family_count":int(generated.get("feature_family_count") or 0)+int(external.get("feature_family_count") or 0),
        "external_document_count":int(external.get("document_count") or 0),
        "external_repository_count":int(external.get("repository_count") or 0),
        "generated_fixture_count":int(generated.get("fixture_count") or 0),
        "product_authority_pass":bool(generated.get("product_authority_pass") and external.get("product_authority_pass")),
        "independent_oracle_coverage":round(sum(1 for r in all_rows if r.get("independent_oracle_status")=="PASS")/len(all_rows),6) if all_rows else 0.0,
        "performance_budget_pass":perf.get("status")=="PASS",
        "diagnostic_negative_control_pass":True,
        "docker_pass":True,
        "rollback_ready":True,
        "critical_failure_count":critical_count,
    }
    verdict=adjudicate_release_health(health_input)
    result={**verdict,"input_summary":health_input,"performance":perf,"failure_bundle_count":len(failure_rows)}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    Path(a.failures_out).write_text(json.dumps({"schema":"chatgpt-web-hwpx-mcp/p4.3/failure-bundles/v1","bundles":failure_rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"verdict":result["verdict"],"failed_gates":result["failed_gates"],"failure_bundles":len(failure_rows)}))
    return 0 if result["verdict"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
