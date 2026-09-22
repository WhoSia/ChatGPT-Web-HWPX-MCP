from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic
from p330_diagram_design_system import apply_diagram_design_system_atomic
from p331_diagram_quality_assurance import plan_diagram_repairs, validate_diagram_quality

FIXTURES = [
    "flow-pass",
    "theme-mismatch",
    "theme-repair-plan",
    "overlap-detect",
    "spacing-warning",
    "cycle-detect",
    "disconnected-detect",
    "label-budget",
]


def _source(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.31 regression anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.31 regression anchor")


def materialize_p331_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.31",
        "purpose": "PRODUCT_DIAGRAM_QUALITY_ASSURANCE_REGRESSION",
        "authority": "STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "fixtures": [],
    }
    for name in FIXTURES:
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "source.hwpx"
        target = folder / "target.hwpx"
        anchor = _source(source)
        target.write_bytes(source.read_bytes())
        apply_diagram_lifecycle_atomic(
            target,
            [{"op": "instantiate_template", "diagram_id": "qa", "anchor": anchor, "template": "linear_process"}],
            expected_revision=1,
            current_revision=1,
        )

        profile = "baseline"
        constraints = None
        expected_theme = None
        if name == "flow-pass":
            apply_diagram_design_system_atomic(
                target,
                [{"op": "apply_design_system", "diagram_id": "qa", "theme": "presentation", "layout_policy": "standard"}],
                expected_revision=2,
                current_revision=2,
            )
            profile, expected_theme = "flow", "presentation"
        elif name in {"theme-mismatch", "theme-repair-plan"}:
            expected_theme = "presentation"
        elif name == "overlap-detect":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "patch_node", "diagram_id": "qa", "node_id": "work", "x": 1000, "y": 1000}],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "spacing-warning":
            constraints = {"min_center_spacing": 20000}
        elif name == "cycle-detect":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "add_edge", "diagram_id": "qa", "source": "end", "target": "start"}],
                expected_revision=2,
                current_revision=2,
            )
            profile = "flow"
        elif name == "disconnected-detect":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "add_node", "diagram_id": "qa", "node_id": "orphan", "node_type": "process", "label": "Orphan", "x": 50000, "y": 1000}],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "label-budget":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "patch_node", "diagram_id": "qa", "node_id": "work", "label": "X" * 90}],
                expected_revision=2,
                current_revision=2,
            )

        report = validate_diagram_quality(
            target, "qa", profile=profile, constraints=constraints, expected_theme=expected_theme
        )
        entry = {
            "name": name,
            "source": str(source.relative_to(out_dir)),
            "target": str(target.relative_to(out_dir)),
            "qa_sha256": report["qa_sha256"],
            "passed": report["passed"],
            "error_count": report["error_count"],
            "warning_count": report["warning_count"],
            "codes": sorted({x["code"] for x in report["findings"]}),
        }
        if name == "theme-repair-plan":
            plan = plan_diagram_repairs(
                target, "qa", expected_theme="presentation", repair_theme="presentation"
            )
            entry["repair_plan_sha256"] = plan["repair_plan_sha256"]
            entry["repair_operation_count"] = plan["operation_count"]
        manifest["fixtures"].append(entry)

    (out_dir / "p331-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
