from __future__ import annotations

import copy
from typing import Any

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

EVIDENCE = {
    "hancom_version": "13.0.0.3622",
    "captured_at_phase": "P3.34-R1",
    "verified_cases": {
        "basic-left-1": {
            "source_sha256": "ac688bc871822c3e18917832160a9404ec61c75a871cd6ba4c673c2baef0107e",
            "target_sha256": "04bedbf11600a88105f1636c68fcb45c0c5ce9a000e86e876feeae354977b95a",
            "direction": "LEFT",
            "count": 1,
        },
        "merged-header-left-1": {
            "source_sha256": "dac45116a7ed7099940a84cd30b327c2e7911aba352ada6c5edf41ba736c716b",
            "target_sha256": "f3ccd62d8808aeec82318e7350c9f5ed385245d6ee262f958c3a71fb1f690b87",
            "direction": "LEFT",
            "count": 1,
        },
        "nonuniform-right-1": {
            "source_sha256": "5cc03a02e381195b360c8621a57dd8dac6b6c1ca6679bf290fc1070aeef5b451",
            "target_sha256": "8e34987c2def3c6b12e76da9b7eb4eaeb6f0b0c4523e3e1cb68a076749d9efba",
            "direction": "RIGHT",
            "count": 1,
        },
    },
    "rejected_case": {
        "basic-right-2": {
            "source_sha256": "e9af8449e9467d891997e0b689d8cd976b2d5b37e918fab8082d9fd376265fb9",
            "target_sha256": "21f6cdb1677cf6396c5cd279dd605cb19e3a1bbf6a145abbc67043a29af2cb11",
            "requested_count": 2,
            "observed_colcnt_delta": 1,
            "reason": "capture does not identify count>1 semantics; excluded from promotion evidence",
        }
    },
}


def column_insertion_contract() -> dict:
    return {
        "phase": "P3.34-R1",
        "status": "CANDIDATE_IMPLEMENTATION_COUNT1_ONLY",
        "authority": "NO_PRODUCTION_EDIT_AUTHORITY_YET",
        "admitted_candidate": {
            "operation": "insert_column_native_bounded",
            "directions": ["LEFT", "RIGHT"],
            "count": 1,
            "vertical_merges": False,
            "nested_tables": False,
        },
        "native_semantics": {
            "new_cell_content": "blank",
            "new_cell_format": "clone same-row anchor-column cell when not crossing a horizontal merge",
            "new_column_width": "anchor logical column width",
            "table_width": "increase by inserted column width",
            "shift": "cells beginning at or after insertion boundary shift colAddr by +1",
            "crossing_horizontal_merge": (
                "increase colSpan by +1; native evidence leaves merged cell cellSz/@width unchanged"
            ),
            "paragraph_id_for_new_cell": "0",
        },
        "holds": {
            "count_gt_1": "NATIVE_EVIDENCE_MISMATCH",
            "vertical_merge": "NOT_IN_NATIVE_GOLD",
            "nested_table": "OUT_OF_SCOPE",
            "production_authority": "IMPLEMENTATION_NATIVE_OPEN_RESAVE_REQUIRED",
        },
        "evidence": EVIDENCE,
    }


def _child(element, local: str):
    return element.find(f"{HP}{local}")


def _iattr(element, local: str, attr: str, default: int | None = None) -> int | None:
    child = _child(element, local)
    if child is None:
        return default
    raw = child.get(attr)
    return default if raw is None else int(raw)


def _set_iattr(element, local: str, attr: str, value: int) -> None:
    child = _child(element, local)
    if child is None:
        raise ValueError(f"cell has no hp:{local}")
    child.set(attr, str(int(value)))


def _blank_clone(cell):
    cloned = copy.deepcopy(cell)
    for item in list(cloned.iter()):
        if item.tag == f"{HP}t":
            item.text = None
        elif item.tag == f"{HP}p":
            item.set("id", "0")
    # Remove stale layout caches from cloned paragraphs.
    for parent in list(cloned.iter()):
        for child in list(parent):
            if child.tag.endswith("linesegarray"):
                parent.remove(child)
    return cloned


def _direct_rows(table) -> list[Any]:
    rows = [child for child in list(table.element) if child.tag == f"{HP}tr"]
    if len(rows) != int(table.row_count):
        raise ValueError("table physical row count is not safely addressable")
    return rows


def _direct_cells(row) -> list[Any]:
    return [child for child in list(row) if child.tag == f"{HP}tc"]


def _coverage(cells: list[Any], col_count: int) -> list[Any]:
    grid: list[Any | None] = [None] * col_count
    for cell in cells:
        ca = _iattr(cell, "cellAddr", "colAddr")
        cs = _iattr(cell, "cellSpan", "colSpan", 1)
        rs = _iattr(cell, "cellSpan", "rowSpan", 1)
        if ca is None or cs is None or rs is None:
            raise ValueError("cell address/span is incomplete")
        if rs != 1:
            raise ValueError("vertical merges are outside P3.34-R1 bounded authority")
        if ca < 0 or ca + cs > col_count:
            raise ValueError("cell span is outside table column bounds")
        for col in range(ca, ca + cs):
            if grid[col] is not None:
                raise ValueError("overlapping logical cells")
            grid[col] = cell
    if any(item is None for item in grid):
        raise ValueError("logical row has uncovered columns")
    return [item for item in grid if item is not None]


