from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from hwpx import HwpxDocument

from p27_tables import _resolve_table, _save_document
from p28_tables import (
    apply_table_edits_atomic as apply_p28_table_edits_atomic,
    build_table_map as build_p28_table_map,
)
from p334r1_column_insertion import (
    apply_bounded_column_insertion,
    column_insertion_contract,
)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

ADMITTED_P28_OPERATIONS = {
    "create_table",
    "delete_table",
    "merge_cells",
    "split_merged_cell",
    "set_cell_text",
    "set_cell_shading",
    "set_cell_borders",
    "equalize_columns",
    "equalize_rows",
    "insert_row_by_clone",
    "delete_row",
    "delete_column",
    "set_column_widths",
    "autofit_columns",
    "set_cell_properties",
    "set_cell_margin",
    "set_cell_size",
    "set_cell_border_fill",
    "set_cell_gradient",
}

DEFERRED_OPERATIONS = {
    "insert_column_by_clone": (
        "SUPERSEDED_BY_P3.34_R1: use insert_column_native_bounded with count=1; "
        "count>1 remains evidence-gated."
    ),
}

VERTICAL_ALIGNMENTS = {"TOP", "CENTER", "BOTTOM"}
PAGE_BREAK_MODES = {"CELL", "TABLE", "NONE"}


def advanced_table_contract() -> dict:
    return {
        "phase": "P3.23",
        "authority": "STRUCTURAL_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "admitted_operations": sorted(
            ADMITTED_P28_OPERATIONS
            | {
                "set_repeat_header",
                "set_row_properties",
                "set_cell_vertical_alignment",
                "set_table_page_break",
                "set_table_borders",
                "set_table_shading",
                "insert_column_native_bounded",
            }
        ),
        "deferred_operations": dict(DEFERRED_OPERATIONS),
        "semantics": {
            "repeat_header": "hp:tbl@repeatHeader plus hp:tc@header on the designated header row",
            "vertical_alignment": "hp:tc/hp:subList@vertAlign",
            "row_height": "anchor-cell hp:cellSz@height across the designated logical row",
            "table_border_fill": "delegates to established P2.7 cell border/shading primitives",
            "column_insertion_p334r1": column_insertion_contract(),
        },
    }


def _cell_vertical_alignment(cell) -> str | None:
    sub_list = cell.element.find(f"{HP}subList")
    return None if sub_list is None else sub_list.get("vertAlign")


