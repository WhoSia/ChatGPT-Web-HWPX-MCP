from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p321_document_composer import compose_document_plan
from p323_advanced_tables import build_advanced_table_map
from p336r2_design import compile_design_plan, evaluate_generated_document

base = {
    "preset": "default",
    "blocks": [
        {"id": "title", "type": "title", "text": "R2 Design Benchmark"},
        {"id": "heading", "type": "heading", "level": 1, "text": "Overview"},
        {"id": "body", "type": "paragraph", "text": "Generated body text."},
        {
            "id": "table",
            "type": "table",
            "rows": 12,
            "cols": 2,
            "first_row_header": True,
            "cells": [["Metric", "Value"]] + [[f"M{i}", str(i)] for i in range(11)],
        },
    ],
}
plan = compile_design_plan(base, "POLISHED_REPORT")["plan"]
with tempfile.TemporaryDirectory(prefix="p336r2-") as tmp:
    path = Path(tmp) / "r2.hwpx"
    receipt = compose_document_plan(path, plan)
    table_map = build_advanced_table_map(path)
    benchmark = evaluate_generated_document(path, "POLISHED_REPORT")
    assert receipt["preset"] == "polished-report"
    assert table_map["tables"][0]["repeat_header"] is True
    assert table_map["tables"][0]["page_break"] == "CELL"
    assert benchmark["mechanical_verdict"] == "PASS"
    assert benchmark["aesthetic_verdict"] == "NOT_ADJUDICATED"
    print(json.dumps({
        "status": "PASS",
        "phase": "P3.36-R2",
        "preset": receipt["preset"],
        "table_repeat_header": True,
        "mechanical_verdict": benchmark["mechanical_verdict"],
    }, ensure_ascii=False))
