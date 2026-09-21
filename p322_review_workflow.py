from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from hwpx import HwpxDocument

from p2_document import build_document_map
from p27_tables import _save_document


SCHEMA = "chatgpt-web-hwpx-mcp/review-workflow/p3.22/v1"


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _resolve_paragraph(document: HwpxDocument, path: Path, locator: Any):
    wanted = str(locator or "")
    mapped = build_document_map(path)["paragraphs"]
    info = next((item for item in mapped if item["locator"] == wanted), None)
    if info is None:
        raise ValueError(f"Unknown paragraph locator: {wanted}")
    section_index = int(info["section_index"])
    body_index = info.get("body_paragraph_index")
    if body_index is None:
        raise ValueError("review target must be a section-body paragraph")
    paragraphs = document.sections[section_index].paragraphs
    paragraph_index = int(body_index)
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        raise ValueError("paragraph locator no longer resolves")
    return paragraphs[paragraph_index], info


def _dataclass_payload(value: Any) -> dict:
    if is_dataclass(value):
        return asdict(value)
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        return dict(attrs)
    return {"repr": repr(value)}


def _metadata_payload(document: HwpxDocument) -> dict | None:
    meta = document.parts.metadata
    if meta is None:
        return None
    return _dataclass_payload(meta)


def _form_field_payload(field: Any) -> dict:
    location = field.location.to_dict() if hasattr(field.location, "to_dict") else {}
    return {
        "field_id": field.field_id,
        "name": field.name,
        "prompt": field.prompt,
        "memo": field.memo,
        "editable": bool(field.editable),
        "value": field.value,
        "field_type": field.field_type,
        "is_placeholder": bool(field.is_placeholder),
        "has_end": bool(field.has_end),
        "location": location,
        "parameters": [
            item.to_dict() if hasattr(item, "to_dict") else _dataclass_payload(item)
            for item in field.parameters
        ],
    }


def _checkbox_payload(box: Any) -> dict:
    return {
        "index": int(box.index),
        "section_index": int(box.section_index),
        "name": box.name,
        "caption": box.caption,
        "value": box.value,
        "checked": bool(box.checked),
    }


def _highlight_payload(item: Any) -> dict:
    payload = item.to_dict() if hasattr(item, "to_dict") else _dataclass_payload(item)
    paragraph = getattr(item, "paragraph", None)
    if paragraph is not None:
        intrinsic_id = getattr(getattr(paragraph, "element", None), "get", lambda _k: None)("id")
        if intrinsic_id is not None:
            payload["paragraph_intrinsic_id"] = str(intrinsic_id)
    return payload


def build_review_workflow_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        changes = []
        for key, change in sorted(document.tracking.changes.items(), key=lambda item: str(item[0])):
            payload = _dataclass_payload(change)
            payload["lookup_key"] = str(key)
            changes.append(payload)

        authors = []
        for key, author in sorted(document.tracking.authors.items(), key=lambda item: str(item[0])):
            payload = _dataclass_payload(author)
            payload["lookup_key"] = str(key)
            authors.append(payload)

        form_fields = [_form_field_payload(item) for item in document.fields.all]
        check_boxes = [_checkbox_payload(item) for item in document.fields.check_boxes]
        highlights = [_highlight_payload(item) for item in document.text.highlights()]
        metadata = _metadata_payload(document)

        result = {
            "schema": SCHEMA,
            "tracked_changes": changes,
            "track_change_authors": authors,
            "form_fields": form_fields,
            "check_boxes": check_boxes,
            "highlights": highlights,
            "metadata": metadata,
            "counts": {
                "tracked_changes": len(changes),
                "track_change_authors": len(authors),
                "form_fields": len(form_fields),
                "check_boxes": len(check_boxes),
                "highlights": len(highlights),
            },
            "unsupported_write_lanes": [
                "accept_or_reject_tracked_change",
                "tracking_toggle_without_change",
                "tracking_protection_password",
                "radio_button_authoring",
                "command_button_authoring",
                "document_history_part_authoring",
            ],
        }
        result["review_workflow_sha256"] = _sha({
            "tracked_changes": changes,
            "track_change_authors": authors,
            "form_fields": form_fields,
            "check_boxes": check_boxes,
            "highlights": highlights,
            "metadata": metadata,
        })
        return result
    finally:
        document.close()


