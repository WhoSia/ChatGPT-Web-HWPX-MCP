from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic
from p330_diagram_design_system import apply_diagram_design_system_atomic, build_diagram_design_system_map

FIXTURES = [
    "theme-classic",
    "theme-mono",
    "semantic-node-style",
    "semantic-edge-style",
    "layout-compact",
    "layout-spacious",
    "parameterized-template",
    "bulk-design-system",
]


def _source(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.30 regression anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.30 regression anchor")


def materialize_p330_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.30",
        "purpose": "PRODUCT_DIAGRAM_DESIGN_SYSTEM_REGRESSION",
        "authority": "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY",
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

        if name == "parameterized-template":
            apply_diagram_design_system_atomic(
                target,
                [{
                    "op": "instantiate_styled_template",
                    "diagram_id": "d1",
                    "anchor": anchor,
                    "template": "linear_process",
                    "labels": {"start": "Input", "work": "Transform", "end": "Output"},
                    "theme": "presentation",
                    "layout_policy": "compact",
                }],
                expected_revision=1,
                current_revision=1,
            )
        else:
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "instantiate_template", "diagram_id": "d1", "anchor": anchor, "template": "decision_gate"}],
                expected_revision=1,
                current_revision=1,
            )
            if name == "theme-classic":
                op = {"op": "apply_theme", "diagram_id": "d1", "theme": "classic"}
            elif name == "theme-mono":
                op = {"op": "apply_theme", "diagram_id": "d1", "theme": "mono"}
            elif name == "semantic-node-style":
                op = {"op": "restyle_node", "diagram_id": "d1", "node_id": "decision", "style": {
                    "fill_color": "#FFE4B5", "stroke_color": "#AA5500", "stroke_width": 333,
                }}
            elif name == "semantic-edge-style":
                op = {"op": "restyle_edge", "diagram_id": "d1", "source": "decision", "target": "accept", "style": {
                    "stroke_color": "#CC6600", "stroke_style": "DASH", "head_style": "ARROW",
                }}
            elif name == "layout-compact":
                op = {"op": "apply_layout_policy", "diagram_id": "d1", "policy": "compact"}
            elif name == "layout-spacious":
                op = {"op": "apply_layout_policy", "diagram_id": "d1", "policy": "spacious"}
            else:
                op = {"op": "apply_design_system", "diagram_id": "d1", "theme": "presentation", "layout_policy": "compact"}
            apply_diagram_design_system_atomic(target, [op], expected_revision=2, current_revision=2)

        final = build_diagram_design_system_map(target)
        manifest["fixtures"].append({
            "name": name,
            "source": str(source.relative_to(out_dir)),
            "target": str(target.relative_to(out_dir)),
            "diagram_count": final["diagram_count"],
            "semantic_style_sha256": final["semantic_style_sha256"],
            "diagram_identity_sha256": final["diagram_identity_sha256"],
            "diagram_relation_sha256": final["diagram_relation_sha256"],
        })

    (out_dir / "p330-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
