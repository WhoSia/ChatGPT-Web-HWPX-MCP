"""P4.27 R3: atomic, two-layer preservation gate for bounded native table edits.

P3.42 already certifies package-part mutation. R3 additionally checks
within-section table semantics before committing an existing HWPX.
Only one explicit cell-text or page-break mutation is admitted initially.
"""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import Callable

from hwpx import HwpxDocument
from hwpx.tools.table_navigation import _collect_document_tables
from lxml import etree

from hwpx_mcp.custody.p342_mutation_footprint import (
    build_mutation_footprint,
    enforce_preservation_grade,
)
from hwpx_mcp.document.p25_controls import TEXT_NESTED_SPECIALS
from hwpx_mcp.document.p27_tables import _cell_text, _save_document
from hwpx_mcp.document.p427_cell_phrase import (
    replace_phrase_in_plain_node,
    validate_phrase_operation,
)
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic,
    build_advanced_table_map,
)

SCHEMA = "chatgpt-web-hwpx-mcp/p4.27/structured-edit-preservation/v1"
ADMITTED = ("set_cell_text", "set_table_page_break", "replace_cell_phrase")
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _xml_outside_tables(element: ET.Element) -> str:
    # Retain each table's position and tail while leaving table contents
    # to the native table comparison. Do not modify the source XML tree.
    element = copy.deepcopy(element)
    for table in element.iter(HP + "tbl"):
        tail = table.tail
        table.clear()
        table.tail = tail
    return ET.canonicalize(ET.tostring(element, encoding="unicode"))


def _paragraph_signatures(path: Path) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Capture body paragraphs and paragraphs containing nested table controls."""
    ordinary: list[tuple] = []
    anchors: list[tuple] = []
    nested_anchors: list[tuple] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not (name.startswith("Contents/section") and name.endswith(".xml")):
                continue
            root = ET.fromstring(archive.read(name))
            for index, paragraph in enumerate(root):
                if paragraph.tag != HP + "p":
                    continue
                signatures = anchors if paragraph.find(".//" + HP + "tbl") is not None else ordinary
                signatures.append((name, index, _xml_outside_tables(paragraph)))
            for cell_index, cell in enumerate(root.iter(HP + "tc")):
                for index, paragraph in enumerate(cell.findall(f"{HP}subList/{HP}p")):
                    if paragraph.find(f"{HP}run/{HP}tbl") is not None:
                        nested_anchors.append((name, cell_index, index, _xml_outside_tables(paragraph)))
    return ordinary, anchors, nested_anchors


_REPLACEABLE_TEXT_CONTROLS = {HP + name for name in TEXT_NESTED_SPECIALS | {"tab"}}


def _cell_inline_objects(cell: ET.Element) -> tuple:
    """Keep non-text content in document order, including text in embedded objects."""
    objects = []
    for paragraph in cell.findall(f"{HP}subList/{HP}p"):
        for run in paragraph.findall(HP + "run"):
            for child in run:
                run_format = tuple(sorted(run.attrib.items()))
                if child.tag == HP + "t":
                    objects.extend(
                        (run_format, _xml_outside_tables(control))
                        for control in child if control.tag not in _REPLACEABLE_TEXT_CONTROLS
                    )
                else:
                    objects.append((run_format, _xml_outside_tables(child)))
    return tuple(objects)


def _target_cell_format(cell: ET.Element) -> dict:
    """Preserve existing cell geometry and the style inherited by replacement text."""
    cell_attributes = dict(cell.attrib)
    cell_attributes.pop("dirty", None)
    formatting = {
        "cell": cell_attributes,
        "geometry": tuple(
            _xml_outside_tables(child) for child in cell if child.tag != HP + "subList"
        ),
    }
    sublist = cell.find(HP + "subList")
    if sublist is not None:
        sublist_attributes = dict(sublist.attrib)
        # The native writer reflows a nonempty replacement in a squeezed cell.
        sublist_attributes.pop("lineWrap", None)
        formatting["sublist"] = sublist_attributes
        formatting["line_wrap"] = sublist.get("lineWrap")
        paragraph = sublist.find(HP + "p")
        if paragraph is not None:
            formatting["paragraph"] = dict(paragraph.attrib)
            run = paragraph.find(HP + "run")
            if run is not None:
                formatting["first_run"] = dict(run.attrib)
    return formatting


def _verify_target_cell_format(before: dict, after: dict, replacement: str) -> None:
    for field, value in before.items():
        if field == "line_wrap" and (value or "").upper() == "SQUEEZE" and replacement:
            if after.get(field) in (value, "BREAK"):
                continue
        if field not in after or after[field] != value:
            raise ValueError(f"R3_UNDECLARED_TARGET_CELL_FORMAT_DRIFT:{field}")


def _cell_signatures(path: Path, edited_cell: tuple[int, int, int] | None) -> tuple[dict, tuple | None, dict | None]:
    """Capture native grid anchors and the target cell's non-text content."""
    document = HwpxDocument.open(str(path))
    try:
        untouched = {}
        target_objects = None
        target_format = None
        for table_index, reference in enumerate(_collect_document_tables(document)):
            for position in reference.table.iter_grid():
                if not position.is_anchor:
                    continue
                identity = (table_index, *position.anchor)
                element = ET.fromstring(etree.tostring(position.cell.element, with_tail=False))
                if identity == edited_cell:
                    target_objects = _cell_inline_objects(element)
                    target_format = _target_cell_format(element)
                else:
                    untouched[identity] = _xml_outside_tables(element)
        return untouched, target_objects, target_format
    finally:
        document.close()


