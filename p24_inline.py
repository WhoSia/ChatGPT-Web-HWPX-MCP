from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from p2_document import _local, _paragraph_nodes, build_document_map

VISIBLE_SPECIALS = {
    "tab": "\t",
    "lineBreak": "\n",
    "nbSpace": "\u00a0",
    "fwSpace": "\u3000",
    "hyphen": "\u00ad",
}
ZERO_WIDTH_MARKUP = {"markpenBegin", "markpenEnd", "titleMark"}
FORBIDDEN_REPLACEMENT_CHARS = set(VISIBLE_SPECIALS.values())


def _attrs_without_ids(node: ElementTree.Element) -> dict[str, str]:
    ignored = {"id", "fieldid", "beginIDRef", "instid", "instId"}
    return {
        _local(key): value
        for key, value in sorted(node.attrib.items(), key=lambda item: _local(item[0]))
        if _local(key) not in ignored
    }


def _first_child(node: ElementTree.Element) -> ElementTree.Element | None:
    return next(iter(node), None)


def _control_descriptor(ctrl: ElementTree.Element) -> tuple[str, ElementTree.Element | None]:
    child = _first_child(ctrl)
    if child is None:
        return "ctrl", None
    return _local(child.tag), child


def _append_text_span(
    spans: list[dict],
    text_parts: list[str],
    value: str | None,
    *,
    run_index: int,
    field_stack: list[dict],
    markup_stack: list[str],
    element: ElementTree.Element,
    slot: str,
    offset: int,
    with_refs: bool,
) -> int:
    if not value:
        return offset
    end = offset + len(value)
    item = {
        "kind": "text",
        "start": offset,
        "end": end,
        "text": value,
        "run_index": run_index,
        "field_stack": [dict(field) for field in field_stack],
        "markup_stack": list(markup_stack),
    }
    if with_refs:
        item["_element"] = element
        item["_slot"] = slot
    spans.append(item)
    text_parts.append(value)
    return end


def _append_special_span(
    spans: list[dict],
    text_parts: list[str],
    node: ElementTree.Element,
    *,
    run_index: int,
    field_stack: list[dict],
    markup_stack: list[str],
    offset: int,
    with_refs: bool,
) -> int:
    kind = _local(node.tag)
    value = VISIBLE_SPECIALS[kind]
    item = {
        "kind": kind,
        "start": offset,
        "end": offset + 1,
        "text": value,
        "run_index": run_index,
        "field_stack": [dict(field) for field in field_stack],
        "markup_stack": list(markup_stack),
        "attributes": {_local(k): v for k, v in node.attrib.items()},
    }
    if with_refs:
        item["_element"] = node
        item["_slot"] = "element"
    spans.append(item)
    text_parts.append(value)
    return offset + 1


def _scan_text_element(
    node: ElementTree.Element,
    *,
    spans: list[dict],
    boundaries: list[dict],
    skeleton: list[dict],
    text_parts: list[str],
    run_index: int,
    field_stack: list[dict],
    markup_stack: list[str],
    offset: int,
    with_refs: bool,
) -> int:
    offset = _append_text_span(
        spans,
        text_parts,
        node.text,
        run_index=run_index,
        field_stack=field_stack,
        markup_stack=markup_stack,
        element=node,
        slot="text",
        offset=offset,
        with_refs=with_refs,
    )
    for child in list(node):
        name = _local(child.tag)
        if name in VISIBLE_SPECIALS:
            skeleton.append({"token": "special", "kind": name, "attrs": _attrs_without_ids(child)})
            offset = _append_special_span(
                spans,
                text_parts,
                child,
                run_index=run_index,
                field_stack=field_stack,
                markup_stack=markup_stack,
                offset=offset,
                with_refs=with_refs,
            )
        elif name in ZERO_WIDTH_MARKUP:
            descriptor = {
                "offset": offset,
                "kind": "markup",
                "name": name,
                "policy": "boundary",
                "attributes": {_local(k): v for k, v in child.attrib.items()},
            }
            boundaries.append(descriptor)
            skeleton.append({"token": "markup", "kind": name, "attrs": _attrs_without_ids(child)})
            if name == "markpenBegin":
                markup_stack.append("markpen")
            elif name == "markpenEnd":
                if markup_stack and markup_stack[-1] == "markpen":
                    markup_stack.pop()
        else:
            boundaries.append({
                "offset": offset,
                "kind": "mixed-inline",
                "name": name,
                "policy": "hard",
                "attributes": {_local(k): v for k, v in child.attrib.items()},
            })
            skeleton.append({"token": "mixed-inline", "kind": name, "attrs": _attrs_without_ids(child)})
        offset = _append_text_span(
            spans,
            text_parts,
            child.tail,
            run_index=run_index,
            field_stack=field_stack,
            markup_stack=markup_stack,
            element=child,
            slot="tail",
            offset=offset,
            with_refs=with_refs,
        )
    return offset


