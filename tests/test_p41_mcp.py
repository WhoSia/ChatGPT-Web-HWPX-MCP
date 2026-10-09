from __future__ import annotations

from hwpx_mcp.interfaces import p41_mcp

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
    @staticmethod
    def materialize_hwpx(path, text, title):
        path.write_bytes(b"fake")
        return {"valid": True}
    @staticmethod
    def validate_hwpx_package(path, ingress=False):
        return {"valid": path.exists(), "ingress": ingress}

def test_p41_tool_surface(monkeypatch):
    core = Core()
    monkeypatch.setattr(
        p41_mcp,
        "runtime_compatibility_matrix",
        lambda candidate: {"phase": "P4.1", "runtime_status": "SUPPORTED_BASELINE", "candidate": candidate},
    )
    monkeypatch.setattr(
        p41_mcp,
        "profile_operations",
        lambda specs, sample_count=3: {"phase": "P4.1", "status": "PASS", "operations": [], "sample_count": sample_count},
    )
    p41_mcp.register_p41_tools(core)
    expected = {
        "get_product_operational_readiness_contract",
        "get_product_runtime_compatibility",
        "profile_product_operational_baseline",
        "diagnose_product_failure",
        "evaluate_python_hwpx_upgrade",
    }
    assert expected <= set(core.mcp.tools)
    assert core.mcp.tools["get_product_runtime_compatibility"]("6.6.0")["ok"]
    assert core.mcp.tools["profile_product_operational_baseline"](2)["ok"]
