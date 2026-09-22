from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic
from p330_diagram_design_system import apply_diagram_design_system_atomic
from p331_diagram_quality_assurance import plan_diagram_repairs, validate_diagram_quality


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p331-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.31 release anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.31 release anchor")

    apply_diagram_lifecycle_atomic(
        path,
        [{"op": "instantiate_template", "diagram_id": "release", "anchor": anchor, "template": "linear_process"}],
        expected_revision=1,
        current_revision=1,
    )
    initial = validate_diagram_quality(path, "release", profile="flow", expected_theme="presentation")
    assert initial["passed"]
    assert {"NODE_THEME_MISMATCH", "EDGE_THEME_MISMATCH"} & {x["code"] for x in initial["findings"]}

    plan = plan_diagram_repairs(
        path,
        "release",
        profile="flow",
        expected_theme="presentation",
        repair_theme="presentation",
    )
    assert plan["operation_count"] == 1
    apply_diagram_design_system_atomic(
        path,
        plan["operations"],
        expected_revision=2,
        current_revision=2,
    )
    final = validate_diagram_quality(path, "release", profile="flow", expected_theme="presentation")
    assert final["passed"]
    assert final["error_count"] == 0
    assert final["warning_count"] == 0
    assert final["graph_summary"]["sources"] == ["start"]
    assert final["graph_summary"]["sinks"] == ["end"]

print("P3.31 release smoke PASS")
