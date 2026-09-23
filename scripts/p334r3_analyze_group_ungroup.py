#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from p327_diagram_composition import build_diagram_composition_map
from p334r2_package_validation import validate_hwpx_package_light

def main()->int:
  ap=argparse.ArgumentParser(); ap.add_argument("--pack",default="artifacts/p334r3-group-ungroup-pack"); args=ap.parse_args()
  root=Path(args.pack); man=json.loads((root/"capture-manifest.json").read_text(encoding="utf-8"))
  reports=[]; failures=[]
  for case in man["cases"]:
    src=Path(case["source"]); tgt=Path(case["target"])
    b=build_diagram_composition_map(src); a=build_diagram_composition_map(tgt); validate_hwpx_package_light(tgt)
    report={"case_id":case["id"],"action":case["action"],
      "before":{"top_level_count":b["top_level_count"],"group_count":b["group_count"],"top_level_objects":b["top_level_objects"],"groups":b["groups"]},
      "after":{"top_level_count":a["top_level_count"],"group_count":a["group_count"],"top_level_objects":a["top_level_objects"],"groups":a["groups"]}}
    if case["action"]=="GROUP_SELECTED":
      report["pass_shape"]=a["group_count"]==1 and a["top_level_count"]==1 and len(a["groups"][0]["members"])==2
    else:
      report["pass_shape"]=a["group_count"]==0 and a["top_level_count"]==2
    if not report["pass_shape"]: failures.append(case["id"])
    (root/case["id"]/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    reports.append(report)
  summary={"schema":"chatgpt-web-hwpx-mcp/p3.34-r3/native-group-ungroup-analysis/v1","pass":not failures,"failures":failures,"reports":reports}
  (root/"analysis-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  print(json.dumps({"pass":summary["pass"],"failures":failures},ensure_ascii=False))
  return 0 if not failures else 2
if __name__=="__main__": raise SystemExit(main())
