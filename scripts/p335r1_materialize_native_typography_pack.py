#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hwpx import HwpxDocument
from p22_formatting import build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light

CASES = [
    {"id":"spacing-neg50","kind":"spacing","value":-50,"text":"자간 경계 음수 ABC 漢字"},
    {"id":"spacing-neg20","kind":"spacing","value":-20,"text":"자간 음수 ABC 漢字"},
    {"id":"spacing-zero","kind":"spacing","value":0,"text":"자간 영점 ABC 漢字"},
    {"id":"spacing-pos20","kind":"spacing","value":20,"text":"자간 양수 ABC 漢字"},
    {"id":"spacing-pos100","kind":"spacing","value":100,"text":"자간 경계 양수 ABC 漢字"},
    {"id":"font-hamchorom","kind":"font","value":"함초롬바탕","text":"한글 ABC 漢字 123"},
    {"id":"font-malgun","kind":"font","value":"맑은 고딕","text":"한글 ABC 漢字 123"},
    {"id":"font-times","kind":"font","value":"Times New Roman","text":"한글 ABC 漢字 123"},
    {"id":"size-9pt","kind":"size","value":9.0,"text":"글자 크기 9pt ABC 漢字"},
    {"id":"size-13_5pt","kind":"size","value":13.5,"text":"글자 크기 13.5pt ABC 漢字"},
]

def make(path: Path, text: str) -> None:
    doc=HwpxDocument.new()
    doc.add_paragraph(text)
    doc.save_to_path(str(path))
    doc.close()
    validate_hwpx_package_light(path)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="artifacts/p335r1-native-typography-pack")
    args=ap.parse_args()
    root=Path(args.out)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True,exist_ok=True)

    manifest={
        "schema":"chatgpt-web-hwpx-mcp/p3.35-r1/native-typography/v1",
        "phase":"P3.35-R1",
        "authority":"EVIDENCE_ONLY",
        "cases":[],
    }
    for spec in CASES:
        d=root/spec["id"]; d.mkdir()
        source=d/"source.hwpx"; target=d/"target.hwpx"
        make(source,spec["text"]); shutil.copy2(source,target)
        mapped=build_formatting_map(source)
        item={**spec,"source":str(source),"target":str(target),"before":mapped}
        (d/"case.json").write_text(json.dumps(item,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        manifest["cases"].append(item)

    (root/"capture-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"P3.35-R1 materialized {len(CASES)} native typography fixtures")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
