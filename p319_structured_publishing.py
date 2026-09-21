from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from lxml import etree
from hwpx import HwpxDocument
from hwpx.oxml.objects import HwpxOxmlInlineObject
from hwpx.oxml.paragraph import HwpxOxmlParagraph
from hwpx.tools.toc_author import (
    add_native_toc as upstream_add_native_toc,
    add_page_crossref as upstream_add_page_crossref,
    mark_toc_dirty as upstream_mark_toc_dirty,
    ensure_body_styles_not_collected,
)

from p2_document import build_document_map
from p27_tables import _save_document
from p28_tables import build_table_map, _resolve_table
from p29_objects import build_object_map, _resolve_picture, _pictures
from p210_equations import build_equation_map, _resolve_equation, _equations


SCHEMA = "chatgpt-web-hwpx-mcp/structured-publishing/p3.19/v1"
HP_URI = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HP = f"{{{HP_URI}}}"
OUTLINE_RE = re.compile(r"^(?:개요|Outline)\s*(\d+)$", re.I)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _new_id() -> str:
    return str(uuid4().int & 0x7FFFFFFF)


def _paragraph_lookup(path: Path) -> dict[str, dict]:
    return {item["locator"]: item for item in build_document_map(path)["paragraphs"]}


def _resolve_paragraph(document: HwpxDocument, path: Path, locator: Any):
    wanted = str(locator or "")
    mapped = _paragraph_lookup(path)
    target = mapped.get(wanted)
    if target is None:
        raise ValueError(f"Unknown paragraph locator: {wanted}")
    section_index = int(target["section_index"])
    paragraph_index = int(target["paragraph_index"])
    section = document.sections[section_index]
    paragraphs = section.paragraphs
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        raise ValueError("paragraph locator no longer resolves")
    global_index = next(
        i
        for i, item in enumerate(build_document_map(path)["paragraphs"])
        if item["locator"] == wanted
    )
    return paragraphs[paragraph_index], target, global_index


def _style_id(style: Any) -> str:
    raw = getattr(style, "raw_id", None)
    if raw is not None:
        return str(raw)
    value = getattr(style, "id", None)
    if value is None:
        raise ValueError("resolved style has no usable id")
    return str(value)


def _outline_style_levels(document: HwpxDocument) -> dict[str, int]:
    result: dict[str, int] = {}
    for style_id, style in document.styles.items():
        labels = [
            str(getattr(style, "name", "") or "").strip(),
            str(getattr(style, "eng_name", "") or "").strip(),
        ]
        for label in labels:
            match = OUTLINE_RE.match(label)
            if match:
                result[str(style_id)] = int(match.group(1))
                break
    return result


def _outline_headings(document: HwpxDocument) -> list[tuple[Any, int, str]]:
    levels = _outline_style_levels(document)
    out = []
    for section in document.sections:
        for paragraph in section.paragraphs:
            style_ref = str(paragraph.element.get("styleIDRef", ""))
            text = (paragraph.text or "").strip()
            if style_ref in levels and text:
                out.append((paragraph, levels[style_ref], text))
    return out


def _unique_paragraph_id(document: HwpxDocument, paragraph: Any) -> str:
    existing: list[str] = []
    for section in document.sections:
        for node in section.element.iter(f"{HP}p"):
            value = node.get("id")
            if value:
                existing.append(value)

    current = paragraph.element.get("id")
    if current and current != "2147483648" and existing.count(current) == 1:
        return current

    used = set(existing)
    value = _new_id()
    while value in used:
        value = _new_id()
    paragraph.element.set("id", value)
    paragraph.section.mark_dirty()
    return value


def _first_text_run(paragraph: Any):
    for run in paragraph.element:
        if _local(run.tag) != "run":
            continue
        for child in run:
            if _local(child.tag) == "t":
                return run, child
    raise ValueError("paragraph has no text run")


def _make(parent: etree._Element, local: str, attrs: dict[str, str] | None = None):
    return parent.makeelement(f"{HP}{local}", attrs or {})


