from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from hwpx import HwpxDocument

from p2_document import _local, _paragraph_nodes, build_document_map

HEADER_NAME = "Contents/header.xml"

RUN_FORMAT_KEYS = {
    "bold", "italic", "underline", "color", "font", "size", "highlight",
    "strike", "underline_shape", "underline_color", "strike_shape", "ratio",
    "letter_spacing", "shadow", "script", "outline", "emboss", "engrave",
}
PARAGRAPH_FORMAT_KEYS = {
    "alignment", "line_spacing_percent", "indent_left_mm", "indent_right_mm",
    "first_line_indent_mm", "spacing_before_pt", "spacing_after_pt",
    "outline_level", "keep_with_next", "keep_lines", "page_break_before",
    "column_break", "bottom_border", "border_color", "border_width",
    "tab_stops", "auto_tab_left", "auto_tab_right",
}


def _attr_key(key: str) -> str:
    return _local(key)


def _element_snapshot(node: ElementTree.Element) -> dict:
    return {
        "tag": _local(node.tag),
        "attrs": {k: node.attrib[k] for k in sorted(node.attrib, key=_attr_key)},
        "children": [_element_snapshot(child) for child in list(node)],
    }


def _child_by_local(node: ElementTree.Element, name: str) -> ElementTree.Element | None:
    for child in list(node):
        if _local(child.tag) == name:
            return child
    return None


def _property_tables(header_root: ElementTree.Element) -> dict:
    char_props: dict[str, dict] = {}
    para_props: dict[str, dict] = {}
    styles: dict[str, dict] = {}
    for node in header_root.iter():
        name = _local(node.tag)
        ident = node.attrib.get("id")
        if not ident:
            continue
        if name == "charPr":
            char_props[str(ident)] = _element_snapshot(node)
        elif name == "paraPr":
            para_props[str(ident)] = _element_snapshot(node)
        elif name == "style":
            styles[str(ident)] = _element_snapshot(node)
    return {"char": char_props, "para": para_props, "style": styles}


def _char_summary(style_id: str | None, tables: dict) -> dict | None:
    if style_id is None:
        return None
    node = tables["char"].get(str(style_id))
    if node is None:
        return {"id": str(style_id), "resolved": False}
    attrs = node["attrs"]
    children = {child["tag"]: child for child in node["children"]}
    underline = children.get("underline", {}).get("attrs", {})
    strike = children.get("strikeout", {}).get("attrs", {})
    font_ref = children.get("fontRef", {}).get("attrs", {})
    height = attrs.get("height")
    try:
        size_pt = int(height) / 100 if height is not None else None
    except ValueError:
        size_pt = None
    return {
        "id": str(style_id),
        "resolved": True,
        "size_pt": size_pt,
        "text_color": attrs.get("textColor"),
        "shade_color": attrs.get("shadeColor"),
        "bold": "bold" in children,
        "italic": "italic" in children,
        "underline": bool(underline) and underline.get("type", "").upper() != "NONE",
        "underline_type": underline.get("type"),
        "underline_color": underline.get("color"),
        "strike": bool(strike) and strike.get("shape", "").upper() != "NONE",
        "strike_shape": strike.get("shape"),
        "font_ref": font_ref or None,
        "script": "sup" if "supscript" in children else ("sub" if "subscript" in children else None),
        "outline": children.get("outline", {}).get("attrs", {}).get("type"),
        "emboss": "emboss" in children,
        "engrave": "engrave" in children,
    }


def _para_summary(style_id: str | None, tables: dict) -> dict | None:
    if style_id is None:
        return None
    node = tables["para"].get(str(style_id))
    if node is None:
        return {"id": str(style_id), "resolved": False}
    children = {child["tag"]: child for child in node["children"]}
    return {
        "id": str(style_id),
        "resolved": True,
        "attributes": node["attrs"],
        "alignment": children.get("align", {}).get("attrs"),
        "margin": children.get("margin", {}).get("attrs"),
        "line_spacing": children.get("lineSpacing", {}).get("attrs"),
        "break_setting": children.get("breakSetting", {}).get("attrs"),
        "heading": children.get("heading", {}).get("attrs"),
        "border": children.get("border", {}).get("attrs"),
    }


