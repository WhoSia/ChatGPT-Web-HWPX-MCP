from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from lxml import etree
from hwpx import HwpxDocument

from p2_document import build_document_map
from p27_tables import _save_document


SETUP_SCHEMA = "chatgpt-web-hwpx-mcp/document-setup/p3.18/v1"
HP_URI = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _section_names(archive: zipfile.ZipFile) -> list[str]:
    names = [
        name for name in archive.namelist()
        if name.startswith("Contents/section") and name.endswith(".xml")
    ]

    def key(name: str) -> tuple[int, str]:
        tail = name.rsplit("section", 1)[-1].split(".xml", 1)[0]
        try:
            return int(tail), name
        except ValueError:
            return 10**9, name

    return sorted(names, key=key)


def _story_payload(node: etree._Element, kind: str) -> dict:
    page_numbers = []
    for child in node.iter():
        local = _local(child.tag)
        if local in {"autoNum", "newNum"}:
            page_numbers.append({
                "tag": local,
                "attrs": dict(sorted(child.attrib.items())),
            })
    text = "".join(
        child.text or ""
        for child in node.iter()
        if _local(child.tag) == "t"
    )
    return {
        "kind": kind,
        "id": node.get("id"),
        "apply_page_type": node.get("applyPageType", "BOTH"),
        "text": text,
        "page_number_fields": page_numbers,
    }


def _section_payload(root: etree._Element, section_index: int, name: str) -> dict:
    sec_pr = next((node for node in root.iter() if _local(node.tag) == "secPr"), None)
    if sec_pr is None:
        raise ValueError(f"{name} has no secPr")

    page_pr = next((node for node in sec_pr.iter() if _local(node.tag) == "pagePr"), None)
    if page_pr is None:
        raise ValueError(f"{name} has no pagePr")

    margin = next(
        (
            node for node in page_pr.iter()
            if node is not page_pr and _local(node.tag) in {"margin", "pageMargin"}
        ),
        None,
    )
    if margin is None:
        raise ValueError(f"{name} has no page margin")

    start_num = next((node for node in sec_pr.iter() if _local(node.tag) == "startNum"), None)

    column_defs = []
    for node in root.iter():
        if _local(node.tag) != "colPr":
            continue
        columns = []
        for child in node:
            if _local(child.tag) == "colSz":
                columns.append(dict(sorted(child.attrib.items())))
        column_defs.append({
            "attrs": dict(sorted(node.attrib.items())),
            "columns": columns,
        })

    stories = []
    seen = set()
    for node in root.iter():
        local = _local(node.tag)
        if local not in {"header", "footer"}:
            continue
        payload = _story_payload(node, local)
        identity = (
            payload["kind"],
            payload["id"],
            payload["apply_page_type"],
            payload["text"],
            json.dumps(payload["page_number_fields"], sort_keys=True),
        )
        if identity in seen:
            continue
        seen.add(identity)
        stories.append(payload)

    restarts = []
    for node in root.iter():
        if _local(node.tag) == "newNum":
            restarts.append(dict(sorted(node.attrib.items())))

    return {
        "section_index": section_index,
        "section": name,
        "page": {
            "width": int(page_pr.get("width", "0") or 0),
            "height": int(page_pr.get("height", "0") or 0),
            "orientation": page_pr.get("landscape"),
            "gutter_type": page_pr.get("gutterType"),
        },
        "margins": {
            key: int(margin.get(key, "0") or 0)
            for key in ("left", "right", "top", "bottom", "header", "footer", "gutter")
        },
        "start_numbering": {} if start_num is None else dict(sorted(start_num.attrib.items())),
        "column_definitions": column_defs,
        "stories": stories,
        "number_restarts": restarts,
    }


def build_document_setup_map(path: Path) -> dict:
    path = Path(path)
    sections = []
    with zipfile.ZipFile(path, "r") as archive:
        for section_index, name in enumerate(_section_names(archive)):
            root = etree.fromstring(archive.read(name))
            sections.append(_section_payload(root, section_index, name))

    result = {
        "schema": SETUP_SCHEMA,
        "section_count": len(sections),
        "sections": sections,
    }
    result["document_setup_sha256"] = _sha(sections)
    return result


