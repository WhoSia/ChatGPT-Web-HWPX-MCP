from __future__ import annotations

import p42_mcp

class MCP:
    def __init__(self):
        self.tools = {}
    def tool(self, *, annotations=None):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco

class Core:
    def __init__(self):
        self.mcp = MCP()
    @staticmethod
    def _caller_subject():
        return "pytest"

def test_p42_tool_surface():
    core = Core()
    p42_mcp.register_p42_tools(core)
    assert {
        "get_dependency_migration_contract",
        "get_dependency_runtime_state",
        "adjudicate_dependency_upgrade",
    } <= set(core.mcp.tools)
    assert core.mcp.tools["get_dependency_migration_contract"]()["phase"] == "P4.2"
