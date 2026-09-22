from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic, build_diagram_lifecycle_map

FIXTURES = [
    "identity-reopen",
    "node-patch",
    "edge-patch",
    "relayout",
    "template",
    "move-subgraph",
    "clone-subgraph",
    "remove-subgraph",
]


def _source(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.29 regression anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(x["locator"] for x in mapped["paragraphs"] if x.get("text") == "P3.29 regression anchor")


def _base_create(anchor: str) -> dict:
    return {
        "op": "create_diagram",
        "diagram_id": "main",
        "anchor": anchor,
        "plan": {
            "layout": "LEFT_TO_RIGHT",
            "nodes": [
                {"id": "start", "type": "terminator", "label": "Start"},
                {"id": "work", "type": "process", "label": "Work"},
                {"id": "end", "type": "terminator", "label": "End"},
            ],
            "edges": [
                {"from": "start", "to": "work"},
                {"from": "work", "to": "end"},
            ],
        },
    }


def materialize_p329_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.29",
        "purpose": "PRODUCT_DIAGRAM_LIFECYCLE_REGRESSION",
        "authority": "STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY",
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

        if name == "template":
            operations = [{
                "op": "instantiate_template",
                "diagram_id": "main",
                "template": "decision_gate",
                "anchor": anchor,
            }]
        else:
            operations = [_base_create(anchor)]

        apply_diagram_lifecycle_atomic(target, operations, expected_revision=1, current_revision=1)

        if name == "node-patch":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "patch_node", "diagram_id": "main", "node_id": "work", "label": "Review", "x": 18000, "width": 9000}],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "edge-patch":
            apply_diagram_lifecycle_atomic(
                target,
                [
                    {"op": "remove_edge", "diagram_id": "main", "source": "work", "target": "end"},
                    {"op": "add_edge", "diagram_id": "main", "source": "start", "target": "end"},
                ],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "relayout":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "relayout_diagram", "diagram_id": "main", "layout": "TOP_DOWN", "order": ["start", "work", "end"], "origin_x": 2500, "origin_y": 1500, "gap_y": 7200}],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "move-subgraph":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "move_subgraph", "diagram_id": "main", "node_ids": ["work", "end"], "dx": 5000, "dy": 1200}],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "clone-subgraph":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "clone_subgraph", "diagram_id": "main", "node_ids": ["start", "work"], "new_prefix": "copy", "dy": 9000}],
                expected_revision=2,
                current_revision=2,
            )
        elif name == "remove-subgraph":
            apply_diagram_lifecycle_atomic(
                target,
                [{"op": "remove_subgraph", "diagram_id": "main", "node_ids": ["work"]}],
                expected_revision=2,
                current_revision=2,
            )

        mapped = build_diagram_lifecycle_map(target)
        manifest["fixtures"].append({
            "name": name,
            "source": str(source.relative_to(out_dir)),
            "target": str(target.relative_to(out_dir)),
            "diagram_count": mapped["diagram_count"],
            "managed_node_count": mapped["managed_node_count"],
            "managed_edge_count": mapped["managed_edge_count"],
            "diagram_identity_sha256": mapped["diagram_identity_sha256"],
            "diagram_relation_sha256": mapped["diagram_relation_sha256"],
        })

    (out_dir / "p329-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