def build_advanced_table_map(path: Path) -> dict:
    base = build_p28_table_map(path)
    document = HwpxDocument.open(str(path))
    try:
        refs = document.tables.all
        by_index = {int(t["table_index"]): t for t in base["tables"]}
        layout_seed: list[dict] = []
        for index, table in enumerate(refs):
            payload = by_index[index]
            attrs = dict(table.element.attrib)
            payload["repeat_header"] = attrs.get("repeatHeader") == "1"
            payload["page_break"] = attrs.get("pageBreak")
            cell_lookup = {(c["row"], c["col"]): c for c in payload["cells"]}
            row_cells: dict[int, list[dict]] = {}
            for position in table.iter_grid():
                if not position.is_anchor:
                    continue
                row, col = position.anchor
                cell_payload = cell_lookup[(row, col)]
                cell_payload["vertical_alignment"] = _cell_vertical_alignment(position.cell)
                row_cells.setdefault(int(row), []).append(cell_payload)

            rows: list[dict] = []
            for row in range(int(payload["rows"])):
                cells = sorted(row_cells.get(row, []), key=lambda item: int(item["col"]))
                rows.append(
                    {
                        "row": row,
                        "anchor_cell_count": len(cells),
                        "all_header": bool(cells) and all(str(c.get("header") or "0") == "1" for c in cells),
                        "heights": sorted({int(c.get("height") or 0) for c in cells}),
                        "vertical_alignments": sorted(
                            {str(c.get("vertical_alignment")) for c in cells if c.get("vertical_alignment")}
                        ),
                    }
                )
            payload["row_geometry"] = rows
            layout_seed.append(
                {
                    "table": payload["locator"],
                    "repeat_header": payload["repeat_header"],
                    "page_break": payload["page_break"],
                    "rows": rows,
                    "cells": [
                        (
                            c["row"],
                            c["col"],
                            c.get("vertical_alignment"),
                            c.get("header"),
                            c.get("width"),
                            c.get("height"),
                            c.get("border_fill_id_ref"),
                        )
                        for c in payload["cells"]
                    ],
                }
            )

        base["advanced_table_layout_sha256"] = hashlib.sha256(
            json.dumps(layout_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        base["advanced_table_contract"] = advanced_table_contract()
        return base
    finally:
        document.close()


def _validate_row(table_payload: dict, raw: object) -> int:
    row = int(raw)
    if row < 0 or row >= int(table_payload["rows"]):
        raise ValueError("row is outside the table bounds")
    return row


def _direct_table_operation(candidate: Path, op: dict) -> dict:
    current = build_advanced_table_map(candidate)
    table_payload = _resolve_table(current, op.get("table"))
    document = HwpxDocument.open(str(candidate))
    try:
        table = document.tables.all[int(table_payload["table_index"])]
        name = str(op["op"])

        if name == "set_repeat_header":
            enabled = bool(op.get("enabled", True))
            header_row = _validate_row(table_payload, op.get("row", 0))
            table.element.set("repeatHeader", "1" if enabled else "0")
            for position in table.iter_grid():
                if not position.is_anchor:
                    continue
                row, _col = position.anchor
                if int(row) == header_row:
                    position.cell.element.set("header", "1" if enabled else "0")
            table.mark_dirty()

        elif name == "set_row_properties":
            row = _validate_row(table_payload, op.get("row"))
            header = op.get("header")
            height = op.get("height")
            if height is not None:
                height = int(height)
                if height <= 0 or height > 1_000_000:
                    raise ValueError("row height is outside admitted bounds")
            touched = 0
            for position in table.iter_grid():
                if not position.is_anchor or int(position.anchor[0]) != row:
                    continue
                if header is not None:
                    position.cell.element.set("header", "1" if bool(header) else "0")
                if height is not None:
                    position.cell.set_size(height=height)
                touched += 1
            if touched == 0:
                raise ValueError("row has no anchor cells")
            table.mark_dirty()

        elif name == "set_cell_vertical_alignment":
            cell_locator = op.get("cell")
            cell_payload = next((c for c in table_payload["cells"] if c["locator"] == cell_locator), None)
            if cell_payload is None:
                raise ValueError(f"Unknown cell locator: {cell_locator}")
            alignment = str(op.get("alignment", "")).upper()
            if alignment not in VERTICAL_ALIGNMENTS:
                raise ValueError("alignment must be TOP, CENTER, or BOTTOM")
            cell = table.cell(int(cell_payload["row"]), int(cell_payload["col"]))
            sub_list = cell.element.find(f"{HP}subList")
            if sub_list is None:
                raise ValueError("cell has no hp:subList; vertical alignment is not safely addressable")
            sub_list.set("vertAlign", alignment)
            table.mark_dirty()

        elif name == "set_table_page_break":
            mode = str(op.get("mode", "")).upper()
            if mode not in PAGE_BREAK_MODES:
                raise ValueError("page-break mode must be CELL, TABLE, or NONE")
            table.element.set("pageBreak", mode)
            table.mark_dirty()

        elif name in {"set_table_borders", "set_table_shading"}:
            color = op.get("color")
            if not isinstance(color, str) or not color:
                raise ValueError(f"{name} requires color")
            line_type = str(op.get("line_type", "SOLID"))
            for position in table.iter_grid():
                if not position.is_anchor:
                    continue
                row, col = position.anchor
                if name == "set_table_borders":
                    table.set_cell_borders(int(row), int(col), color=color, line_type=line_type)
                else:
                    table.set_cell_shading(int(row), int(col), color)
            table.mark_dirty()

        elif name == "insert_column_native_bounded":
            receipt = apply_bounded_column_insertion(table, table_payload, op)
            _save_document(document, candidate, candidate)
            return {
                "ok": True,
                "op": name,
                "table": table_payload["locator"],
                "native_semantics": "P3.34-R1_COUNT1",
                "authority": "COUNT1_LEFT_RIGHT_NATIVE_COLUMN_INSERTION",
                "receipt": receipt,
            }

        else:
            raise ValueError(f"Unsupported P3.23 direct table operation: {name}")

        _save_document(document, candidate, candidate)
        return {"ok": True, "op": name, "table": table_payload["locator"]}
    finally:
        document.close()


def _normalize_operations(operations: list[dict], before: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one advanced-table operation is required")
    if len(operations) > 64:
        raise ValueError("Too many advanced-table operations")
    normalized: list[dict] = []
    direct = {
        "set_repeat_header",
        "set_row_properties",
        "set_cell_vertical_alignment",
        "set_table_page_break",
        "set_table_borders",
        "set_table_shading",
        "insert_column_native_bounded",
    }
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each advanced-table operation must be an object")
        name = str(raw.get("op", ""))
        if name in DEFERRED_OPERATIONS:
            raise ValueError(DEFERRED_OPERATIONS[name])
        if name in direct:
            table = _resolve_table(before, raw.get("table"))
            if name in {"set_repeat_header", "set_row_properties"}:
                _validate_row(table, raw.get("row", 0))
            if name == "set_cell_vertical_alignment":
                cell = raw.get("cell")
                if not any(item["locator"] == cell for item in table["cells"]):
                    raise ValueError(f"Unknown cell locator: {cell}")
            if name == "insert_column_native_bounded":
                cell = raw.get("cell")
                payload = next((item for item in table["cells"] if item["locator"] == cell), None)
                if payload is None:
                    raise ValueError(f"Unknown cell locator: {cell}")
                if int(payload["row_span"]) != 1 or int(payload["col_span"]) != 1:
                    raise ValueError("insert_column_native_bounded requires an unmerged anchor cell")
                direction = str(raw.get("direction", "")).upper()
                if direction not in {"LEFT", "RIGHT"}:
                    raise ValueError("direction must be LEFT or RIGHT")
                if int(raw.get("count", 1)) != 1:
                    raise ValueError("P3.34-R1 production authority admits exactly count=1")
            normalized.append(dict(raw))
            continue
        if name not in ADMITTED_P28_OPERATIONS:
            raise ValueError(f"Unsupported advanced-table operation: {name}")
        normalized.append(dict(raw))
    return normalized


def apply_advanced_table_edits_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")

    before = build_advanced_table_map(path)
    normalized = _normalize_operations(operations, before)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p323-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    transcripts: list[dict] = []
    validation = None

    direct = {
        "set_repeat_header",
        "set_row_properties",
        "set_cell_vertical_alignment",
        "set_table_page_break",
        "set_table_borders",
        "set_table_shading",
        "insert_column_native_bounded",
    }

    try:
        for op in normalized:
            name = str(op["op"])
            if name in direct:
                transcripts.append(_direct_table_operation(candidate, op))
            else:
                delegated = apply_p28_table_edits_atomic(
                    candidate,
                    [op],
                    expected_revision=current_revision,
                    current_revision=current_revision,
                    validator=None,
                )
                transcripts.append(
                    {
                        "ok": True,
                        "op": name,
                        "delegated": {
                            "table_structure_changed": delegated["table_structure_changed"],
                            "table_format_changed": delegated["table_format_changed"],
                            "table_object_changed": delegated["table_object_changed"],
                        },
                    }
                )

        after = build_advanced_table_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    result = {
        "before": {
            "table_count": before["table_count"],
            "table_structure_sha256": before["table_structure_sha256"],
            "table_format_sha256": before["table_format_sha256"],
            "table_object_sha256": before["table_object_sha256"],
            "advanced_table_layout_sha256": before["advanced_table_layout_sha256"],
        },
        "after": {
            "table_count": after["table_count"],
            "table_structure_sha256": after["table_structure_sha256"],
            "table_format_sha256": after["table_format_sha256"],
            "table_object_sha256": after["table_object_sha256"],
            "advanced_table_layout_sha256": after["advanced_table_layout_sha256"],
        },
        "table_structure_changed": before["table_structure_sha256"] != after["table_structure_sha256"],
        "table_format_changed": before["table_format_sha256"] != after["table_format_sha256"],
        "table_object_changed": before["table_object_sha256"] != after["table_object_sha256"],
        "advanced_table_layout_changed": (
            before["advanced_table_layout_sha256"] != after["advanced_table_layout_sha256"]
        ),
        "operation_count": len(normalized),
        "operations": normalized,
        "transcripts": transcripts,
        "authority": "STRUCTURAL_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
    if validation is not None:
        result["validation"] = validation
    return result
