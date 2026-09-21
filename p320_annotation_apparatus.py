from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from hwpx import HwpxDocument

from p2_document import build_document_map
from p27_tables import _save_document


SCHEMA = "chatgpt-web-hwpx-mcp/annotation-apparatus/p3.20/v1"


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _resolve_paragraph(document: HwpxDocument, path: Path, locator: Any):
    wanted = str(locator or "")
    mapped = build_document_map(path)["paragraphs"]
    info = next((item for item in mapped if item["locator"] == wanted), None)
    if info is None:
        raise ValueError(f"Unknown paragraph locator: {wanted}")
    section_index = int(info["section_index"])
    body_index = info.get("body_paragraph_index")
    if body_index is None:
        raise ValueError("annotation paragraph target must be a section-body paragraph")
    paragraph_index = int(body_index)
    paragraphs = document.sections[section_index].paragraphs
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        raise ValueError("paragraph locator no longer resolves")
    return paragraphs[paragraph_index], info


def _text(node) -> str:
    return "".join(
        (child.text or "")
        for child in node.iter()
        if _local(child.tag) == "t"
    )


def build_annotation_apparatus_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        mapped = build_document_map(path)["paragraphs"]
        by_pos = {
            (int(item["section_index"]), int(item["paragraph_index"])): item["locator"]
            for item in mapped
        }

        footnotes = []
        endnotes = []
        memos = []
        index_marks = []
        bookmarks = []
        hyperlinks = []
        rich_fields = []

        for section_index, section in enumerate(document.sections):
            for paragraph_index, paragraph in enumerate(section.paragraphs):
                locator = by_pos.get((section_index, paragraph_index))
                for node in paragraph.element.iter():
                    local = _local(node.tag)
                    if local == "footNote":
                        footnotes.append({
                            "paragraph": locator,
                            "text": _text(node),
                            "number": node.get("number"),
                            "suffix_char": node.get("suffixChar"),
                        })
                    elif local == "endNote":
                        endnotes.append({
                            "paragraph": locator,
                            "text": _text(node),
                            "number": node.get("number"),
                            "suffix_char": node.get("suffixChar"),
                        })
                    elif local == "memo":
                        memos.append({
                            "paragraph": locator,
                            "id": node.get("id"),
                            "memo_shape_id_ref": node.get("memoShapeIDRef"),
                            "text": _text(node),
                        })
                    elif local == "indexmark":
                        first = next(
                            (child.text or "" for child in node if _local(child.tag) == "firstKey"),
                            "",
                        )
                        second = next(
                            (child.text or "" for child in node if _local(child.tag) == "secondKey"),
                            None,
                        )
                        index_marks.append({
                            "paragraph": locator,
                            "first": first,
                            "second": second,
                        })
                    elif local == "bookmark":
                        bookmarks.append({
                            "paragraph": locator,
                            "name": node.get("name"),
                        })
                    elif local == "fieldBegin":
                        field_type = node.get("type")
                        row = {
                            "paragraph": locator,
                            "type": field_type,
                            "id": node.get("id"),
                            "dirty": node.get("dirty"),
                            "editable": node.get("editable"),
                        }
                        params = {}
                        for child in node.iter():
                            child_local = _local(child.tag)
                            if child_local.endswith("Param") and child.get("name"):
                                params[child.get("name")] = child.text or ""
                        if field_type == "HYPERLINK":
                            url = node.get("name")
                            row["url"] = url
                            if url:
                                params.setdefault("URL", url)
                        row["parameters"] = params
                        if field_type == "HYPERLINK":
                            hyperlinks.append(row)
                        elif field_type in {"DATE", "PATH", "MAILMERGE", "PROOFREADING_MARKS_SIGN"}:
                            rich_fields.append(row)

        # Memos may be section-level siblings rather than descendants of a body paragraph.
        seen_memo_ids = {item["id"] for item in memos if item["id"]}
        for section_index, section in enumerate(document.sections):
            for node in section.element.iter():
                if _local(node.tag) != "memo":
                    continue
                memo_id = node.get("id")
                if memo_id and memo_id in seen_memo_ids:
                    continue
                memos.append({
                    "paragraph": None,
                    "id": memo_id,
                    "memo_shape_id_ref": node.get("memoShapeIDRef"),
                    "text": _text(node),
                })
                if memo_id:
                    seen_memo_ids.add(memo_id)

        result = {
            "schema": SCHEMA,
            "footnotes": footnotes,
            "endnotes": endnotes,
            "memos": memos,
            "index_marks": index_marks,
            "bookmarks": bookmarks,
            "hyperlinks": hyperlinks,
            "rich_fields": rich_fields,
            "counts": {
                "footnotes": len(footnotes),
                "endnotes": len(endnotes),
                "memos": len(memos),
                "index_marks": len(index_marks),
                "bookmarks": len(bookmarks),
                "hyperlinks": len(hyperlinks),
                "rich_fields": len(rich_fields),
            },
        }
        result["annotation_apparatus_sha256"] = _sha({
            "footnotes": footnotes,
            "endnotes": endnotes,
            "memos": memos,
            "index_marks": index_marks,
            "bookmarks": bookmarks,
            "hyperlinks": hyperlinks,
            "rich_fields": rich_fields,
        })
        return result
    finally:
        document.close()


