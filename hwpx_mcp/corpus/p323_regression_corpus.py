from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p313r1_fixture_pack import _validate_minimal_hwpx
from p323_advanced_tables import apply_advanced_table_edits_atomic, build_advanced_table_map


SCHEMA = "chatgpt-web-hwpx-mcp/advanced-table-regression/p3.23/v1"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _base(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.23 advanced table regression")
    table = doc.add_table(rows=3, cols=3)
    for r in range(3):
        for c in range(3):
            table.set_cell_text(r, c, f"R{r}C{c}")
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _resolve(path: Path, operations: list[dict]) -> list[dict]:
    mapped = build_advanced_table_map(path)
    table = mapped["tables"][0]
    tokens = {
        "$TABLE": table["locator"],
        "$R0C0": next(c["locator"] for c in table["cells"] if c["row"] == 0 and c["col"] == 0),
        "$R0C1": next(c["locator"] for c in table["cells"] if c["row"] == 0 and c["col"] == 1),
        "$R1C1": next(c["locator"] for c in table["cells"] if c["row"] == 1 and c["col"] == 1),
    }
    resolved = json.loads(json.dumps(operations, ensure_ascii=False))
    for op in resolved:
        for key in ("table", "cell", "start_cell", "end_cell"):
            if op.get(key) in tokens:
                op[key] = tokens[op[key]]
    return resolved


def _fixture(out: Path, fixture_id: str, operations: list[dict]) -> dict:
    root = out / fixture_id
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.hwpx"
    target = root / "target.hwpx"
    _base(source)
    target.write_bytes(source.read_bytes())

    before = build_advanced_table_map(source)
    resolved = _resolve(target, operations)
    result = apply_advanced_table_edits_atomic(
        target,
        resolved,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    after = build_advanced_table_map(target)

    return {
        "fixture_id": fixture_id,
        "operations": resolved,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "source_advanced_table_sha256": before["advanced_table_layout_sha256"],
        "target_advanced_table_sha256": after["advanced_table_layout_sha256"],
        "source_structure_sha256": before["table_structure_sha256"],
        "target_structure_sha256": after["table_structure_sha256"],
        "advanced_table_layout_changed": result["advanced_table_layout_changed"],
        "table_structure_changed": result["table_structure_changed"],
    }


def materialize_p323_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "repeat-header",
            [{"op": "set_repeat_header", "table": "$TABLE", "row": 0, "enabled": True}],
        ),
        _fixture(
            out,
            "row-height",
            [{"op": "set_row_properties", "table": "$TABLE", "row": 1, "height": 2600}],
        ),
        _fixture(
            out,
            "vertical-alignment",
            [{"op": "set_cell_vertical_alignment", "table": "$TABLE", "cell": "$R1C1", "alignment": "BOTTOM"}],
        ),
        _fixture(
            out,
            "page-break",
            [{"op": "set_table_page_break", "table": "$TABLE", "mode": "TABLE"}],
        ),
        _fixture(
            out,
            "merge-and-style",
            [
                {"op": "merge_cells", "table": "$TABLE", "start_cell": "$R0C0", "end_cell": "$R0C1"},
                {"op": "set_table_shading", "table": "$TABLE", "color": "#F2F2F2"},
                {"op": "set_table_borders", "table": "$TABLE", "color": "#000000", "line_type": "SOLID"},
            ],
        ),
        _fixture(
            out,
            "row-column-structure",
            [
                {"op": "insert_row_by_clone", "table": "$TABLE", "ref_row": 1, "count": 1},
                {"op": "delete_column", "table": "$TABLE", "col": 2},
            ],
        ),
    ]

    manifest = {
        "schema": SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "purpose": "PRODUCT_ADVANCED_TABLE_REGRESSION",
        "authority": "STRUCTURAL_AUTHORITY_ONLY",
        "native_batch_status": "DEFERRED_BY_DESIGN",
        "explicit_gate": "insert_column_by_clone remains EVIDENCE_GATE_CLOSED",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p323-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