def _cell_phrase(path: Path, identity: tuple[int, int, int], operation: dict | None = None):
    """Read or update one cell through the same native traversal as its locator."""
    table_index, row, col = identity
    document = HwpxDocument.open(str(path))
    try:
        table = _collect_document_tables(document)[table_index].table
        cell = table.cell(row, col)
        if operation is not None:
            if next(cell.element.iter(HP + "tbl"), None) is not None:
                raise ValueError("NESTED_TABLE_HOST_CELL_TEXT_EDIT_DEFERRED")
            paragraphs = cell.paragraphs
            index = operation["paragraph_index"]
            if index >= len(paragraphs):
                raise ValueError("P427_CELL_PARAGRAPH_INDEX_INVALID")
            paragraph = paragraphs[index]
            replace_phrase_in_plain_node(
                paragraph.element, operation["old_text"], operation["new_text"],
            )
            table.mark_dirty()
        element = ET.fromstring(etree.tostring(cell.element, with_tail=False))
        signature = _xml_outside_tables(element)
        text = _cell_text(cell)
        if operation is not None:
            _save_document(document, path, path)
        return text, signature
    finally:
        document.close()


def _semantic_table(table: dict) -> dict:
    # Exclude volatile human descriptions (such as preceding paragraph text)
    # and revision-bound locator hashes. Preserve all actual table-cell fields.
    return {
        "section_path": table["section_path"],
        "rows": table["rows"],
        "cols": table["cols"],
        "attributes": table["attributes"],
        "repeat_header": table["repeat_header"],
        "page_break": table["page_break"],
        "cells": table["cells"],
        "row_geometry": table["row_geometry"],
    }


def _expected_native_delta(before: list[dict], op: dict) -> list[dict]:
    expected = copy.deepcopy(before)
    target_indices = [i for i, table in enumerate(expected)
                      if table["locator"] == op.get("table")]
    if len(target_indices) != 1:
        raise ValueError("R3_TARGET_TABLE_AMBIGUOUS_OR_MISSING")
    target = expected[target_indices[0]]
    name = op["op"]
    if name in {"set_cell_text", "replace_cell_phrase"}:
        if name == "replace_cell_phrase":
            validate_phrase_operation(op)
        elif type(op.get("text")) is not str:
            raise ValueError("R3_CELL_TEXT_MUST_BE_STRING")
        cells = [cell for cell in target["cells"] if cell["locator"] == op.get("cell")]
        if len(cells) != 1:
            raise ValueError("R3_TARGET_CELL_AMBIGUOUS_OR_MISSING")
        if name == "set_cell_text":
            cells[0]["text"] = op["text"]
    elif name == "set_table_page_break":
        mode = str(op.get("mode", "")).upper()
        if mode not in {"CELL", "TABLE", "NONE"}:
            raise ValueError("R3_PAGE_BREAK_MODE_INVALID")
        target["page_break"] = mode
        target["attributes"]["pageBreak"] = mode
    else:
        raise ValueError("R3_EDIT_OPERATION_NOT_ADMITTED")
    return expected


def _verify_semantics(before: dict, after: dict, expected: list[dict]) -> dict:
    original = before["tables"]
    current = after["tables"]
    if len(current) != len(original):
        raise ValueError("R3_UNEXPECTED_TABLE_COUNT_CHANGE")
    if len(current) != len(expected):
        raise ValueError("R3_UNEXPECTED_TABLE_COUNT_CHANGE")
    unexpected: list[int] = []
    for index, (old, now, desired) in enumerate(zip(original, current, expected)):
        # A table reordering is not a safe targeted edit.
        if (old["locator"] != now["locator"]
                or old["section_path"] != now["section_path"]):
            unexpected.append(index)
        elif _semantic_table(now) != _semantic_table(desired):
            unexpected.append(index)
    if unexpected:
        raise ValueError(f"R3_UNDECLARED_TABLE_SEMANTIC_DRIFT:{unexpected}")
    if all(_semantic_table(o) == _semantic_table(n)
           for o, n in zip(original, current)):
        raise ValueError("R3_TARGET_EDIT_NOT_OBSERVED")
    return {
        "tables_compared": len(current),
        "unapproved_table_changes": 0,
        "target_edit_observed": True,
        "authority": "NATIVE_TABLE_SEMANTIC_MAP_NOT_HANCOM_RENDER",
    }


