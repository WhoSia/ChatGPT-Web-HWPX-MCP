from hwpx_mcp.interfaces import p45_mcp
class MCP:
 def __init__(self):self.tools={}
 def tool(self,**kwargs):
  def d(fn):self.tools[fn.__name__]=fn;return fn
  return d
class Store:
 def query_release_observations(self,**kwargs):return []
 def query_corpus_provenance(self,**kwargs):return []
class Core:
 def __init__(self):self.mcp=MCP()
 def _caller_subject(self):return "test"
def test_p45_tools_register():
 c=Core();p45_mcp.register_p45_tools(c,Store());assert {"get_slo_readiness","append_drift_incident","get_native_render_adjudication_queue","get_operator_quality_alerts"} <= set(c.mcp.tools)
 event=c.mcp.tools["append_drift_incident"]({"locus":"SEMANTIC_MODEL_DIVERGENCE","severity":"HIGH"});assert event["routing"]["route"]=="NATIVE_RENDER_REQUIRED"
 assert c.mcp.tools["get_native_render_adjudication_queue"]()["queue_count"]==1
