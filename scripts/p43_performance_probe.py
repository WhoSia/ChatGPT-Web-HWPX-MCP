from __future__ import annotations
import argparse,json,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from hwpx import HwpxDocument
from p41_operational import profile_operations
from hwpx_mcp.quality.p43_quality import evaluate_metric,load_release_history

def make_doc(path:Path):
    doc=HwpxDocument.new();doc.add_paragraph("P4.3 benchmark");doc.add_paragraph("cross-release health");doc.save_to_path(str(path));doc.close()
def validate(path:Path):
    with zipfile.ZipFile(path,"r") as z:
        assert z.infolist()[0].filename=="mimetype" and z.read("mimetype")==b"application/hwp+zip"

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--samples",type=int,default=7);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);existing=root/"existing.hwpx";make_doc(existing);validate(existing)
        def cv():target=root/"candidate.hwpx";make_doc(target);validate(target)
        raw=profile_operations({"create_validate":(cv,None),"existing_validate":(lambda:validate(existing),None)},sample_count=a.samples)
    history=load_release_history()
    metrics={
        "create_validate_p95_ms":next(x for x in raw["operations"] if x["operation"]=="create_validate")["latency_ms"]["p95"],
        "existing_validate_p95_ms":next(x for x in raw["operations"] if x["operation"]=="existing_validate")["latency_ms"]["p95"],
    }
    evaluations={k:evaluate_metric(history,k,v) for k,v in metrics.items()}
    status="PASS" if all(x["status"]=="PASS" for x in evaluations.values()) else "REGRESSION"
    receipt={"schema":"chatgpt-web-hwpx-mcp/p4.3/performance/v1","samples":a.samples,"metrics":metrics,"evaluations":evaluations,"status":status,"calibration_release_count":history["entry_count"]}
    Path(a.out).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False))
    return 0 if status=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
