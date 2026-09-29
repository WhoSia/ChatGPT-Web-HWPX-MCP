from __future__ import annotations
import hashlib,json,re,statistics,zipfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping,Sequence
PHASE="P4.4";PRODUCT="0.30.0-p4.4";MIN_CALIBRATION_RELEASES=5
def _stable(v:Any)->str:return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _sha(v:Any)->str:return hashlib.sha256(_stable(v).encode()).hexdigest()
def _utc()->str:return datetime.now(timezone.utc).isoformat()
def health_intelligence_contract()->dict:
    b={"schema":"chatgpt-web-hwpx-mcp/p4.4/health-intelligence-contract/v1","phase":PHASE,"product":PRODUCT,
       "release_health_store":{"backend":"POSTGRES","semantics":"APPEND_ONLY_IDEMPOTENT_EVENTS","schema_version":1},
       "authority_boundary":{"production_authoring":"python-hwpx==6.6.0","independent_oracles":["raw ZIP/OWPML","hwpxkit==0.2.1/hwp-rs"],"native_render":"ESCALATION_WORLD_CONTACT_ONLY","mutation_authority_transferred":False},
       "drift_policy":{"minimum_releases_for_calibrated_slo":5,"precalibration":"PROVISIONAL_HARD_BUDGET","calibrated":"ROBUST_MEDIAN_MAD"},
       "feature_attribution":{"mode":"RAW_PACKAGE_EVIDENCE","forced_classification":False,"supports_abstention":True},
       "support_bundle":{"document_bytes":False,"raw_stack_trace":False,"secrets":False}}
    return {**b,"contract_sha256":_sha(b)}
def canonical_release_observation(o:Mapping[str,Any])->dict:
    phase=str(o.get("phase") or "").strip();product=str(o.get("product") or "").strip();head=str(o.get("exact_head") or "").strip()
    if not phase or not product or not head:raise ValueError("release observation requires phase, product, and exact_head")
    p={"schema":"chatgpt-web-hwpx-mcp/p4.4/release-observation/v1","phase":phase[:40],"product":product[:80],"exact_head":head[:80],
       "observed_at":str(o.get("observed_at") or _utc())[:80],"python_hwpx":str(o.get("python_hwpx") or "")[:40],
       "authority":str(o.get("authority") or "OPERATOR_RECORDED")[:120],"feature_family":str(o.get("feature_family") or "")[:120],
       "feature_family_count":int(o.get("feature_family_count") or 0),"corpus_document_count":int(o.get("corpus_document_count") or 0),
       "product_authority_pass":bool(o.get("product_authority_pass",True)),"independent_oracle_coverage":float(o.get("independent_oracle_coverage") or 0.0),
       "oracle_divergence_count":int(o.get("oracle_divergence_count") or 0),"critical_failure_count":int(o.get("critical_failure_count") or 0),
       "native_render_escalation_count":int(o.get("native_render_escalation_count") or 0),
       "metrics":{str(k):float(v) for k,v in dict(o.get("metrics") or {}).items() if v is not None}}
    p["observation_sha256"]=_sha(p);return p
def canonical_corpus_provenance(r:Mapping[str,Any])->dict:
    sid=str(r.get("source_id") or "").strip();ns=str(r.get("federation_namespace") or "").strip()
    if not sid or not ns:raise ValueError("corpus provenance requires source_id and federation_namespace")
    p={"schema":"chatgpt-web-hwpx-mcp/p4.4/corpus-provenance/v1","record_kind":str(r.get("record_kind") or "DOCUMENT")[:40],
       "source_id":sid[:180],"federation_namespace":ns[:160],"institution":str(r.get("institution") or "")[:180],
       "archetype":str(r.get("archetype") or "")[:160],"feature_family":str(r.get("feature_family") or "")[:120],
       "source_kind":str(r.get("source_kind") or "UNKNOWN")[:80],"repository":str(r.get("repository") or "")[:180],
       "upstream_commit":str(r.get("upstream_commit") or r.get("commit") or "")[:80],"git_blob_sha":str(r.get("git_blob_sha") or "")[:80],
       "document_sha256":str(r.get("document_sha256") or "")[:64],"license":str(r.get("license") or "")[:120],
       "blocking":bool(r.get("blocking",False)),"acquisition_status":str(r.get("acquisition_status") or "PINNED")[:80],
       "observed_at":str(r.get("observed_at") or _utc())[:80]}
    p["provenance_sha256"]=_sha(p);return p
