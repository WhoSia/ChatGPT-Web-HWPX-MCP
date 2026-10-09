from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from hwpx import HwpxDocument
from hwpx_mcp.document.p318_document_setup import build_document_setup_map

def download(url: str, target: Path)->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":"ChatGPT-Web-HWPX-MCP-P4.2/1.0"})
    last=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                data=r.read(12_000_000)
            if len(data)>=12_000_000:raise RuntimeError("real-document canary exceeded 12MB bound")
            target.write_bytes(data);return data
        except Exception as exc:
            last=exc
            if attempt<2:time.sleep(2**attempt)
    raise RuntimeError(f"download failed after bounded retries: {type(last).__name__}") from last

def probe(path: Path)->dict:
    with zipfile.ZipFile(path,"r") as z:
        package_ok=z.infolist()[0].filename=="mimetype" and z.read("mimetype")==b"application/hwp+zip"
    doc=HwpxDocument.open(str(path))
    try:
        paragraph_count=len(doc.paragraphs)
        section_count=len(doc.sections)
    finally:
        doc.close()
    setup=build_document_setup_map(path)
    return {
        "package_valid":package_ok,
        "paragraph_count":paragraph_count,
        "section_count":section_count,
        "setup_section_count":setup["section_count"],
        "orientations":[x["page"]["orientation"] for x in setup["sections"]],
    }

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--manifest",required=True);p.add_argument("--out",required=True);a=p.parse_args()
    rows=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    version=md.version("python-hwpx");results=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for row in rows:
            target=root/(row["source_id"]+".hwpx")
            try:
                data=download(row["download_url"],target)
                result=probe(target)
                results.append({
                    "source_id":row["source_id"],"institution":row["institution"],"source_page":row["source_page"],
                    "license":row["license"],"byte_size":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                    "status":"PASS" if result["package_valid"] else "FAIL",**result,
                })
            except Exception as exc:
                results.append({"source_id":row["source_id"],"institution":row["institution"],"source_page":row["source_page"],"license":row["license"],"status":"FAIL","error_class":type(exc).__name__,"error":str(exc)[:300]})
    passed=sum(x["status"]=="PASS" for x in results)
    receipt={"schema":"chatgpt-web-hwpx-mcp/p4.2/real-document-matrix/v1","python_hwpx":version,"sources":results,"passed":passed,"total":len(results),"verdict":"PASS" if passed==len(results) and passed>0 else "FAIL"}
    Path(a.out).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False))
    return 0 if receipt["verdict"]=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
