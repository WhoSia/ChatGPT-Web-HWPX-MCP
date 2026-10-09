from __future__ import annotations
from hwpx_mcp.interfaces import p43_mcp

class MCP:
    def __init__(self):self.tools={}
    def tool(self,*,annotations=None):
        def deco(fn):self.tools[fn.__name__]=fn;return fn
        return deco
class Core:
    def __init__(self):self.mcp=MCP()
    @staticmethod
    def _caller_subject():return "pytest"

def test_p43_tool_surface():
    core=Core();p43_mcp.register_p43_tools(core)
    expected={"get_continuous_product_health_contract","get_cross_release_benchmark_history","localize_product_regression","build_reproducible_failure_bundle","adjudicate_continuous_product_health"}
    assert expected<=set(core.mcp.tools)
    assert core.mcp.tools["get_continuous_product_health_contract"]()["phase"]=="P4.3"
