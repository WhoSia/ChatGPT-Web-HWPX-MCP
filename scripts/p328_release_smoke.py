from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p328_high_level_diagrams import apply_high_level_diagrams_atomic, build_high_level_diagram_map


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p328-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.28 release anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.28 release anchor")

    apply_high_level_diagrams_atomic(
        path,
        [{
            "op": "insert_flowchart",
            "anchor": anchor,
            "steps": [
                {"id": "start", "label": "Start", "type": "terminator"},
                {"id": "work", "label": "Work", "type": "process"},
                {"id": "check", "label": "Check", "type": "decision"},
                {"id": "end", "label": "End", "type": "terminator"},
            ],
        }],
        expected_revision=1,
        current_revision=1,
    )
    mapped = build_high_level_diagram_map(path)
    assert mapped["labeled_node_count"] == 4
    labels = {item["draw_text"]["text"] for item in mapped["labeled_nodes"]}
    assert {"Start", "Work", "Check", "End"} <= labels

print("P3.28 release smoke PASS")
