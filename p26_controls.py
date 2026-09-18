from __future__ import annotations

import copy
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from p2_document import _local, _paragraph_nodes, build_document_map
from p24_inline import _public_scan, _scan_paragraph, build_inline_map
from p25_controls import (
    _apply_operation as _apply_p25_operation,
    _clear_layout_cache,
    _field_runs,
    _ns_tag,
    _parent_map,
    _plain_text_run,
    _run_text,
    _validate_hyperlink_url,
)

DATE_FORMAT = "YYYY년 M월 D일"
DATE_COMMAND = ":1년 2월 3일"
PATH_FORMAT = "filename"
PATH_LITERAL = "$F"


def _validate_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    text = value.strip()
    if len(text) > 1024 or any(ord(ch) in {0, 10, 13} for ch in text):
        raise ValueError(f"{label} contains unsupported characters or is too long")
    return text


def _bookmark_names(inline_map: dict) -> set[str]:
    return {
        bookmark["name"]
        for paragraph in inline_map["paragraphs"]
        for bookmark in paragraph.get("bookmarks", [])
        if bookmark.get("name")
    }


def _bookmark_reference_count(inline_map: dict, name: str) -> int:
    target = "#" + name
    return sum(
        1
        for paragraph in inline_map["paragraphs"]
        for field in paragraph.get("fields", [])
        if field.get("type") == "HYPERLINK" and field.get("name") == target
    )


def _validate_partial_hyperlink(paragraph: dict, raw: dict, *, url: str) -> dict:
    start = raw.get("start")
    end = raw.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("hyperlink wrapping requires integer start/end offsets")
    if start < 0 or end <= start or end > int(paragraph["inline_text_length"]):
        raise ValueError("hyperlink wrapping range is invalid")

    spans = [
        span for span in paragraph["spans"]
        if int(span["end"]) > start and int(span["start"]) < end
    ]
    if not spans or any(span["kind"] != "text" for span in spans):
        raise ValueError("hyperlink range must contain ordinary text only")
    if any(span.get("field_stack") or span.get("markup_stack") for span in spans):
        raise ValueError("hyperlink range cannot overlap existing field/markup content")
    if int(spans[0]["start"]) > start or int(spans[-1]["end"]) < end:
        raise ValueError("hyperlink range contains an unrepresented control gap")

    internal = [
        boundary for boundary in paragraph["boundaries"]
        if start < int(boundary["offset"]) < end
    ]
    if internal:
        raise ValueError("hyperlink range crosses preserved inline structure")

    return {
        "target": raw["target"],
        "start": start,
        "end": end,
        "url": url,
    }


