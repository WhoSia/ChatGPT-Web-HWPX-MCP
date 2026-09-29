from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

PHASE="P4.3"
PRODUCT="0.29.0-p4.3"
HISTORY_PATH=Path(__file__).resolve().parent/"benchmarks"/"p43_release_history.json"
MIN_CALIBRATION_RELEASES=5

def _stable(value:Any)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def _sha(value:Any)->str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()

def load_release_history(path:Path|str=HISTORY_PATH)->dict:
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    entries=list(data.get("entries") or [])
    if not entries:
        raise ValueError("cross-release benchmark history is empty")
    for entry in entries:
        if not entry.get("product") or not entry.get("exact_head"):
            raise ValueError("benchmark history entry lacks release identity")
    payload={**data,"entry_count":len(entries)}
    payload["history_sha256"]=_sha(data)
    return payload

def quality_service_contract()->dict:
    contract={
        "schema":"chatgpt-web-hwpx-mcp/p4.3/quality-service-contract/v1",
        "phase":PHASE,
        "product":PRODUCT,
        "production_engine":{"name":"python-hwpx","version":"6.6.0","role":"PRIMARY_AUTHORING_ENGINE"},
        "independent_oracles":[
            {"name":"raw-owpml","version":"product-defined","role":"PACKAGE_AND_XML_STRUCTURE_ORACLE"},
            {"name":"python-hwpx","version":"6.6.0","role":"PRIMARY_PARSE_AUTHORING_ORACLE"},
            {"name":"hwpxkit","version":"0.2.1","role":"INDEPENDENT_RUST_PARSE_ORACLE","runtime":"CI_ONLY"},
        ],
        "representative_lanes":{
            "public_real_documents":"ephemeral official-source download; bytes never committed by P4.3",
            "generated_feature_families":[
                "DOCUMENT_SETUP","STRUCTURED_PUBLISHING","ADVANCED_TABLES","DRAWING_LAYER"
            ],
        },
        "benchmark_policy":{
            "history":"reviewed append-only release observations",
            "minimum_releases_for_calibrated_slo":MIN_CALIBRATION_RELEASES,
            "before_minimum":"PROVISIONAL_HARD_BUDGET",
            "after_minimum":"ROBUST_HISTORY_CALIBRATED_BUDGET",
            "shared_runner_timings":"release health evidence, not native-render SLO authority",
        },
        "oracle_policy":{
            "product_authority":"raw OWPML + python-hwpx structural/section-semantic agreement",
            "independent_oracle":"hwpxkit disagreement is retained as diagnostic evidence, not silently majority-voted",
            "independent_coverage_floor":0.80,
        },
        "failure_bundle":{
            "raw_document_bytes":False,
            "raw_stack_trace":False,
            "document_sha256":True,
            "oracle_versions":True,
            "reproduction_route":True,
        },
        "authority":"CONTINUOUS_PRODUCT_HEALTH_NOT_NATIVE_RENDER_OR_HUMAN_VISUAL_AUTHORITY",
    }
    return {**contract,"contract_sha256":_sha(contract)}

def calibrate_budget(history:Mapping[str,Any],metric:str)->dict:
    values=[]
    for entry in history.get("entries",[]):
        raw=(entry.get("metrics") or {}).get(metric)
        if raw is not None:
            values.append(float(raw))
    if not values:
        raise ValueError(f"no benchmark observations for {metric}")
    if len(values)<MIN_CALIBRATION_RELEASES:
        # Deliberately broad until there are enough exact-head releases to estimate a stable distribution.
        ceiling=max(max(values)*2.5,10.0 if "existing" in metric else 1000.0)
        return {
            "metric":metric,"mode":"PROVISIONAL_HARD_BUDGET","observation_count":len(values),
            "ceiling_ms":round(ceiling,3),"calibrated_slo":False,
            "reason":f"need at least {MIN_CALIBRATION_RELEASES} exact-head release observations",
        }
    med=statistics.median(values)
    abs_dev=[abs(x-med) for x in values]
    mad=statistics.median(abs_dev)
    robust_sigma=1.4826*mad
    ceiling=max(med+6*robust_sigma,med*1.35)
    return {
        "metric":metric,"mode":"ROBUST_HISTORY_CALIBRATED_BUDGET","observation_count":len(values),
        "median_ms":round(med,3),"mad_ms":round(mad,3),"ceiling_ms":round(ceiling,3),
        "calibrated_slo":True,
    }

def evaluate_metric(history:Mapping[str,Any],metric:str,observed_ms:float)->dict:
    budget=calibrate_budget(history,metric)
    observed=float(observed_ms)
    return {**budget,"observed_ms":round(observed,3),"status":"PASS" if observed<=budget["ceiling_ms"] else "REGRESSION"}