def _table_level_size(table):
    for child in list(table.element):
        if child.tag == f"{HP}sz":
            return child
    raise ValueError("table has no direct hp:sz")


def _nested_table_present(table) -> bool:
    seen_root = False
    for item in table.element.iter():
        if item.tag == f"{HP}tbl":
            if not seen_root:
                seen_root = True
            else:
                return True
    return False


def apply_bounded_column_insertion(table, table_payload: dict, op: dict) -> dict:
    """Apply the P3.34-R1 count=1 Hancom-native candidate semantics.

    This is intentionally a candidate primitive only. The production MCP surface
    must not expose it until a generated-output Hancom open/resave witness passes.
    """
    count = int(op.get("count", 1))
    if count != 1:
        raise ValueError("P3.34-R1 admits exactly count=1; count>1 native evidence is unresolved")

    direction = str(op.get("direction", "")).upper()
    if direction not in {"LEFT", "RIGHT"}:
        raise ValueError("direction must be LEFT or RIGHT")

    anchor_locator = op.get("cell")
    cells_by_locator = {item["locator"]: item for item in table_payload["cells"]}
    anchor = cells_by_locator.get(anchor_locator)
    if anchor is None:
        raise ValueError(f"Unknown cell locator: {anchor_locator}")
    if int(anchor["row_span"]) != 1 or int(anchor["col_span"]) != 1:
        raise ValueError("anchor cell must be an unmerged logical cell")

    if _nested_table_present(table):
        raise ValueError("nested tables are outside P3.34-R1 bounded authority")

    col_count = int(table_payload["cols"])
    anchor_col = int(anchor["col"])
    boundary = anchor_col if direction == "LEFT" else anchor_col + 1
    if boundary < 0 or boundary > col_count:
        raise ValueError("computed insertion boundary is outside table")

    rows = _direct_rows(table)
    row_grids: list[list[Any]] = []
    width_candidates: list[int] = []
    for row in rows:
        direct = _direct_cells(row)
        grid = _coverage(direct, col_count)
        row_grids.append(grid)
        source = grid[anchor_col]
        source_ca = _iattr(source, "cellAddr", "colAddr")
        source_cs = _iattr(source, "cellSpan", "colSpan", 1)
        if source_ca == anchor_col and source_cs == 1:
            width = _iattr(source, "cellSz", "width")
            if width is not None and width > 0:
                width_candidates.append(width)

    if not width_candidates or len(set(width_candidates)) != 1:
        raise ValueError("anchor logical column width is not uniquely identified")
    inserted_width = width_candidates[0]

    crossing_rows = 0
    inserted_rows = 0
    for row, grid in zip(rows, row_grids):
        direct = _direct_cells(row)
        crossing = None
        for cell in direct:
            ca = _iattr(cell, "cellAddr", "colAddr")
            cs = _iattr(cell, "cellSpan", "colSpan", 1)
            if ca is not None and cs is not None and ca < boundary < ca + cs:
                crossing = cell
                break

        # Snapshot the clone source before shifting addresses.
        source = grid[anchor_col]
        source_ca = _iattr(source, "cellAddr", "colAddr")
        source_cs = _iattr(source, "cellSpan", "colSpan", 1)

        for cell in direct:
            ca = _iattr(cell, "cellAddr", "colAddr")
            if ca is None:
                raise ValueError("cell has no colAddr")
            if cell is crossing:
                _set_iattr(cell, "cellSpan", "colSpan", int(_iattr(cell, "cellSpan", "colSpan", 1)) + 1)
            elif ca >= boundary:
                _set_iattr(cell, "cellAddr", "colAddr", ca + 1)

        if crossing is not None:
            crossing_rows += 1
            continue

        if source_ca != anchor_col or source_cs != 1:
            raise ValueError(
                "row has no direct span-1 clone source at anchor column; semantics not in native gold"
            )
        new_cell = _blank_clone(source)
        _set_iattr(new_cell, "cellAddr", "colAddr", boundary)
        _set_iattr(new_cell, "cellSpan", "colSpan", 1)
        _set_iattr(new_cell, "cellSpan", "rowSpan", 1)
        _set_iattr(new_cell, "cellSz", "width", inserted_width)

        # Keep direct hp:tc children ordered by logical colAddr.
        insert_index = len(list(row))
        for idx, child in enumerate(list(row)):
            if child.tag != f"{HP}tc":
                continue
            child_ca = _iattr(child, "cellAddr", "colAddr")
            if child_ca is not None and child_ca > boundary:
                insert_index = idx
                break
        row.insert(insert_index, new_cell)
        inserted_rows += 1

    table.element.set("colCnt", str(col_count + 1))
    size = _table_level_size(table)
    current_width = int(size.get("width", "0") or 0)
    if current_width <= 0:
        raise ValueError("table width is not positive")
    size.set("width", str(current_width + inserted_width))
    table.mark_dirty()

    return {
        "ok": True,
        "op": "insert_column_native_bounded",
        "direction": direction,
        "count": 1,
        "anchor_col": anchor_col,
        "insertion_boundary": boundary,
        "inserted_width": inserted_width,
        "rows_with_new_cell": inserted_rows,
        "rows_with_crossing_span_extension": crossing_rows,
        "native_evidence": "P3.34-R1_COUNT1",
        "production_authority": "NOT_YET_PROMOTED_NATIVE_REOPEN_REQUIRED",
    }