def _scan_paragraph(paragraph: ElementTree.Element, *, with_refs: bool = False) -> dict:
    spans: list[dict] = []
    boundaries: list[dict] = []
    fields: list[dict] = []
    skeleton: list[dict] = []
    text_parts: list[str] = []
    field_stack: list[dict] = []
    markup_stack: list[str] = []
    offset = 0
    run_index = 0

    for run in list(paragraph):
        if _local(run.tag) != "run":
            continue
        for child in list(run):
            name = _local(child.tag)
            if name == "t":
                offset = _scan_text_element(
                    child,
                    spans=spans,
                    boundaries=boundaries,
                    skeleton=skeleton,
                    text_parts=text_parts,
                    run_index=run_index,
                    field_stack=field_stack,
                    markup_stack=markup_stack,
                    offset=offset,
                    with_refs=with_refs,
                )
                continue

            if name in VISIBLE_SPECIALS:
                skeleton.append({"token": "special", "kind": name, "attrs": _attrs_without_ids(child)})
                offset = _append_special_span(
                    spans,
                    text_parts,
                    child,
                    run_index=run_index,
                    field_stack=field_stack,
                    markup_stack=markup_stack,
                    offset=offset,
                    with_refs=with_refs,
                )
                continue

            if name == "ctrl":
                ctrl_name, ctrl_child = _control_descriptor(child)
                if ctrl_name == "fieldBegin" and ctrl_child is not None:
                    field = {
                        "id": ctrl_child.attrib.get("id"),
                        "type": ctrl_child.attrib.get("type") or "",
                        "name": ctrl_child.attrib.get("name") or "",
                        "begin": offset,
                    }
                    boundaries.append({
                        "offset": offset,
                        "kind": "field-begin",
                        "name": field["type"],
                        "policy": "field-boundary",
                    })
                    skeleton.append({
                        "token": "field-begin",
                        "type": field["type"],
                        "name": field["name"],
                        "attrs": _attrs_without_ids(ctrl_child),
                    })
                    field_stack.append(field)
                    continue
                if ctrl_name == "fieldEnd" and ctrl_child is not None:
                    ref = ctrl_child.attrib.get("beginIDRef")
                    matched_index = None
                    for index in range(len(field_stack) - 1, -1, -1):
                        if ref and field_stack[index].get("id") == ref:
                            matched_index = index
                            break
                    if matched_index is None and field_stack:
                        matched_index = len(field_stack) - 1
                    field = field_stack.pop(matched_index) if matched_index is not None else None
                    boundaries.append({
                        "offset": offset,
                        "kind": "field-end",
                        "name": "" if field is None else field["type"],
                        "policy": "field-boundary",
                    })
                    skeleton.append({
                        "token": "field-end",
                        "type": "" if field is None else field["type"],
                        "name": "" if field is None else field["name"],
                    })
                    if field is not None:
                        fields.append({
                            "type": field["type"],
                            "name": field["name"],
                            "start": field["begin"],
                            "end": offset,
                        })
                    continue

                boundaries.append({
                    "offset": offset,
                    "kind": "control",
                    "name": ctrl_name,
                    "policy": "hard",
                    "attributes": {} if ctrl_child is None else {_local(k): v for k, v in ctrl_child.attrib.items()},
                })
                skeleton.append({
                    "token": "control",
                    "kind": ctrl_name,
                    "attrs": {} if ctrl_child is None else _attrs_without_ids(ctrl_child),
                })
                continue

            boundaries.append({
                "offset": offset,
                "kind": "object",
                "name": name,
                "policy": "hard",
                "attributes": {_local(k): v for k, v in child.attrib.items()},
            })
            skeleton.append({"token": "object", "kind": name, "attrs": _attrs_without_ids(child)})
        run_index += 1

    for field in reversed(field_stack):
        fields.append({
            "type": field["type"],
            "name": field["name"],
            "start": field["begin"],
            "end": None,
            "unclosed": True,
        })
        skeleton.append({"token": "field-unclosed", "type": field["type"], "name": field["name"]})

    ordered_fields = sorted(
        fields,
        key=lambda item: (item["start"], item["end"] is None, item["end"] or -1),
    )
    for field_index, field in enumerate(ordered_fields):
        field["field_index"] = field_index
    return {
        "inline_text": "".join(text_parts),
        "spans": spans,
        "boundaries": boundaries,
        "fields": ordered_fields,
        "skeleton": skeleton,
        "run_count": run_index,
    }


