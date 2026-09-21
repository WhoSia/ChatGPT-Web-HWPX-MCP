from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map

FIXTURES = [
    "textbox-create",
    "rectangle-create",
    "anchored-layout",
    "wrap-zorder",
    "geometry-rotation-flip",
    "remove-object",
]


def _source(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.25 drawing anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.25 drawing anchor")


def materialize_p325_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.25",
        "purpose": "PRODUCT_DRAWING_LAYER_REGRESSION",
        "authority": "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY",
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

        if name in {"textbox-create", "anchored-layout", "wrap-zorder", "geometry-rotation-flip", "remove-object"}:
            apply_drawing_layer_atomic(
                target,
                [{
                    "op": "insert_textbox",
                    "anchor": anchor,
                    "text": "P3.25",
                    "width": 9000,
                    "height": 4500,
                    "treat_as_char": False,
                    "horizontal_offset": 800,
                    "vertical_offset": 600,
                    "z_order": 3,
                }],
                expected_revision=1,
                current_revision=1,
            )
        else:
            apply_drawing_layer_atomic(
                target,
                [{
                    "op": "insert_rectangle",
                    "anchor": anchor,
                    "width": 8000,
                    "height": 4000,
                    "treat_as_char": False,
                }],
                expected_revision=1,
                current_revision=1,
            )

        mapped = build_drawing_layer_map(target)
        drawing = mapped["objects"][0]
        if name == "anchored-layout":
            apply_drawing_layer_atomic(
                target,
                [{
                    "op": "set_drawing_layout",
                    "drawing": drawing["locator"],
                    "horz_rel_to": "PAPER",
                    "vert_rel_to": "PAPER",
                    "horizontal_offset": 2400,
                    "vertical_offset": 1800,
                }],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "wrap-zorder":
            apply_drawing_layer_atomic(
                target,
                [{
                    "op": "set_drawing_layout",
                    "drawing": drawing["locator"],
                    "text_wrap": "IN_FRONT_OF_TEXT",
                    "z_order": 17,
                }],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "geometry-rotation-flip":
            apply_drawing_layer_atomic(
                target,
                [
                    {"op": "resize_drawing_object", "drawing": drawing["locator"], "width": 11000, "height": 5500},
                    {"op": "rotate_drawing_object", "drawing": drawing["locator"], "angle": 20},
                    {"op": "flip_drawing_object", "drawing": drawing["locator"], "horizontal": True, "vertical": True},
                ],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "remove-object":
            apply_drawing_layer_atomic(
                target,
                [{"op": "remove_drawing_object", "drawing": drawing["locator"]}],
                expected_revision=2,
                current_revision=2,
            )

        final = build_drawing_layer_map(target)
        manifest["fixtures"].append({
            "name": name,
            "source": str(source.relative_to(out_dir)),
            "target": str(target.relative_to(out_dir)),
            "drawing_count": final["drawing_count"],
            "drawing_structure_sha256": final["drawing_structure_sha256"],
            "drawing_geometry_sha256": final["drawing_geometry_sha256"],
        })

    manifest_path = out_dir / "p325-regression-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