def _field_begin(run, *, field_type: str, field_id: str, editable: bool, dirty: bool):
    ctrl = _make(run, "ctrl")
    run.append(ctrl)
    begin = _make(ctrl, "fieldBegin", {
        "id": field_id,
        "type": field_type,
        "name": "",
        "editable": "1" if editable else "0",
        "dirty": "1" if dirty else "0",
        "zorder": "-1",
        "fieldid": _new_id(),
        "metaTag": "",
    })
    ctrl.append(begin)
    return begin


def _field_end(run, field_id: str):
    ctrl = _make(run, "ctrl")
    run.append(ctrl)
    ctrl.append(_make(ctrl, "fieldEnd", {"beginIDRef": field_id}))


def _param(parent, tag: str, name: str, value: str):
    node = _make(parent, tag, {"name": name})
    node.text = value
    parent.append(node)


def _reroute_style_zero_body(document: HwpxDocument) -> int:
    body_style = None
    style_zero_para = "0"
    for style_id, style in document.styles.items():
        sid = _style_id(style)
        name = str(getattr(style, "name", "") or "").strip()
        eng = str(getattr(style, "eng_name", "") or "").strip()
        if sid == "0" and getattr(style, "para_pr_id_ref", None) is not None:
            style_zero_para = str(style.para_pr_id_ref)
        if sid != "0" and body_style is None and (name == "본문" or eng.lower() == "body"):
            body_style = sid
    if body_style is None:
        raise ValueError("native TOC requires a non-style-0 Body/본문 style")

    changed = 0
    for section in document.sections:
        section_changed = False
        for paragraph in section.paragraphs:
            element = paragraph.element
            if element.get("styleIDRef", "0") != "0":
                continue
            if not (paragraph.text or "").strip():
                continue
            # Do not reroute header/footer nested paragraphs: section.paragraphs is body only.
            element.set("styleIDRef", body_style)
            if element.get("paraPrIDRef") is None:
                element.set("paraPrIDRef", style_zero_para)
            changed += 1
            section_changed = True
        if section_changed:
            section.mark_dirty()
    return changed


def _toc_entry(parent_template, title: str, target_id: str, cached_page: int):
    p = _make(parent_template, "p", {
        "id": _new_id(),
        "paraPrIDRef": "0",
        "styleIDRef": "0",
        "pageBreak": "0",
        "columnBreak": "0",
        "merged": "0",
    })
    field_id = _new_id()

    run1 = _make(p, "run", {"charPrIDRef": "0"})
    p.append(run1)
    begin = _field_begin(run1, field_type="HYPERLINK", field_id=field_id, editable=False, dirty=True)
    params = _make(begin, "parameters", {"cnt": "5", "name": ""})
    begin.append(params)
    _param(params, "integerParam", "Prop", "0")
    _param(params, "stringParam", "Command", f"?#{target_id};0;1;0;")
    _param(params, "stringParam", "Category", "HWPHYPERLINK_TYPE_HWP")
    _param(params, "stringParam", "TargetType", "HWPHYPERLINK_TARGET_OUTLINE")
    _param(params, "stringParam", "DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB")

    run2 = _make(p, "run", {"charPrIDRef": "0"})
    p.append(run2)
    text = _make(run2, "t")
    text.text = title
    tab = _make(text, "tab", {"width": "34032", "leader": "3", "type": "2"})
    tab.tail = str(cached_page)
    text.append(tab)
    run2.append(text)

    run3 = _make(p, "run", {"charPrIDRef": "0"})
    p.append(run3)
    _field_end(run3, field_id)
    return p


