from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx.tools.package_validator import validate_editor_open_safety

from p321_document_composer import compose_document_plan
from hwpx_mcp.document.p325_drawing_layer import build_drawing_layer_map
from hwpx_mcp.rendering.p47_native_authoring import compile_unified_authoring_plan
from hwpx_mcp.rendering.p48_components import component_authoring_contract, compile_document_components
from hwpx_mcp.interfaces.p48_mcp import _execute_visual_plans
from hwpx_mcp.rendering.p412_native_repair import audit_repaired_visuals


spec = {
    "title": "P4.8 smoke",
    "archetype": "TECHNICAL_NOTE",
    "sections": [{
        "heading": "핵심",
        "components": [
            {"id": "d", "type": "definition", "title": "상태", "text": "관찰 가능한 값이다."},
            {"id": "e", "type": "equation", "label": "one", "latex": r"x^2+1"},
            {"id": "r", "type": "equation_reference", "target": "one"},
            {
                "id": "b",
                "type": "bar_chart",
                "title": "비교",
                "data": [{"label": "A", "value": 1}, {"label": "B", "value": 3}],
            },
        ],
    }],
}
contract = component_authoring_contract()
assert contract["product"] == "0.34.0-p4.8"
compiled = compile_document_components(spec)
assert compiled["ready"] is True
assert compiled["equation_labels"] == {"one": "1"}
unified = compile_unified_authoring_plan(compiled["unified_spec"])

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p48-smoke.hwpx"
    composition = compose_document_plan(path, unified["rich"]["plan"])
    visual = _execute_visual_plans(path, compiled["visual_plans"], composition["bindings"])
    assert visual and visual[0]["type"] == "bar_chart"
    mapped = build_drawing_layer_map(path)
    assert mapped["family_counts"].get("polygon", 0) == 0
    assert mapped["family_counts"].get("rect", 0) == 0
    repaired = audit_repaired_visuals(path, visual)
    assert repaired["status"] == "PASS", repaired["issues"]
    assert all(item["primitive_family"] == "PARAGRAPH_TEXT_VISUALIZATION" for item in visual)
    safety = validate_editor_open_safety(path.read_bytes())
    assert safety.ok, safety.issues

print("P4.8 semantic component authoring + P4.12 active visual substitution smoke PASS")
