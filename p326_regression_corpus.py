from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p326_drawing_style import apply_drawing_style_atomic, build_drawing_style_map

FIXTURES=[
    "line-authoring","ellipse-authoring","polygon-authoring","arc-authoring",
    "stroke-arrowheads","solid-fill","shadow-transparency","mixed-shape-style",
]


def _source(path: Path) -> str:
    doc=HwpxDocument.new()
    doc.add_paragraph("P3.26 shape anchor")
    doc.save_to_path(str(path))
    doc.close()
    m=build_document_map(path)
    return next(x["locator"] for x in m["paragraphs"] if x.get("text")=="P3.26 shape anchor")


def materialize_p326_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True,exist_ok=True)
    manifest={
        "phase":"P3.26",
        "purpose":"PRODUCT_DRAWING_STYLE_REGRESSION",
        "authority":"STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY",
        "native_render_batch_status":"DEFERRED_BY_DESIGN",
        "fixtures":[],
    }
    for name in FIXTURES:
        folder=out_dir/name
        folder.mkdir(parents=True,exist_ok=True)
        source=folder/"source.hwpx"
        target=folder/"target.hwpx"
        anchor=_source(source)
        target.write_bytes(source.read_bytes())
        if name in {"line-authoring","stroke-arrowheads","shadow-transparency"}:
            create={"op":"insert_line","anchor":anchor,"start_x":0,"start_y":0,"end_x":9000,"end_y":3000}
        elif name in {"ellipse-authoring","solid-fill","mixed-shape-style"}:
            create={"op":"insert_ellipse","anchor":anchor,"width":8000,"height":5000}
        elif name=="polygon-authoring":
            create={"op":"insert_polygon","anchor":anchor,"points":[[0,0],[8000,0],[6500,5500],[1500,6000]]}
        else:
            create={"op":"insert_arc","anchor":anchor,"width":6500,"height":6500,"corner":"TOP_LEFT","arc_type":"CHORD"}
        apply_drawing_style_atomic(target,[create],expected_revision=1,current_revision=1)
        obj=build_drawing_style_map(target)["objects"][0]
        if name=="stroke-arrowheads":
            apply_drawing_style_atomic(target,[
                {"op":"set_shape_stroke","drawing":obj["locator"],"color":"#335577","width":480,"style":"DASH"},
                {"op":"set_shape_arrowheads","drawing":obj["locator"],"head_style":"ARROW","tail_style":"FILLED_CIRCLE"},
            ],expected_revision=2,current_revision=2)
        elif name=="solid-fill":
            apply_drawing_style_atomic(target,[{"op":"set_shape_fill","drawing":obj["locator"],"color":"#CCEEFF","alpha":20}],expected_revision=2,current_revision=2)
        elif name=="shadow-transparency":
            apply_drawing_style_atomic(target,[
                {"op":"set_shape_stroke","drawing":obj["locator"],"alpha":40},
                {"op":"set_shape_shadow","drawing":obj["locator"],"type":"DROP","color":"#777777","offset_x":300,"offset_y":300,"alpha":80},
            ],expected_revision=2,current_revision=2)
        elif name=="mixed-shape-style":
            apply_drawing_style_atomic(target,[
                {"op":"set_shape_stroke","drawing":obj["locator"],"color":"#663399","width":360,"style":"DOT"},
                {"op":"set_shape_fill","drawing":obj["locator"],"color":"#F5E6FF","alpha":15},
                {"op":"set_shape_shadow","drawing":obj["locator"],"type":"DROP","offset_x":250,"offset_y":250,"alpha":60},
            ],expected_revision=2,current_revision=2)
        m=build_drawing_style_map(target)
        manifest["fixtures"].append({
            "name":name,
            "source":str(source.relative_to(out_dir)),
            "target":str(target.relative_to(out_dir)),
            "drawing_count":m["drawing_count"],
            "drawing_style_sha256":m["drawing_style_sha256"],
            "shape_geometry_sha256":m["shape_geometry_sha256"],
        })
    (out_dir/"p326-regression-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest
