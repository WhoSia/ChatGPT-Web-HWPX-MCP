from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic, build_diagram_lifecycle_map

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p329-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.29 release anchor")
    doc.save_to_path(str(path))
    doc.close()
    anchor = next(
        x["locator"] for x in build_document_map(path)["paragraphs"]
        if x.get("text") == "P3.29 release anchor"
    )

    apply_diagram_lifecycle_atomic(
        path,
        [{"op": "instantiate_template", "diagram_id": "release", "template": "linear_process", "anchor": anchor}],
        expected_revision=1,
        current_revision=1,
    )
    apply_diagram_lifecycle_atomic(
        path,
        [{"op": "patch_node", "diagram_id": "release", "node_id": "work", "label": "Review", "x": 17000}],
        expected_revision=2,
        current_revision=2,
    )
    apply_diagram_lifecycle_atomic(
        path,
        [{"op": "clone_subgraph", "diagram_id": "release", "node_ids": ["start", "work"], "new_prefix": "copy", "dy": 9000}],
        expected_revision=3,
        current_revision=3,
    )

    mapped = build_diagram_lifecycle_map(path)
    assert mapped["diagram_count"] == 1
    d = mapped["diagrams"][0]
    assert {n["node_id"] for n in d["nodes"]} >= {"start", "work", "end", "copy-start", "copy-work"}
    assert {e["edge_id"] for e in d["edges"]} >= {"start->work", "work->end", "copy-start->copy-work"}
    assert next(n for n in d["nodes"] if n["node_id"] == "work")["label"] == "Review"

print("P3.29 release smoke PASS")