def apply_annotation_apparatus_atomic(
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
        raise ValueError("Annotation transaction requires 1..64 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each annotation operation must be an object")

    before = build_annotation_apparatus_map(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p320-annotation-",
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

                if name in {"add_footnote", "add_endnote"}:
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    text = str(op.get("text") or "")
                    if not text:
                        raise ValueError(f"{name} requires non-empty text")
                    kwargs = {"paragraph": paragraph}
                    if op.get("char_pr_id_ref") is not None:
                        kwargs["char_pr_id_ref"] = op["char_pr_id_ref"]
                    note = (
                        document.notes.add_footnote(text, **kwargs)
                        if name == "add_footnote"
                        else document.notes.add_endnote(text, **kwargs)
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "text": text,
                        "note_text": getattr(note, "text", None),
                    })

                elif name == "add_memo":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    text = str(op.get("text") or "")
                    if not text:
                        raise ValueError("add_memo requires non-empty text")
                    kwargs: dict[str, Any] = {"anchor": paragraph}
                    for key in (
                        "memo_shape_id_ref", "memo_id", "char_pr_id_ref",
                        "field_id", "author", "created", "number",
                        "anchor_char_pr_id_ref",
                    ):
                        if op.get(key) is not None:
                            kwargs[key] = op[key]
                    memo = document.notes.add_memo(text, **kwargs)
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "text": text,
                        "memo_id": getattr(memo, "id", None),
                        "field_id": getattr(memo, "field_id", None),
                    })

                elif name == "remove_memo":
                    index = int(op.get("memo_index", -1))
                    memos = list(document.notes.memos)
                    if index < 0 or index >= len(memos):
                        raise ValueError("memo_index is outside the document")
                    memo = memos[index]
                    document.notes.remove_memo(memo)
                    receipts.append({"op": name, "memo_index": index})

                elif name == "add_index_mark":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    first = str(op.get("first") or "").strip()
                    if not first:
                        raise ValueError("add_index_mark requires first")
                    second = op.get("second")
                    paragraph.add_index_mark(
                        first,
                        second=None if second is None else str(second),
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "first": first,
                        "second": None if second is None else str(second),
                    })

                elif name == "add_bookmark":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    bookmark = str(op.get("name") or "").strip()
                    if not bookmark:
                        raise ValueError("add_bookmark requires name")
                    document.refs.add_bookmark(bookmark, paragraph=paragraph)
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "name": bookmark,
                    })

                elif name == "add_hyperlink":
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    url = str(op.get("url") or "").strip()
                    display_text = str(op.get("display_text") or "")
                    if not url or not display_text:
                        raise ValueError("add_hyperlink requires url and display_text")
                    kwargs = {"paragraph": paragraph}
                    if op.get("char_pr_id_ref") is not None:
                        kwargs["char_pr_id_ref"] = op["char_pr_id_ref"]
                    document.refs.add_hyperlink(url, display_text, **kwargs)
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "url": url,
                        "display_text": display_text,
                    })

                elif name in {
                    "add_date_field", "add_path_field",
                    "add_mail_merge_field", "add_proofreading_mark",
                }:
                    paragraph, info = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    if name == "add_date_field":
                        cached = str(op.get("cached_text") or "")
                        if not cached:
                            raise ValueError("add_date_field requires cached_text")
                        paragraph.add_date_field(
                            cached,
                            date_format=str(op.get("date_format", "YYYY년 M월 D일")),
                            date_nation=str(op.get("date_nation", "KOR")),
                            char_pr_id_ref=op.get("char_pr_id_ref"),
                        )
                    elif name == "add_path_field":
                        cached = str(op.get("cached_text") or "")
                        if not cached:
                            raise ValueError("add_path_field requires cached_text")
                        paragraph.add_path_field(
                            cached,
                            path_format=str(op.get("path_format", "filename")),
                            char_pr_id_ref=op.get("char_pr_id_ref"),
                        )
                    elif name == "add_mail_merge_field":
                        field_name = str(op.get("name") or "").strip()
                        if not field_name:
                            raise ValueError("add_mail_merge_field requires name")
                        paragraph.add_mail_merge_field(
                            field_name,
                            cached_text=op.get("cached_text"),
                            char_pr_id_ref=op.get("char_pr_id_ref"),
                        )
                    else:
                        paragraph.add_proofreading_mark(
                            str(op.get("mark", "space")),
                            char_pr_id_ref=op.get("char_pr_id_ref"),
                        )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                    })

                else:
                    raise ValueError(f"Unsupported annotation operation: {name}")

            for section in document.sections:
                section.remove_layout_caches()
            _save_document(document, candidate, candidate)
        finally:
            document.close()

        after = build_annotation_apparatus_map(candidate)
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
        "before_sha256": before["annotation_apparatus_sha256"],
        "after_sha256": after["annotation_apparatus_sha256"],
        "changed": before["annotation_apparatus_sha256"] != after["annotation_apparatus_sha256"],
        "before_counts": before["counts"],
        "after_counts": after["counts"],
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_ANNOTATION_APPARATUS_AUTHORITY",
        "authoring_backend": "python-hwpx 6.x public/verified authoring surfaces",
    }
