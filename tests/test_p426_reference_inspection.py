"""P4.26 actual HWPX reference fields observed through an MCP tool."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hwpx_mcp.interfaces.p426_academic_references import register_academic_reference_tools
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan

DOC = "doc_" + "b" * 24
OWNER = "synthetic-academic-owner"


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class AcademicReferenceInspectionTests(unittest.TestCase):
    def test_real_saved_native_bookmark_crossref_and_mcp_inspection(self):
        plan = build_report_plan(
            title="교차참조 실험", sections=[{"heading": "결과", "content": [
                {"type": "paragraph", "id": "measurements",
                 "bookmark": "Measurements", "text": "실험값은 여기에 있다."},
                {"type": "paragraph", "id": "pointer",
                 "text": "이쪽을 참조한다. ", "page_ref_target": "measurements"},
            ]}],
        )
        compiled = compile_rich_document_plan(plan)
        with tempfile.TemporaryDirectory(prefix="p426-native-ref-inspect-") as tmp:
            target = Path(tmp) / "document.hwpx"
            compose_document_plan(target, compiled["plan"])
            raw = target.read_bytes()
        mcp = FakeMcp()
        core = SimpleNamespace(
            mcp=mcp, _caller_subject=lambda: OWNER,
            _paths=lambda id: (id, None),
            DOCUMENT_STORE=SimpleNamespace(load_current=lambda id: {
                "owner_subject": OWNER, "revision": 2, "bytes": raw,
            }),
        )
        register_academic_reference_tools(core)
        result = mcp.tools["inspect_document_references"](DOC)
        self.assertEqual(result["crossref_field_count"], 1)
        self.assertIn("Measurements", [b["name"] for b in result["bookmarks"]])
        self.assertEqual(result["revision"], 2)
        self.assertEqual(
            result["page_reference_authority"],
            "NATIVE_FIELD_WITH_CACHED_PAGE_REPAGINATION_REQUIRED",
        )

    def test_no_owned_document_references_exposed(self):
        mcp = FakeMcp()
        core = SimpleNamespace(
            mcp=mcp, _caller_subject=lambda: OWNER,
            _paths=lambda id: id,
            DOCUMENT_STORE=SimpleNamespace(
                load_current=lambda id: {"owner_subject": "another-owner"}),
        )
        register_academic_reference_tools(core)
        with self.assertRaises(FileNotFoundError):
            mcp.tools["inspect_document_references"](DOC)


if __name__ == "__main__":
    unittest.main()
