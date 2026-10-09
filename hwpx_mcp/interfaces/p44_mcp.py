from __future__ import annotations
from mcp.types import ToolAnnotations
from hwpx_mcp.quality.p44_health_intelligence import attribute_hwpx_feature_families,build_operator_dashboard,build_support_bundle,detect_longitudinal_drift,health_intelligence_contract,route_native_render_escalation
from hwpx_mcp.quality.p44_health_store import DurableHealthIntelligenceStore,default_database_url
def register_p44_tools(core,store=None):
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False);append=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
    if store is None:store=DurableHealthIntelligenceStore(default_database_url());store.bootstrap()
    @core.mcp.tool(annotations=read)
    def get_release_health_intelligence_contract()->dict:core._caller_subject();return {"ok":True,**health_intelligence_contract(),"store_mode":store.mode}
    @core.mcp.tool(annotations=append)
    def append_release_health_observation(observation:dict)->dict:core._caller_subject();return {"ok":True,**store.append_release_observation(observation)}
    @core.mcp.tool(annotations=read)
    def query_release_health_history(limit:int=100,phase:str="",feature_family:str="")->dict:
        core._caller_subject();rows=store.query_release_observations(limit=limit,phase=phase,feature_family=feature_family);return {"ok":True,"count":len(rows),"events":rows}
    @core.mcp.tool(annotations=read)
    def query_federated_corpus_provenance(limit:int=100,feature_family:str="",namespace:str="")->dict:
        core._caller_subject();rows=store.query_corpus_provenance(limit=limit,feature_family=feature_family,namespace=namespace);return {"ok":True,"count":len(rows),"records":rows}
    @core.mcp.tool(annotations=read)
    def attribute_document_feature_families(document_id:str)->dict:
        core._caller_subject();meta=core._load_metadata(document_id);core._require_owner(meta);path,_=core._paths(document_id);return {"ok":True,**attribute_hwpx_feature_families(path)}
    @core.mcp.tool(annotations=read)
    def detect_release_compatibility_drift(metric:str="create_validate_p95_ms",feature_family:str="")->dict:
        core._caller_subject();r=detect_longitudinal_drift(store.query_release_observations(limit=500,feature_family=feature_family),metric=metric);return {"ok":r["status"]!="DRIFT_DETECTED",**r}
    @core.mcp.tool(annotations=read)
    def route_native_render_world_contact(observation:dict)->dict:core._caller_subject();return {"ok":True,**route_native_render_escalation(observation)}
    @core.mcp.tool(annotations=read)
    def get_operator_quality_dashboard()->dict:
        core._caller_subject();return {"ok":True,**build_operator_dashboard(store.query_release_observations(limit=500),store.query_corpus_provenance(limit=1000))}
    @core.mcp.tool(annotations=read)
    def export_operator_support_bundle(context:dict)->dict:
        core._caller_subject();return {"ok":True,**build_support_bundle(context,store.query_release_observations(limit=500),store.query_corpus_provenance(limit=1000))}
    return {"phase":"P4.4","authority":"DURABLE_RELEASE_HEALTH_INTELLIGENCE_AND_OPERATOR_QUALITY"}
