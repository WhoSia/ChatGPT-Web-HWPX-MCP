from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from hwpx import HwpxDocument
from hwpx_mcp.operations.p41_operational import profile_operations
from p42_migration import PRODUCT

FROZEN_P41 = {
    "python_hwpx_create_and_package_validate": 298.197,
    "existing_hwpx_package_validate": 1.274,
}
REGRESSION_FACTOR = 2.5
ABSOLUTE_CEILINGS = {
    "python_hwpx_create_and_package_validate": 1000.0,
    "existing_hwpx_package_validate": 10.0,
}

def make_doc(path: Path):
    doc=HwpxDocument.new()
    doc.add_paragraph("P4.2 performance canary")
    doc.add_paragraph("둘째 문단")
    doc.save_to_path(str(path))
    doc.close()

def validate(path: Path):
    with zipfile.ZipFile(path,"r") as z:
        assert z.infolist()[0].filename=="mimetype"
        assert z.read("mimetype")==b"application/hwp+zip"

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--samples",type=int,default=3);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);existing=root/"existing.hwpx";make_doc(existing);validate(existing)
        def create_validate():
            target=root/"candidate.hwpx";make_doc(target);validate(target)
        result=profile_operations({
            "python_hwpx_create_and_package_validate":(create_validate,ABSOLUTE_CEILINGS["python_hwpx_create_and_package_validate"]),
            "existing_hwpx_package_validate":(lambda:validate(existing),ABSOLUTE_CEILINGS["existing_hwpx_package_validate"]),
        },sample_count=a.samples)
    comparisons=[]
    for row in result["operations"]:
        baseline=FROZEN_P41[row["operation"]]
        ratio=row["latency_ms"]["p95"]/baseline
        ok=row["status"]=="PASS" and ratio<=REGRESSION_FACTOR
        comparisons.append({"operation":row["operation"],"baseline_p95_ms":baseline,"observed_p95_ms":row["latency_ms"]["p95"],"ratio":round(ratio,4),"pass":ok})
    result["product"]=PRODUCT;result["baseline"]="P4.1 exact-head CI";result["regression_factor"]=REGRESSION_FACTOR
    result["comparisons"]=comparisons;result["budget_status"]="PASS" if all(x["pass"] for x in comparisons) else "REGRESSION"
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result["budget_status"]=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
