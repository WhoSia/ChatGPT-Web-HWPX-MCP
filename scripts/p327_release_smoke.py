from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p327_diagram_composition import apply_diagram_composition_atomic, build_diagram_composition_map


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p327-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.27 release anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.27 release anchor")

    apply_diagram_composition_atomic(
        path,
        [{
            "op": "insert_diagram_block",
            "preset": "three_stage",
            "anchor": anchor,
            "horizontal_offset": 1400,
            "vertical_offset": 900,
        }],
        expected_revision=1,
        current_revision=1,
    )
    mapped = build_diagram_composition_map(path)
    assert mapped["group_count"] == 1
    group = mapped["groups"][0]
    assert len(group["members"]) == 3

    apply_diagram_composition_atomic(
        path,
        [{"op": "translate_group", "group": group["locator"], "dx": 600, "dy": 400}],
        expected_revision=2,
        current_revision=2,
    )
    reopened = build_diagram_composition_map(path)
    moved = reopened["groups"][0]
    assert moved["position"]["horzOffset"] == "2000"
    assert moved["position"]["vertOffset"] == "1300"

print("P3.27 release smoke PASS")
