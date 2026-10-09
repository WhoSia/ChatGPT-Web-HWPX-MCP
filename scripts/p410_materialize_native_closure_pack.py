from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.quality.p410_closure import PRODUCT, closure_contract
from scripts.p48_component_benchmark import run as run_component_benchmark
from scripts.p49_materialize_equation_witnesses import run as run_equation_witnesses


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    sources = out / "sources"
    capture = out / "capture"
    review = out / "review"
    sources.mkdir(exist_ok=True)
    capture.mkdir(exist_ok=True)
    review.mkdir(exist_ok=True)

    component_dir = sources / "archetypes"
    equation_dir = sources / "equations"
    component = run_component_benchmark(component_dir)
    equation = run_equation_witnesses(equation_dir)

    repo_root = Path(__file__).resolve().parents[1]
    runner_src = repo_root / "scripts" / "p49_run_hancom_capture.ps1"
    runner_dst = capture / "p410_run_hancom_capture.ps1"
    shutil.copy2(runner_src, runner_dst)

    human_template = {
        "phase": "P4.10",
        "product": PRODUCT,
        "status": "PENDING",
        "archetypes": {
            name: {
                "human_visual_status": "PENDING",
                "no_clipping_or_corruption": False,
                "lab_report_vector_escape_absent": None if name != "LAB_REPORT" else False,
                "bar_label_value_preserved": False,
                "kpi_card_preserved": False,
                "notes": "",
            }
            for name in sorted(row["archetype"] for row in component["rows"])
        },
        "equation_alignment": {
            row["variant_id"]: {
                "expected_alignment": row["expected_alignment"],
                "observed_alignment": "PENDING",
                "human_visual_status": "PENDING",
                "no_clipping_or_corruption": False,
                "notes": "",
            }
            for row in equation["rows"]
        },
        "authority": "TEMPLATE_ONLY_NO_NATIVE_OR_HUMAN_VERDICT",
    }
    human_path = review / "p410-human-visual-adjudication-template.json"
    human_path.write_text(json.dumps(human_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    closure_evidence = {
        "phase": "P4.10",
        "product": PRODUCT,
        "exact_head": None,
        "exact_head_ci_pass": False,
        "exact_head_docker_pass": False,
        "production_boundary_pass": False,
        "native_hancom": {
            "capture_pass": False,
            "fail_count": None,
            "pdf_count": None,
            "manifest_sha256": None,
        },
        "human_visual": {
            "status": "PENDING",
            "lab_report_vector_escape_absent": False,
            "bar_label_value_preserved": False,
            "kpi_card_preserved": False,
        },
        "authority": "P4.10_EVIDENCE_TEMPLATE_ONLY",
    }
    closure_path = review / "p410-closure-evidence-template.json"
    closure_path.write_text(json.dumps(closure_evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readme = """P4.10 native Hancom closure pack

1. This packet is structural/source evidence only until it is opened by the real interactive Hancom session.
2. Do not kill pre-existing Hwp.exe processes. The bundled runner only owns PIDs spawned after each COM activation.
3. Run archetypes and equation witnesses separately so each manifest has a single evidence family.

PowerShell (from the extracted pack root):

$root = (Get-Location).Path
$runner = Join-Path $root "capture\\p410_run_hancom_capture.ps1"

& $runner -SourceDir (Join-Path $root "sources\\archetypes") -OutputDir (Join-Path $root "native\\archetypes")
& $runner -SourceDir (Join-Path $root "sources\\equations") -OutputDir (Join-Path $root "native\\equations")

Get-FileHash (Join-Path $root "native\\archetypes\\p49-native-capture-manifest.json") -Algorithm SHA256
Get-FileHash (Join-Path $root "native\\equations\\p49-native-capture-manifest.json") -Algorithm SHA256

Then return the complete native/ directory (PDFs + manifests) for visual adjudication.
"""
    readme_path = out / "README-NATIVE-CAPTURE.txt"
    readme_path.write_text(readme, encoding="utf-8")

    files = []
    for path in sorted(out.rglob("*")):
        if path.is_file():
            files.append({
                "path": path.relative_to(out).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })

    result = {
        "phase": "P4.10",
        "product": PRODUCT,
        "schema": "chatgpt-web-hwpx-mcp/p410/native-closure-pack/v1",
        "contract_sha256": closure_contract()["contract_sha256"],
        "archetype_count": component["archetype_count"],
        "equation_witness_count": equation["witness_count"],
        "files": files,
        "authority": "SOURCE_PACKET_READY_NATIVE_HANCOM_AND_HUMAN_VISUAL_EVIDENCE_PENDING",
    }
    result["pack_manifest_sha256"] = hashlib.sha256(
        json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest_path = out / "p410-native-closure-pack.json"
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/p410-native-closure-pack"))
    args = parser.parse_args()
    run(args.out)
