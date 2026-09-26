from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from p321_document_composer import compose_document_plan
from p338_rich_builder import compile_rich_document_plan, evaluate_preview_readiness
from p339_design_intelligence import prepare_authoring_strategy
from p340_feedback_loop import diagnose_document_with_render, plan_executable_editorial_repairs
from p342_mutation_footprint import apply_document_design_repairs_with_footprint_atomic
from p334r2_package_validation import validate_hwpx_package_light
from p344_autonomous_authoring import diagnostic_summary, evaluate_runtime_gate, repair_plan_summary

MANIFEST=ROOT/"benchmarks"/"authorbench_p344_frozen.json"


def sha_file(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head()->str:
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    except Exception:
        return ""


def rich_plan(case:dict)->dict:
    return {
        "preset":case["preset"],
        "document":{"title":case["title"]},
        "sections":[{
            "page":{"paper_size":"A4","orientation":"PORTRAIT","margin_left_mm":20,"margin_right_mm":20,"margin_top_mm":20,"margin_bottom_mm":20},
            "footer":"AUTHORBENCH P3.44 · "+case["case_id"],
            "page_numbers":True,
            "blocks":[
                {"id":"title","type":"title","text":case["title"]},
                {"id":"s1","type":"heading","level":1,"text":case["section1"]},
                {"id":"b1","type":"paragraph","text":case["body1"]},
                {"id":"table-h","type":"heading","level":2,"text":"검토 표"},
                {"id":"table","type":"table","rows":len(case["table"]),"cols":len(case["table"][0]),"first_row_header":True,"cells":case["table"]},
                {"id":"s2","type":"heading","level":1,"text":case["section2"]},
                {"id":"b2","type":"paragraph","text":case["body2"]},
                {"id":"con-h","type":"heading","level":1,"text":"결론"},
                {"id":"con","type":"paragraph","text":case["conclusion"]},
            ]
        }]
    }


def materialize(out_dir:Path)->dict:
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True,exist_ok=True)
    fixtures=out_dir/"fixtures";fixtures.mkdir(exist_ok=True)
    blind=[]
    full=[]
    for case in manifest["cases"]:
        case_dir=fixtures/case["case_id"];case_dir.mkdir(exist_ok=True)
        path=case_dir/"input.hwpx"
        compiled=compile_rich_document_plan(rich_plan(case))
        compose=compose_document_plan(path,compiled["plan"],validator=lambda p:validate_hwpx_package_light(p))
        strategy=prepare_authoring_strategy({"archetype":case["archetype"],"semantic_outline":["TITLE","SECTION","BODY","ANALYTICAL_TABLE","SECTION","BODY","CONCLUSION"]})
        repairs=[]
        revision=1
        for _ in range(2):
            diag=diagnose_document_with_render(path,mode=case["archetype"])
            summary=diagnostic_summary(diag)
            plan=plan_executable_editorial_repairs(path,diag,strategy=strategy)
            ps=repair_plan_summary(plan)
            if summary["verdict"]!="NEEDS_REPAIR" or not ps["repairable"]:
                break
            tx=apply_document_design_repairs_with_footprint_atomic(
                path,plan,expected_revision=revision,current_revision=revision,
                validator=lambda p:validate_hwpx_package_light(p),
            )
            revision+=1
            repairs.append({
                "p342_receipt_sha256":tx.get("p342_receipt_sha256"),
                "preservation_passed":bool((tx.get("preservation_enforcement") or {}).get("passed")),
                "preservation_grade":(tx.get("mutation_footprint") or {}).get("preservation",{}).get("actual_grade"),
            })
        final=diagnose_document_with_render(path,mode=case["archetype"])
        final_summary=diagnostic_summary(final)
        final_plan=plan_executable_editorial_repairs(path,final,strategy=strategy)
        final_ps=repair_plan_summary(final_plan)
        snapshot={
            "static_verdict":final_summary["verdict"],
            "render_requirement":"REQUIRED",
            "render_verdict":"NOT_PROVIDED",
            "repairable":final_ps["repairable"],
            "repairs_used":len(repairs),
            "max_repairs":2,
            "policy_ok":True,
            "footprint_ok":all(x["preservation_passed"] for x in repairs),
            "human_requirement":"NOT_REQUIRED",
            "human_verdict":"PENDING",
        }
        gate=evaluate_runtime_gate(snapshot)
        preview=evaluate_preview_readiness(path,mode=case["archetype"])
        row={
            "case_id":case["case_id"],
            "split":case["split"],
            "domain":case["domain"],
            "archetype":case["archetype"],
            "artifact_sha256":sha_file(path),
            "bytes":path.stat().st_size,
            "revision":revision,
            "preview_verdict":preview["verdict"],
            "final_static":final_summary,
            "repairs":repairs,
            "gate_snapshot":snapshot,
            "gate":gate,
            "path":path.relative_to(out_dir).as_posix(),
        }
        full.append(row)
        blind.append({
            "case_id":row["case_id"],
            "artifact_sha256":row["artifact_sha256"],
            "final_static":row["final_static"],
            "repairs":row["repairs"],
            "gate_snapshot":row["gate_snapshot"],
        })
    receipt={
        "schema":"authorbench/p3.44/materialization/v1",
        "phase":"P3.44",
        "source_commit":git_head(),
        "frozen_manifest_sha256":sha_file(MANIFEST),
        "case_count":len(full),
        "cases":full,
        "authority":"CURRENT_IMPLEMENTATION_AGAINST_PREIMPLEMENTATION_FROZEN_MANIFEST",
    }
    (out_dir/"authorbench-p344-materialization.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out_dir/"authorbench-p344-blind.json").write_text(json.dumps({"schema":"authorbench/p3.44/blind-packet/v1","cases":blind},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    capture={
        "schema":"authorbench/p3.44/capture-ready-manifest/v1",
        "phase":"P3.44",
        "source_commit":receipt["source_commit"],
        "frozen_manifest_sha256":receipt["frozen_manifest_sha256"],
        "fixtures":[{"fixture_id":x["case_id"],"path":x["path"],"sha256":x["artifact_sha256"],"archetype":x["archetype"],"split":x["split"]} for x in full],
        "authority":"PRE_NATIVE_CAPTURE_INPUTS; NO_RENDER_PASS_CLAIM",
    }
    (out_dir/"capture-ready-manifest.json").write_text(json.dumps(capture,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return receipt


if __name__=="__main__":
    out=Path(sys.argv[1] if len(sys.argv)>1 else "artifacts/p344-authorbench")
    receipt=materialize(out)
    print(json.dumps({"cases":receipt["case_count"],"source_commit":receipt["source_commit"]}))
