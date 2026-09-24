from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p23_richtext import apply_rich_formatting_atomic
from p321_document_composer import compose_document_plan
from p336r2_design import (
    compile_design_plan,
    evaluate_generated_document,
    paragraph_features_from_hwpx,
)

base = {
    "preset": "default",
    "blocks": [
        {"id": "body", "type": "paragraph", "text": "Body text"},
        {
            "id": "table",
            "type": "table",
            "rows": 14,
            "cols": 2,
            "first_row_header": True,
            "cells": [["Nested report title", ""]] + [[f"M{i}", str(i)] for i in range(13)],
        },
    ],
}

results = {}
with tempfile.TemporaryDirectory(prefix="p336r2r2-") as tmp:
    root = Path(tmp)
    for mode in ("INSTITUTIONAL_COMPATIBILITY", "POLISHED_REPORT"):
        path = root / f"{mode.lower()}.hwpx"
        plan = compile_design_plan(base, mode)["plan"]
        compose_document_plan(path, plan)
        nested = next(item for item in paragraph_features_from_hwpx(path) if item["in_table"])
        apply_rich_formatting_atomic(
            path,
            [
                {"op": "set_run_format", "target": nested["locator"], "format": {"size": 18}},
                {"op": "set_paragraph_format", "target": nested["locator"], "format": {"alignment": "CENTER"}},
            ],
            expected_revision=1,
            current_revision=1,
            validator=None,
        )
        benchmark = evaluate_generated_document(path, mode)
        roles = benchmark["presentation_roles"]
        assert benchmark["mechanical_verdict"] == "PASS"
        assert benchmark["aesthetic_verdict"] == "NOT_ADJUDICATED"
        assert roles["primary_hierarchy_count"] == 0
        assert roles["recovery"]["applied"] is True
        assert roles["recovery"]["strategy"] == "EARLY_NESTED_SIZE_CENTER_TITLE"
        assert roles["final_hierarchy_count"] >= 1
        recovery_gate = next(
            gate for gate in benchmark["gates"]
            if gate["gate"] == "MULTI_CONTAINER_HIERARCHY_RECOVERY"
        )
        assert recovery_gate["status"] == "PASS"
        results[mode] = {
            "mechanical_verdict": benchmark["mechanical_verdict"],
            "recovery_strategy": roles["recovery"]["strategy"],
            "hierarchy_count": roles["final_hierarchy_count"],
        }

print(json.dumps({
    "status": "PASS",
    "phase": "P3.36-R2-R2",
    "modes": results,
    "aesthetic_verdict": "NOT_ADJUDICATED",
}, ensure_ascii=False))
