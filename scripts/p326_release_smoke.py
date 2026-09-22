from __future__ import annotations
import sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from hwpx import HwpxDocument
from p2_document import build_document_map
from p326_drawing_style import apply_drawing_style_atomic,build_drawing_style_map
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"p326-smoke.hwpx"
    doc=HwpxDocument.new(); doc.add_paragraph("shape smoke"); doc.save_to_path(str(path)); doc.close()
    m=build_document_map(path)
    anchor=next(x["locator"] for x in m["paragraphs"] if x.get("text")=="shape smoke")
    apply_drawing_style_atomic(path,[
        {"op":"insert_line","anchor":anchor,"start_x":0,"start_y":0,"end_x":9000,"end_y":3000},
        {"op":"insert_ellipse","anchor":anchor,"width":8000,"height":5000,"fill_color":"#DDEEFF"},
        {"op":"insert_polygon","anchor":anchor,"points":[[0,0],[7000,0],[3500,5500]],"fill_color":"#FFF0CC"},
        {"op":"insert_arc","anchor":anchor,"width":6000,"height":6000,"arc_type":"PIE","fill_color":"#E8DDFF"},
    ],expected_revision=1,current_revision=1)
    m=build_drawing_style_map(path)
    assert m["drawing_count"]==4
    line=next(x for x in m["objects"] if x["kind"]=="line")
    apply_drawing_style_atomic(path,[
        {"op":"set_shape_stroke","drawing":line["locator"],"color":"#224466","width":420,"style":"DASH","alpha":30},
        {"op":"set_shape_arrowheads","drawing":line["locator"],"head_style":"ARROW","tail_style":"FILLED_CIRCLE"},
        {"op":"set_shape_shadow","drawing":line["locator"],"type":"DROP","offset_x":300,"offset_y":300,"alpha":70},
    ],expected_revision=2,current_revision=2)
    final=build_drawing_style_map(path)
    styled=next(x for x in final["styles"] if x["kind"]=="line")
    assert styled["line_shape"]["color"]=="#224466"
    assert styled["line_shape"]["headStyle"]=="ARROW"
    assert styled["shadow"]["type"]=="DROP"
print("P3.26 release smoke PASS")
