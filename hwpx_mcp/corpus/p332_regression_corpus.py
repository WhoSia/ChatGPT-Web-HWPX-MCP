from __future__ import annotations

import json
import shutil
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p328_high_level_diagrams import _insert_labeled_node, _insert_pointer_line, _set_existing_shape_text
from p327_diagram_composition import _position_xy, _resolve_top, _size
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic, build_diagram_lifecycle_map
from p332_brownfield_diagrams import (
    apply_legacy_diagram_refactor_atomic,
    build_brownfield_diagram_map,
    plan_diagram_adoption,
    plan_legacy_diagram_refactor,
    promote_diagram_candidate_atomic,
)

FIXTURES = [
    "recognize-pass",
    "promote-pass",
    "occupied-name-hold",
    "stale-plan",
    "mixed-managed-unmanaged",
    "refactor-layout-theme",
    "reingest-managed",
    "unconnected-shapes-no-candidate",
]


def _blank(path: Path) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.32 regression anchor")
    doc.save_to_path(str(path))
    doc.close()
    mapped = build_document_map(path)
    return next(p["locator"] for p in mapped["paragraphs"] if p.get("text") == "P3.32 regression anchor")


def _legacy_pair(path: Path, anchor: str, *, occupied: bool = False, connected: bool = True) -> tuple[str, str]:
    a = _insert_labeled_node(path, {
        "anchor": anchor,
        "node_type": "process",
        "text": "Legacy A",
        "horizontal_offset": 1000,
        "vertical_offset": 1000,
        "name": "legacy-meta" if occupied else "",
    })["created_node"]
    b = _insert_labeled_node(path, {
        "anchor": anchor,
        "node_type": "terminator",
        "text": "Legacy B",
        "horizontal_offset": 12000,
        "vertical_offset": 1000,
    })["created_node"]
    if connected:
        left = _resolve_top(path, a)
        right = _resolve_top(path, b)
        ax, ay = _position_xy(left)
        bx, by = _position_xy(right)
        aw, ah = _size(left)
        bw, bh = _size(right)
        _insert_pointer_line(
            path,
            anchor=anchor,
            start=(ax + aw // 2, ay + ah // 2),
            end=(bx + bw // 2, by + bh // 2),
            line_color="#555555",
            line_width=200,
        )
    return a, b


def materialize_p332_regression_corpus(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "P3.32",
        "purpose": "PRODUCT_BROWNFIELD_DIAGRAM_ADOPTION_REGRESSION",
        "authority": "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "fixtures": [],
    }
    for name in FIXTURES:
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "source.hwpx"
        target = folder / "target.hwpx"
        anchor = _blank(source)

        if name == "unconnected-shapes-no-candidate":
            _legacy_pair(source, anchor, connected=False)
        elif name == "occupied-name-hold":
            _legacy_pair(source, anchor, occupied=True)
        elif name == "mixed-managed-unmanaged":
            apply_diagram_lifecycle_atomic(
                source,
                [{"op": "instantiate_template", "diagram_id": "managed", "anchor": anchor, "template": "linear_process"}],
                expected_revision=1,
                current_revision=1,
            )
            _legacy_pair(source, anchor)
        else:
            _legacy_pair(source, anchor)

        target.write_bytes(source.read_bytes())
        entry = {"name": name}

        if name == "recognize-pass":
            mapped = build_brownfield_diagram_map(target)
            entry.update({
                "candidate_count": mapped["candidate_count"],
                "promotable_candidate_count": mapped["promotable_candidate_count"],
                "recognition_sha256": mapped["recognition_sha256"],
            })
        elif name == "promote-pass":
            candidate = build_brownfield_diagram_map(target)["candidates"][0]
            plan = plan_diagram_adoption(target, candidate["candidate_id"], "legacy")
            receipt = promote_diagram_candidate_atomic(target, plan, expected_revision=1, current_revision=1)
            entry.update({
                "adoption_plan_sha256": plan["adoption_plan_sha256"],
                "identity_sha256": receipt["identity_sha256"],
                "relation_sha256": receipt["relation_sha256"],
            })
        elif name == "occupied-name-hold":
            candidate = build_brownfield_diagram_map(target)["candidates"][0]
            entry.update({"promotable": candidate["promotable"], "hold_reasons": candidate["hold_reasons"]})
        elif name == "stale-plan":
            candidate = build_brownfield_diagram_map(target)["candidates"][0]
            plan = plan_diagram_adoption(target, candidate["candidate_id"], "legacy")
            first = candidate["nodes"][0]["locator"]
            _set_existing_shape_text(target, {"drawing": first, "text": "Changed"})
            try:
                promote_diagram_candidate_atomic(target, plan, expected_revision=2, current_revision=2)
                stale_rejected = False
            except ValueError:
                stale_rejected = True
            entry.update({"stale_rejected": stale_rejected, "adoption_plan_sha256": plan["adoption_plan_sha256"]})
        elif name == "mixed-managed-unmanaged":
            mapped = build_brownfield_diagram_map(target)
            entry.update({
                "managed_diagram_count": mapped["managed_diagram_count"],
                "candidate_count": mapped["candidate_count"],
                "promotable_candidate_count": mapped["promotable_candidate_count"],
            })
        elif name == "refactor-layout-theme":
            candidate = build_brownfield_diagram_map(target)["candidates"][0]
            adoption = plan_diagram_adoption(target, candidate["candidate_id"], "legacy")
            promote_diagram_candidate_atomic(target, adoption, expected_revision=1, current_revision=1)
            refactor = plan_legacy_diagram_refactor(target, "legacy", layout_policy="standard", theme="mono")
            receipt = apply_legacy_diagram_refactor_atomic(
                target, refactor, expected_revision=2, current_revision=2
            )
            entry.update({
                "refactor_plan_sha256": refactor["refactor_plan_sha256"],
                "relation_preserved": receipt["relation_preserved"],
                "relation_sha256": receipt["relation_sha256"],
            })
        elif name == "reingest-managed":
            candidate = build_brownfield_diagram_map(target)["candidates"][0]
            adoption = plan_diagram_adoption(target, candidate["candidate_id"], "legacy")
            promote_diagram_candidate_atomic(target, adoption, expected_revision=1, current_revision=1)
            reingested = folder / "reingested.hwpx"
            shutil.copyfile(target, reingested)
            lifecycle = build_diagram_lifecycle_map(reingested)
            entry.update({
                "managed_diagram_count": lifecycle["diagram_count"],
                "relation_sha256": lifecycle["diagrams"][0]["relation_sha256"],
            })
        elif name == "unconnected-shapes-no-candidate":
            mapped = build_brownfield_diagram_map(target)
            entry.update({"candidate_count": mapped["candidate_count"]})

        entry["source"] = str(source.relative_to(out_dir))
        entry["target"] = str(target.relative_to(out_dir))
        manifest["fixtures"].append(entry)

    (out_dir / "p332-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