_RULES={"DOCUMENT_SETUP":[("section_properties",.62),("page_properties",.38)],"STRUCTURED_PUBLISHING":[("bookmark",.55),("index_or_toc",.45)],
"ADVANCED_TABLES":[("table",.45),("merged_table",.42),("cell_geometry",.18)],"DRAWING_LAYER":[("drawing",.92)],
"FORMATTING":[("character_formatting",.45),("paragraph_formatting",.28)],"NOTES":[("notes",.98)],"FORM_FIELDS":[("form_field",.96)],
"NUMBERING":[("numbering",.93)],"MERGED_TABLES":[("merged_table",.99)],"TEXTBOX_FIELDS":[("textbox",.75),("form_field",.18)],
"HYPERLINKS":[("hyperlink",.99)],"LINE_SPACING":[("line_spacing",.99)]}
def _sig(text:str,patterns:Sequence[str])->bool:return any(re.search(p,text,re.I) for p in patterns)
def inspect_hwpx_evidence(path:Path|str)->dict:
    p=Path(path);digest=hashlib.sha256(p.read_bytes()).hexdigest()
    with zipfile.ZipFile(p) as z:
        names=sorted(z.namelist());parts=[];total=0
        for n in names:
            if not n.lower().endswith((".xml",".hpf")):continue
            data=z.read(n);total+=len(data)
            if total>12_000_000:break
            parts.append(data.decode("utf-8","ignore"))
    t="\n".join(parts).lower()
    s={"section_properties":_sig(t,[r"secpr",r"sectionpr"]),"page_properties":_sig(t,[r"pagepr",r"pagesz",r"pagemargin"]),
       "bookmark":_sig(t,[r"bookmark"]),"index_or_toc":_sig(t,[r"indexmark",r"tableofcontents",r"\btoc\b"]),
       "table":_sig(t,[r"<[^>]*tbl\b",r"<[^>]*table\b"]),"merged_table":_sig(t,[r"rowspan\s*=\s*[\"'](?:[2-9]|[1-9][0-9]+)",r"colspan\s*=\s*[\"'](?:[2-9]|[1-9][0-9]+)"]),
       "cell_geometry":_sig(t,[r"cellmargin",r"cellspacing",r"celladdr"]),"drawing":_sig(t,[r"<[^>]*(?:pic|rect|ellipse|line|polygon|curve|container)\b",r"drawtext"]),
       "character_formatting":_sig(t,[r"charpr",r"fontref",r"underline",r"strikeout"]),"paragraph_formatting":_sig(t,[r"parapr",r"align\s*=",r"indent\s*="]),
       "notes":_sig(t,[r"footnote",r"endnote"]),"form_field":_sig(t,[r"fieldbegin",r"fieldend",r"formfield",r"fieldtype"]),
       "numbering":_sig(t,[r"<[^>]*numbering\b",r"numpr",r"level\s*="]),"textbox":_sig(t,[r"textbox",r"drawtext",r"textart"]),
       "hyperlink":_sig(t,[r"hyperlink",r"href\s*="]),"line_spacing":_sig(t,[r"linespacing",r"line-spacing",r"lineheight"])}
    return {"schema":"chatgpt-web-hwpx-mcp/p4.4/raw-feature-evidence/v1","document_sha256":digest,"package_entry_count":len(names),"signals":s}
