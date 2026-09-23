#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0,str(REPO_ROOT))

from p22_formatting import build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def local(tag:str)->str:
    return tag.rsplit("}",1)[-1]

def raw_char_pr(path:Path, char_id:str|None)->dict|None:
    if char_id is None:
        return None
    with zipfile.ZipFile(path) as zf:
        root=ET.fromstring(zf.read("Contents/header.xml"))
    for node in root.iter():
        if local(node.tag)=="charPr" and node.attrib.get("id")==str(char_id):
            return {
                "attrs":dict(sorted(node.attrib.items())),
                "children":[
                    {
                        "tag":local(child.tag),
                        "attrs":dict(sorted(child.attrib.items())),
                        "text":child.text,
                    }
                    for child in list(node)
                ],
            }
    return None

def fontface_census(path:Path)->dict:
    with zipfile.ZipFile(path) as zf:
        root=ET.fromstring(zf.read("Contents/header.xml"))
    out={}
    for family in root.iter():
        if local(family.tag)!="fontface":
            continue
        lang=str(family.attrib.get("lang") or "")
        rows=[]
        for font in list(family):
            if local(font.tag)!="font":
                continue
            row={"attrs":dict(sorted(font.attrib.items())),"children":[]}
            for child in list(font):
                row["children"].append({
                    "tag":local(child.tag),
                    "attrs":dict(sorted(child.attrib.items())),
                    "text":child.text,
                })
            rows.append(row)
        out[lang]=rows
    return out

def first_text_run(mapped:dict)->dict:
    for para in mapped["paragraphs"]:
        for run in para["runs"]:
            if run.get("text"):
                return run
    raise RuntimeError("No text-bearing run found")

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--pack",default="artifacts/p335r1-native-typography-pack")
    args=ap.parse_args()
    root=Path(args.pack)
    manifest=json.loads((root/"capture-manifest.json").read_text(encoding="utf-8"))

    reports=[]; failures=[]
    for case in manifest["cases"]:
        d=root/case["id"]; source=d/"source.hwpx"; target=d/"target.hwpx"
        if not target.exists():
            failures.append({"case":case["id"],"reason":"target_missing"}); continue
        validate_hwpx_package_light(source); validate_hwpx_package_light(target)
        before=build_formatting_map(source); after=build_formatting_map(target)
        br=first_text_run(before); ar=first_text_run(after)
        report={
            "case_id":case["id"],"kind":case["kind"],"requested_value":case["value"],
            "source_sha256":sha(source),"target_sha256":sha(target),
            "byte_identical":source.read_bytes()==target.read_bytes(),
            "before_run":br,"after_run":ar,
            "before_char_pr":raw_char_pr(source,br.get("char_pr_id_ref")),
            "after_char_pr":raw_char_pr(target,ar.get("char_pr_id_ref")),
            "before_fontfaces":fontface_census(source),
            "after_fontfaces":fontface_census(target),
        }
        # Stage-1 evidence collection deliberately does not assume exact native encoding.
        changed=(report["source_sha256"]!=report["target_sha256"])
        if case["kind"]=="spacing":
            spacing=(ar.get("style") or {}).get("letter_spacing_by_script") or {}
            report["observed_spacing_by_script"]=spacing
            report["diagnostic"]=bool(spacing) or case["value"]==0
        elif case["kind"]=="font":
            style=ar.get("style") or {}
            report["observed_font_ref"]=style.get("font_ref")
            report["observed_font_faces"]=style.get("font_faces")
            report["diagnostic"]=bool(style.get("font_ref"))
        else:
            style=ar.get("style") or {}
            report["observed_size_pt"]=style.get("size_pt")
            report["diagnostic"]=style.get("size_pt") is not None
        report["changed"]=changed
        if not report["diagnostic"]:
            failures.append({"case":case["id"],"reason":"native_result_not_diagnostic"})
        (d/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        reports.append(report)

    summary={
        "schema":"chatgpt-web-hwpx-mcp/p3.35-r1/native-typography-analysis/v1",
        "cases_analyzed":len(reports),
        "diagnostic_failures":failures,
        "diagnostic_pass":len(reports)==len(manifest["cases"]) and not failures,
        "reports":reports,
    }
    (root/"analysis-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"diagnostic_pass":summary["diagnostic_pass"],"failures":failures},ensure_ascii=False))
    return 0 if summary["diagnostic_pass"] else 2

if __name__=="__main__":
    raise SystemExit(main())
