from __future__ import annotations
import p349_mcp
class MCP:
    def __init__(self):self.tools={}
    def tool(self,*,annotations=None):
        def d(fn):self.tools[fn.__name__]=fn;return fn
        return d
class Core:
    def __init__(self):self.mcp=MCP()
    @staticmethod
    def _caller_subject():return "pytest"
class FakeRegistry:pass
class FakeAdapters:pass
def test_tool_surface_registration(monkeypatch):
    core=Core();owned={"doc":({},object())}
    class CR:
        def __init__(self,*a):pass
        def analyze(self,*a):return {"status":"PASS","authority":"DESCRIPTIVE_ONLY_NOT_ACTIVATION_AUTHORITY"}
        def certify(self,*a):return {"status":"PASS","composition_id":"sha256:"+"1"*64}
        def snapshot(self,*a):return {"generation":1}
        def activate(self,*a):return {"authority":"ATOMIC_CERTIFIED_COMPOSITION_ACTIVATION_PASS"}
        def rollback(self,*a):return {"authority":"ATOMIC_CERTIFIED_COMPOSITION_ROLLBACK_PASS"}
    monkeypatch.setattr(p349_mcp,"CompositionRegistry",CR);monkeypatch.setattr(p349_mcp,"composition_contract",lambda:{"phase":"P3.49","product":"0.26.0-p3.49"});p349_mcp.register_p349_tools(core,lambda d:owned[d],FakeRegistry(),FakeAdapters());assert {"get_extension_composition_contract","analyze_extension_composition","certify_extension_composition","get_extension_composition_state","activate_extension_composition","rollback_extension_composition"}<=set(core.mcp.tools);assert core.mcp.tools["analyze_extension_composition"]("doc",[],[])["ok"]