def localize_regression(observation:Mapping[str,Any])->dict:
    raw=bool(observation.get("raw_owpml_pass"))
    primary=bool(observation.get("python_hwpx_pass"))
    independent=bool(observation.get("hwpxkit_pass"))
    semantic_match=observation.get("semantic_match")
    performance=bool(observation.get("performance_regression"))
    if not raw:
        locus="PACKAGE_OR_CONTAINER"
        confidence="HIGH"
        action="Inspect ZIP/OWPML package construction before parser-specific debugging."
    elif not primary and independent:
        locus="PRIMARY_ENGINE_COMPATIBILITY"
        confidence="HIGH"
        action="Reproduce against python-hwpx with the exact document SHA and feature family."
    elif primary and not independent:
        locus="INDEPENDENT_ORACLE_DIVERGENCE"
        confidence="MEDIUM"
        action="Treat as oracle disagreement; do not classify as product regression without structural/native evidence."
    elif not primary and not independent:
        locus="OWPML_INTEROPERABILITY_OR_SHARED_UNSUPPORTED_FEATURE"
        confidence="MEDIUM"
        action="Inspect the feature family and raw XML; seek an additional native or parser oracle."
    elif semantic_match is False:
        locus="SEMANTIC_MODEL_DIVERGENCE"
        confidence="HIGH"
        action="Compare section/text/object semantics across parsers while preserving raw package evidence."
    elif performance:
        locus="PERFORMANCE_REGRESSION"
        confidence="HIGH"
        action="Compare the operation against cross-release history and isolate CPU/I/O/startup contribution."
    else:
        locus="NO_REGRESSION_DETECTED"
        confidence="HIGH"
        action="No repair action required."
    payload={"phase":PHASE,"product":PRODUCT,"locus":locus,"confidence":confidence,"action":action,
             "feature_family":str(observation.get("feature_family") or "UNKNOWN")}
    return {**payload,"localization_sha256":_sha(payload)}

def build_failure_bundle(context:Mapping[str,Any])->dict:
    allowed={
        "release":str(context.get("release") or PRODUCT)[:80],
        "exact_head":str(context.get("exact_head") or "")[:80],
        "feature_family":str(context.get("feature_family") or "UNKNOWN")[:120],
        "source_id":str(context.get("source_id") or "")[:180],
        "document_sha256":str(context.get("document_sha256") or "")[:64],
        "oracle":str(context.get("oracle") or "")[:80],
        "oracle_version":str(context.get("oracle_version") or "")[:80],
        "error_class":str(context.get("error_class") or "UNKNOWN")[:120],
        "message":str(context.get("message") or "")[:500],
        "reproduction_route":str(context.get("reproduction_route") or "")[:500],
    }
    localization=localize_regression(context)
    body={
        "schema":"chatgpt-web-hwpx-mcp/p4.3/failure-bundle/v1",
        **allowed,
        "localization":localization,
        "raw_document_bytes_included":False,
        "raw_stack_trace_included":False,
    }
    body["bundle_id"]="sha256:"+_sha(body)
    return body

def adjudicate_release_health(receipt:Mapping[str,Any])->dict:
    family_count=int(receipt.get("feature_family_count") or 0)
    public_count=int(receipt.get("public_document_count") or 0)
    generated_count=int(receipt.get("generated_fixture_count") or 0)
    product_authority=bool(receipt.get("product_authority_pass"))
    independent_coverage=float(receipt.get("independent_oracle_coverage") or 0.0)
    performance=bool(receipt.get("performance_budget_pass"))
    diagnostics=bool(receipt.get("diagnostic_negative_control_pass"))
    docker=bool(receipt.get("docker_pass"))
    rollback=bool(receipt.get("rollback_ready"))
    critical=int(receipt.get("critical_failure_count") or 0)
    gates={
        "representative_family_floor":family_count>=12,
        "public_real_document_floor":public_count>=3,
        "generated_fixture_floor":generated_count>=18,
        "product_authority_all_pass":product_authority,
        "independent_oracle_coverage_floor":independent_coverage>=0.80,
        "performance_budget":performance,
        "diagnostic_negative_control":diagnostics,
        "docker":docker,
        "rollback_ready":rollback,
        "no_critical_failures":critical==0,
    }
    failed=[k for k,v in gates.items() if not v]
    verdict="PASS" if not failed else "HOLD"
    payload={
        "phase":PHASE,"product":PRODUCT,"gates":gates,"failed_gates":failed,"verdict":verdict,
        "coverage_note":"Representative product-health seed; not a claim of population-wide HWPX representativeness.",
    }
    return {**payload,"health_sha256":_sha(payload)}