def _add_native_toc(document: HwpxDocument, *, at_index: int, title: str, level: int) -> dict:
    if level < 1 or level > 10:
        raise ValueError("TOC level must be 1..10")
    headings = [
        (paragraph, heading_level, text)
        for paragraph, heading_level, text in _outline_headings(document)
        if heading_level <= level
    ]
    if not headings:
        raise ValueError("no outline headings found for TOC")

    rerouted = ensure_body_styles_not_collected(document)
    upstream = upstream_add_native_toc(
        document,
        at_index=at_index,
        title=title,
        level=level,
        headings=[paragraph for paragraph, _heading_level, _text in headings],
        dirty=True,
        hyperlink=True,
    )
    return {
        "toc_field_id": upstream["tocFieldId"],
        "entry_count": upstream["entryCount"],
        "anchors": list(upstream.get("anchors") or []),
        "body_style_zero_rerouted": rerouted,
        "dirty": True,
        "cached_pages_are_estimates": bool(upstream.get("cachedPagesAreEstimates", True)),
        "authoring_backend": "python-hwpx.tools.toc_author.add_native_toc",
    }

def _add_page_crossref(document: HwpxDocument, paragraph: Any, target: Any, cached_page: int) -> dict:
    if cached_page < 1:
        raise ValueError("cached_page must be positive")
    upstream = upstream_add_page_crossref(
        document,
        paragraph,
        target,
        cached_page=cached_page,
    )
    return {
        "field_id": upstream["fieldId"],
        "target_paragraph_id": upstream["targetId"],
        "cached_page": upstream["cachedPage"],
        "authoring_backend": "python-hwpx.tools.toc_author.add_page_crossref",
    }

def build_structured_publishing_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        paragraph_map = build_document_map(path)["paragraphs"]
        by_pos = {(int(p["section_index"]), int(p["paragraph_index"])): p["locator"] for p in paragraph_map}
        style_rows = []
        for style_id, style in document.styles.items():
            style_rows.append({
                "id": str(style_id),
                "name": getattr(style, "name", None),
                "eng_name": getattr(style, "eng_name", None),
                "para_pr_id_ref": getattr(style, "para_pr_id_ref", None),
                "char_pr_id_ref": getattr(style, "char_pr_id_ref", None),
            })

        paragraphs = []
        fields = []
        bookmarks = []
        captions = []
        global_index = 0
        for section_index, section in enumerate(document.sections):
            for paragraph_index, paragraph in enumerate(section.paragraphs):
                locator = by_pos.get((section_index, paragraph_index))
                para_pr = document.styles.paragraph_property(paragraph.para_pr_id_ref)
                heading = getattr(para_pr, "heading", None) if para_pr is not None else None
                paragraphs.append({
                    "locator": locator,
                    "global_index": global_index,
                    "section_index": section_index,
                    "paragraph_index": paragraph_index,
                    "text": paragraph.text or "",
                    "style_id_ref": paragraph.element.get("styleIDRef"),
                    "para_pr_id_ref": paragraph.element.get("paraPrIDRef"),
                    "outline": None if heading is None else {
                        "type": getattr(heading, "type", None),
                        "level": getattr(heading, "level", None),
                        "id_ref": getattr(heading, "id_ref", None),
                    },
                })
                for node in paragraph.element.iter():
                    local = _local(node.tag)
                    if local == "bookmark":
                        bookmarks.append({"paragraph": locator, "name": node.get("name")})
                    elif local == "fieldBegin":
                        fields.append({
                            "paragraph": locator,
                            "type": node.get("type"),
                            "id": node.get("id"),
                            "dirty": node.get("dirty"),
                        })
                    elif local == "caption":
                        text = "".join(
                            (t.text or "") for t in node.iter() if _local(t.tag) == "t"
                        )
                        captions.append({
                            "paragraph": locator,
                            "text": text,
                            "side": node.get("side"),
                            "full_sz": node.get("fullSz"),
                        })
                global_index += 1

        result = {
            "schema": SCHEMA,
            "styles": style_rows,
            "style_names": document.styles.names(),
            "paragraphs": paragraphs,
            "bookmarks": bookmarks,
            "fields": fields,
            "toc_field_count": sum(1 for f in fields if f["type"] == "TABLEOFCONTENTS"),
            "crossref_field_count": sum(1 for f in fields if f["type"] == "CROSSREF"),
            "captions": captions,
        }
        result["structured_publishing_sha256"] = _sha({
            "styles": style_rows,
            "paragraphs": paragraphs,
            "bookmarks": bookmarks,
            "fields": fields,
            "captions": captions,
        })
        return result
    finally:
        document.close()


