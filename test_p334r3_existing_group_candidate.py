from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from p326_drawing_style import apply_drawing_style_atomic
from p327_diagram_composition import apply_diagram_composition_atomic, build_diagram_composition_map
from p334r2_package_validation import validate_hwpx_package_light


def _base(path: Path) -> str:
    doc=HwpxDocument.new()
    doc.add_paragraph("P3.34-R3 candidate")
    doc.add_paragraph("R3 anchor")
    doc.save_to_path(str(path))
    doc.close()
    return next(p["locator"] for p in build_document_map(path)["paragraphs"] if p["text"]=="R3 anchor")


def _two_ellipses(path: Path) -> list[str]:
    anchor=_base(path)
    apply_drawing_style_atomic(path,[
        {"op":"insert_ellipse","anchor":anchor,"width":7200,"height":4200,"fill_color":"#DDEEFF","treat_as_char":False},
        {"op":"insert_ellipse","anchor":anchor,"width":6200,"height":5000,"fill_color":"#FFE6D5","treat_as_char":False},
    ],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    mapped=build_drawing_layer_map(path)
    ellipses=[x for x in mapped["objects"] if x["kind"]=="ellipse"]
    apply_drawing_layer_atomic(path,[
        {"op":"set_drawing_layout","drawing":ellipses[0]["locator"],"horz_rel_to":"PARA","vert_rel_to":"PARA","horizontal_offset":9000,"vertical_offset":7000,"text_wrap":"IN_FRONT_OF_TEXT"},
        {"op":"set_drawing_layout","drawing":ellipses[1]["locator"],"horz_rel_to":"PARA","vert_rel_to":"PARA","horizontal_offset":22000,"vertical_offset":11000,"text_wrap":"IN_FRONT_OF_TEXT"},
    ],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    return [x["locator"] for x in build_diagram_composition_map(path)["top_level_objects"]]


def test_group_existing_two_ellipses_uses_native_bbox_rebasing(tmp_path: Path):
    path=tmp_path/"group.hwpx"
    drawings=_two_ellipses(path)
    result=apply_diagram_composition_atomic(
        path,[{"op":"group_existing_objects","drawings":drawings}],
        expected_revision=1,current_revision=1,validator=validate_hwpx_package_light,
    )
    after=build_diagram_composition_map(path)
    assert result["group_topology_changed"] is True
    assert after["top_level_count"]==1 and after["group_count"]==1
    group=after["groups"][0]
    assert group["position"]["horzOffset"]=="9000"
    assert group["position"]["vertOffset"]=="7000"
    assert (group["width"],group["height"])==(19200,9000)
    offsets=sorted((int(m["offset"]["x"]),int(m["offset"]["y"])) for m in group["members"])
    assert offsets==[(0,0),(13000,4000)]


def test_ungroup_existing_rect_group_uses_origin_plus_local_offsets(tmp_path: Path):
    path=tmp_path/"ungroup.hwpx"
    anchor=_base(path)
    apply_diagram_composition_atomic(path,[{
        "op":"insert_group","anchor":anchor,"horizontal_offset":18000,"vertical_offset":12000,
        "members":[
            {"kind":"rect","x":0,"y":0,"width":6000,"height":3000,"fill_color":"#EAF7EA"},
            {"kind":"rect","x":9500,"y":3500,"width":7000,"height":4200,"fill_color":"#FFF6DD"},
        ],
    }],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    before=build_diagram_composition_map(path)
    group=before["groups"][0]
    preserved_instids=sorted(m["instid"] for m in group["members"])

    result=apply_diagram_composition_atomic(
        path,[{"op":"ungroup_existing_objects","group":group["locator"]}],
        expected_revision=2,current_revision=2,validator=validate_hwpx_package_light,
    )
    after=build_diagram_composition_map(path)
    assert result["group_topology_changed"] is True
    assert after["group_count"]==0 and after["top_level_count"]==2
    positions=sorted(
        (int(o["position"]["horzOffset"]),int(o["position"]["vertOffset"]))
        for o in after["top_level_objects"]
    )
    assert positions==[(18000,12000),(27500,15500)]
    assert sorted(o["instid"] for o in after["top_level_objects"])==preserved_instids
