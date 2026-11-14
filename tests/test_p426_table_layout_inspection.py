"""P4.26 actual HWPX long-table pagination attributes exposed over MCP."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.interfaces.p426_table_layout import register_table_layout_tools

DOC = "doc_" + "e" * 24
OWNER = "table-layout-owner"


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class TableLayoutToolTests(unittest.TestCase):
    def _core(self, row):
        mcp = FakeMcp()
        core = SimpleNamespace(
            mcp=mcp, _caller_subject=lambda: OWNER,
            _paths=lambda document_id: (document_id, None),
            DOCUMENT_STORE=SimpleNamespace(load_current=lambda document_id: row),
        )
        register_table_layout_tools(core)
        return mcp.tools

    def test_native_80_row_table_reopens_with_repeat_header(self):
        rows = [["회차", "전압", "전류"]] + [
            [str(i), str(i * 2), f"{i / 10:.2f}"]
            for i in range(1, 80)
        ]
        plan = build_report_plan(
            title="반복 측정", sections=[{"heading": "결과", "tables": [{
                "cells": rows,
                "first_row_header": True,
                "table_format": {"page_break": "CELL", "repeat_header": True},
            }]}],
        )
        compiled = compile_rich_document_plan(plan)
        with tempfile.TemporaryDirectory(prefix="p426-table-inspection-") as tmp:
            source = Path(tmp) / "long.hwpx"
            receipt = compose_document_plan(source, compiled["plan"])
            self.assertTrue(receipt["atomic_commit"])
            raw = source.read_bytes()
        tools = self._core({
            "owner_subject": OWNER, "revision": 7, "bytes": raw,
        })
        mapped = tools["inspect_document_table_layout"](DOC)
        self.assertEqual(mapped["table_count"], 1)
        self.assertEqual(mapped["revision"], 7)
        self.assertEqual(mapped["tables"][0]["rows"], 80)
        self.assertEqual(mapped["tables"][0]["page_break"], "CELL")
        self.assertTrue(mapped["tables"][0]["repeat_header"])
        self.assertTrue(mapped["tables"][0]["first_row_marked_header"])
        self.assertFalse(mapped["page_boundary_verified"])

    def test_ownership_and_inputs_are_checked_before_reading(self):
        tools = self._core({
            "owner_subject": "someone-else", "revision": 1, "bytes": b"test",
        })
        with self.assertRaises(FileNotFoundError):
            tools["inspect_document_table_layout"](DOC)
        with self.assertRaisesRegex(ValueError, "OFFSET_INVALID"):
            tools["inspect_document_table_layout"](DOC, offset=-1)
        with self.assertRaisesRegex(ValueError, "LIMIT_INVALID"):
            tools["inspect_document_table_layout"](DOC, limit=101)


if __name__ == "__main__":
    unittest.main()