def _apply_named_style(document: HwpxDocument, paragraph: Any, spec: Any, sync_character_style: bool) -> dict:
    style = document.styles.resolve(spec)
    sid = _style_id(style)
    paragraph.element.set("styleIDRef", sid)
    if getattr(style, "para_pr_id_ref", None) is not None:
        paragraph.element.set("paraPrIDRef", str(style.para_pr_id_ref))
    if sync_character_style and getattr(style, "char_pr_id_ref", None) is not None:
        for run in paragraph.element:
            if _local(run.tag) == "run":
                run.set("charPrIDRef", str(style.char_pr_id_ref))
    paragraph.section.mark_dirty()
    return {
        "style_id": sid,
        "style_name": getattr(style, "name", None),
        "eng_name": getattr(style, "eng_name", None),
        "sync_character_style": sync_character_style,
    }


def _caption_object(document: HwpxDocument, path: Path, op: dict) -> dict:
    kind = str(op.get("kind") or "").lower()
    text = str(op.get("text") or "")
    if not text:
        raise ValueError("caption text must be non-empty")
    kwargs = {
        "side": str(op.get("side", "TOP")).upper(),
        "full_sz": bool(op.get("full_sz", False)),
        "gap": int(op.get("gap", 850)),
    }
    if op.get("width") is not None:
        kwargs["width"] = int(op["width"])

    if kind == "table":
        mapped = build_table_map(path)
        target = _resolve_table(mapped, op.get("target"))
        table = document.tables.all[int(target["table_index"])]
        caption = table.set_caption(text, **kwargs)
        locator = target["locator"]
    elif kind == "picture":
        mapped = build_object_map(path)
        target = _resolve_picture(mapped, op.get("target"))
        current = _pictures(document)[int(target["picture_index"])]
        paragraph = current.get("paragraph")
        if paragraph is None:
            raise ValueError("picture paragraph cannot be resolved")
        obj = HwpxOxmlInlineObject(current["element"], paragraph)
        caption = obj.set_caption(text, **kwargs)
        locator = target["locator"]
    elif kind == "equation":
        mapped = build_equation_map(path)
        target = _resolve_equation(mapped, op.get("target"))
        current = _equations(document)[int(target["equation_index"])]
        section = document.sections[int(current["section_index"])]
        pidx = int(current["paragraph_index"])
        if pidx < 0 or pidx >= len(section.paragraphs):
            raise ValueError("equation paragraph cannot be resolved")
        obj = HwpxOxmlInlineObject(current["element"], section.paragraphs[pidx])
        caption = obj.set_caption(text, **kwargs)
        locator = target["locator"]
    else:
        raise ValueError("caption kind must be table, picture, or equation")

    return {
        "kind": kind,
        "target": locator,
        "text": caption.text,
        "side": caption.side,
        "full_sz": caption.full_sz,
        "gap": caption.gap,
    }


