from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.rendering.p412_native_repair import PRODUCT, defect_eradication_contract
from scripts.p48_component_benchmark import run as run_component_benchmark

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(out: Path, exact_head: str) -> dict:
    if len(exact_head) != 40:
        raise ValueError("exact_head must be 40 hex characters")
    out.mkdir(parents=True,exist_ok=True)
    sources=out/"sources"/"archetypes"
    capture=out/"capture"
    review=out/"review"
    sources.mkdir(parents=True,exist_ok=True)
    capture.mkdir(parents=True,exist_ok=True)
    review.mkdir(parents=True,exist_ok=True)

    benchmark=run_component_benchmark(sources)
    root=Path(__file__).resolve().parents[1]
    shutil.copy2(root/"scripts"/"p49_run_hancom_capture.ps1",capture/"p412_run_hancom_capture.ps1")
    shutil.copy2(root/"scripts"/"p411_windows_capture_worker.ps1",capture/"p412_windows_capture_worker.ps1")

    unsafe=[row for row in benchmark["rows"] if int(row.get("drawing_count") or 0) != 0]
    if unsafe:
        raise RuntimeError("P4.12 repaired benchmark unexpectedly contains drawing objects: " + json.dumps(unsafe,ensure_ascii=False))

    source_files=[]
    for row in benchmark["rows"]:
        path=sources/row["filename"]
        source_files.append({
            "archetype":row["archetype"],
            "path":path.relative_to(out).as_posix(),
            "sha256":_sha(path),
            "bytes":path.stat().st_size,
            "p412_repair_audit_status":row.get("p412_repair_audit_status"),
            "drawing_count":row.get("drawing_count"),
        })

    source_manifest={
        "phase":"P4.12",
        "product":PRODUCT,
        "exact_head":exact_head,
        "source_count":len(source_files),
        "sources":source_files,
        "authority":"P4.12_REPAIRED_ARCHETYPE_SOURCE_CUSTODY",
    }
    source_manifest_path=out/"p412-source-manifest.json"
    source_manifest_path.write_text(json.dumps(source_manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    request={
        "job_id":hashlib.sha256((exact_head+"\0"+_sha(source_manifest_path)).encode()).hexdigest()[:24],
        "exact_head":exact_head,
        "source_manifest_sha256":_sha(source_manifest_path),
        "source_dir":str(sources),
        "output_dir":str(out/"native"),
        "hancom_version_expected":"13.0.0.3622",
        "capture_kind":"p412_repaired_archetype",
    }
    (review/"p412-capture-request.json").write_text(json.dumps(request,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    adjudication={
        "phase":"P4.12",
        "product":PRODUCT,
        "exact_head":exact_head,
        "status":"NATIVE_RERENDER_PENDING",
        "cases":{
            row["archetype"]:{
                "native_capture_pass":False,
                "vector_escape":None,
                "bar_visible":None,
                "kpi_visible":None,
                "novel_defects":[],
                "visual_slo_status":"PENDING",
            } for row in benchmark["rows"]
        },
        "blocking_promotion":"HOLD",
        "authority":"TEMPLATE_ONLY_NATIVE_RERENDER_REQUIRED",
    }
    (review/"p412-native-adjudication-template.json").write_text(
        json.dumps(adjudication,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )

    readme=f"""P4.12 closed-loop native rerender pack
Exact head: {exact_head}
Product: {PRODUCT}

The five HWPX sources use the P4.12 certified paragraph-text visual substitution.
They must be captured in real Hancom before visual SLO recovery can be claimed.

PowerShell from this extracted pack root:

$root=(Get-Location).Path
$runner=Join-Path $root "capture\\p412_run_hancom_capture.ps1"
& $runner -SourceDir (Join-Path $root "sources\\archetypes") -OutputDir (Join-Path $root "native")
Get-FileHash (Join-Path $root "native\\p49-native-capture-manifest.json") -Algorithm SHA256

Return the native directory (PDFs + manifest) for P4.12 requalification.
"""
    (out/"README-P412-NATIVE-RERENDER.txt").write_text(readme,encoding="utf-8")

    files=[]
    for path in sorted(out.rglob("*")):
        if path.is_file():
            files.append({"path":path.relative_to(out).as_posix(),"bytes":path.stat().st_size,"sha256":_sha(path)})
    result={
        "phase":"P4.12","product":PRODUCT,"exact_head":exact_head,
        "schema":"chatgpt-web-hwpx-mcp/p412/native-rerender-pack/v1",
        "contract_sha256":defect_eradication_contract()["contract_sha256"],
        "archetype_count":benchmark["archetype_count"],
        "files":files,
        "authority":"P4.12_NATIVE_RERENDER_SOURCE_PACKET_READY",
    }
    result["pack_manifest_sha256"]=hashlib.sha256(
        json.dumps(files,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    (out/"p412-native-rerender-pack.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("/tmp/p412-native-rerender-pack"))
    p.add_argument("--exact-head",required=True)
    a=p.parse_args()
    run(a.out,a.exact_head)
