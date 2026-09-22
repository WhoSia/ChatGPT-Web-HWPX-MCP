from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p328_high_level_diagrams import _insert_labeled_node, _insert_pointer_line
from p327_diagram_composition import _position_xy, _resolve_top, _size
from p329_diagram_lifecycle import build_diagram_lifecycle_map
from p332_brownfield_diagrams import (
    apply_legacy_diagram_refactor_atomic,
    build_brownfield_diagram_map,
    plan_diagram_adoption,
    plan_legacy_diagram_refactor,
    promote_diagram_candidate_atomic,
)

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p332-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.32 release anchor")
    doc.save_to_path(str(path))
    doc.close()
    anchor = next(
        p["locator"] for p in build_document_map(path)["paragraphs"]
        if p.get("text") == "P3.32 release anchor"
    )
    a = _insert_labeled_node(path, {
        "anchor": anchor, "node_type": "process", "text": "Existing",
        "horizontal_offset": 1000, "vertical_offset": 1000,
    })["created_node"]
    b = _insert_labeled_node(path, {
        "anchor": anchor, "node_type": "terminator", "text": "Done",
        "horizontal_offset": 12000, "vertical_offset": 1000,
    })["created_node"]
    left, right = _resolve_top(path, a), _resolve_top(path, b)
    ax, ay = _position_xy(left); bx, by = _position_xy(right)
    aw, ah = _size(left); bw, bh = _size(right)
    _insert_pointer_line(
        path, anchor=anchor,
        start=(ax + aw // 2, ay + ah // 2),
        end=(bx + bw // 2, by + bh // 2),
        line_color="#555555", line_width=200,
    )

    mapped = build_brownfield_diagram_map(path)
    assert mapped["candidate_count"] == 1
    assert mapped["promotable_candidate_count"] == 1
    candidate = mapped["candidates"][0]
    plan = plan_diagram_adoption(path, candidate["candidate_id"], "release")
    receipt = promote_diagram_candidate_atomic(path, plan, expected_revision=1, current_revision=1)
    assert receipt["node_count"] == 2 and receipt["edge_count"] == 1

    relation = receipt["relation_sha256"]
    refactor = plan_legacy_diagram_refactor(path, "release", layout_policy="standard", theme="mono")
    result = apply_legacy_diagram_refactor_atomic(path, refactor, expected_revision=2, current_revision=2)
    assert result["relation_preserved"]
    final = build_diagram_lifecycle_map(path)["diagrams"][0]
    assert final["relation_sha256"] == relation

print("P3.32 release smoke PASS")
