#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from p327_diagram_composition import build_diagram_composition_map
from p334r2_package_validation import validate_hwpx_package_light

def compact(path:Path)->dict:
    m=build_diagram_composition_map(path)
    top=[{"kind":o["kind"],"instid":o.get("instid"),"width":o.get("width"),"height":o.get("height"),"position":o.get("position"),"group_level":o.get("group_level")} for o in m["top_level_objects"]]
    groups=[{"position":g["position"],"width":g["width"],"height":g["height"],"members":g["members"]} for g in m["groups"]]
    return {"top_level_count":m["top_level_count"],"group_count":m["group_count"],"top":top,"groups":groups}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--pack",default="artifacts/p334r3-candidate-roundtrip-pack");args=ap.parse_args()
    root=Path(args.pack);man=json.loads((root/"roundtrip-manifest.json").read_text(encoding="utf-8"))
    failures=[];reports=[]
    for case in man["cases"]:
        d=root/case["id"];b=d/"candidate-before-hancom.hwpx";a=d/"candidate-after-hancom.hwpx"
        if not a.exists(): failures.append({"case":case["id"],"reason":"after_missing"});continue
        validate_hwpx_package_light(b);validate_hwpx_package_light(a)
        bs=compact(b);as_=compact(a)
        if case["expected"]=="grouped":
            ok=as_["group_count"]==1 and as_["top_level_count"]==1 and len(as_["groups"][0]["members"])==2
            if ok:
                bg=bs["groups"][0];ag=as_["groups"][0]
                ok=(bg["position"]==ag["position"] and bg["width"]==ag["width"] and bg["height"]==ag["height"] and
                    sorted((m["instid"],m["offset"],m["org_size"]) for m in bg["members"])==
                    sorted((m["instid"],m["offset"],m["org_size"]) for m in ag["members"]))
        else:
            ok=as_["group_count"]==0 and as_["top_level_count"]==2
            if ok:
                def rows(s): return sorted((o["instid"],o["width"],o["height"],o["position"].get("horzOffset"),o["position"].get("vertOffset")) for o in s["top"])
                ok=rows(bs)==rows(as_)
        report={"case_id":case["id"],"before":bs,"after":as_,"pass":ok}
        if not ok: failures.append({"case":case["id"],"reason":"semantic_drift"})
        (d/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        reports.append(report)
    summary={"schema":"chatgpt-web-hwpx-mcp/p3.34-r3/candidate-roundtrip-analysis/v1","pass":not failures and len(reports)==len(man["cases"]),"failures":failures,"reports":reports}
    (root/"analysis-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"pass":summary["pass"],"failures":failures},ensure_ascii=False))
    return 0 if summary["pass"] else 2
if __name__=="__main__": raise SystemExit(main())
