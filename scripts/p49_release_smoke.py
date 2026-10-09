from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx.tools.package_validator import validate_editor_open_safety

from p321_document_composer import compose_document_plan
from p47_native_authoring import compile_unified_authoring_plan
from p48_components import compile_document_components
from hwpx_mcp.interfaces.p48_mcp import _execute_bar_chart, _execute_kpi_strip
from hwpx_mcp.quality.p49_equation_witnesses import alignment_witness_contract, adjudicate_alignment_witness
from p49_visual_conformance import audit_materialized_visuals, certify_visual_plans


spec = {
    "title": "P4.9 release smoke",
    "archetype": "LAB_REPORT",
    "sections": [{
        "heading": "Visual conformance",
        "components": [
            {
                "id": "bars",
                "type": "bar_chart",
                "title": "Unequal bars",
                "data": [
                    {"label": "short", "value": 1},
                    {"label": "long", "value": 9},
                ],
            },
            {
                "id": "kpis",
                "type": "kpi_strip",
                "items": [
                    {"label": "samples", "value": "128"},
                    {"label": "pass", "value": "100%"},
                ],
            },
        ],
    }],
}

compiled = compile_document_components(spec)
assert compiled["ready"] is True
assert [plan["type"] for plan in compiled["visual_plans"]] == ["bar_chart", "kpi_strip"]
static = certify_visual_plans(compiled["visual_plans"])
assert static["status"] == "PASS", static["issues"]

unified = compile_unified_authoring_plan(compiled["unified_spec"])
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p49-release-smoke.hwpx"
    composition = compose_document_plan(path, unified["rich"]["plan"])
    receipts = []
    for plan in compiled["visual_plans"]:
        anchor = str(composition["bindings"][str(plan["anchor_block_id"])]["locator"])
        if plan["type"] == "bar_chart":
            receipts.append(_execute_bar_chart(path, plan, anchor))
        elif plan["type"] == "kpi_strip":
            receipts.append(_execute_kpi_strip(path, plan, anchor))
        else:
            raise AssertionError(plan["type"])
    materialized = audit_materialized_visuals(path, receipts)
    assert materialized["status"] == "PASS", materialized["issues"]
    safety = validate_editor_open_safety(path.read_bytes())
    assert safety.ok, safety.issues

witness = alignment_witness_contract()
assert witness["witness_kind"] == "SAME_CARGO_ALIGNMENT_TRIAD"
assert [x["expected_alignment"] for x in witness["variants"]] == ["LEFT", "CENTER", "RIGHT"]
assert len({x["cargo"] for x in witness["variants"]}) == 1
pending = adjudicate_alignment_witness(None)
assert pending["status"] == "WORLD_CONTACT_PENDING"
assert pending["eligible"] == []

print("P4.9 native visual conformance + discriminating equation witness smoke PASS")
