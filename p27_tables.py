from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from hwpx import HwpxDocument
from hwpx.table_patch import apply_table_ops
from hwpx.tools.table_navigation import _collect_document_tables


def _hash_locator(prefix: str, seed: str) -> str:
    return prefix + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def _section_path(table) -> str:
    section = table.paragraph.section
    return str(getattr(section, "part_name", "") or "Contents/section0.xml")


def _cell_text(cell) -> str:
    paragraphs = list(getattr(cell, "paragraphs", []) or [])
    if paragraphs:
        return "\n".join((p.text or "") for p in paragraphs)
    return str(getattr(cell, "text", "") or "")


def _table_locator(section_path: str, local_index: int, global_index: int, table) -> tuple[str, str]:
    intrinsic = table.element.get("id") or table.element.get("instid")
    if intrinsic:
        return _hash_locator("tbl_", f"{section_path}:id:{intrinsic}"), "intrinsic-id"
    return _hash_locator("tbl_", f"{section_path}:ordinal:{local_index}:global:{global_index}"), "revision-bound-ordinal"


def _cell_locator(table_locator: str, row: int, col: int) -> str:
    return _hash_locator("cell_", f"{table_locator}:{row}:{col}")


def build_table_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        refs = _collect_document_tables(document)
        local_counts: dict[str, int] = {}
        tables: list[dict] = []
        structure_seed: list[dict] = []
        format_seed: list[dict] = []

        for global_index, ref in enumerate(refs):
            table = ref.table
            section_path = _section_path(table)
            local_index = local_counts.get(section_path, 0)
            local_counts[section_path] = local_index + 1
            locator, stability = _table_locator(section_path, local_index, global_index, table)
            intrinsic = table.element.get("id") or table.element.get("instid")
            cells: list[dict] = []
            seen: set[tuple[int, int]] = set()

            for position in table.iter_grid():
                anchor_row, anchor_col = position.anchor
                if (anchor_row, anchor_col) in seen:
                    continue
                seen.add((anchor_row, anchor_col))
                cell = position.cell
                row_span, col_span = position.span
                attrs = dict(cell.element.attrib)
                cell_payload = {
                    "locator": _cell_locator(locator, anchor_row, anchor_col),
                    "address_stability": "revision-bound-grid-anchor",
                    "row": anchor_row,
                    "col": anchor_col,
                    "row_span": row_span,
                    "col_span": col_span,
                    "text": _cell_text(cell),
                    "width": int(getattr(cell, "width", 0) or 0),
                    "height": int(getattr(cell, "height", 0) or 0),
                    "border_fill_id_ref": attrs.get("borderFillIDRef"),
                    "header": attrs.get("header"),
                    "protect": attrs.get("protect"),
                    "editable": attrs.get("editable"),
                }
                cells.append(cell_payload)

            cells.sort(key=lambda item: (item["row"], item["col"]))
            table_payload = {
                "locator": locator,
                "address_stability": stability,
                "intrinsic_id": intrinsic,
                "table_index": global_index,
                "section_path": section_path,
                "section_table_index": local_index,
                "paragraph_index": ref.paragraph_index,
                "rows": table.row_count,
                "cols": table.column_count,
                "caption_text": ref.caption_text,
                "preceding_paragraph_text": ref.preceding_paragraph_text,
                "header_text": ref.header_text,
                "attributes": dict(table.element.attrib),
                "cells": cells,
            }
            tables.append(table_payload)
            structure_seed.append({
                "locator": locator,
                "section_path": section_path,
                "rows": table.row_count,
                "cols": table.column_count,
                "cells": [
                    (c["row"], c["col"], c["row_span"], c["col_span"])
                    for c in cells
                ],
            })
            format_seed.append({
                "locator": locator,
                "table_attrs": dict(table.element.attrib),
                "cells": [
                    (
                        c["row"], c["col"], c["width"], c["height"],
                        c["border_fill_id_ref"], c["header"], c["protect"], c["editable"],
                    )
                    for c in cells
                ],
            })

        structure_sha = hashlib.sha256(
            json.dumps(structure_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        format_sha = hashlib.sha256(
            json.dumps(format_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "table_count": len(tables),
            "tables": tables,
            "table_structure_sha256": structure_sha,
            "table_format_sha256": format_sha,
        }
    finally:
        document.close()


def _table_index(table_map: dict) -> dict[str, dict]:
    return {item["locator"]: item for item in table_map["tables"]}


def _cell_index(table_payload: dict) -> dict[str, dict]:
    return {item["locator"]: item for item in table_payload["cells"]}


def _resolve_table(table_map: dict, locator: object) -> dict:
    if not isinstance(locator, str):
        raise ValueError("table locator must be a string")
    table = _table_index(table_map).get(locator)
    if table is None:
        raise ValueError(f"Unknown table locator: {locator}")
    return table


def _resolve_cell(table_payload: dict, locator: object) -> dict:
    if not isinstance(locator, str):
        raise ValueError("cell locator must be a string")
    cell = _cell_index(table_payload).get(locator)
    if cell is None:
        raise ValueError(f"Unknown cell locator: {locator}")
    return cell


def _save_document(document: HwpxDocument, candidate: Path, base: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=base.stem + ".p27-lib-", suffix=".hwpx", dir=str(base.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        document.save_to_path(str(tmp))
        os.replace(tmp, candidate)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _direct_table_operation(candidate: Path, table_locator: str, op: dict) -> None:
    current = build_table_map(candidate)
    target = _resolve_table(current, table_locator)
    document = HwpxDocument.open(str(candidate))
    try:
        refs = _collect_document_tables(document)
        table = refs[int(target["table_index"])].table
        name = op["op"]

        if name == "merge_cells":
            start = _resolve_cell(target, op.get("start_cell"))
            end = _resolve_cell(target, op.get("end_cell"))
            r0, c0 = int(start["row"]), int(start["col"])
            r1 = int(end["row"]) + int(end["row_span"]) - 1
            c1 = int(end["col"]) + int(end["col_span"]) - 1
            table.merge_cells(r0, c0, r1, c1)
        elif name == "split_merged_cell":
            cell = _resolve_cell(target, op.get("cell"))
            table.split_merged_cell(int(cell["row"]), int(cell["col"]))
        elif name == "set_cell_text":
            cell = _resolve_cell(target, op.get("cell"))
            table.set_cell_text(
                int(cell["row"]), int(cell["col"]), str(op.get("text", "")),
                logical=True, preserve_format=True,
            )
        elif name == "set_cell_shading":
            cell = _resolve_cell(target, op.get("cell"))
            color = op.get("color")
            if not isinstance(color, str) or not color:
                raise ValueError("set_cell_shading requires color")
            table.set_cell_shading(int(cell["row"]), int(cell["col"]), color)
        elif name == "set_cell_borders":
            cell = _resolve_cell(target, op.get("cell"))
            color = op.get("color")
            line_type = str(op.get("line_type", "SOLID"))
            if not isinstance(color, str) or not color:
                raise ValueError("set_cell_borders requires color")
            table.set_cell_borders(
                int(cell["row"]), int(cell["col"]), color=color, line_type=line_type,
            )
        elif name == "equalize_columns":
            table.equalize_column_widths()
        elif name == "equalize_rows":
            table.equalize_row_heights()
        else:
            raise ValueError(f"Unsupported direct table operation: {name}")

        _save_document(document, candidate, candidate)
    finally:
        document.close()


def _patch_table_operation(candidate: Path, table_locator: str, op: dict) -> dict:
    current = build_table_map(candidate)
    target = _resolve_table(current, table_locator)
    name = op["op"]
    patch: dict = {
        "op": name,
        "section_path": target["section_path"],
        "table_index": int(target["section_table_index"]),
    }

    if name == "insert_row_by_clone":
        patch["ref_row"] = int(op["ref_row"])
        patch["count"] = int(op.get("count", 1))
    elif name == "delete_row":
        patch["row"] = int(op["row"])
    elif name == "delete_column":
        patch["col"] = int(op["col"])
    elif name == "set_column_widths":
        widths = op.get("widths")
        if not isinstance(widths, (list, dict)):
            raise ValueError("set_column_widths requires widths list or mapping")
        patch["widths"] = widths
    elif name == "autofit_columns":
        if "min_frac" in op:
            patch["min_frac"] = float(op["min_frac"])
        if "damp" in op:
            patch["damp"] = float(op["damp"])
    else:
        raise ValueError(f"Unsupported table-patch operation: {name}")

    result = apply_table_ops(candidate.read_bytes(), [patch])
    if not result.ok:
        reasons = [item.to_dict() for item in result.skipped]
        raise ValueError(f"Table structure operation refused: {reasons}")
    candidate.write_bytes(result.data)
    return result.to_dict()


def _normalize_operations(operations: list[dict], before: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one table operation is required")
    if len(operations) > 50:
        raise ValueError("Too many table operations")
    normalized: list[dict] = []
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each table operation must be an object")
        name = raw.get("op")
        table_locator = raw.get("table")
        table = _resolve_table(before, table_locator)

        if name in {"insert_row_by_clone", "delete_row", "delete_column", "set_column_widths", "autofit_columns"}:
            normalized.append(dict(raw))
        elif name in {
            "merge_cells", "split_merged_cell", "set_cell_text",
            "set_cell_shading", "set_cell_borders", "equalize_columns", "equalize_rows",
        }:
            if name in {"split_merged_cell", "set_cell_text", "set_cell_shading", "set_cell_borders"}:
                _resolve_cell(table, raw.get("cell"))
            if name == "merge_cells":
                _resolve_cell(table, raw.get("start_cell"))
                _resolve_cell(table, raw.get("end_cell"))
            normalized.append(dict(raw))
        else:
            raise ValueError(f"Unsupported table operation: {name}")
    return normalized


def _rebinding(before: dict, after: dict) -> dict:
    after_tables = _table_index(after)
    table_bindings: list[dict] = []
    cell_bindings: list[dict] = []

    for table in before["tables"]:
        after_table = after_tables.get(table["locator"])
        table_bindings.append({
            "before_locator": table["locator"],
            "after_locator": table["locator"] if after_table else None,
            "status": "stable" if after_table else "deleted-or-reacquire",
            "address_stability": table["address_stability"],
        })
        if after_table is None:
            for cell in table["cells"]:
                cell_bindings.append({
                    "table": table["locator"],
                    "before_locator": cell["locator"],
                    "after_locator": None,
                    "status": "deleted-or-reacquire",
                })
            continue

        by_signature: dict[tuple, list[dict]] = {}
        for cell in after_table["cells"]:
            signature = (
                cell["text"], cell["row_span"], cell["col_span"],
                cell["border_fill_id_ref"], cell["width"], cell["height"],
            )
            by_signature.setdefault(signature, []).append(cell)

        for cell in table["cells"]:
            signature = (
                cell["text"], cell["row_span"], cell["col_span"],
                cell["border_fill_id_ref"], cell["width"], cell["height"],
            )
            candidates = by_signature.get(signature, [])
            exact = next(
                (item for item in candidates if item["row"] == cell["row"] and item["col"] == cell["col"]),
                None,
            )
            if exact is not None:
                chosen = exact
                status = "stable"
            elif len(candidates) == 1:
                chosen = candidates[0]
                status = "rebound"
            else:
                chosen = None
                status = "deleted-or-ambiguous"
            cell_bindings.append({
                "table": table["locator"],
                "before_locator": cell["locator"],
                "after_locator": chosen["locator"] if chosen else None,
                "status": status,
                "before_address": [cell["row"], cell["col"]],
                "after_address": [chosen["row"], chosen["col"]] if chosen else None,
            })

    return {
        "tables": table_bindings,
        "cells": cell_bindings,
        "reacquire_required": any(item["status"] not in {"stable", "rebound"} for item in cell_bindings),
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
    normalized = _normalize_operations(operations, before)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p27-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    transcripts: list[dict] = []
    validation = None

    try:
        for op in normalized:
            name = op["op"]
            table_locator = str(op["table"])
            if name in {"insert_row_by_clone", "delete_row", "delete_column", "set_column_widths", "autofit_columns"}:
                transcripts.append(_patch_table_operation(candidate, table_locator, op))
            else:
                _direct_table_operation(candidate, table_locator, op)
                transcripts.append({"ok": True, "op": name, "table": table_locator})

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
        },
        "after": {
            "table_count": after["table_count"],
            "table_structure_sha256": after["table_structure_sha256"],
            "table_format_sha256": after["table_format_sha256"],
        },
        "table_structure_changed": before["table_structure_sha256"] != after["table_structure_sha256"],
        "table_format_changed": before["table_format_sha256"] != after["table_format_sha256"],
        "table_rebinding": _rebinding(before, after),
        "operation_count": len(normalized),
        "operations": normalized,
        "transcripts": transcripts,
    }
    if validation is not None:
        result["validation"] = validation
    return result
