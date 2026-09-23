#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))

from hwpx import HwpxDocument
from p2_document import build_document_map
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from p326_drawing_style import apply_drawing_style_atomic
from p327_diagram_composition import apply_diagram_composition_atomic, build_diagram_composition_map
from p334r2_package_validation import validate_hwpx_package_light

def anchor(path:Path)->str:
    return next(p["locator"] for p in build_document_map(path)["paragraphs"] if p["text"]=="R3 anchor")

def base(path:Path):
    doc=HwpxDocument.new();doc.add_paragraph("P3.34-R3 candidate round-trip");doc.add_paragraph("R3 anchor");doc.save_to_path(str(path));doc.close()

def add_two_ellipses(path:Path):
    a=anchor(path)
    apply_drawing_style_atomic(path,[
      {"op":"insert_ellipse","anchor":a,"width":7200,"height":4200,"fill_color":"#DDEEFF","treat_as_char":False},
      {"op":"insert_ellipse","anchor":a,"width":6200,"height":5000,"fill_color":"#FFE6D5","treat_as_char":False},
    ],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    objs=[o for o in build_drawing_layer_map(path)["objects"] if o["kind"]=="ellipse"]
    apply_drawing_layer_atomic(path,[
      {"op":"set_drawing_layout","drawing":objs[0]["locator"],"horz_rel_to":"PARA","vert_rel_to":"PARA","horizontal_offset":9000,"vertical_offset":7000,"text_wrap":"IN_FRONT_OF_TEXT"},
      {"op":"set_drawing_layout","drawing":objs[1]["locator"],"horz_rel_to":"PARA","vert_rel_to":"PARA","horizontal_offset":22000,"vertical_offset":11000,"text_wrap":"IN_FRONT_OF_TEXT"},
    ],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)

def make_group(path:Path,x:int,y:int):
    a=anchor(path)
    apply_diagram_composition_atomic(path,[{"op":"insert_group","anchor":a,"horizontal_offset":x,"vertical_offset":y,"members":[
      {"kind":"rect","x":0,"y":0,"width":6500,"height":3400,"fill_color":"#EEF4FF"},
      {"kind":"rect","x":9000,"y":2500,"width":5200,"height":4800,"fill_color":"#FCEAEA"},
    ]}],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)

def snapshot(path:Path)->dict:
    m=build_diagram_composition_map(path)
    return {"top_level_count":m["top_level_count"],"group_count":m["group_count"],"top_level_objects":m["top_level_objects"],"groups":m["groups"]}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--out",default="artifacts/p334r3-candidate-roundtrip-pack");args=ap.parse_args()
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    cases=[]

    d=root/"candidate-group-existing";d.mkdir(exist_ok=True);p=d/"candidate-before-hancom.hwpx";base(p);add_two_ellipses(p)
    locs=[o["locator"] for o in build_diagram_composition_map(p)["top_level_objects"]]
    apply_diagram_composition_atomic(p,[{"op":"group_existing_objects","drawings":locs}],expected_revision=2,current_revision=2,validator=validate_hwpx_package_light)
    cases.append({"id":"candidate-group-existing","expected":"grouped","snapshot":snapshot(p)})

    d=root/"candidate-ungroup-existing";d.mkdir(exist_ok=True);p=d/"candidate-before-hancom.hwpx";base(p);make_group(p,5000,6000)
    g=build_diagram_composition_map(p)["groups"][0]["locator"]
    apply_diagram_composition_atomic(p,[{"op":"ungroup_existing_objects","group":g}],expected_revision=2,current_revision=2,validator=validate_hwpx_package_light)
    cases.append({"id":"candidate-ungroup-existing","expected":"ungrouped","snapshot":snapshot(p)})

    d=root/"candidate-ungroup-translated";d.mkdir(exist_ok=True);p=d/"candidate-before-hancom.hwpx";base(p);make_group(p,18000,12000)
    g=build_diagram_composition_map(p)["groups"][0]["locator"]
    apply_diagram_composition_atomic(p,[{"op":"ungroup_existing_objects","group":g}],expected_revision=2,current_revision=2,validator=validate_hwpx_package_light)
    cases.append({"id":"candidate-ungroup-translated","expected":"ungrouped","snapshot":snapshot(p)})

    manifest={"schema":"chatgpt-web-hwpx-mcp/p3.34-r3/candidate-roundtrip/v1","phase":"P3.34-R3","cases":[]}
    for case in cases:
        d=root/case["id"];after=d/"candidate-after-hancom.hwpx"
        if after.exists(): after.unlink()
        (d/"case.json").write_text(json.dumps(case,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        manifest["cases"].append(case)
    (root/"roundtrip-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("P3.34-R3 materialized 3 implementation-generated group/ungroup fixtures")
    return 0
if __name__=="__main__": raise SystemExit(main())