def attribute_feature_families_from_evidence(e:Mapping[str,Any])->dict:
    signals=dict(e.get("signals") or {});c=[]
    for fam,rules in _RULES.items():
        hit=[n for n,_ in rules if signals.get(n)];score=min(.99,sum(w for n,w in rules if signals.get(n)))
        if score>=.60:c.append({"family":fam,"confidence":round(score,3),"evidence":hit})
    c.sort(key=lambda x:(-x["confidence"],x["family"]));ab=not c
    b={"phase":PHASE,"product":PRODUCT,"document_sha256":str(e.get("document_sha256") or "")[:64],"candidates":c,
       "top_family":None if ab else c[0]["family"],"top_confidence":0.0 if ab else c[0]["confidence"],"abstain":ab,
       "authority":"HEURISTIC_ATTRIBUTION_NOT_MUTATION_OR_SEMANTIC_AUTHORITY"}
    return {**b,"attribution_sha256":_sha(b)}
def attribute_hwpx_feature_families(path:Path|str)->dict:
    e=inspect_hwpx_evidence(path);return {**attribute_feature_families_from_evidence(e),"evidence":e["signals"],"package_entry_count":e["package_entry_count"]}
def detect_longitudinal_drift(obs:Sequence[Mapping[str,Any]],metric:str="create_validate_p95_ms")->dict:
    rows=[canonical_release_observation(x) for x in obs]
    if len(rows)<2:return {"status":"INSUFFICIENT_HISTORY","observation_count":len(rows),"metric":metric,"findings":[],"calibrated_slo":False}
    cur=rows[-1];base=rows[:-1];find=[]
    if all(r["product_authority_pass"] for r in base[-3:]) and not cur["product_authority_pass"]:find.append({"kind":"PRODUCT_AUTHORITY_REGRESSION","severity":"CRITICAL"})
    bdiv=[r["oracle_divergence_count"] for r in base[-5:]]
    if bdiv and cur["oracle_divergence_count"]>max(bdiv):find.append({"kind":"ORACLE_DIVERGENCE_INCREASE","severity":"HIGH","baseline_max":max(bdiv),"current":cur["oracle_divergence_count"]})
    vals=[r["metrics"][metric] for r in base if metric in r["metrics"]];cal=len(vals)>=MIN_CALIBRATION_RELEASES;budget=None
    if cal and metric in cur["metrics"]:
        med=statistics.median(vals);mad=statistics.median(abs(x-med) for x in vals);ceiling=max(med*1.35,med+6*1.4826*mad)
        budget={"median":round(med,3),"mad":round(mad,3),"ceiling":round(ceiling,3)}
        if cur["metrics"][metric]>ceiling:find.append({"kind":"PERFORMANCE_REGRESSION","severity":"HIGH","metric":metric,"observed":cur["metrics"][metric],"ceiling":round(ceiling,3)})
    return {"status":"DRIFT_DETECTED" if find else "NO_MATERIAL_DRIFT","observation_count":len(rows),"metric":metric,"calibrated_slo":cal,"budget":budget,
            "engine_changed":bool(cur["python_hwpx"] and base[-1]["python_hwpx"] and cur["python_hwpx"]!=base[-1]["python_hwpx"]),"findings":find,
            "current_release":{"phase":cur["phase"],"product":cur["product"],"exact_head":cur["exact_head"]}}
