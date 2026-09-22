from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p326_drawing_style import apply_drawing_style_atomic
from p327_diagram_composition import (
    apply_diagram_composition_atomic,
    build_diagram_composition_map,
)

FIXTURES = [
    "group-create",
    "group-translate",
    "align",
    "distribute",
    "static-connector",
    "diagram-block",
]


def _source(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.27 diagram anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.27 diagram anchor")


def materialize_p327_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.27",
        "purpose": "PRODUCT_DIAGRAM_COMPOSITION_REGRESSION",
        "authority": "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY",
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

        if name in {"group-create", "group-translate", "diagram-block"}:
            op = (
                {"op": "insert_diagram_block", "preset": "three_stage", "anchor": anchor, "horizontal_offset": 1000, "vertical_offset": 800}
                if name == "diagram-block"
                else {
                    "op": "insert_group",
                    "anchor": anchor,
                    "horizontal_offset": 1000,
                    "vertical_offset": 800,
                    "members": [
                        {"kind": "rect", "x": 0, "y": 0, "width": 5000, "height": 3000},
                        {"kind": "ellipse", "x": 7000, "y": 0, "width": 4000, "height": 3000},
                    ],
                }
            )
            apply_diagram_composition_atomic(target, [op], expected_revision=1, current_revision=1)
            if name == "group-translate":
                group = build_diagram_composition_map(target)["groups"][0]
                apply_diagram_composition_atomic(
                    target,
                    [{"op": "translate_group", "group": group["locator"], "dx": 700, "dy": 500}],
                    expected_revision=2,
                    current_revision=2,
                )
        else:
            apply_drawing_style_atomic(
                target,
                [
                    {"op": "insert_ellipse", "anchor": anchor, "width": 4000, "height": 3000, "treat_as_char": False},
                    {"op": "insert_ellipse", "anchor": anchor, "width": 4000, "height": 3000, "treat_as_char": False},
                    {"op": "insert_ellipse", "anchor": anchor, "width": 4000, "height": 3000, "treat_as_char": False},
                ],
                expected_revision=1,
                current_revision=1,
            )
            mapped = build_diagram_composition_map(target)
            locs = [item["locator"] for item in mapped["top_level_objects"] if item["kind"] == "ellipse"]
            from p325_drawing_layer import _mutate_section, _find_node, HP
            for index, locator in enumerate(locs):
                item = next(x for x in build_diagram_composition_map(target)["top_level_objects"] if x["locator"] == locator)
                def mutate(root, item=item, index=index):
                    node = _find_node(root, item)
                    pos = node.find(f"{HP}pos")
                    pos.set("horzOffset", str(index * 8000))
                    pos.set("vertOffset", str(1000 + index * 700))
                _mutate_section(target, item["section"], mutate)
            if name == "align":
                apply_diagram_composition_atomic(
                    target,
                    [{"op": "align_objects", "drawings": locs, "mode": "TOP"}],
                    expected_revision=2,
                    current_revision=2,
                )
            elif name == "distribute":
                apply_diagram_composition_atomic(
                    target,
                    [{"op": "distribute_objects", "drawings": locs, "mode": "HORIZONTAL"}],
                    expected_revision=2,
                    current_revision=2,
                )
            else:
                apply_diagram_composition_atomic(
                    target,
                    [{"op": "insert_static_connector", "source": locs[0], "target": locs[-1]}],
                    expected_revision=2,
                    current_revision=2,
                )

        final = build_diagram_composition_map(target)
        manifest["fixtures"].append({
            "name": name,
            "source": str(source.relative_to(out_dir)),
            "target": str(target.relative_to(out_dir)),
            "top_level_count": final["top_level_count"],
            "group_count": final["group_count"],
            "diagram_placement_sha256": final["diagram_placement_sha256"],
            "group_topology_sha256": final["group_topology_sha256"],
        })

    (out_dir / "p327-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
