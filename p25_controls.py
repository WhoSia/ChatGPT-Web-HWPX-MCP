from __future__ import annotations

import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from p2_document import _local, _paragraph_nodes, build_document_map
from p24_inline import (
    VISIBLE_SPECIALS,
    _public_scan,
    _scan_paragraph,
    build_inline_map,
)

SPECIAL_KINDS = set(VISIBLE_SPECIALS)
TEXT_NESTED_SPECIALS = {"lineBreak", "nbSpace", "fwSpace", "hyphen"}


def _ns_tag(reference: ElementTree.Element, local_name: str) -> str:
    tag = reference.tag
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[0] + "}" + local_name
    return local_name


def _parent_map(root: ElementTree.Element) -> dict[ElementTree.Element, ElementTree.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _clear_layout_cache(paragraph: ElementTree.Element) -> None:
    for child in list(paragraph):
        if _local(child.tag).lower() == "linesegarray":
            paragraph.remove(child)


def _plain_text_run(run: ElementTree.Element) -> bool:
    children = list(run)
    return (
        len(children) == 1
        and _local(children[0].tag) == "t"
        and len(list(children[0])) == 0
        and not (children[0].tail or "")
    )


def _run_text(run: ElementTree.Element) -> str:
    out: list[str] = []
    for node in run.iter():
        if _local(node.tag) == "t" and node.text:
            out.append(node.text)
    return "".join(out)


def _field_runs(paragraph: ElementTree.Element) -> list[dict]:
    fields: list[dict] = []
    stack: list[dict] = []
    runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
    for run_index, run in enumerate(runs):
        for child in list(run):
            if _local(child.tag) != "ctrl":
                continue
            ctrl_child = next(iter(child), None)
            if ctrl_child is None:
                continue
            kind = _local(ctrl_child.tag)
            if kind == "fieldBegin":
                stack.append({
                    "id": ctrl_child.attrib.get("id"),
                    "type": ctrl_child.attrib.get("type") or "",
                    "name": ctrl_child.attrib.get("name") or "",
                    "begin_run_index": run_index,
                    "begin_run": run,
                    "begin_element": ctrl_child,
                })
            elif kind == "fieldEnd":
                ref = ctrl_child.attrib.get("beginIDRef")
                match = None
                for idx in range(len(stack) - 1, -1, -1):
                    if ref and stack[idx].get("id") == ref:
                        match = idx
                        break
                if match is None and stack:
                    match = len(stack) - 1
                if match is not None:
                    field = stack.pop(match)
                    field.update({
                        "end_run_index": run_index,
                        "end_run": run,
                        "end_element": ctrl_child,
                    })
                    fields.append(field)
    fields.sort(key=lambda item: (item["begin_run_index"], item["end_run_index"]))
    for index, field in enumerate(fields):
        field["field_index"] = index
    return fields


def _require_field(paragraph: ElementTree.Element, field_index: object) -> dict:
    if not isinstance(field_index, int) or field_index < 0:
        raise ValueError("field_index must be a non-negative integer")
    fields = _field_runs(paragraph)
    if field_index >= len(fields):
        raise ValueError("field_index is outside the target paragraph")
    return fields[field_index]


def _validate_hyperlink_url(url: object) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("hyperlink url must be a non-empty string")
    value = url.strip()
    if len(value) > 8192:
        raise ValueError("hyperlink url is too long")
    if any(ord(ch) in {0, 10, 13} for ch in value):
        raise ValueError("hyperlink url contains forbidden control characters")
    return value


def _validate_create_hyperlink(paragraph_map: dict, operation: dict) -> dict:
    start = operation.get("start")
    end = operation.get("end")
    url = _validate_hyperlink_url(operation.get("url"))
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("create_hyperlink requires integer start/end offsets")
    if start < 0 or end <= start or end > int(paragraph_map["inline_text_length"]):
        raise ValueError("create_hyperlink range is invalid")

    spans = [
        span for span in paragraph_map["spans"]
        if int(span["end"]) > start and int(span["start"]) < end
    ]
    if not spans or any(span["kind"] != "text" for span in spans):
        raise ValueError("create_hyperlink range must contain ordinary text only")
    if any(span.get("field_stack") or span.get("markup_stack") for span in spans):
        raise ValueError("create_hyperlink cannot wrap existing field/markup content")
    if int(spans[0]["start"]) != start or int(spans[-1]["end"]) != end:
        raise ValueError("create_hyperlink must align to complete text spans in P2.5")

    run_indexes = sorted({int(span["run_index"]) for span in spans})
    if run_indexes != list(range(run_indexes[0], run_indexes[-1] + 1)):
        raise ValueError("create_hyperlink selected runs are not contiguous")
    boundaries = [
        boundary for boundary in paragraph_map["boundaries"]
        if start <= int(boundary["offset"]) <= end
    ]
    if boundaries:
        raise ValueError("create_hyperlink range crosses preserved inline structure")
    return {
        "op": "create_hyperlink",
        "target": operation["target"],
        "start": start,
        "end": end,
        "url": url,
        "run_indexes": run_indexes,
    }


def _normalize_operations(operations: list[dict], inline_map: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one control edit operation is required")
    if len(operations) > 100:
        raise ValueError("Too many control edit operations")
    index = {item["locator"]: item for item in inline_map["paragraphs"]}
    normalized: list[dict] = []

    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each control edit operation must be an object")
        op = raw.get("op")
        target = raw.get("target")
        if not isinstance(target, str) or target not in index:
            raise ValueError(f"Unknown paragraph locator: {target}")
        paragraph = index[target]

        if op == "create_hyperlink":
            normalized.append(_validate_create_hyperlink(paragraph, raw))
            continue
        if op == "retarget_hyperlink":
            field_index = raw.get("field_index")
            if not isinstance(field_index, int) or field_index < 0:
                raise ValueError("retarget_hyperlink requires non-negative field_index")
            normalized.append({
                "op": op,
                "target": target,
                "field_index": field_index,
                "url": _validate_hyperlink_url(raw.get("url")),
            })
            continue
        if op == "remove_hyperlink":
            field_index = raw.get("field_index")
            if not isinstance(field_index, int) or field_index < 0:
                raise ValueError("remove_hyperlink requires non-negative field_index")
            normalized.append({"op": op, "target": target, "field_index": field_index})
            continue
        if op == "set_field_name":
            field_index = raw.get("field_index")
            name = raw.get("name")
            if not isinstance(field_index, int) or field_index < 0:
                raise ValueError("set_field_name requires non-negative field_index")
            if not isinstance(name, str) or len(name) > 8192:
                raise ValueError("set_field_name requires a bounded string name")
            normalized.append({
                "op": op,
                "target": target,
                "field_index": field_index,
                "name": name,
            })
            continue
        if op == "insert_special_atom":
            offset = raw.get("offset")
            kind = raw.get("kind")
            if not isinstance(offset, int) or offset < 0 or offset > int(paragraph["inline_text_length"]):
                raise ValueError("insert_special_atom offset is invalid")
            if kind not in SPECIAL_KINDS:
                raise ValueError(f"Unsupported special atom kind: {kind}")
            normalized.append({
                "op": op, "target": target, "offset": offset, "kind": kind
            })
            continue
        if op == "delete_special_atom":
            offset = raw.get("offset")
            if not isinstance(offset, int) or offset < 0:
                raise ValueError("delete_special_atom requires non-negative offset")
            matches = [
                span for span in paragraph["spans"]
                if int(span["start"]) == offset and span["kind"] in SPECIAL_KINDS
            ]
            if len(matches) != 1:
                raise ValueError("delete_special_atom offset must identify exactly one special atom")
            normalized.append({
                "op": op,
                "target": target,
                "offset": offset,
                "kind": matches[0]["kind"],
            })
            continue
        raise ValueError(f"Unsupported control edit operation: {op}")
    return normalized


def _create_hyperlink(paragraph: ElementTree.Element, op: dict) -> None:
    scan = _public_scan(_scan_paragraph(paragraph))
    checked = _validate_create_hyperlink({**scan, "locator": op["target"]}, op)
    runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
    selected = [runs[index] for index in checked["run_indexes"]]
    if not all(_plain_text_run(run) for run in selected):
        raise ValueError("create_hyperlink requires complete plain text runs in P2.5")

    first = selected[0]
    last = selected[-1]
    children = list(paragraph)
    insert_before = children.index(first)
    insert_after = children.index(last) + 1

    field_id = uuid.uuid4().hex
    begin_run = ElementTree.Element(first.tag, dict(first.attrib))
    for key in list(begin_run.attrib):
        if _local(key) == "charPrIDRef":
            begin_run.attrib.pop(key, None)
    begin_ctrl = ElementTree.SubElement(begin_run, _ns_tag(first, "ctrl"))
    ElementTree.SubElement(
        begin_ctrl,
        _ns_tag(first, "fieldBegin"),
        {
            "id": field_id,
            "type": "HYPERLINK",
            "name": checked["url"],
            "editable": "false",
            "dirty": "false",
        },
    )

    end_run = ElementTree.Element(last.tag, dict(last.attrib))
    for key in list(end_run.attrib):
        if _local(key) == "charPrIDRef":
            end_run.attrib.pop(key, None)
    end_ctrl = ElementTree.SubElement(end_run, _ns_tag(last, "ctrl"))
    ElementTree.SubElement(
        end_ctrl,
        _ns_tag(last, "fieldEnd"),
        {"beginIDRef": field_id},
    )

    paragraph.insert(insert_before, begin_run)
    paragraph.insert(insert_after + 1, end_run)
    _clear_layout_cache(paragraph)


def _retarget_hyperlink(paragraph: ElementTree.Element, field_index: int, url: str) -> None:
    field = _require_field(paragraph, field_index)
    if field["type"] != "HYPERLINK":
        raise ValueError("Selected field is not a HYPERLINK")
    field["begin_element"].set("name", url)
    _clear_layout_cache(paragraph)


def _remove_hyperlink(paragraph: ElementTree.Element, field_index: int) -> None:
    field = _require_field(paragraph, field_index)
    if field["type"] != "HYPERLINK":
        raise ValueError("Selected field is not a HYPERLINK")
    begin_run = field["begin_run"]
    end_run = field["end_run"]
    # P2.5 removes only canonical control-only wrapper runs. Display runs survive.
    for run in (begin_run, end_run):
        children = list(run)
        if len(children) != 1 or _local(children[0].tag) != "ctrl":
            raise ValueError("Hyperlink wrapper run contains additional content; refusing removal")
    paragraph.remove(end_run)
    paragraph.remove(begin_run)
    _clear_layout_cache(paragraph)


def _set_field_name(paragraph: ElementTree.Element, field_index: int, name: str) -> None:
    field = _require_field(paragraph, field_index)
    field["begin_element"].set("name", name)
    _clear_layout_cache(paragraph)


def _find_plain_text_insertion(paragraph: ElementTree.Element, offset: int) -> tuple[ElementTree.Element, ElementTree.Element, int]:
    scan = _scan_paragraph(paragraph, with_refs=True)
    candidates = [
        span for span in scan["spans"]
        if span["kind"] == "text" and int(span["start"]) <= offset <= int(span["end"])
    ]
    for span in candidates:
        element = span.get("_element")
        slot = span.get("_slot")
        if element is None or slot != "text" or _local(element.tag) != "t":
            continue
        parent = _parent_map(paragraph).get(element)
        if parent is None or _local(parent.tag) != "run" or not _plain_text_run(parent):
            continue
        local_offset = offset - int(span["start"])
        return parent, element, local_offset
    raise ValueError("Special atom insertion requires a plain hp:t-backed offset in P2.5")


def _insert_special(paragraph: ElementTree.Element, offset: int, kind: str) -> None:
    run, text_node, local_offset = _find_plain_text_insertion(paragraph, offset)
    value = text_node.text or ""
    before, after = value[:local_offset], value[local_offset:]

    if kind in TEXT_NESTED_SPECIALS:
        text_node.text = before
        atom = ElementTree.Element(_ns_tag(text_node, kind))
        atom.tail = after
        text_node.append(atom)
    elif kind == "tab":
        children = list(paragraph)
        run_pos = children.index(run)
        paragraph.remove(run)
        before_run = ElementTree.Element(run.tag, dict(run.attrib))
        before_t = ElementTree.SubElement(before_run, text_node.tag, dict(text_node.attrib))
        before_t.text = before

        tab_run = ElementTree.Element(run.tag, dict(run.attrib))
        ElementTree.SubElement(tab_run, _ns_tag(run, "tab"))

        after_run = ElementTree.Element(run.tag, dict(run.attrib))
        after_t = ElementTree.SubElement(after_run, text_node.tag, dict(text_node.attrib))
        after_t.text = after

        replacement = [item for item in (before_run, tab_run, after_run) if _run_text(item) or any(_local(c.tag) == "tab" for c in item)]
        for idx, item in enumerate(replacement):
            paragraph.insert(run_pos + idx, item)
    else:
        raise ValueError(f"Unsupported special atom kind: {kind}")
    _clear_layout_cache(paragraph)


def _delete_special(paragraph: ElementTree.Element, offset: int, kind: str) -> None:
    scan = _scan_paragraph(paragraph, with_refs=True)
    matches = [
        span for span in scan["spans"]
        if int(span["start"]) == offset and span["kind"] == kind
    ]
    if len(matches) != 1:
        raise ValueError("Special atom moved or became ambiguous during transaction")
    span = matches[0]
    atom = span.get("_element")
    if atom is None:
        raise ValueError("Special atom has no editable XML element")
    parents = _parent_map(paragraph)
    parent = parents.get(atom)
    if parent is None:
        raise ValueError("Special atom has no mutable parent")

    tail = atom.tail or ""
    siblings = list(parent)
    idx = siblings.index(atom)
    if idx > 0:
        prev = siblings[idx - 1]
        prev.tail = (prev.tail or "") + tail
    else:
        parent.text = (parent.text or "") + tail
    parent.remove(atom)

    # Canonical direct-run tab can leave empty runs; remove them only when empty.
    if _local(parent.tag) == "run" and not list(parent) and not (parent.text or ""):
        paragraph.remove(parent)
    _clear_layout_cache(paragraph)


def _apply_operation(paragraph: ElementTree.Element, op: dict) -> None:
    kind = op["op"]
    if kind == "create_hyperlink":
        _create_hyperlink(paragraph, op)
    elif kind == "retarget_hyperlink":
        _retarget_hyperlink(paragraph, op["field_index"], op["url"])
    elif kind == "remove_hyperlink":
        _remove_hyperlink(paragraph, op["field_index"])
    elif kind == "set_field_name":
        _set_field_name(paragraph, op["field_index"], op["name"])
    elif kind == "insert_special_atom":
        _insert_special(paragraph, op["offset"], op["kind"])
    elif kind == "delete_special_atom":
        _delete_special(paragraph, op["offset"], op["kind"])
    else:
        raise ValueError(f"Unsupported control edit operation: {kind}")


def _patch_candidate(path: Path, normalized: list[dict]) -> None:
    current_map = build_document_map(path)
    locator_index = {item["locator"]: item for item in current_map["paragraphs"]}
    by_section: dict[str, list[dict]] = {}
    for op in normalized:
        mapped = locator_index.get(op["target"])
        if mapped is None:
            raise ValueError("Control target locator did not survive candidate preparation")
        by_section.setdefault(mapped["section"], []).append({
            **op,
            "paragraph_index": int(mapped["paragraph_index"]),
        })

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p25-control-", suffix=".hwpx", dir=str(path.parent)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                section_ops = by_section.get(info.filename)
                if section_ops:
                    root = ElementTree.fromstring(payload)
                    paragraphs = _paragraph_nodes(root)
                    grouped: dict[int, list[dict]] = {}
                    for op in section_ops:
                        grouped.setdefault(int(op["paragraph_index"]), []).append(op)
                    for paragraph_index, ops in grouped.items():
                        paragraph = paragraphs[paragraph_index]
                        # Field-index operations first; offset insert/delete in descending offset
                        field_ops = [op for op in ops if "field_index" in op]
                        create_ops = [op for op in ops if op["op"] == "create_hyperlink"]
                        atom_ops = [op for op in ops if op["op"] in {"insert_special_atom", "delete_special_atom"}]
                        for op in sorted(field_ops, key=lambda item: item["field_index"], reverse=True):
                            _apply_operation(paragraph, op)
                        for op in sorted(create_ops, key=lambda item: item["start"], reverse=True):
                            _apply_operation(paragraph, op)
                        for op in sorted(atom_ops, key=lambda item: item["offset"], reverse=True):
                            _apply_operation(paragraph, op)
                    payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                target.writestr(info, payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def apply_control_edits_atomic(
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
    before_inline = build_inline_map(path)
    normalized = _normalize_operations(operations, before_inline)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p25-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    validation = None
    try:
        _patch_candidate(candidate, normalized)
        after_document = build_document_map(candidate)
        after_inline = build_inline_map(candidate)
        if before_document["structure_sha256"] != after_document["structure_sha256"]:
            raise ValueError("Control transaction changed paragraph structure; refusing commit")
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
            "semantic_sha256": before_document["semantic_sha256"],
            "structure_sha256": before_document["structure_sha256"],
            "inline_text_sha256": before_inline["inline_text_sha256"],
            "inline_structure_sha256": before_inline["inline_structure_sha256"],
        },
        "after": {
            "semantic_sha256": after_document["semantic_sha256"],
            "structure_sha256": after_document["structure_sha256"],
            "inline_text_sha256": after_inline["inline_text_sha256"],
            "inline_structure_sha256": after_inline["inline_structure_sha256"],
        },
        "semantic_changed": before_document["semantic_sha256"] != after_document["semantic_sha256"],
        "structure_changed": False,
        "inline_text_changed": before_inline["inline_text_sha256"] != after_inline["inline_text_sha256"],
        "inline_structure_changed": before_inline["inline_structure_sha256"] != after_inline["inline_structure_sha256"],
        "operation_count": len(normalized),
        "changes": normalized,
    }
    if validation is not None:
        result["validation"] = validation
    return result
