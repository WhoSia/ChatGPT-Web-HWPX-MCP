import p44_mcp
class MCP:
 def __init__(self):self.tools={}
 def tool(self,*,annotations=None):
  def deco(fn):self.tools[fn.__name__]=fn;return fn
  return deco
class Store:
 mode="fake-append-only"
 def __init__(self):self.releases=[{"phase":"P4.1","product":"0.27","exact_head":"1"*40,"observed_at":"2026-09-27T00:00:00+00:00","metrics":{}},{"phase":"P4.2","product":"0.28","exact_head":"2"*40,"observed_at":"2026-09-28T00:00:00+00:00","metrics":{}}];self.corpus=[{"source_id":"x","federation_namespace":"pytest","source_kind":"TEST","observed_at":"2026-09-29T00:00:00+00:00"}]
 def append_release_observation(self,row):return {"event_id":"x","inserted":True,"payload_sha256":"x"}
 def query_release_observations(self,**kwargs):return self.releases
 def query_corpus_provenance(self,**kwargs):return self.corpus
class Core:
 def __init__(self):self.mcp=MCP()
 @staticmethod
 def _caller_subject():return "pytest"
def test_tools():
 c=Core();p44_mcp.register_p44_tools(c,Store());expected={"get_release_health_intelligence_contract","append_release_health_observation","query_release_health_history","query_federated_corpus_provenance","attribute_document_feature_families","detect_release_compatibility_drift","route_native_render_world_contact","get_operator_quality_dashboard","export_operator_support_bundle"};assert expected<=set(c.mcp.tools);assert c.mcp.tools["get_release_health_intelligence_contract"]()["phase"]=="P4.4";assert c.mcp.tools["get_operator_quality_dashboard"]()["release_observation_count"]==2
