from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p328_high_level_diagrams import apply_high_level_diagrams_atomic, build_high_level_diagram_map

FIXTURES = [
    "labeled-rect",
    "labeled-ellipse",
    "labeled-diamond",
    "callout",
    "plan-ltr",
    "plan-topdown",
    "flowchart",
    "org-chart",
]


def _source(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.28 regression anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.28 regression anchor")


def materialize_p328_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.28",
        "purpose": "PRODUCT_HIGH_LEVEL_DIAGRAM_REGRESSION",
        "authority": "STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "fixtures": [],
    }
    for name in FIXTURES:
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "source.hwpx"
        target = folder / "target.hwpx"
        anchor = _source(source)
        target.write_bytes(source.read_bytes())

        if name.startswith("labeled-"):
            node_type = {
                "labeled-rect": "process",
                "labeled-ellipse": "terminator",
                "labeled-diamond": "decision",
            }[name]
            op = {
                "op": "insert_labeled_node",
                "anchor": anchor,
                "node_type": node_type,
                "text": name,
                "horizontal_offset": 1200,
                "vertical_offset": 900,
            }
        elif name == "callout":
            op = {
                "op": "insert_callout",
                "anchor": anchor,
                "text": "Callout",
                "horizontal_offset": 1200,
                "vertical_offset": 900,
                "target_x": 15000,
                "target_y": 7000,
            }
        elif name in {"plan-ltr", "plan-topdown"}:
            op = {
                "op": "insert_diagram_plan",
                "anchor": anchor,
                "plan": {
                    "layout": "LEFT_TO_RIGHT" if name == "plan-ltr" else "TOP_DOWN",
                    "nodes": [
                        {"id": "a", "type": "terminator", "label": "A"},
                        {"id": "b", "type": "process", "label": "B"},
                        {"id": "c", "type": "decision", "label": "C"},
                    ],
                    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
                },
            }
        elif name == "flowchart":
            op = {
                "op": "insert_flowchart",
                "anchor": anchor,
                "steps": ["Start", "Process", "Review", "End"],
            }
        else:
            op = {
                "op": "insert_org_chart",
                "anchor": anchor,
                "root": {
                    "id": "root",
                    "label": "Root",
                    "children": [
                        {"id": "left", "label": "Left"},
                        {"id": "right", "label": "Right"},
                    ],
                },
            }

        apply_high_level_diagrams_atomic(target, [op], expected_revision=1, current_revision=1)
        final = build_high_level_diagram_map(target)
        manifest["fixtures"].append({
            "name": name,
            "source": str(source.relative_to(out_dir)),
            "target": str(target.relative_to(out_dir)),
            "labeled_node_count": final["labeled_node_count"],
            "shape_text_sha256": final["shape_text_sha256"],
            "diagram_placement_sha256": final["diagram_placement_sha256"],
        })

    (out_dir / "p328-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