def apply_bounded_table_edit_with_preservation_atomic(
    path: Path,
    operation: dict,
    *,
    expected_revision: int,
    current_revision: int,
    candidate_validator: Callable[[Path], dict | None] | None = None,
) -> dict:
    """Edit a staged HWPX; commit only after package and cell-level gates pass.

    candidate_validator is an optional post-edit inspection hook. If it raises
    or alters undeclared parts/tables, the original file is not committed.
    """
    source = Path(path)
    if expected_revision != current_revision:
        raise ValueError("Stale revision")
    if not isinstance(operation, dict) or operation.get("op") not in ADMITTED:
        raise ValueError("R3_EDIT_OPERATION_NOT_ADMITTED")
    before = build_advanced_table_map(source)
    untouched_body, untouched_anchors, untouched_nested_anchors = _paragraph_signatures(source)
    expected = _expected_native_delta(before["tables"], operation)
    target = next(t for t in before["tables"] if t["locator"] == operation["table"])
    edited_cell = None
    if operation["op"] in {"set_cell_text", "replace_cell_phrase"}:
        cell = next(c for c in target["cells"] if c["locator"] == operation["cell"])
        edited_cell = (target["table_index"], cell["row"], cell["col"])
    untouched_cells, target_objects, target_format = _cell_signatures(source, edited_cell)
    expected_scope = {
        "changed_parts": [target["section_path"]],
        "added_parts": [],
        "removed_parts": [],
        "required_changed_parts": [target["section_path"]],
        "label": "P4.27_SINGLE_NATIVE_TABLE_EDIT",
    }

    fd, name = tempfile.mkstemp(
        prefix=source.stem + ".p427-preserved-", suffix=".hwpx",
        dir=str(source.parent),
    )
    os.close(fd)
    candidate = Path(name)
    try:
        shutil.copy2(source, candidate)
        phrase_signature = None
        if operation["op"] == "replace_cell_phrase":
            text, phrase_signature = _cell_phrase(candidate, edited_cell, operation)
            expected_cell = next(c for c in expected[target["table_index"]]["cells"]
                                 if c["locator"] == operation["cell"])
            expected_cell["text"] = text
            edit_receipt = {"operation_count": 1, "paragraph_index": operation["paragraph_index"]}
        else:
            edit_receipt = apply_advanced_table_edits_atomic(
                candidate, [operation],
                expected_revision=expected_revision,
                current_revision=current_revision,
            )
        validation = candidate_validator(candidate) if candidate_validator is not None else None
        after = build_advanced_table_map(candidate)
        semantic = _verify_semantics(before, after, expected)
        body, anchors, nested_anchors = _paragraph_signatures(candidate)
        if body != untouched_body:
            raise ValueError("R3_UNDECLARED_BODY_PARAGRAPH_DRIFT")
        if anchors != untouched_anchors:
            raise ValueError("R3_UNDECLARED_TABLE_ANCHOR_PARAGRAPH_DRIFT")
        if nested_anchors != untouched_nested_anchors:
            raise ValueError("R3_UNDECLARED_NESTED_TABLE_ANCHOR_DRIFT")
        cells, edited_objects, edited_format = _cell_signatures(candidate, edited_cell)
        if edited_cell is not None and (target_objects is None or edited_objects != target_objects):
            raise ValueError("R3_UNDECLARED_TARGET_CELL_OBJECT_DRIFT")
        if phrase_signature is not None:
            if _cell_phrase(candidate, edited_cell)[1] != phrase_signature:
                raise ValueError("P427_UNDECLARED_PHRASE_CELL_DRIFT")
        elif target_format is not None and edited_format is not None:
            _verify_target_cell_format(target_format, edited_format, operation["text"])
        if cells != untouched_cells:
            raise ValueError("R3_UNDECLARED_CELL_XML_DRIFT")
        certificate = build_mutation_footprint(source, candidate, expected_scope)
        enforcement = enforce_preservation_grade(certificate, "TARGETED_PARTS_ONLY")
        candidate_sha256 = certificate["after"]["package_sha256"]
        if isinstance(validation, dict) and "sha256" in validation:
            if validation["sha256"] != candidate_sha256:
                raise ValueError("R3_PACKAGE_VALIDATION_SHA256_MISMATCH")
        os.replace(candidate, source)
    except Exception:
        candidate.unlink(missing_ok=True)
        raise

    return {
        "schema": SCHEMA,
        "operation": operation["op"],
        "edit_receipt": edit_receipt,
        "semantic_preservation": semantic,
        "package_validation": validation,
        "unrelated_body_paragraphs_verified": len(untouched_body),
        "table_anchor_paragraphs_verified": len(untouched_anchors),
        "nested_table_anchor_paragraphs_verified": len(untouched_nested_anchors),
        "unrelated_cells_verified": len(untouched_cells),
        "target_cell_inline_objects_verified": len(target_objects or ()),
        "mutation_footprint": certificate,
        "preservation_enforcement": enforcement,
        "committed_sha256": candidate_sha256,
        "authority": "NATIVE_STRUCTURAL_AND_PACKAGE_PART_GATES_NOT_VISUAL",
    }
