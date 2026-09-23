#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))

from hwpx import HwpxDocument
from p2_document import build_document_map
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from p327_diagram_composition import apply_diagram_composition_atomic, build_diagram_composition_map
from p334r2_package_validation import validate_hwpx_package_light

def anchor(path:Path)->str:
    return next(p["locator"] for p in build_document_map(path)["paragraphs"] if p["text"]=="R3 anchor")

def build_base(path:Path):
    doc=HwpxDocument.new(); doc.add_paragraph("P3.34-R3 native grouping probe"); doc.add_paragraph("R3 anchor"); doc.save_to_path(str(path)); doc.close()

def add_two_rectangles(path:Path):
    a=anchor(path)
    apply_drawing_layer_atomic(path,[
      {"op":"insert_rectangle","anchor":a,"width":7200,"height":3600,"horizontal_offset":3600,"vertical_offset":3600},
      {"op":"insert_rectangle","anchor":a,"width":5400,"height":5400,"horizontal_offset":14400,"vertical_offset":7200},
    ],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out",default="artifacts/p334r3-group-ungroup-pack"); args=ap.parse_args()
    root=Path(args.out); root.mkdir(parents=True,exist_ok=True)
    cases=[]

    # existing top-level -> native group
    d=root/"group-two-rectangles"; d.mkdir(exist_ok=True)
    src=d/"source.hwpx"; tgt=d/"target.hwpx"; build_base(src); add_two_rectangles(src); shutil.copy2(src,tgt)
    cases.append({"id":"group-two-rectangles","action":"GROUP_SELECTED","source":str(src),"target":str(tgt)})

    # existing generated group -> native ungroup
    d=root/"ungroup-existing-group"; d.mkdir(exist_ok=True)
    src=d/"source.hwpx"; tgt=d/"target.hwpx"; build_base(src)
    a=anchor(src)
    apply_diagram_composition_atomic(src,[{"op":"insert_group","anchor":a,"horizontal_offset":5000,"vertical_offset":6000,"members":[
      {"kind":"rect","x":0,"y":0,"width":6500,"height":3400,"fill_color":"#EEF4FF"},
      {"kind":"rect","x":9000,"y":2500,"width":5200,"height":4800,"fill_color":"#FCEAEA"},
    ]}],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    shutil.copy2(src,tgt)
    cases.append({"id":"ungroup-existing-group","action":"UNGROUP","source":str(src),"target":str(tgt)})

    # translated group -> native ungroup, gives a second transform witness
    d=root/"ungroup-translated-group"; d.mkdir(exist_ok=True)
    src=d/"source.hwpx"; tgt=d/"target.hwpx"; build_base(src)
    a=anchor(src)
    apply_diagram_composition_atomic(src,[{"op":"insert_group","anchor":a,"horizontal_offset":18000,"vertical_offset":12000,"members":[
      {"kind":"rect","x":1000,"y":1500,"width":6000,"height":3000,"fill_color":"#EAF7EA"},
      {"kind":"rect","x":10500,"y":5000,"width":7000,"height":4200,"fill_color":"#FFF6DD"},
    ]}],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    shutil.copy2(src,tgt)
    cases.append({"id":"ungroup-translated-group","action":"UNGROUP","source":str(src),"target":str(tgt)})

    manifest={"schema":"chatgpt-web-hwpx-mcp/p3.34-r3/native-group-ungroup/v1","phase":"P3.34-R3","authority":"EVIDENCE_ONLY","cases":[]}
    for c in cases:
      before=build_diagram_composition_map(Path(c["source"]))
      c["before"]={"top_level_count":before["top_level_count"],"group_count":before["group_count"],"top_level_objects":before["top_level_objects"],"groups":before["groups"]}
      manifest["cases"].append(c)
      (root/c["id"]/"case.json").write_text(json.dumps(c,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (root/"capture-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"P3.34-R3 materialized {len(cases)} native grouping fixtures")
    return 0
if __name__=="__main__": raise SystemExit(main())
