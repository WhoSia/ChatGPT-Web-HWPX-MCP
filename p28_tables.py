from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from hwpx import HwpxDocument
from hwpx.table_patch import apply_table_ops

from p27_tables import (
    _cell_index,
    _resolve_cell,
    _resolve_table,
    _save_document,
    apply_table_edits_atomic as apply_p27_table_edits_atomic,
    build_table_map as build_p27_table_map,
)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _cell_margin(cell) -> dict[str, int]:
    margin = cell.element.find(f"{HP}cellMargin")
    if margin is None:
        return {"left": 0, "right": 0, "top": 0, "bottom": 0}
    return {
        key: int(margin.get(key, "0") or 0)
        for key in ("left", "right", "top", "bottom")
    }


def build_table_map(path: Path) -> dict:
    base = build_p27_table_map(path)
    document = HwpxDocument.open(str(path))
    try:
        refs = document.tables.all
        by_index = {int(t["table_index"]): t for t in base["tables"]}
        advanced_seed: list[dict] = []
        for index, ref in enumerate(refs):
            payload = by_index[index]
            cell_lookup = {(c["row"], c["col"]): c for c in payload["cells"]}
            for position in ref.iter_grid():
                if not position.is_anchor:
                    continue
                row, col = position.anchor
                cell_payload = cell_lookup[(row, col)]
                cell = position.cell
                attrs = dict(cell.element.attrib)
                cell_payload["name"] = attrs.get("name", "")
                cell_payload["has_margin"] = attrs.get("hasMargin")
                cell_payload["margin"] = _cell_margin(cell)
            advanced_seed.append({
                "table": payload["locator"],
                "cells": [
                    {
                        "row": c["row"],
                        "col": c["col"],
                        "header": c.get("header"),
                        "protect": c.get("protect"),
                        "editable": c.get("editable"),
                        "name": c.get("name"),
                        "has_margin": c.get("has_margin"),
                        "margin": c.get("margin"),
                        "width": c["width"],
                        "height": c["height"],
                        "border_fill_id_ref": c.get("border_fill_id_ref"),
                    }
                    for c in payload["cells"]
                ],
            })
        base["table_object_sha256"] = hashlib.sha256(
            json.dumps(
                advanced_seed,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return base
    finally:
        document.close()


def _validate_bool(value: object, name: str) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value in (0, 1, "0", "1"):
        return str(value)
    raise ValueError(f"{name} must be boolean")


def _create_table(candidate: Path, op: dict) -> dict:
    rows = int(op.get("rows", 0))
    cols = int(op.get("cols", 0))
    if not 1 <= rows <= 200 or not 1 <= cols <= 100:
        raise ValueError("create_table rows/cols are outside the admitted bounds")
    width = op.get("width")
    height = op.get("height")
    if width is not None and int(width) <= 0:
        raise ValueError("create_table width must be positive")
    if height is not None and int(height) <= 0:
        raise ValueError("create_table height must be positive")

    before = build_table_map(candidate)
    document = HwpxDocument.open(str(candidate))
    try:
        table = document.add_table(
            rows=rows,
            cols=cols,
            width=None if width is None else int(width),
            height=None if height is None else int(height),
        )
        cells = op.get("cells")
        if cells is not None:
            if not isinstance(cells, list):
                raise ValueError("create_table cells must be a row list")
            for r, row in enumerate(cells[:rows]):
                if not isinstance(row, list):
                    raise ValueError("create_table cells rows must be lists")
                for c, value in enumerate(row[:cols]):
                    table.set_cell_text(r, c, str(value))
        _save_document(document, candidate, candidate)
    finally:
        document.close()

    after = build_table_map(candidate)
    before_locators = {item["locator"] for item in before["tables"]}
    created = [item for item in after["tables"] if item["locator"] not in before_locators]
    if len(created) != 1:
        raise ValueError("create_table did not yield one uniquely identifiable table")
    return {"created_table": created[0]["locator"], "rows": rows, "cols": cols}


def _delete_table(candidate: Path, table_locator: str) -> dict:
    current = build_table_map(candidate)
    target = _resolve_table(current, table_locator)
    patch = {
        "op": "delete_table",
        "section_path": target["section_path"],
        "table_index": int(target["section_table_index"]),
    }
    result = apply_table_ops(candidate.read_bytes(), [patch])
    if not result.ok:
        raise ValueError(
            "delete_table refused: "
            + json.dumps([x.to_dict() for x in result.skipped], ensure_ascii=False)
        )
    candidate.write_bytes(result.data)
    return result.to_dict()


def _advanced_cell_operation(candidate: Path, op: dict) -> dict:
    current = build_table_map(candidate)
    table_payload = _resolve_table(current, op.get("table"))
    cell_payload = _resolve_cell(table_payload, op.get("cell"))
    document = HwpxDocument.open(str(candidate))
    try:
        table = document.tables.all[int(table_payload["table_index"])]
        cell = table.cell(int(cell_payload["row"]), int(cell_payload["col"]))
        name = op["op"]

        if name == "set_cell_properties":
            if "header" in op:
                cell.element.set("header", _validate_bool(op["header"], "header"))
            if "protect" in op:
                cell.element.set("protect", _validate_bool(op["protect"], "protect"))
            if "editable" in op:
                cell.element.set("editable", _validate_bool(op["editable"], "editable"))
            if "name" in op:
                value = str(op["name"])
                if len(value) > 512:
                    raise ValueError("cell name is too long")
                cell.element.set("name", value)
            table.mark_dirty()
        elif name == "set_cell_margin":
            margin = cell.element.find(f"{HP}cellMargin")
            if margin is None:
                margin = cell.element.makeelement(
                    f"{HP}cellMargin",
                    {"left": "0", "right": "0", "top": "0", "bottom": "0"},
                )
                cell.element.append(margin)
            for side in ("left", "right", "top", "bottom"):
                if side in op:
                    value = int(op[side])
                    if value < 0 or value > 100000:
                        raise ValueError(f"cell margin {side} is outside admitted bounds")
                    margin.set(side, str(value))
            cell.element.set("hasMargin", "1")
            table.mark_dirty()
        elif name == "set_cell_size":
            width = None if "width" not in op else int(op["width"])
            height = None if "height" not in op else int(op["height"])
            if width is not None and width <= 0:
                raise ValueError("cell width must be positive")
            if height is not None and height <= 0:
                raise ValueError("cell height must be positive")
            cell.set_size(width=width, height=height)
        elif name == "set_cell_border_fill":
            ref = op.get("border_fill_id_ref")
            if ref is None or str(ref) == "":
                raise ValueError("border_fill_id_ref is required")
            table.set_cell_border_fill(
                int(cell_payload["row"]),
                int(cell_payload["col"]),
                str(ref),
            )
        elif name == "set_cell_gradient":
            colors = op.get("colors")
            if not isinstance(colors, list):
                raise ValueError("set_cell_gradient requires colors list")
            table.set_cell_fill_gradient(
                int(cell_payload["row"]),
                int(cell_payload["col"]),
                [str(x) for x in colors],
                gradient_type=str(op.get("gradient_type", "LINEAR")),
                angle=int(op.get("angle", 90)),
            )
        else:
            raise ValueError(f"Unsupported advanced cell operation: {name}")

        _save_document(document, candidate, candidate)
        return {"ok": True, "op": name, "table": table_payload["locator"], "cell": cell_payload["locator"]}
    finally:
        document.close()


def _normalize_p28_operations(operations: list[dict], before: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one table operation is required")
    if len(operations) > 50:
        raise ValueError("Too many table operations")
    result: list[dict] = []
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each table operation must be an object")
        name = raw.get("op")
        if name == "create_table":
            result.append(dict(raw))
            continue
        if name == "delete_table":
            _resolve_table(before, raw.get("table"))
            result.append(dict(raw))
            continue
        if name in {
            "set_cell_properties",
            "set_cell_margin",
            "set_cell_size",
            "set_cell_border_fill",
            "set_cell_gradient",
        }:
            table = _resolve_table(before, raw.get("table"))
            _resolve_cell(table, raw.get("cell"))
            result.append(dict(raw))
            continue
        if name == "insert_column_by_clone":
            raise ValueError(
                "insert_column_by_clone evidence gate remains closed: "
                "no upstream render-verified column-insert primitive exists"
            )
        result.append(dict(raw))
    return result


def _rebinding(before: dict, after: dict) -> dict:
    before_tables = {item["locator"]: item for item in before["tables"]}
    after_tables = {item["locator"]: item for item in after["tables"]}
    created = [locator for locator in after_tables if locator not in before_tables]
    deleted = [locator for locator in before_tables if locator not in after_tables]
    stable = [locator for locator in before_tables if locator in after_tables]
    return {
        "created_tables": created,
        "deleted_tables": deleted,
        "stable_tables": stable,
        "reacquire_required": bool(created or deleted),
    }


def apply_table_edits_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")

    before = build_table_map(path)
    normalized = _normalize_p28_operations(operations, before)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p28-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    transcripts: list[dict] = []
    validation = None

    try:
        for op in normalized:
            name = op["op"]
            if name == "create_table":
                transcripts.append({"ok": True, "op": name, **_create_table(candidate, op)})
            elif name == "delete_table":
                transcripts.append(_delete_table(candidate, str(op["table"])))
            elif name in {
                "set_cell_properties",
                "set_cell_margin",
                "set_cell_size",
                "set_cell_border_fill",
                "set_cell_gradient",
            }:
                transcripts.append(_advanced_cell_operation(candidate, op))
            else:
                # Delegate one established P2.7 operation at a time against the
                # candidate's current locators/digests.
                delegated = apply_p27_table_edits_atomic(
                    candidate,
                    [op],
                    expected_revision=current_revision,
                    current_revision=current_revision,
                    validator=None,
                )
                transcripts.append({
                    "ok": True,
                    "op": name,
                    "delegated": {
                        "table_structure_changed": delegated["table_structure_changed"],
                        "table_format_changed": delegated["table_format_changed"],
                    },
                })

        after = build_table_map(candidate)
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
        },
        "after": {
            "table_count": after["table_count"],
            "table_structure_sha256": after["table_structure_sha256"],
            "table_format_sha256": after["table_format_sha256"],
            "table_object_sha256": after["table_object_sha256"],
        },
        "table_structure_changed": before["table_structure_sha256"] != after["table_structure_sha256"],
        "table_format_changed": before["table_format_sha256"] != after["table_format_sha256"],
        "table_object_changed": before["table_object_sha256"] != after["table_object_sha256"],
        "table_object_rebinding": _rebinding(before, after),
        "operation_count": len(normalized),
        "operations": normalized,
        "transcripts": transcripts,
    }
    if validation is not None:
        result["validation"] = validation
    return result