def apply_structured_publishing_atomic(
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
        raise ValueError("Structured-publishing transaction requires 1..64 operations")

    before = build_structured_publishing_map(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p319-pub-", suffix=".hwpx", dir=str(path.parent)
    )
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None

    try:
        document = HwpxDocument.open(str(candidate))
        try:
            for op in operations:
                if not isinstance(op, dict):
                    raise ValueError("each operation must be an object")
                name = str(op.get("op") or "")

                if name == "apply_list_format":
                    targets = op.get("paragraphs")
                    if targets is None:
                        targets = [op.get("paragraph")]
                    if not isinstance(targets, list) or not targets:
                        raise ValueError("apply_list_format requires paragraph(s)")
                    indexes = []
                    locators = []
                    for locator in targets:
                        _p, info, global_index = _resolve_paragraph(document, candidate, locator)
                        indexes.append(global_index)
                        locators.append(info["locator"])
                    result = document.styles.apply_list_format(
                        paragraph_indexes=indexes,
                        kind=str(op.get("kind", "bullet")).lower(),
                        level=int(op.get("level", 1)),
                        bullet_char=op.get("bullet_char"),
                        number_format=op.get("number_format"),
                        start=None if op.get("start") is None else int(op["start"]),
                    )
                    receipts.append({
                        "op": name,
                        "paragraphs": locators,
                        "kind": str(op.get("kind", "bullet")).lower(),
                        "level": int(op.get("level", 1)),
                        "result": repr(result),
                    })

                elif name == "apply_named_style":
                    paragraph, info, _idx = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    receipt = _apply_named_style(
                        document,
                        paragraph,
                        op.get("style"),
                        bool(op.get("sync_character_style", True)),
                    )
                    receipts.append({"op": name, "paragraph": info["locator"], **receipt})

                elif name == "set_outline_level":
                    paragraph, info, global_index = _resolve_paragraph(
                        document, candidate, op.get("paragraph")
                    )
                    level = int(op.get("level", 1))
                    if level < 0 or level > 10:
                        raise ValueError("outline level must be 0..10")
                    if level > 0 and bool(op.get("apply_outline_style", True)):
                        style = document.styles.resolve(f"개요 {level}")
                        _apply_named_style(document, paragraph, style, True)
                    result = document.styles.apply_paragraph_format(
                        paragraph_index=global_index,
                        outline_level=level,
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "level": level,
                        "result": repr(result),
                    })

                elif name == "add_heading":
                    level = int(op.get("level", 1))
                    text = str(op.get("text") or "")
                    if not text:
                        raise ValueError("add_heading requires text")
                    section_index = int(op.get("section_index", len(document.sections) - 1))
                    heading = document.add_heading(text, level=level, section=section_index)
                    receipts.append({
                        "op": name,
                        "level": level,
                        "text": text,
                        "paragraph_id": heading.element.get("id"),
                    })

                elif name == "set_caption":
                    receipts.append({"op": name, **_caption_object(document, candidate, op)})

                elif name == "add_bookmark":
                    paragraph, info, _idx = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    bookmark = str(op.get("name") or "").strip()
                    if not bookmark:
                        raise ValueError("bookmark name must be non-empty")
                    paragraph.add_bookmark(bookmark)
                    receipts.append({"op": name, "paragraph": info["locator"], "name": bookmark})

                elif name == "add_page_crossref":
                    paragraph, info, _idx = _resolve_paragraph(document, candidate, op.get("paragraph"))
                    target, target_info, _target_idx = _resolve_paragraph(
                        document, candidate, op.get("target_paragraph")
                    )
                    receipt = _add_page_crossref(
                        document, paragraph, target, int(op.get("cached_page", 1))
                    )
                    receipts.append({
                        "op": name,
                        "paragraph": info["locator"],
                        "target_paragraph": target_info["locator"],
                        **receipt,
                    })

                elif name == "add_native_toc":
                    receipt = _add_native_toc(
                        document,
                        at_index=int(op.get("at_index", 0)),
                        title=str(op.get("title", "<제목 차례>")),
                        level=int(op.get("level", 3)),
                    )
                    receipts.append({"op": name, **receipt})

                elif name == "mark_toc_dirty":
                    count = upstream_mark_toc_dirty(document)
                    receipts.append({
                        "op": name,
                        "marked": count,
                        "authoring_backend": "python-hwpx.tools.toc_author.mark_toc_dirty",
                    })

                else:
                    raise ValueError(f"Unsupported structured-publishing operation: {name}")

            for section in document.sections:
                section.remove_layout_caches()
            _save_document(document, candidate, candidate)
        finally:
            document.close()

        after = build_structured_publishing_map(candidate)
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
        "before_sha256": before["structured_publishing_sha256"],
        "after_sha256": after["structured_publishing_sha256"],
        "changed": before["structured_publishing_sha256"] != after["structured_publishing_sha256"],
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_PUBLISHING_AUTHORITY",
        "native_field_semantics": {
            "toc": "TABLEOFCONTENTS field; dirty=1 requests Hancom regeneration on open",
            "crossref": "CROSSREF page cache is authored with a cached estimate and is renderer-refreshable",
        },
    }