def _run_text(run: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in run.iter():
        if _local(node.tag) == "t" and node.text:
            parts.append(node.text)
    return "".join(parts)


def _range_safe_run(run: ElementTree.Element) -> bool:
    """Whether a run can be split without guessing about inline controls."""
    children = list(run)
    if len(children) != 1 or _local(children[0].tag) != "t":
        return False
    text_node = children[0]
    return len(list(text_node)) == 0 and not (text_node.tail or "")


def build_formatting_map(path: Path) -> dict:
    document_map = build_document_map(path)
    paragraph_by_position = {
        (item["section"], int(item["paragraph_index"])): item
        for item in document_map["paragraphs"]
    }
    paragraphs: list[dict] = []
    with zipfile.ZipFile(path, "r") as archive:
        header_root = ElementTree.fromstring(archive.read(HEADER_NAME))
        tables = _property_tables(header_root)
        ref_list = next((node for node in header_root.iter() if _local(node.tag) == "refList"), None)
        ref_snapshot = _element_snapshot(ref_list) if ref_list is not None else None

        for section in document_map["sections"]:
            section_name = section["section"]
            root = ElementTree.fromstring(archive.read(section_name))
            para_index = 0
            for node in root.iter():
                if _local(node.tag) != "p":
                    continue
                mapped = paragraph_by_position[(section_name, para_index)]
                para_pr = node.attrib.get("paraPrIDRef")
                style_ref = node.attrib.get("styleIDRef")
                runs: list[dict] = []
                direct_run_index = 0
                direct_offset = 0
                for child in list(node):
                    if _local(child.tag) != "run":
                        continue
                    char_ref = child.attrib.get("charPrIDRef")
                    run_text = _run_text(child)
                    start = direct_offset
                    end = start + len(run_text)
                    runs.append({
                        "run_index": direct_run_index,
                        "char_pr_id_ref": char_ref,
                        "text": run_text,
                        "start": start,
                        "end": end,
                        "range_safe": _range_safe_run(child),
                        "style": _char_summary(char_ref, tables),
                    })
                    direct_offset = end
                    direct_run_index += 1
                direct_text = "".join(run["text"] for run in runs)
                paragraphs.append({
                    "locator": mapped["locator"],
                    "section": section_name,
                    "section_index": mapped["section_index"],
                    "paragraph_index": para_index,
                    "body_paragraph_index": mapped.get("body_paragraph_index"),
                    "body_global_index": mapped.get("body_global_index"),
                    "container": mapped.get("container"),
                    "para_pr_id_ref": para_pr,
                    "style_id_ref": style_ref,
                    "page_break": node.attrib.get("pageBreak"),
                    "column_break": node.attrib.get("columnBreak"),
                    "paragraph_property": _para_summary(para_pr, tables),
                    "direct_text": direct_text,
                    "direct_text_length": len(direct_text),
                    "runs": runs,
                })
                para_index += 1

    digest_seed = {
        "ref_list": ref_snapshot,
        "paragraphs": [
            {
                "locator": item["locator"],
                "para_pr_id_ref": item["para_pr_id_ref"],
                "style_id_ref": item["style_id_ref"],
                "page_break": item["page_break"],
                "column_break": item["column_break"],
                "runs": [
                    {
                        "start": run["start"],
                        "end": run["end"],
                        "char_pr_id_ref": run["char_pr_id_ref"],
                    }
                    for run in item["runs"]
                ],
            }
            for item in paragraphs
        ],
    }
    formatting_sha256 = hashlib.sha256(
        json.dumps(digest_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "formatting_sha256": formatting_sha256,
        "paragraphs": paragraphs,
        "property_counts": {
            "char": len(tables["char"]),
            "para": len(tables["para"]),
            "style": len(tables["style"]),
        },
    }


def _format_paragraph_index(format_map: dict) -> dict[str, dict]:
    return {item["locator"]: item for item in format_map["paragraphs"]}


def _normalize_formatting_operations(operations: list[dict], before_format: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one formatting operation is required")
    if len(operations) > 100:
        raise ValueError("Too many formatting operations")
    index = _format_paragraph_index(before_format)
    normalized: list[dict] = []
    seen: set[tuple] = set()

    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each formatting operation must be an object")
        op = raw.get("op")
        target = raw.get("target")
        if not isinstance(target, str) or target not in index:
            raise ValueError(f"Unknown paragraph locator: {target}")
        fmt = raw.get("format")
        if not isinstance(fmt, dict) or not fmt:
            raise ValueError(f"{op} requires a non-empty format object")

        if op == "set_run_format":
            unknown = sorted(set(fmt) - RUN_FORMAT_KEYS)
            if unknown:
                raise ValueError(f"Unsupported run format keys: {', '.join(unknown)}")
            run_index = raw.get("run_index")
            if run_index is not None:
                if not isinstance(run_index, int) or run_index < 0:
                    raise ValueError("run_index must be a non-negative integer")
                if run_index >= len(index[target]["runs"]):
                    raise ValueError("run_index is outside the target paragraph")
                run_indexes = [run_index]
            else:
                run_indexes = [
                    run["run_index"] for run in index[target]["runs"] if run["text"]
                ]
                if not run_indexes:
                    raise ValueError("Target paragraph has no text run to format")
            for idx in run_indexes:
                key = (op, target, idx)
                if key in seen:
                    raise ValueError("Duplicate run-format target in one transaction")
                seen.add(key)
            normalized.append({
                "op": op,
                "target": target,
                "run_indexes": run_indexes,
                "format": dict(fmt),
            })
            continue

        if op == "set_paragraph_format":
            unknown = sorted(set(fmt) - PARAGRAPH_FORMAT_KEYS)
            if unknown:
                raise ValueError(f"Unsupported paragraph format keys: {', '.join(unknown)}")
            paragraph = index[target]
            if paragraph.get("body_global_index") is None:
                raise ValueError(
                    "P2.2 paragraph-property mutation supports direct section-body paragraphs only"
                )
            key = (op, target)
            if key in seen:
                raise ValueError("Duplicate paragraph-format target in one transaction")
            seen.add(key)
            normalized.append({
                "op": op,
                "target": target,
                "body_global_index": int(paragraph["body_global_index"]),
                "format": dict(fmt),
            })
            continue

        raise ValueError(f"Unsupported formatting operation: {op}")
    return normalized


def _style_flags(document: HwpxDocument, char_pr_id_ref: str | None) -> tuple[bool, bool, bool]:
    if char_pr_id_ref is None:
        return False, False, False
    style = document.styles.char_property(char_pr_id_ref)
    if style is None:
        return False, False, False
    children = style.child_attributes
    underline = children.get("underline")
    return (
        "bold" in children,
        "italic" in children,
        underline is not None and underline.get("type", "").upper() != "NONE",
    )


def _ensure_run_style(
    document: HwpxDocument,
    base_ref: str | None,
    fmt: dict,
) -> str:
    current_bold, current_italic, current_underline = _style_flags(document, base_ref)
    options = dict(fmt)
    options["bold"] = bool(options.get("bold", current_bold))
    options["italic"] = bool(options.get("italic", current_italic))
    options["underline"] = bool(options.get("underline", current_underline))
    if options.get("font") is not None:
        document.styles.ensure_font(str(options["font"]))
    options["base_char_pr_id"] = base_ref
    return document.styles.ensure_run(**options)


def _patch_run_style_refs(path: Path, assignments: list[dict]) -> None:
    if not assignments:
        return
    current_map = build_document_map(path)
    current_index = {item["locator"]: item for item in current_map["paragraphs"]}
    by_section: dict[str, list[dict]] = {}
    for assignment in assignments:
        target = current_index.get(assignment["target"])
        if target is None:
            raise ValueError("Formatting target locator did not survive style-table update")
        by_section.setdefault(target["section"], []).append({
            **assignment,
            "paragraph_index": int(target["paragraph_index"]),
        })

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p22-run-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target_zip:
            for info in source.infolist():
                payload = source.read(info.filename)
                section_ops = by_section.get(info.filename)
                if section_ops:
                    root = ElementTree.fromstring(payload)
                    paragraphs = _paragraph_nodes(root)
                    for assignment in section_ops:
                        paragraph = paragraphs[assignment["paragraph_index"]]
                        runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
                        idx = int(assignment["run_index"])
                        if idx >= len(runs):
                            raise ValueError("Target run disappeared during formatting transaction")
                        runs[idx].set("charPrIDRef", str(assignment["char_pr_id_ref"]))
                        for child in list(paragraph):
                            if _local(child.tag).lower() == "linesegarray":
                                paragraph.remove(child)
                    payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(info, payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def apply_formatting_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")

    before_document = build_document_map(path)
    before_format = build_formatting_map(path)
    normalized = _normalize_formatting_operations(operations, before_format)
    before_index = _format_paragraph_index(before_format)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p22-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    shutil.copy2(path, candidate)
    validation: dict | None = None
    assignments: list[dict] = []
    try:
        document = HwpxDocument.open(str(candidate))
        try:
            for op in normalized:
                if op["op"] == "set_paragraph_format":
                    document.styles.apply_paragraph_format(
                        paragraph_index=op["body_global_index"],
                        **op["format"],
                    )
                    continue

                paragraph = before_index[op["target"]]
                runs = {run["run_index"]: run for run in paragraph["runs"]}
                for run_index in op["run_indexes"]:
                    base_ref = runs[run_index]["char_pr_id_ref"]
                    new_ref = _ensure_run_style(document, base_ref, op["format"])
                    assignments.append({
                        "target": op["target"],
                        "run_index": run_index,
                        "char_pr_id_ref": new_ref,
                    })
            fd2, styled_name = tempfile.mkstemp(
                prefix=path.stem + ".p22-lib-", suffix=".hwpx", dir=str(path.parent)
            )
            os.close(fd2)
            styled_path = Path(styled_name)
            try:
                document.save_to_path(str(styled_path))
                os.replace(styled_path, candidate)
            finally:
                try:
                    styled_path.unlink()
                except FileNotFoundError:
                    pass
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        _patch_run_style_refs(candidate, assignments)
        after_document = build_document_map(candidate)
        after_format = build_formatting_map(candidate)
        if before_document["semantic_sha256"] != after_document["semantic_sha256"]:
            raise ValueError("Formatting transaction changed document text; refusing commit")
        if before_document["structure_sha256"] != after_document["structure_sha256"]:
            raise ValueError("Formatting transaction changed paragraph structure; refusing commit")
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    after_index = _format_paragraph_index(after_format)
    changes: list[dict] = []
    for op in normalized:
        changes.append({
            "op": op["op"],
            "target": op["target"],
            "before": before_index[op["target"]],
            "after": after_index.get(op["target"]),
            "requested_format": op["format"],
            **({"run_indexes": op["run_indexes"]} if "run_indexes" in op else {}),
        })

    result = {
        "before": {
            "semantic_sha256": before_document["semantic_sha256"],
            "structure_sha256": before_document["structure_sha256"],
            "formatting_sha256": before_format["formatting_sha256"],
        },
        "after": {
            "semantic_sha256": after_document["semantic_sha256"],
            "structure_sha256": after_document["structure_sha256"],
            "formatting_sha256": after_format["formatting_sha256"],
        },
        "semantic_changed": before_document["semantic_sha256"] != after_document["semantic_sha256"],
        "structure_changed": before_document["structure_sha256"] != after_document["structure_sha256"],
        "formatting_changed": before_format["formatting_sha256"] != after_format["formatting_sha256"],
        "changes": changes,
        "operation_count": len(normalized),
    }
    if validation is not None:
        result["validation"] = validation
    return result