def _section_index(value: Any, count: int, *, allow_last: bool = False) -> int:
    index = int(value)
    high = count if allow_last else count - 1
    if index < 0 or index > high:
        raise ValueError(f"section_index {index} is outside admitted range")
    return index


def _paragraph_target(document: HwpxDocument, candidate: Path, locator: Any):
    wanted = str(locator or "")
    mapped = build_document_map(candidate)
    target = next((p for p in mapped["paragraphs"] if p["locator"] == wanted), None)
    if target is None:
        raise ValueError(f"Unknown paragraph locator: {wanted}")
    section = document.sections[int(target["section_index"])]
    paragraph_index = int(target["paragraph_index"])
    paragraphs = section.paragraphs
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        raise ValueError("paragraph locator no longer resolves")
    return paragraphs[paragraph_index]


def _apply_one(document: HwpxDocument, candidate: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    section_count = len(document.sections)

    if name == "set_page_setup":
        section_index = _section_index(op.get("section_index", 0), section_count)
        kwargs = {
            key: op[key]
            for key in (
                "paper_size", "width_mm", "height_mm", "orientation", "margins_mm",
                "margin_left_mm", "margin_right_mm", "margin_top_mm", "margin_bottom_mm",
                "header_margin_mm", "footer_margin_mm", "gutter_mm", "columns",
                "column_gap_mm",
            )
            if key in op
        }
        setup = document.page.setup(section=section_index, **kwargs)
        return {"op": name, "section_index": section_index, "result": repr(setup)}

    if name == "set_page_size":
        section_index = _section_index(op.get("section_index", 0), section_count)
        kwargs = {
            key: op[key]
            for key in ("width", "height", "orientation", "gutter_type")
            if key in op
        }
        if not kwargs:
            raise ValueError("set_page_size requires at least one size/orientation field")
        document.page.set_size(section=section_index, **kwargs)
        return {"op": name, "section_index": section_index, "values": kwargs}

    if name == "set_page_margin":
        section_index = _section_index(op.get("section_index", 0), section_count)
        kwargs = {
            key: int(op[key])
            for key in ("left", "right", "top", "bottom", "header", "footer", "gutter")
            if key in op
        }
        if not kwargs:
            raise ValueError("set_page_margin requires at least one margin field")
        document.page.set_margins(section=section_index, **kwargs)
        return {"op": name, "section_index": section_index, "values": kwargs}

    if name == "set_columns":
        section_index = _section_index(op.get("section_index", 0), section_count)
        count = int(op.get("count", op.get("col_count", 2)))
        if count < 1 or count > 255:
            raise ValueError("column count must be 1..255")
        kwargs = {
            "col_count": count,
            "section": section_index,
            "col_type": str(op.get("col_type", "NEWSPAPER")),
            "layout": str(op.get("layout", "LEFT")),
            "same_size": bool(op.get("same_size", True)),
            "same_gap": int(op.get("same_gap", 1200)),
        }
        for key in ("column_widths", "separator_type", "separator_width", "separator_color"):
            if key in op:
                kwargs[key] = op[key]
        control = document.page.set_columns(**kwargs)
        return {
            "op": name,
            "section_index": section_index,
            "count": count,
            "control_tag": _local(control.element.tag),
        }

    if name in {"set_header", "set_footer"}:
        section_index = _section_index(op.get("section_index", 0), section_count)
        page_type = str(op.get("page_type", "BOTH")).upper()
        if page_type not in {"BOTH", "EVEN", "ODD"}:
            raise ValueError("page_type must be BOTH, EVEN, or ODD")
        kwargs: dict[str, Any] = {"section": section_index, "page_type": page_type}
        if "text" in op:
            kwargs["text"] = str(op.get("text", ""))
        elif "content" in op:
            if not isinstance(op["content"], list):
                raise ValueError("header/footer content must be a list")
            kwargs["content"] = op["content"]
        else:
            raise ValueError(f"{name} requires text or content")
        story = (
            document.page.set_header(**kwargs)
            if name == "set_header"
            else document.page.set_footer(**kwargs)
        )
        return {
            "op": name,
            "section_index": section_index,
            "page_type": story.apply_page_type,
            "story_id": story.id,
        }

    if name in {"remove_header", "remove_footer"}:
        section_index = _section_index(op.get("section_index", 0), section_count)
        page_type = str(op.get("page_type", "BOTH")).upper()
        if name == "remove_header":
            document.page.remove_header(section=section_index, page_type=page_type)
        else:
            document.page.remove_footer(section=section_index, page_type=page_type)
        return {"op": name, "section_index": section_index, "page_type": page_type}

    if name == "set_page_number":
        section_index = _section_index(op.get("section_index", 0), section_count)
        kwargs = {
            "section": section_index,
            "target": str(op.get("target", "footer")),
            "page_type": str(op.get("page_type", "BOTH")).upper(),
            "format": str(op.get("format", "page")),
            "align": str(op.get("align", "CENTER")).upper(),
            "position": str(op.get("position", "BOTTOM_CENTER")).upper(),
            "prefix": str(op.get("prefix", "")),
            "suffix": str(op.get("suffix", "")),
        }
        if op.get("format_type") is not None:
            kwargs["format_type"] = str(op["format_type"])
        story = document.page.set_page_number(**kwargs)
        return {
            "op": name,
            "section_index": section_index,
            "target": kwargs["target"],
            "page_type": story.apply_page_type,
            "story_id": story.id,
        }

    if name == "restart_page_number":
        paragraph = _paragraph_target(document, candidate, op.get("paragraph"))
        number = int(op.get("number", 1))
        if number < 1:
            raise ValueError("page restart number must be positive")
        control = document.page.restart_page_number(paragraph, number=number, kind="PAGE")
        return {"op": name, "number": number, "control_tag": _local(control.element.tag)}

    if name == "set_section_start_numbering":
        section_index = _section_index(op.get("section_index", 0), section_count)
        section = document.sections[section_index]
        kwargs = {}
        for key in ("page_starts_on", "page", "picture", "table", "equation"):
            if key in op:
                kwargs[key] = op[key]
        if not kwargs:
            raise ValueError("set_section_start_numbering requires at least one field")
        section.properties.set_start_numbering(**kwargs)
        return {"op": name, "section_index": section_index, "values": kwargs}

    if name == "add_section":
        after = op.get("after")
        if after is None:
            section = document.add_section()
        else:
            after_index = _section_index(after, section_count)
            section = document.add_section(after=after_index)
        text = op.get("text")
        if text is not None:
            section.add_paragraph(str(text), inherit_style=False)
        return {
            "op": name,
            "section_count_after": len(document.sections),
            "part_name": section.part_name,
        }

    if name == "remove_section":
        if section_count <= 1:
            raise ValueError("cannot remove the last document section")
        section_index = _section_index(op.get("section_index", section_count - 1), section_count)
        document.remove_section(section_index)
        return {
            "op": name,
            "removed_section_index": section_index,
            "section_count_after": len(document.sections),
        }

    raise ValueError(f"Unsupported document-setup operation: {name}")


def apply_document_setup_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 64:
        raise ValueError("Document-setup transaction requires 1..64 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each document-setup operation must be an object")

    before = build_document_setup_map(path)

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p318-setup-",
        suffix=".hwpx",
        dir=str(path.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts: list[dict] = []
    validation = None

    try:
        document = HwpxDocument.open(str(candidate))
        try:
            for op in operations:
                receipts.append(_apply_one(document, candidate, op))
            for section in document.sections:
                section.remove_layout_caches()
            _save_document(document, candidate, candidate)
        finally:
            document.close()

        after = build_document_setup_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "before": {
            "section_count": before["section_count"],
            "document_setup_sha256": before["document_setup_sha256"],
        },
        "after": {
            "section_count": after["section_count"],
            "document_setup_sha256": after["document_setup_sha256"],
        },
        "document_setup_changed": (
            before["document_setup_sha256"] != after["document_setup_sha256"]
        ),
        "section_count_changed": before["section_count"] != after["section_count"],
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_DOCUMENT_SETUP_AUTHORITY",
    }