def route_native_render_escalation(o:Mapping[str,Any])->dict:
    locus=str(o.get("locus") or o.get("localization") or "").upper();sev=str(o.get("severity") or "MEDIUM").upper();high=bool(o.get("high_value")) or sev in {"HIGH","CRITICAL"}
    if o.get("native_render_evidence_present"):route,reason="NO_ESCALATION","native-render evidence already exists"
    elif locus in {"PACKAGE_OR_CONTAINER","PRIMARY_ENGINE_COMPATIBILITY","PERFORMANCE_REGRESSION"}:route,reason="ENGINEERING_REPRODUCTION","parser/package evidence is already actionable"
    elif o.get("semantic_match") is False and high:route,reason="NATIVE_RENDER_REQUIRED","high-value semantic divergence requires world-contact"
    elif locus in {"INDEPENDENT_ORACLE_DIVERGENCE","OWPML_INTEROPERABILITY_OR_SHARED_UNSUPPORTED_FEATURE","SEMANTIC_MODEL_DIVERGENCE"} and high:route,reason="NATIVE_RENDER_REQUIRED","high-value parser evidence remains ambiguous"
    elif o.get("attribution_abstain") and high:route,reason="NATIVE_RENDER_REQUIRED","high-value feature attribution abstained"
    elif locus in {"INDEPENDENT_ORACLE_DIVERGENCE","OWPML_INTEROPERABILITY_OR_SHARED_UNSUPPORTED_FEATURE","SEMANTIC_MODEL_DIVERGENCE"}:route,reason="PARSER_EVIDENCE_CONTINUE","retain ambiguity without native escalation yet"
    else:route,reason="NO_ESCALATION","no unresolved ambiguity requiring native world-contact"
    b={"phase":PHASE,"route":route,"reason":reason,"high_value":high,"locus":locus or "UNSPECIFIED"};return {**b,"routing_sha256":_sha(b)}
def build_operator_dashboard(releases:Sequence[Mapping[str,Any]],prov:Sequence[Mapping[str,Any]])->dict:
    rr=[canonical_release_observation(x) for x in releases];pp=[canonical_corpus_provenance(x) for x in prov]
    drift=detect_longitudinal_drift(rr) if rr else {"status":"INSUFFICIENT_HISTORY","findings":[],"calibrated_slo":False};latest=rr[-1] if rr else None
    fam=sorted({x["feature_family"] for x in pp if x["feature_family"]});ns=sorted({x["federation_namespace"] for x in pp if x["federation_namespace"]})
    b={"schema":"chatgpt-web-hwpx-mcp/p4.4/operator-dashboard/v1","phase":PHASE,"product":PRODUCT,"release_observation_count":len(rr),
       "latest_certified_release":None if latest is None else {"phase":latest["phase"],"product":latest["product"],"exact_head":latest["exact_head"]},
       "compatibility_drift":drift,"federated_corpus":{"record_count":len(pp),"namespace_count":len(ns),"feature_families":fam,"namespaces":ns},
       "native_render_escalation_backlog":sum(x["native_render_escalation_count"] for x in rr[-5:]),"slo_calibrated":bool(drift.get("calibrated_slo")),
       "slo_note":"requires >=5 historical baseline observations for median/MAD calibration"}
    return {**b,"dashboard_sha256":_sha(b)}
_BAD=re.compile(r"(?:token|secret|passphrase|authorization|raw_stack|stack_trace|document_bytes|file_bytes|content_bytes)",re.I)
def _san(v:Any,d:int=0)->Any:
    if d>5:return "[DEPTH_LIMIT]"
    if isinstance(v,Mapping):return {str(k)[:120]:_san(x,d+1) for k,x in v.items() if not _BAD.search(str(k))}
    if isinstance(v,(list,tuple)):return [_san(x,d+1) for x in list(v)[:50]]
    if isinstance(v,str):return v[:1000]
    return v if isinstance(v,(int,float,bool)) or v is None else str(v)[:1000]
def build_support_bundle(context:Mapping[str,Any],releases:Sequence[Mapping[str,Any]],prov:Sequence[Mapping[str,Any]])->dict:
    body={"schema":"chatgpt-web-hwpx-mcp/p4.4/support-bundle/v1","phase":PHASE,"product":PRODUCT,"context":_san(context),
          "dashboard":build_operator_dashboard(releases,prov),"release_events":[canonical_release_observation(x) for x in releases][-20:],
          "provenance_events":[canonical_corpus_provenance(x) for x in prov][-50:],"privacy":{"document_bytes_included":False,"raw_stack_trace_included":False,"secrets_included":False}}
    bid="sha256:"+_sha(body);return {**body,"bundle_id":bid,"suggested_filename":f"hwpx-p44-support-{bid[7:19]}.json"}