def _public_scan(scan: dict) -> dict:
    return {
        "inline_text": scan["inline_text"],
        "inline_text_length": len(scan["inline_text"]),
        "inline_text_sha256": hashlib.sha256(scan["inline_text"].encode("utf-8")).hexdigest(),
        "spans": [
            {key: value for key, value in span.items() if not key.startswith("_")}
            for span in scan["spans"]
        ],
        "boundaries": scan["boundaries"],
        "fields": scan["fields"],
        "run_count": scan["run_count"],
    }


def build_inline_map(path: Path) -> dict:
    document_map = build_document_map(path)
    by_position = {
        (item["section"], int(item["paragraph_index"])): item
        for item in document_map["paragraphs"]
    }
    paragraphs: list[dict] = []
    skeleton_rows: list[dict] = []

    with zipfile.ZipFile(path, "r") as archive:
        for section in document_map["sections"]:
            section_name = section["section"]
            root = ElementTree.fromstring(archive.read(section_name))
            paragraph_index = 0
            for paragraph in root.iter():
                if _local(paragraph.tag) != "p":
                    continue
                mapped = by_position[(section_name, paragraph_index)]
                scan = _scan_paragraph(paragraph)
                public = _public_scan(scan)
                paragraphs.append({
                    "locator": mapped["locator"],
                    "section": section_name,
                    "section_index": mapped["section_index"],
                    "paragraph_index": paragraph_index,
                    "container": mapped.get("container"),
                    **public,
                })
                skeleton_rows.append({
                    "locator": mapped["locator"],
                    "tokens": scan["skeleton"],
                })
                paragraph_index += 1

    inline_structure_sha256 = hashlib.sha256(
        json.dumps(
            skeleton_rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    inline_text_sha256 = hashlib.sha256(
        "\n".join(item["inline_text"] for item in paragraphs).encode("utf-8")
    ).hexdigest()
    return {
        "inline_structure_sha256": inline_structure_sha256,
        "inline_text_sha256": inline_text_sha256,
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
    }


def _context_key(span: dict) -> tuple:
    fields = tuple(
        (field.get("type"), field.get("name"), field.get("id"))
        for field in span.get("field_stack", [])
    )
    markup = tuple(span.get("markup_stack", []))
    return fields, markup


def _validate_replace(paragraph: dict, operation: dict) -> dict:
    start = operation.get("start")
    end = operation.get("end")
    replacement = operation.get("text")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("replace_inline_text requires integer start/end offsets")
    if start < 0 or end <= start or end > int(paragraph["inline_text_length"]):
        raise ValueError(
            f"Invalid inline range [{start}, {end}) for text length {paragraph['inline_text_length']}"
        )
    if not isinstance(replacement, str):
        raise ValueError("replace_inline_text requires string text")
    if len(replacement) > 100_000:
        raise ValueError("Replacement text is too large")
    if any(char in FORBIDDEN_REPLACEMENT_CHARS for char in replacement):
        raise ValueError(
            "P2.4 replacement text may not introduce tab/line-break/space-marker atoms"
        )

    expected = operation.get("expected_text")
    selected = paragraph["inline_text"][start:end]
    if expected is not None and (not isinstance(expected, str) or expected != selected):
        raise ValueError("expected_text does not match the selected inline text")

    overlapping = [
        span for span in paragraph["spans"]
        if int(span["end"]) > start and int(span["start"]) < end
    ]
    if not overlapping:
        raise ValueError("Inline range does not intersect editable text")
    non_text = [span for span in overlapping if span["kind"] != "text"]
    if non_text:
        raise ValueError(
            "Inline range intersects a structural/special character atom; split the request around it"
        )
    if int(overlapping[0]["start"]) > start or int(overlapping[-1]["end"]) < end:
        raise ValueError("Inline range contains an unrepresented/control gap")

    contexts = {_context_key(span) for span in overlapping}
    if len(contexts) != 1:
        raise ValueError("Inline range crosses a field or mixed-markup context boundary")

    internal_boundaries = [
        boundary for boundary in paragraph["boundaries"]
        if start < int(boundary["offset"]) < end
    ]
    if internal_boundaries:
        labels = [f"{item['kind']}:{item['name']}" for item in internal_boundaries]
        raise ValueError(
            "Inline range crosses preserved inline structure: " + ", ".join(labels)
        )

    return {
        "op": "replace_inline_text",
        "target": operation["target"],
        "start": start,
        "end": end,
        "text": replacement,
        "expected_text": expected,
        "before_text": selected,
        "field_context": list(overlapping[0].get("field_stack", [])),
        "markup_context": list(overlapping[0].get("markup_stack", [])),
    }


def _normalize_operations(operations: list[dict], inline_map: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one inline edit operation is required")
    if len(operations) > 100:
        raise ValueError("Too many inline edit operations")
    index = {item["locator"]: item for item in inline_map["paragraphs"]}
    normalized: list[dict] = []
    by_target: dict[str, list[tuple[int, int]]] = {}

    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each inline edit operation must be an object")
        if raw.get("op") != "replace_inline_text":
            raise ValueError(f"Unsupported inline edit operation: {raw.get('op')}")
        target = raw.get("target")
        if not isinstance(target, str) or target not in index:
            raise ValueError(f"Unknown paragraph locator: {target}")
        normalized_op = _validate_replace(index[target], raw)
        ranges = by_target.setdefault(target, [])
        for prior_start, prior_end in ranges:
            if normalized_op["start"] < prior_end and prior_start < normalized_op["end"]:
                raise ValueError("Overlapping inline edit ranges are not allowed in one transaction")
        ranges.append((normalized_op["start"], normalized_op["end"]))
        normalized.append(normalized_op)
    return normalized


def _apply_one_replace(paragraph: ElementTree.Element, operation: dict) -> None:
    scan = _scan_paragraph(paragraph, with_refs=True)
    public = _public_scan(scan)
    checked = _validate_replace(
        {
            **public,
            "locator": operation["target"],
        },
        operation,
    )

    start = checked["start"]
    end = checked["end"]
    replacement = checked["text"]
    overlaps = [
        span for span in scan["spans"]
        if span["kind"] == "text" and int(span["end"]) > start and int(span["start"]) < end
    ]
    if not overlaps:
        raise ValueError("Inline range became non-editable during transaction")

    grouped: dict[tuple[int, str], dict] = {}
    first_key: tuple[int, str] | None = None
    first_insert_absolute: int | None = None

    for span in overlaps:
        element = span["_element"]
        slot = span["_slot"]
        key = (id(element), slot)
        current = getattr(element, slot) or ""
        record = grouped.setdefault(key, {
            "element": element,
            "slot": slot,
            "original": current,
            "cuts": [],
        })
        local_start = max(start, int(span["start"])) - int(span["start"])
        local_end = min(end, int(span["end"])) - int(span["start"])
        record["cuts"].append((local_start, local_end))
        if int(span["start"]) <= start < int(span["end"]):
            first_key = key
            first_insert_absolute = local_start

    if first_key is None or first_insert_absolute is None:
        raise ValueError("Inline replacement start is not backed by a text storage slot")

    for key, record in grouped.items():
        original = record["original"]
        cuts = sorted(record["cuts"])
        cursor = 0
        pieces: list[str] = []
        insert_position = None
        for cut_start, cut_end in cuts:
            pieces.append(original[cursor:cut_start])
            if key == first_key and insert_position is None and cut_start <= first_insert_absolute <= cut_end:
                insert_position = sum(len(piece) for piece in pieces)
            cursor = cut_end
        pieces.append(original[cursor:])
        value = "".join(pieces)
        if key == first_key:
            if insert_position is None:
                insert_position = min(first_insert_absolute, len(value))
            value = value[:insert_position] + replacement + value[insert_position:]
        setattr(record["element"], record["slot"], value)

    for child in list(paragraph):
        if _local(child.tag).lower() == "linesegarray":
            paragraph.remove(child)


def _patch_inline_candidate(path: Path, normalized: list[dict]) -> None:
    current_map = build_document_map(path)
    locator_index = {item["locator"]: item for item in current_map["paragraphs"]}
    by_section: dict[str, list[dict]] = {}
    for op in normalized:
        mapped = locator_index.get(op["target"])
        if mapped is None:
            raise ValueError("Inline target locator did not survive candidate preparation")
        by_section.setdefault(mapped["section"], []).append({
            **op,
            "paragraph_index": int(mapped["paragraph_index"]),
        })

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p24-inline-", suffix=".hwpx", dir=str(path.parent)
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
                    for paragraph_index, operations in grouped.items():
                        paragraph = paragraphs[paragraph_index]
                        for op in sorted(operations, key=lambda item: int(item["start"]), reverse=True):
                            _apply_one_replace(paragraph, op)
                    payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                target.writestr(info, payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def apply_inline_edits_atomic(
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

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p24-", suffix=".hwpx", dir=str(path.parent)
    )
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    validation = None
    try:
        _patch_inline_candidate(candidate, normalized)
        after_document = build_document_map(candidate)
        after_inline = build_inline_map(candidate)

        if before_document["structure_sha256"] != after_document["structure_sha256"]:
            raise ValueError("Inline text transaction changed paragraph structure; refusing commit")
        if before_inline["inline_structure_sha256"] != after_inline["inline_structure_sha256"]:
            raise ValueError("Inline text transaction changed preserved inline structure; refusing commit")
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
        "inline_structure_changed": False,
        "operation_count": len(normalized),
        "changes": normalized,
    }
    if validation is not None:
        result["validation"] = validation
    return result
