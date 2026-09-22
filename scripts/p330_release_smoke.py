from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p330_diagram_design_system import apply_diagram_design_system_atomic, build_diagram_design_system_map


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p330-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.30 release anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.30 release anchor")

    apply_diagram_design_system_atomic(
        path,
        [{
            "op": "instantiate_styled_template",
            "diagram_id": "release",
            "anchor": anchor,
            "template": "decision_gate",
            "labels": {
                "input": "Request",
                "decision": "Approved?",
                "accept": "Publish",
                "reject": "Revise",
            },
            "theme": "presentation",
            "layout_policy": "compact",
        }],
        expected_revision=1,
        current_revision=1,
    )
    reopened = build_diagram_design_system_map(path)
    assert reopened["diagram_count"] == 1
    diagram = reopened["diagrams"][0]
    assert {n["node_id"] for n in diagram["nodes"]} == {"input", "decision", "accept", "reject"}
    decision = next(n for n in diagram["nodes"] if n["node_id"] == "decision")
    assert decision["semantic_role"] == "decision"
    assert decision["effective_style"]["fill_color"] == "#FFF0D6"
    branches = [e for e in diagram["edges"] if e["source"] == "decision"]
    assert len(branches) == 2
    assert all(e["semantic_role"] == "branch" for e in branches)
    assert all(e["effective_style"]["stroke_color"] == "#D97706" for e in branches)

print("P3.30 release smoke PASS")
