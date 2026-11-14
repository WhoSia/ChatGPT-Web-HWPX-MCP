"""P4.27 R3: atomic, two-layer preservation gate for bounded native table edits.

P3.42 already certifies package-part mutation. R3 additionally checks
within-section table semantics before committing an existing HWPX.
Only one explicit cell-text or page-break mutation is admitted initially.
"""
from __future__ import annotations

import copy
import hashlib
import os
import shutil
import tempfile
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import Callable

from hwpx_mcp.custody.p342_mutation_footprint import (
    build_mutation_footprint,
    enforce_preservation_grade,
)
from hwpx_mcp.document.p323_advanced_tables import (
    apply_advanced_table_edits_atomic,
    build_advanced_table_map,
)

SCHEMA = "chatgpt-web-hwpx-mcp/p4.27/structured-edit-preservation/v1"
ADMITTED = ("set_cell_text", "set_table_page_break")
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _body_paragraph_signatures(path: Path) -> tuple[list[tuple], list[tuple]]:
    """Compare ordinary body paragraphs and the XML surrounding table controls."""
    ordinary: list[tuple] = []
    anchors: list[tuple] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not (name.startswith("Contents/section") and name.endswith(".xml")):
                continue
            root = ET.fromstring(archive.read(name))
            for index, paragraph in enumerate(list(root)):
                if paragraph.tag != HP + "p":
                    continue
                tables = paragraph.findall(".//" + HP + "tbl")
                if tables:
                    # Keep the table's position and tail. Its contents are checked
                    # separately by the table map and can change during an edit.
                    for table in tables:
                        tail = table.tail
                        table.clear()
                        table.tail = tail
                    signature = ET.canonicalize(ET.tostring(paragraph, encoding="unicode"))
                    anchors.append((name, index, signature))
                    continue
                signature = ET.canonicalize(ET.tostring(paragraph, encoding="unicode"))
                ordinary.append((name, index, signature))
    return ordinary, anchors


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
    if name == "set_cell_text":
        if type(op.get("text")) is not str:
            raise ValueError("R3_CELL_TEXT_MUST_BE_STRING")
        cells = [cell for cell in target["cells"] if cell["locator"] == op.get("cell")]
        if len(cells) != 1:
            raise ValueError("R3_TARGET_CELL_AMBIGUOUS_OR_MISSING")
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
    untouched_body, untouched_anchors = _body_paragraph_signatures(source)
    expected = _expected_native_delta(before["tables"], operation)
    target = next(t for t in before["tables"] if t["locator"] == operation["table"])
    expected_scope = {
        "changed_parts": sorted({str(target["section_path"]), "Contents/header.xml"}),
        "added_parts": [],
        "removed_parts": [],
        "required_changed_parts": [str(target["section_path"])],
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
        edit_receipt = apply_advanced_table_edits_atomic(
            candidate, [operation],
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
        validation = candidate_validator(candidate) if candidate_validator is not None else None
        after = build_advanced_table_map(candidate)
        semantic = _verify_semantics(before, after, expected)
        body, anchors = _body_paragraph_signatures(candidate)
        if body != untouched_body:
            raise ValueError("R3_UNDECLARED_BODY_PARAGRAPH_DRIFT")
        if anchors != untouched_anchors:
            raise ValueError("R3_UNDECLARED_TABLE_ANCHOR_PARAGRAPH_DRIFT")
        certificate = build_mutation_footprint(source, candidate, expected_scope)
        enforcement = enforce_preservation_grade(certificate, "TARGETED_PARTS_ONLY")
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
        "mutation_footprint": certificate,
        "preservation_enforcement": enforcement,
        "committed_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "authority": "NATIVE_STRUCTURAL_AND_PACKAGE_PART_GATES_NOT_VISUAL",
    }