def _normalize_operations(operations: list[dict], inline_map: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one control edit operation is required")
    if len(operations) > 100:
        raise ValueError("Too many control edit operations")

    paragraphs = {item["locator"]: item for item in inline_map["paragraphs"]}
    bookmark_names = _bookmark_names(inline_map)
    normalized: list[dict] = []
    per_target_has_text_changing_field: set[str] = set()
    per_target_has_offset_op: set[str] = set()

    p25_ops = {
        "retarget_hyperlink", "remove_hyperlink", "set_field_name",
        "insert_special_atom", "delete_special_atom",
    }

    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each control edit operation must be an object")
        op = raw.get("op")
        target = raw.get("target")
        if not isinstance(target, str) or target not in paragraphs:
            raise ValueError(f"Unknown paragraph locator: {target}")
        paragraph = paragraphs[target]

        if op in {"create_hyperlink", "create_bookmark_reference"}:
            if op == "create_hyperlink":
                url = _validate_hyperlink_url(raw.get("url"))
            else:
                bookmark = _validate_name(raw.get("bookmark"), "bookmark")
                if bookmark not in bookmark_names:
                    raise ValueError(f"Unknown bookmark: {bookmark}")
                url = "#" + bookmark
            item = _validate_partial_hyperlink(paragraph, raw, url=url)
            item["op"] = op
            if op == "create_bookmark_reference":
                item["bookmark"] = url[1:]
            normalized.append(item)
            per_target_has_offset_op.add(target)
            continue

        if op == "retarget_bookmark_reference":
            bookmark = _validate_name(raw.get("bookmark"), "bookmark")
            if bookmark not in bookmark_names:
                raise ValueError(f"Unknown bookmark: {bookmark}")
            field_index = raw.get("field_index")
            if not isinstance(field_index, int) or field_index < 0:
                raise ValueError("retarget_bookmark_reference requires non-negative field_index")
            normalized.append({
                "op": op, "target": target, "field_index": field_index,
                "bookmark": bookmark, "url": "#" + bookmark,
            })
            continue

        if op == "create_bookmark":
            name = _validate_name(raw.get("name"), "bookmark name")
            if name in bookmark_names:
                raise ValueError(f"Bookmark already exists: {name}")
            offset = raw.get("offset")
            if not isinstance(offset, int) or offset < 0 or offset > int(paragraph["inline_text_length"]):
                raise ValueError("create_bookmark offset is invalid")
            normalized.append({"op": op, "target": target, "offset": offset, "name": name})
            bookmark_names.add(name)
            per_target_has_offset_op.add(target)
            continue

        if op in {"rename_bookmark", "remove_bookmark"}:
            bookmark_index = raw.get("bookmark_index")
            if not isinstance(bookmark_index, int) or bookmark_index < 0:
                raise ValueError(f"{op} requires non-negative bookmark_index")
            bookmarks = paragraph.get("bookmarks", [])
            if bookmark_index >= len(bookmarks):
                raise ValueError("bookmark_index is outside the target paragraph")
            old_name = bookmarks[bookmark_index]["name"]
            if op == "rename_bookmark":
                new_name = _validate_name(raw.get("name"), "bookmark name")
                if new_name != old_name and new_name in bookmark_names:
                    raise ValueError(f"Bookmark already exists: {new_name}")
                normalized.append({
                    "op": op, "target": target, "bookmark_index": bookmark_index,
                    "old_name": old_name, "name": new_name,
                    "update_references": bool(raw.get("update_references", True)),
                })
                bookmark_names.discard(old_name)
                bookmark_names.add(new_name)
            else:
                refs = _bookmark_reference_count(inline_map, old_name)
                if refs:
                    raise ValueError(
                        f"Bookmark {old_name!r} still has {refs} internal hyperlink reference(s); "
                        "retarget or remove those references first"
                    )
                normalized.append({
                    "op": op, "target": target, "bookmark_index": bookmark_index,
                    "old_name": old_name,
                })
                bookmark_names.discard(old_name)
            continue

        if op in {"set_date_field_properties", "set_path_field_properties", "set_mail_merge_field_properties"}:
            field_index = raw.get("field_index")
            if not isinstance(field_index, int) or field_index < 0:
                raise ValueError(f"{op} requires non-negative field_index")
            fields = paragraph.get("fields", [])
            if field_index >= len(fields):
                raise ValueError("field_index is outside the target paragraph")
            field = fields[field_index]
            expected_type = {
                "set_date_field_properties": "DATE",
                "set_path_field_properties": "PATH",
                "set_mail_merge_field_properties": "MAILMERGE",
            }[op]
            if field.get("type") != expected_type:
                raise ValueError(f"Selected field is not {expected_type}")

            item = {"op": op, "target": target, "field_index": field_index}
            cached = raw.get("cached_text")
            if cached is not None:
                if not isinstance(cached, str) or len(cached) > 100_000:
                    raise ValueError("cached_text must be a bounded string")
                item["cached_text"] = cached
                per_target_has_text_changing_field.add(target)

            if op == "set_date_field_properties":
                date_format = raw.get("date_format", DATE_FORMAT)
                date_nation = raw.get("date_nation", "KOR")
                if date_format != DATE_FORMAT or date_nation != "KOR":
                    raise ValueError("P2.6 supports only DATE format 'YYYY년 M월 D일' with nation 'KOR'")
                item.update({"date_format": date_format, "date_nation": date_nation})
            elif op == "set_path_field_properties":
                path_format = raw.get("path_format", PATH_FORMAT)
                if path_format != PATH_FORMAT:
                    raise ValueError("P2.6 supports only PATH format 'filename'")
                item["path_format"] = path_format
            else:
                name = _validate_name(raw.get("name"), "mail-merge field name")
                item["name"] = name
                item["old_name"] = field.get("parameters", {}).get("Command", {}).get("value", "")
                item["sync_cached_text"] = bool(raw.get("sync_cached_text", True))
            normalized.append(item)
            continue

        if op in p25_ops:
            # Validate the legacy operation through a compact equivalent contract.
            if op in {"retarget_hyperlink", "remove_hyperlink", "set_field_name"}:
                field_index = raw.get("field_index")
                if not isinstance(field_index, int) or field_index < 0:
                    raise ValueError(f"{op} requires non-negative field_index")
                item = {"op": op, "target": target, "field_index": field_index}
                if op == "retarget_hyperlink":
                    item["url"] = _validate_hyperlink_url(raw.get("url"))
                elif op == "set_field_name":
                    name = raw.get("name")
                    if not isinstance(name, str) or len(name) > 8192:
                        raise ValueError("set_field_name requires a bounded string name")
                    item["name"] = name
                normalized.append(item)
            elif op == "insert_special_atom":
                offset = raw.get("offset")
                kind = raw.get("kind")
                if not isinstance(offset, int) or offset < 0 or offset > int(paragraph["inline_text_length"]):
                    raise ValueError("insert_special_atom offset is invalid")
                if kind not in {"tab", "lineBreak", "nbSpace", "fwSpace", "hyphen"}:
                    raise ValueError(f"Unsupported special atom kind: {kind}")
                normalized.append({"op": op, "target": target, "offset": offset, "kind": kind})
                per_target_has_offset_op.add(target)
            else:
                offset = raw.get("offset")
                if not isinstance(offset, int) or offset < 0:
                    raise ValueError("delete_special_atom requires non-negative offset")
                matches = [
                    span for span in paragraph["spans"]
                    if int(span["start"]) == offset and span["kind"] in {"tab", "lineBreak", "nbSpace", "fwSpace", "hyphen"}
                ]
                if len(matches) != 1:
                    raise ValueError("delete_special_atom offset must identify exactly one special atom")
                normalized.append({"op": op, "target": target, "offset": offset, "kind": matches[0]["kind"]})
                per_target_has_offset_op.add(target)
            continue

        raise ValueError(f"Unsupported control edit operation: {op}")

    conflict = per_target_has_text_changing_field & per_target_has_offset_op
    if conflict:
        raise ValueError(
            "Cannot mix cached-text field mutation with offset-addressed control edits "
            f"on the same paragraph in one transaction: {sorted(conflict)}"
        )
    return normalized


def _clone_plain_run(run: ElementTree.Element, text: str) -> ElementTree.Element:
    clone = copy.deepcopy(run)
    t = next((child for child in list(clone) if _local(child.tag) == "t"), None)
    if t is None:
        raise ValueError("Plain run has no hp:t")
    for child in list(t):
        t.remove(child)
    t.text = text
    t.tail = None
    return clone


def _split_for_range(paragraph: ElementTree.Element, start: int, end: int) -> tuple[ElementTree.Element, ElementTree.Element]:
    scan = _scan_paragraph(paragraph, with_refs=True)
    touched = [
        span for span in scan["spans"]
        if span["kind"] == "text" and int(span["end"]) > start and int(span["start"]) < end
    ]
    if not touched:
        raise ValueError("Hyperlink range became non-editable")

    parents = _parent_map(paragraph)
    first_selected: ElementTree.Element | None = None
    last_selected: ElementTree.Element | None = None

    # Split from the highest run index backwards so child positions stay usable.
    by_run: dict[int, dict] = {}
    for span in touched:
        element = span.get("_element")
        if element is None or span.get("_slot") != "text":
            raise ValueError("Partial hyperlink requires direct hp:t text storage")
        run = parents.get(element)
        if run is None or _local(run.tag) != "run" or not _plain_text_run(run):
            raise ValueError("Partial hyperlink requires plain text runs")
        by_run[int(span["run_index"])] = {"span": span, "run": run}

    selected_runs: list[tuple[int, ElementTree.Element]] = []
    for run_index in sorted(by_run, reverse=True):
        span = by_run[run_index]["span"]
        run = by_run[run_index]["run"]
        text = _run_text(run)
        local_start = max(start, int(span["start"])) - int(span["start"])
        local_end = min(end, int(span["end"])) - int(span["start"])
        pieces = [
            ("before", text[:local_start]),
            ("selected", text[local_start:local_end]),
            ("after", text[local_end:]),
        ]
        position = list(paragraph).index(run)
        paragraph.remove(run)
        built: list[tuple[str, ElementTree.Element]] = []
        for label, value in pieces:
            if value:
                built.append((label, _clone_plain_run(run, value)))
        for offset, (label, clone) in enumerate(built):
            paragraph.insert(position + offset, clone)
            if label == "selected":
                selected_runs.append((run_index, clone))

    if not selected_runs:
        raise ValueError("Hyperlink range produced no selected runs")
    selected_runs.sort(key=lambda pair: pair[0])
    first_selected = selected_runs[0][1]
    last_selected = selected_runs[-1][1]
    return first_selected, last_selected


def _wrap_hyperlink(paragraph: ElementTree.Element, op: dict) -> str:
    first, last = _split_for_range(paragraph, int(op["start"]), int(op["end"]))
    children = list(paragraph)
    first_pos = children.index(first)
    last_pos = children.index(last)
    field_id = uuid.uuid4().hex

    begin_run = ElementTree.Element(first.tag)
    begin_ctrl = ElementTree.SubElement(begin_run, _ns_tag(first, "ctrl"))
    ElementTree.SubElement(begin_ctrl, _ns_tag(first, "fieldBegin"), {
        "id": field_id,
        "type": "HYPERLINK",
        "name": op["url"],
        "editable": "false",
        "dirty": "false",
    })
    end_run = ElementTree.Element(last.tag)
    end_ctrl = ElementTree.SubElement(end_run, _ns_tag(last, "ctrl"))
    ElementTree.SubElement(end_ctrl, _ns_tag(last, "fieldEnd"), {"beginIDRef": field_id})

    paragraph.insert(first_pos, begin_run)
    paragraph.insert(last_pos + 2, end_run)
    _clear_layout_cache(paragraph)
    return field_id


def _bookmark_controls(paragraph: ElementTree.Element) -> list[dict]:
    result: list[dict] = []
    for run in [child for child in list(paragraph) if _local(child.tag) == "run"]:
        for ctrl in [child for child in list(run) if _local(child.tag) == "ctrl"]:
            child = next(iter(ctrl), None)
            if child is not None and _local(child.tag) == "bookmark":
                result.append({"run": run, "element": child, "name": child.attrib.get("name") or ""})
    return result


def _split_run_at_offset(paragraph: ElementTree.Element, offset: int) -> int:
    scan = _scan_paragraph(paragraph, with_refs=True)
    if offset == 0:
        return 0
    if offset == len(scan["inline_text"]):
        return len(list(paragraph))
    candidates = [
        span for span in scan["spans"]
        if span["kind"] == "text" and int(span["start"]) <= offset <= int(span["end"])
    ]
    parents = _parent_map(paragraph)
    for span in candidates:
        element = span.get("_element")
        if element is None or span.get("_slot") != "text":
            continue
        run = parents.get(element)
        if run is None or _local(run.tag) != "run" or not _plain_text_run(run):
            continue
        local = offset - int(span["start"])
        text = _run_text(run)
        pos = list(paragraph).index(run)
        if local == 0:
            return pos
        if local == len(text):
            return pos + 1
        before = _clone_plain_run(run, text[:local])
        after = _clone_plain_run(run, text[local:])
        paragraph.remove(run)
        paragraph.insert(pos, before)
        paragraph.insert(pos + 1, after)
        return pos + 1
    raise ValueError("Bookmark offset requires a plain hp:t-backed location")


def _create_bookmark(paragraph: ElementTree.Element, offset: int, name: str) -> None:
    position = _split_run_at_offset(paragraph, offset)
    reference = next((child for child in list(paragraph) if _local(child.tag) == "run"), None)
    if reference is None:
        raise ValueError("Bookmark target paragraph has no run template")
    run = ElementTree.Element(reference.tag)
    ctrl = ElementTree.SubElement(run, _ns_tag(reference, "ctrl"))
    ElementTree.SubElement(ctrl, _ns_tag(reference, "bookmark"), {"name": name})
    paragraph.insert(position, run)
    _clear_layout_cache(paragraph)


def _field_param(begin: ElementTree.Element, name: str) -> ElementTree.Element:
    for node in begin.iter():
        if node.attrib.get("name") == name and _local(node.tag) in {"stringParam", "integerParam", "booleanParam"}:
            return node
    raise ValueError(f"Field is missing expected parameter: {name}")


def _field_cached_text(field: dict) -> ElementTree.Element:
    if field["begin_run"] is not field["end_run"]:
        raise ValueError("Typed P2.6 field mutation requires canonical single-run field layout")
    run = field["begin_run"]
    children = list(run)
    begin_ctrl = next(
        child for child in children
        if _local(child.tag) == "ctrl" and field["begin_element"] in list(child)
    )
    end_ctrl = next(
        child for child in children
        if _local(child.tag) == "ctrl" and field["end_element"] in list(child)
    )
    begin_pos, end_pos = children.index(begin_ctrl), children.index(end_ctrl)
    texts = [child for child in children[begin_pos + 1:end_pos] if _local(child.tag) == "t"]
    if len(texts) != 1:
        raise ValueError("Typed field does not expose exactly one cached text node")
    return texts[0]


def _apply_typed_field(paragraph: ElementTree.Element, op: dict) -> None:
    fields = _field_runs(paragraph)
    idx = int(op["field_index"])
    if idx >= len(fields):
        raise ValueError("field_index moved during transaction")
    field = fields[idx]
    begin = field["begin_element"]
    kind = op["op"]

    if kind == "set_date_field_properties":
        if field["type"] != "DATE":
            raise ValueError("Selected field is not DATE")
        _field_param(begin, "Command").text = DATE_COMMAND
        _field_param(begin, "DateNation").text = op["date_nation"]
        _field_param(begin, "DateFormat").text = op["date_format"]
    elif kind == "set_path_field_properties":
        if field["type"] != "PATH":
            raise ValueError("Selected field is not PATH")
        _field_param(begin, "Command").text = PATH_LITERAL
        _field_param(begin, "Format").text = PATH_LITERAL
    elif kind == "set_mail_merge_field_properties":
        if field["type"] != "MAILMERGE":
            raise ValueError("Selected field is not MAILMERGE")
        old_name = _field_param(begin, "Command").text or ""
        new_name = op["name"]
        _field_param(begin, "Command").text = new_name
        _field_param(begin, "FieldValue").text = new_name
        if "cached_text" not in op and op.get("sync_cached_text"):
            cached = _field_cached_text(field)
            if (cached.text or "") == "{{" + old_name + "}}":
                cached.text = "{{" + new_name + "}}"
    else:
        raise ValueError(f"Unsupported typed field operation: {kind}")

    if "cached_text" in op:
        _field_cached_text(field).text = op["cached_text"]
    _clear_layout_cache(paragraph)


def _control_inventory(inline_map: dict) -> list[dict]:
    rows: list[dict] = []
    for paragraph in inline_map["paragraphs"]:
        locator = paragraph["locator"]
        for field in paragraph.get("fields", []):
            rows.append({
                "kind": "field",
                "locator": locator,
                "index": field["field_index"],
                "intrinsic_id": field.get("id"),
                "identity": field.get("control_identity"),
                "type": field.get("type"),
                "name": field.get("name"),
                "start": field.get("start"),
                "end": field.get("end"),
            })
        for bookmark in paragraph.get("bookmarks", []):
            rows.append({
                "kind": "bookmark",
                "locator": locator,
                "index": bookmark["bookmark_index"],
                "identity": bookmark.get("control_identity"),
                "name": bookmark.get("name"),
                "offset": bookmark.get("offset"),
            })
    return rows


def _control_rebinding(before: dict, after: dict) -> dict:
    before_rows = _control_inventory(before)
    after_rows = _control_inventory(after)
    after_fields = {
        row["intrinsic_id"]: row for row in after_rows
        if row["kind"] == "field" and row.get("intrinsic_id")
    }
    used_after: set[int] = set()
    bindings: list[dict] = []

    for row in before_rows:
        match = None
        if row["kind"] == "field" and row.get("intrinsic_id"):
            match = after_fields.get(row["intrinsic_id"])
        elif row["kind"] == "bookmark":
            candidates = [
                item for item in after_rows
                if item["kind"] == "bookmark"
                and item["locator"] == row["locator"]
                and item["offset"] == row["offset"]
            ]
            if len(candidates) == 1:
                match = candidates[0]
        if match is None:
            bindings.append({"before": row, "after": None, "status": "deleted_or_unresolved"})
        else:
            used_after.add(id(match))
            status = "stable" if row.get("identity") == match.get("identity") else "rebound"
            bindings.append({"before": row, "after": match, "status": status})

    created = [row for row in after_rows if id(row) not in used_after]
    return {"bindings": bindings, "created": created}


def _patch_candidate(path: Path, normalized: list[dict]) -> None:
    document_map = build_document_map(path)
    locator_index = {item["locator"]: item for item in document_map["paragraphs"]}
    by_section: dict[str, list[dict]] = {}
    global_reference_renames: list[tuple[str, str]] = []

    for op in normalized:
        mapped = locator_index.get(op["target"])
        if mapped is None:
            raise ValueError("Control target locator did not survive candidate preparation")
        by_section.setdefault(mapped["section"], []).append({
            **op, "paragraph_index": int(mapped["paragraph_index"])
        })
        if op["op"] == "rename_bookmark" and op.get("update_references"):
            global_reference_renames.append((op["old_name"], op["name"]))

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p26-control-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target_zip:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                    root = ElementTree.fromstring(payload)
                    paragraphs = _paragraph_nodes(root)
                    section_ops = by_section.get(info.filename, [])
                    grouped: dict[int, list[dict]] = {}
                    for op in section_ops:
                        grouped.setdefault(int(op["paragraph_index"]), []).append(op)

                    for paragraph_index, ops in grouped.items():
                        paragraph = paragraphs[paragraph_index]
                        field_ops = [op for op in ops if "field_index" in op]
                        bookmark_ops = [op for op in ops if "bookmark_index" in op]
                        offset_ops = [
                            op for op in ops
                            if op["op"] in {
                                "create_hyperlink", "create_bookmark_reference",
                                "create_bookmark", "insert_special_atom", "delete_special_atom",
                            }
                        ]

                        for op in sorted(field_ops, key=lambda item: item["field_index"], reverse=True):
                            if op["op"] in {
                                "set_date_field_properties", "set_path_field_properties",
                                "set_mail_merge_field_properties",
                            }:
                                _apply_typed_field(paragraph, op)
                            elif op["op"] == "retarget_bookmark_reference":
                                legacy = {
                                    "op": "retarget_hyperlink", "target": op["target"],
                                    "field_index": op["field_index"], "url": op["url"],
                                }
                                _apply_p25_operation(paragraph, legacy)
                            else:
                                _apply_p25_operation(paragraph, op)

                        for op in sorted(bookmark_ops, key=lambda item: item["bookmark_index"], reverse=True):
                            bookmarks = _bookmark_controls(paragraph)
                            idx = int(op["bookmark_index"])
                            if idx >= len(bookmarks):
                                raise ValueError("bookmark_index moved during transaction")
                            bookmark = bookmarks[idx]
                            if op["op"] == "rename_bookmark":
                                bookmark["element"].set("name", op["name"])
                            elif op["op"] == "remove_bookmark":
                                paragraph.remove(bookmark["run"])
                            else:
                                raise ValueError(f"Unsupported bookmark operation: {op['op']}")
                            _clear_layout_cache(paragraph)

                        for op in sorted(
                            offset_ops,
                            key=lambda item: int(item.get("start", item.get("offset", 0))),
                            reverse=True,
                        ):
                            if op["op"] in {"create_hyperlink", "create_bookmark_reference"}:
                                _wrap_hyperlink(paragraph, op)
                            elif op["op"] == "create_bookmark":
                                _create_bookmark(paragraph, int(op["offset"]), op["name"])
                            else:
                                _apply_p25_operation(paragraph, op)

                    if global_reference_renames:
                        for node in root.iter():
                            if _local(node.tag) != "fieldBegin" or node.attrib.get("type") != "HYPERLINK":
                                continue
                            current = node.attrib.get("name") or ""
                            for old, new in global_reference_renames:
                                if current == "#" + old:
                                    node.set("name", "#" + new)
                                    current = "#" + new

                    payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(info, payload)
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

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p26-", suffix=".hwpx", dir=str(path.parent))
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
        "control_rebinding": _control_rebinding(before_inline, after_inline),
        "operation_count": len(normalized),
        "changes": normalized,
    }
    if validation is not None:
        result["validation"] = validation
    return result
