import hashlib
import tempfile
from pathlib import Path

from hwpx_mcp.interfaces.p47_mcp import register_p47_tools
from hwpx_mcp.rendering.p47_native_authoring import equation_render_frontier


class MCP:
    def __init__(self):
        self.tools = {}
    def tool(self, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class Core:
    def __init__(self, root):
        self.mcp = MCP()
        self.root = Path(root)
    def _caller_subject(self):
        return "test-subject"
    def _download_secret(self):
        return b"x"
    def _cleanup_expired(self):
        return None
    def sanitize_filename(self, value):
        return str(value)
    def _new_document_id(self):
        return "doc_p47"
    def _idempotent_document_id(self, owner, request):
        return "doc_" + hashlib.sha256((owner + request).encode()).hexdigest()[:12]
    def _paths(self, document_id):
        return self.root / f"{document_id}.hwpx", self.root / f"{document_id}.json"
    def _load_metadata(self, document_id):
        raise FileNotFoundError(document_id)
    def _require_owner(self, metadata):
        return None
    def _delete_document_files(self, document_id):
        for p in self._paths(document_id):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    def validate_hwpx_package(self, path, ingress=False):
        raw = Path(path).read_bytes()
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    def _metadata(self, document_id, **kwargs):
        return {"document_id": document_id, "revision": 1, **kwargs}


def test_registers_small_surface_and_pending_frontier():
    with tempfile.TemporaryDirectory() as tmp:
        core = Core(tmp)
        def refresh(*args, **kwargs):
            return None
        def deliver(*args, **kwargs):
            return {"delivered": True, "args": args}
        register_p47_tools(core, refresh, deliver)
        assert {
            "get_authoring_v2_contract",
            "inspect_equation_render_frontier",
            "adjudicate_equation_render_evidence",
            "compile_unified_authoring_plan",
            "create_unified_document_and_deliver",
        } <= set(core.mcp.tools)
        frontier = core.mcp.tools["inspect_equation_render_frontier"]()
        assert frontier["candidate_count"] == equation_render_frontier()["candidate_count"]
        pending = core.mcp.tools["adjudicate_equation_render_evidence"](None)
        assert pending["promotion_eligible"] == []
