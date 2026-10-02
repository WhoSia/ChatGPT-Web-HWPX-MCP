import hashlib
import io
import tempfile
from pathlib import Path

from hwpx import HwpxDocument

import p46_mcp


class MCP:
    def __init__(self):
        self.tools = {}
    def tool(self, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


class Core:
    def __init__(self):
        self.mcp = MCP()
    def _caller_subject(self):
        return "test"
    def validate_hwpx_package(self, path, ingress=False):
        raw = Path(path).read_bytes()
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    def _utc_iso(self):
        return "2026-09-30T00:00:00Z"


def test_p46_tools_register_and_atomic_equation_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p46.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("Anchor")
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        path.write_bytes(buffer.getvalue())
        meta = {"revision": 1, "source": "created"}
        refreshed = []

        def owned(_document_id):
            return meta, path

        def refresh(document_id, metadata, validation, *maps):
            refreshed.append((document_id, int(metadata["revision"]), validation["sha256"]))
            return metadata

        core = Core()
        p46_mcp.register_p46_tools(core, owned, refresh)
        assert {
            "get_native_authoring_contract",
            "inspect_native_authoring_capabilities",
            "compile_native_authoring_bundle",
            "apply_native_authoring_bundle",
            "get_real_document_generation_benchmark",
        } <= set(core.mcp.tools)

        contract = core.mcp.tools["get_native_authoring_contract"]()
        assert contract["phase"] == "P4.6"

        compiled = core.mcp.tools["compile_native_authoring_bundle"](
            "doc_test",
            {"equations": [{"op": "insert_equation", "paragraph": "first_body", "latex": r"\frac{a}{b}"}]},
        )
        assert compiled["ready"] is True

        result = core.mcp.tools["apply_native_authoring_bundle"](
            "doc_test",
            1,
            {"equations": [{"op": "insert_equation", "paragraph": "first_body", "latex": r"\frac{a}{b}"}]},
        )
        assert result["revision_before"] == 1
        assert result["revision_after"] == 2
        assert result["lane_counts"]["equations"] == 1
        assert len(refreshed) == 1
