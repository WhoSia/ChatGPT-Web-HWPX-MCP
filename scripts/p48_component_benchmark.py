from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx.tools.package_validator import validate_editor_open_safety

from p321_document_composer import compose_document_plan
from p325_drawing_layer import build_drawing_layer_map
from p28_tables import build_table_map
from p210_equations import build_equation_map
from hwpx_mcp.rendering.p47_native_authoring import compile_unified_authoring_plan
from p48_components import ARCHETYPES, compile_document_components
from hwpx_mcp.interfaces.p48_mcp import _execute_visual_plans
from p49_visual_conformance import audit_materialized_visuals, certify_visual_plans
from p411_visual_oracle import structural_region_provenance_from_audit
from p412_native_repair import audit_repaired_visuals


def _scenario(archetype: str) -> dict:
    components = [
        {"id": "intro", "type": "paragraph", "text": f"{archetype} component benchmark."},
        {"id": "def", "type": "definition", "title": "기준량", "text": "비교의 기준이 되는 양이다."},
        {"id": "eq", "type": "equation", "label": "ratio", "latex": r"r=\frac{a}{b}"},
        {"id": "ref", "type": "equation_reference", "target": "ratio", "suffix": "을 사용한다."},
        {
            "id": "table",
            "type": "data_table",
            "headers": ["구분", "값"],
            "rows": [["A", "10"], ["B", "20"]],
            "caption": "표 1. 입력 자료",
        },
        {
            "id": "chart",
            "type": "bar_chart",
            "title": "구분별 값",
            "data": [{"label": "A", "value": 10}, {"label": "B", "value": 20}],
        },
        {
            "id": "kpi",
            "type": "kpi_strip",
            "items": [{"label": "표본", "value": "2"}, {"label": "합계", "value": "30"}],
        },
    ]
    if archetype == "POLICY_BRIEF":
        components.insert(1, {"id": "callout", "type": "callout", "label": "핵심 판단", "text": "B가 A보다 크다."})
    if archetype == "LAB_REPORT":
        components.append({"id": "proof", "type": "proof", "heading": "검산", "text": "표와 식의 값을 대조한다."})
    return {
        "title": f"P4.8 {archetype}",
        "archetype": archetype,
        "sections": [{"heading": "본문", "components": components}],
    }


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for archetype in sorted(ARCHETYPES):
        compiled = compile_document_components(_scenario(archetype))
        if not compiled["ready"]:
            raise RuntimeError(f"{archetype} compile blocked: {compiled['blockers']}")
        unified = compile_unified_authoring_plan(compiled["unified_spec"])
        path = out / f"p48-{archetype.lower()}.hwpx"
        composition = compose_document_plan(path, unified["rich"]["plan"])
        visual_certificate = certify_visual_plans(compiled["visual_plans"])
        if visual_certificate["status"] != "PASS":
            raise RuntimeError(f"{archetype} P4.9 visual certificate failed: {visual_certificate['issues']}")
        visual = _execute_visual_plans(path, compiled["visual_plans"], composition["bindings"])
        p412_repair_audit = audit_repaired_visuals(path, visual)
        p411_region_provenance = {
            "region_count": 0,
            "region_provenance_sha256": p412_repair_audit["materialized_repair_audit_sha256"],
            "authority": "P4.12_PARAGRAPH_VISUALIZATION_HAS_NO_DRAWING_REGION_OBJECTS",
        }
        if p412_repair_audit["status"] != "PASS":
            raise RuntimeError(
                f"{archetype} P4.12 post-materialization repaired visual audit failed: "
                f"{p412_repair_audit['issues']}"
            )
        raw = path.read_bytes()
        safety = validate_editor_open_safety(raw)
        if not safety.ok:
            raise RuntimeError(f"{archetype} editor-open safety failed: {safety.issues}")
        drawings = build_drawing_layer_map(path)
        tables = build_table_map(path)
        equations = build_equation_map(path)
        rows.append({
            "archetype": archetype,
            "filename": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "component_count": compiled["component_count"],
            "visual_component_count": len(visual),
            "visual_certificate_sha256": visual_certificate["visual_certificate_sha256"],
            "visual_certificate_status": visual_certificate["status"],
            "materialized_visual_audit_sha256": None,
            "materialized_visual_audit_status": "SUPERSEDED_BY_P4.12_PARAGRAPH_SUBSTITUTION",
            "p412_repair_audit_sha256": p412_repair_audit["materialized_repair_audit_sha256"],
            "p412_repair_audit_status": p412_repair_audit["status"],
            "p411_region_provenance_sha256": p411_region_provenance["region_provenance_sha256"],
            "p411_region_provenance_count": p411_region_provenance["region_count"],
            "drawing_count": drawings["drawing_count"],
            "table_count": tables["table_count"],
            "equation_count": equations["equation_count"],
            "editor_open_safety": True,
        })
    result = {
        "phase": "P4.8",
        "product": "0.34.0-p4.8",
        "archetype_count": len(rows),
        "rows": rows,
        "authority": "CROSS_ARCHETYPE_STRUCTURAL_GENERATION_BENCHMARK_NOT_NATIVE_RENDER_OR_HUMAN_VISUAL_AUTHORITY",
    }
    result["benchmark_sha256"] = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (out / "p48-component-benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/p48-component-benchmark"))
    args = parser.parse_args()
    run(args.out)
