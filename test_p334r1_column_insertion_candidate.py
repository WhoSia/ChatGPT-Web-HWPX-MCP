from pathlib import Path

import pytest
from hwpx import HwpxDocument

from p27_tables import _save_document
from p323_advanced_tables import build_advanced_table_map
from p334r1_column_insertion import apply_bounded_column_insertion, column_insertion_contract


def _build(path: Path, *, widths=None, merged=False, prefix="T"):
    doc = HwpxDocument.new()
    table = doc.add_table(rows=3, cols=3, width=54000)
    for r in range(3):
        for c in range(3):
            table.set_cell_text(r, c, f"{prefix}-R{r+1}C{c+1}", logical=True)
    if widths:
        for r in range(3):
            for c, width in enumerate(widths):
                table.cell(r, c).set_size(width=width)
    if merged:
        table.merge_cells(0, 0, 0, 1)
        table.set_cell_text(0, 0, "HEADER", logical=True)
    doc.save_to_path(path)


def _apply(path: Path, *, direction: str):
    before = build_advanced_table_map(path)
    table_payload = before["tables"][0]
    anchor = next(c for c in table_payload["cells"] if c["row"] == 1 and c["col"] == 1)
    doc = HwpxDocument.open(str(path))
    try:
        table = doc.tables.all[0]
        receipt = apply_bounded_column_insertion(
            table,
            table_payload,
            {"op": "insert_column_native_bounded", "cell": anchor["locator"], "direction": direction, "count": 1},
        )
        _save_document(doc, path, path)
    finally:
        doc.close()
    return receipt, build_advanced_table_map(path)


def _at(table_payload, row, col):
    return next(c for c in table_payload["cells"] if c["row"] == row and c["col"] == col)


def test_contract_keeps_production_authority_closed():
    contract = column_insertion_contract()
    assert contract["status"] == "CANDIDATE_IMPLEMENTATION_COUNT1_ONLY"
    assert contract["authority"] == "NO_PRODUCTION_EDIT_AUTHORITY_YET"
    assert contract["holds"]["count_gt_1"] == "NATIVE_EVIDENCE_MISMATCH"


def test_basic_left_matches_native_count_one_geometry(tmp_path: Path):
    path = tmp_path / "left.hwpx"
    _build(path, prefix="A")
    receipt, after = _apply(path, direction="LEFT")
    table = after["tables"][0]
    assert (table["rows"], table["cols"]) == (3, 4)
    assert receipt["inserted_width"] == 18000
    assert receipt["rows_with_new_cell"] == 3
    assert receipt["rows_with_crossing_span_extension"] == 0
    assert _at(table, 1, 1)["text"] == ""
    assert _at(table, 1, 2)["text"] == "A-R2C2"
    assert [c["width"] for c in table["cells"] if c["row"] == 1] == [18000, 18000, 18000, 18000]


def test_nonuniform_right_clones_anchor_column_width(tmp_path: Path):
    path = tmp_path / "right.hwpx"
    _build(path, widths=[12000, 18000, 24000], prefix="W")
    receipt, after = _apply(path, direction="RIGHT")
    table = after["tables"][0]
    assert receipt["inserted_width"] == 18000
    assert _at(table, 1, 2)["text"] == ""
    assert _at(table, 1, 3)["text"] == "W-R2C3"
    assert [c["width"] for c in table["cells"] if c["row"] == 1] == [12000, 18000, 18000, 24000]


def test_crossing_horizontal_merge_extends_span_without_rewriting_cell_width(tmp_path: Path):
    path = tmp_path / "merged.hwpx"
    _build(path, merged=True, prefix="M")
    receipt, after = _apply(path, direction="LEFT")
    table = after["tables"][0]
    header = _at(table, 0, 0)
    assert header["col_span"] == 3
    assert header["width"] == 36000
    assert receipt["rows_with_crossing_span_extension"] == 1
    assert receipt["rows_with_new_cell"] == 2


def test_count_gt_one_remains_closed(tmp_path: Path):
    path = tmp_path / "count2.hwpx"
    _build(path)
    before = build_advanced_table_map(path)
    table_payload = before["tables"][0]
    anchor = next(c for c in table_payload["cells"] if c["row"] == 1 and c["col"] == 1)
    doc = HwpxDocument.open(str(path))
    try:
        with pytest.raises(ValueError, match="exactly count=1"):
            apply_bounded_column_insertion(
                doc.tables.all[0],
                table_payload,
                {"cell": anchor["locator"], "direction": "RIGHT", "count": 2},
            )
    finally:
        doc.close()