def apply_review_workflow_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 96:
        raise ValueError("Review transaction requires 1..96 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each review operation must be an object")

    before = build_review_workflow_map(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p322-review-",
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
                name = str(op.get("op") or "")

                if name in {"tracked_insert", "tracked_delete", "tracked_replace"}:
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    author = str(op.get("author") or "AI Agent")
                    date = op.get("date")
                    if name == "tracked_insert":
                        text = str(op.get("text") or "")
                        if not text:
                            raise ValueError("tracked_insert requires non-empty text")
                        change = document.tracking.insert(
                            paragraph,
                            text,
                            author=author,
                            date=date,
                            char_pr_id_ref=op.get("char_pr_id_ref"),
                        )
                        payload = change.to_dict()
                    elif name == "tracked_delete":
                        match = op.get("match")
                        if match is not None and not str(match):
                            raise ValueError("tracked_delete match cannot be empty")
                        change = document.tracking.delete(
                            paragraph,
                            match=None if match is None else str(match),
                            author=author,
                            date=date,
                        )
                        payload = change.to_dict()
                    else:
                        old = str(op.get("old") or "")
                        new = str(op.get("new") or "")
                        if not old:
                            raise ValueError("tracked_replace requires old")
                        change = document.tracking.replace(
                            paragraph,
                            old,
                            new,
                            author=author,
                            date=date,
                        )
                        payload = change.to_dict()
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "result": payload,
                    })

                elif name == "add_form_field":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    field_name = str(op.get("name") or "").strip()
                    if not field_name:
                        raise ValueError("add_form_field requires name")
                    field = document.fields.add(
                        field_name,
                        prompt=str(op.get("prompt") or ""),
                        memo=str(op.get("memo") or ""),
                        editable=bool(op.get("editable", True)),
                        paragraph=paragraph,
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "field": _form_field_payload(field),
                    })

                elif name == "fill_form_field":
                    selectors = [
                        op.get("field_index") is not None,
                        op.get("field_id") is not None,
                        op.get("name") is not None,
                    ]
                    if sum(selectors) != 1:
                        raise ValueError("fill_form_field requires exactly one field selector")
                    kwargs: dict[str, Any] = {}
                    for key in ("field_index", "field_id", "name", "box_width", "font_pt"):
                        if op.get(key) is not None:
                            kwargs[key] = op[key]
                    result = document.fields.fill(str(op.get("value") or ""), **kwargs)
                    receipts.append({
                        "op": name,
                        "before": getattr(result, "before", None),
                        "after": getattr(result, "after", None),
                        "field_id": getattr(getattr(result, "field", None), "field_id", None),
                    })

                elif name == "add_check_box":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    caption = str(op.get("caption") or "")
                    if not caption:
                        raise ValueError("add_check_box requires caption")
                    box = document.fields.add_check_box(
                        caption,
                        checked=bool(op.get("checked", False)),
                        name=None if op.get("name") is None else str(op.get("name")),
                        paragraph=paragraph,
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "check_box": _checkbox_payload(box),
                    })

                elif name == "set_check_box":
                    has_index = op.get("index") is not None
                    has_name = op.get("name") is not None
                    if has_index == has_name:
                        raise ValueError("set_check_box requires exactly one of index or name")
                    kwargs = {"index": int(op["index"])} if has_index else {"name": str(op["name"])}
                    box = document.fields.set_check_box(bool(op.get("checked")), **kwargs)
                    receipts.append({"op": name, "check_box": _checkbox_payload(box)})

                elif name == "add_highlight":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    match = str(op.get("match") or "")
                    if not match:
                        raise ValueError("add_highlight requires match")
                    item = document.text.highlight(
                        paragraph,
                        match,
                        color=str(op.get("color") or "#FFFF00"),
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "highlight": _highlight_payload(item),
                    })

                elif name == "add_proofreading_mark":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    paragraph.add_proofreading_mark(
                        str(op.get("mark", "space")),
                        char_pr_id_ref=op.get("char_pr_id_ref"),
                    )
                    receipts.append({"op": name, "paragraph": info["locator"]})

                elif name == "set_document_metadata":
                    allowed = {
                        "title", "creator", "subject", "keyword",
                        "created_date", "modified_date",
                    }
                    kwargs = {key: op[key] for key in allowed if key in op}
                    if not kwargs:
                        raise ValueError("set_document_metadata requires at least one supported field")
                    for date_key in ("created_date", "modified_date"):
                        if kwargs.get(date_key) is not None:
                            value = str(kwargs[date_key])
                            if len(value) != 20 or value[4] != "-" or value[7] != "-" or not value.endswith("Z"):
                                raise ValueError(f"{date_key} must be ISO 8601 UTC like 2026-09-21T07:00:00Z")
                            kwargs[date_key] = value
                    document.parts.set_document_metadata(**kwargs)
                    receipts.append({"op": name, "fields": sorted(kwargs)})

                else:
                    raise ValueError(f"Unsupported review operation: {name}")

            for section in document.sections:
                section.remove_layout_caches()
            _save_document(document, candidate, candidate)
        finally:
            document.close()

        after = build_review_workflow_map(candidate)
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
        "before_sha256": before["review_workflow_sha256"],
        "after_sha256": after["review_workflow_sha256"],
        "changed": before["review_workflow_sha256"] != after["review_workflow_sha256"],
        "before_counts": before["counts"],
        "after_counts": after["counts"],
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_REVIEW_WORKFLOW_AUTHORITY",
        "authoring_backend": "python-hwpx 6.4 public review/form/text/parts surfaces",
        "unsupported_write_lanes": after["unsupported_write_lanes"],
    }
